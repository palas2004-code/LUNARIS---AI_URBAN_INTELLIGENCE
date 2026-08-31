import logging
import base64
import uuid
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from backend.models import DetectionEvent
from backend.database import get_supabase
from backend.config import settings
from backend.privacy import redact_sensitive_pii, CV2_AVAILABLE
from backend.logger import log_system_event, AuditEventType
from backend.security import apply_rate_limiting, sanitize_string, validate_coordinates

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

logger = logging.getLogger("lunaris.detections")
router = APIRouter(prefix="/detections", tags=["AI Detections"])

def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates geodesic distance between two coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def compute_severity_rating(
    defect_type: str,
    confidence: float,
    depth_cm: float,
    area_cm2: float,
    consensus_count: int,
    traffic_density: str = "HEAVY",
    pedestrian_proximity: bool = False
) -> tuple[str, str]:
    """
    Transparent Severity Engine
    Evaluates depth, surface area, multi-bus observations, and traffic corridor density.
    Example: Large pothole (depth > 8cm) + heavy traffic + 3 buses detected it = CRITICAL.
    """
    reasons = []
    score = 0

    # 1. Defect Dimensions
    if depth_cm >= 8.0 or area_cm2 >= 1400:
        score += 3
        reasons.append(f"Large defect geometry (Depth: {depth_cm:.1f}cm, Area: {int(area_cm2)}cm²)")
    elif depth_cm >= 4.0:
        score += 2
        reasons.append(f"Moderate depth ({depth_cm:.1f}cm)")
    else:
        score += 1

    # 2. Multi-Bus Consensus Factor
    if consensus_count >= settings.CONSENSUS_VERIFICATION_THRESHOLD:
        score += 3
        reasons.append(f"Multi-Bus Consensus Verified ({consensus_count} independent buses)")
    elif consensus_count == 2:
        score += 1
        reasons.append(f"Dual-bus confirmed ({consensus_count} buses)")

    # 3. Traffic Density & Road Location
    if traffic_density in ["HEAVY", "CONGESTED"]:
        score += 2
        reasons.append("High-density arterial transit route")

    # 4. Pedestrian Proximity
    if pedestrian_proximity:
        score += 2
        reasons.append("Pedestrian zone proximity hazard")

    # 5. Confidence
    if confidence >= 95.0:
        score += 1

    if score >= 7:
        severity = "CRITICAL"
    elif score >= 5:
        severity = "HIGH"
    elif score >= 3:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    reason_str = " + ".join(reasons) if reasons else "Standard Edge Detection Heuristics"
    return severity, reason_str

@router.post("/event", status_code=status.HTTP_201_CREATED)
async def ingest_detection_event(event: DetectionEvent, background_tasks: BackgroundTasks):
    """
    Ingest a verified road defect from edge YOLO workers.
    Features:
    - Privacy PII Redaction (Blur faces & license plates)
    - Deduplication & Multi-Bus Verification
    - Transparent Severity Calculation
    - Supabase Realtime Alert Dispatch
    """
    try:
        supabase = get_supabase()
        detection_uuid = str(uuid.uuid4())
        new_incident_id = f"RD-{uuid.uuid4().hex[:4].upper()}"
        
        # 1. Parse Bounding Box & Dimensions
        bbox_dict = {}
        depth_cm = 8.5
        area_cm2 = 1200.0
        if event.bounding_boxes and len(event.bounding_boxes) > 0:
            first_box = event.bounding_boxes[0]
            bbox_dict = first_box.dict()
            depth_cm = first_box.estimated_depth_cm or depth_cm
            area_cm2 = first_box.area_cm2 or area_cm2

        # 2. Privacy Redaction & Supabase Storage Upload
        file_path = f"detections/{datetime.utcnow().strftime('%Y/%m/%d')}/{detection_uuid}.jpg"
        evidence_url = event.evidence_image_url
        img_bytes_len = None

        if event.evidence_image_base64:
            try:
                raw_b64 = event.evidence_image_base64
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",")[1]
                img_data = base64.b64decode(raw_b64)
                
                # Apply OpenCV PII Redactor to blur faces and license plates
                nparr = np.frombuffer(img_data, np.uint8)
                cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if cv_img is not None:
                    redacted_img = redact_sensitive_pii(cv_img)
                    _, buffer = cv2.imencode('.jpg', redacted_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    img_data = buffer.tobytes()

                img_bytes_len = len(img_data)
                
                # Upload to Supabase Storage Bucket: incident-evidence
                supabase.storage.from_(settings.EVIDENCE_BUCKET).upload(
                    path=file_path,
                    file=img_data,
                    file_options={"content-type": "image/jpeg"}
                )
                evidence_url = supabase.storage.from_(settings.EVIDENCE_BUCKET).get_public_url(file_path)
            except Exception as se:
                logger.warning("Evidence storage upload notice: %s", se)

        # 3. Insert Raw Detection into public.detections
        det_row = {
            "id": detection_uuid,
            "camera_id": f"CAM-{event.bus_id.replace('BUS-', '')}",
            "bus_id": event.bus_id,
            "detection_type": event.type,
            "confidence": event.confidence,
            "severity": event.severity.upper(),
            "latitude": event.lat,
            "longitude": event.lng,
            "gps_accuracy": 1.5,
            "detected_at": (event.timestamp or datetime.utcnow()).isoformat(),
            "frame_storage_path": file_path if evidence_url else None,
            "video_storage_path": None,
            "bounding_box": bbox_dict,
            "model_name": "YOLOv8-Urban-V2",
            "model_version": "2.6.4"
        }
        supabase.from_("detections").insert(det_row).execute()

        # 4. Multi-Bus Verification & Duplicate Algorithm
        target_incident_id = None
        matched_incident = None
        
        try:
            cutoff_time = (datetime.utcnow() - timedelta(hours=settings.DUPLICATE_TIME_WINDOW_HOURS)).isoformat()
            existing_res = supabase.from_("incidents").select("*") \
                .eq("category", event.category or event.type) \
                .neq("status", "RESOLVED") \
                .gte("created_at", cutoff_time) \
                .execute()

            if existing_res.data:
                for row in existing_res.data:
                    dist_m = haversine_distance_meters(row["latitude"], row["longitude"], event.lat, event.lng)
                    if dist_m <= settings.DUPLICATE_DISTANCE_THRESHOLD_METERS:
                        target_incident_id = row["incident_id"]
                        matched_incident = row
                        logger.info(f"Matched existing incident {target_incident_id} ({dist_m:.1f}m away)")
                        break
        except Exception as query_err:
            logger.debug(f"Incident query note: {query_err}")

        if matched_incident:
            # Existing Incident Found — Apply Multi-Bus Verification
            current_buses = set(matched_incident.get("verified_by_buses") or [])
            current_buses.add(event.bus_id)
            consensus_count = len(current_buses)
            
            # Determine Verification Status & Duplicate Tag
            if consensus_count >= settings.CONSENSUS_VERIFICATION_THRESHOLD:
                new_status = "VERIFIED"
                duplicate_status = "confirmed_duplicate"
                boosted_conf = min(99.4, max(event.confidence, 98.0))
            elif consensus_count == 2:
                new_status = "POSSIBLE DUPLICATE"
                duplicate_status = "possible_duplicate"
                boosted_conf = max(event.confidence, 94.0)
            else:
                new_status = matched_incident.get("status", "UNRESOLVED")
                duplicate_status = "separate_incident"
                boosted_conf = event.confidence

            # Re-evaluate Severity using Transparent Severity Engine
            severity, severity_reason = compute_severity_rating(
                defect_type=event.type,
                confidence=boosted_conf,
                depth_cm=depth_cm,
                area_cm2=area_cm2,
                consensus_count=consensus_count,
                traffic_density="HEAVY"
            )

            supabase.from_("incidents").update({
                "consensus_count": consensus_count,
                "confidence_score": boosted_conf,
                "status": new_status,
                "duplicate_status": duplicate_status,
                "severity": severity,
                "severity_reason": severity_reason,
                "verified_by_buses": list(current_buses),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("incident_id", target_incident_id).execute()

        else:
            # Create New Separate Incident
            target_incident_id = new_incident_id
            consensus_count = 1
            severity, severity_reason = compute_severity_rating(
                defect_type=event.type,
                confidence=event.confidence,
                depth_cm=depth_cm,
                area_cm2=area_cm2,
                consensus_count=1,
                traffic_density="HEAVY"
            )

            # Automatic Department Routing Rule
            cat_lower = (event.category or event.type).lower()
            if "pothole" in cat_lower or "damage" in cat_lower:
                assigned_dept = "Road Maintenance Department"
                assigned_dept_id = "a0000000-0000-0000-0000-000000000001"
            elif "water" in cat_lower or "drain" in cat_lower:
                assigned_dept = "Drainage Department"
                assigned_dept_id = "a0000000-0000-0000-0000-000000000002"
            elif "traffic" in cat_lower or "signal" in cat_lower:
                assigned_dept = "Traffic Department"
                assigned_dept_id = "a0000000-0000-0000-0000-000000000003"
            else:
                assigned_dept = "Urban Infrastructure"
                assigned_dept_id = "a0000000-0000-0000-0000-000000000004"

            incident_data = {
                "incident_id": target_incident_id,
                "title": f"Verified {event.type} on {event.location}",
                "category": event.category or event.type,
                "severity": severity,
                "severity_reason": severity_reason,
                "status": "UNRESOLVED",
                "duplicate_status": "separate_incident",
                "latitude": event.lat,
                "longitude": event.lng,
                "address": event.location,
                "consensus_count": 1,
                "confidence_score": event.confidence,
                "verified_by_buses": [event.bus_id],
                "department_id": assigned_dept_id,
                "assigned_authority": assigned_dept,
                "initial_detection_id": detection_uuid,
                "created_at": (event.timestamp or datetime.utcnow()).isoformat()
            }
            supabase.from_("incidents").insert(incident_data).execute()

        # 5. Insert Evidence Reference into public.evidence
        if evidence_url:
            try:
                supabase.from_("evidence").insert({
                    "incident_id": target_incident_id,
                    "detection_id": detection_uuid,
                    "bucket_id": settings.EVIDENCE_BUCKET,
                    "storage_path": file_path,
                    "public_url": evidence_url,
                    "file_type": "image/jpeg",
                    "file_size_bytes": img_bytes_len
                }).execute()
            except Exception as e:
                logger.warning("Evidence row insert notice: %s", e)

        # 6. Record Junction Entry in public.incident_detections
        try:
            supabase.from_("incident_detections").insert({
                "incident_id": target_incident_id,
                "detection_id": detection_uuid,
                "bus_id": event.bus_id
            }).execute()
        except Exception:
            pass

        # 7. Trigger Notification in public.notifications (High & Critical)
        if severity in ["HIGH", "CRITICAL"]:
            notif_payload = {
                "incident_id": target_incident_id,
                "title": f"{'🚨 HIGH PRIORITY' if severity == 'HIGH' else '🛑 CRITICAL PRIORITY'}",
                "message": f"{event.type} detected at {event.location}. Detected by {event.bus_id}",
                "priority": severity,
                "read": False
            }
            try:
                supabase.from_("notifications").insert(notif_payload).execute()
            except Exception as ne:
                logger.warning(f"Notification insert notice: {ne}")

            # 8. Optional Resend Email Dispatch
            from backend.email_service import send_authority_alert_email
            background_tasks.add_task(
                send_authority_alert_email,
                department_name=assigned_dept if 'assigned_dept' in locals() else "Road Maintenance Department",
                incident_id=target_incident_id,
                defect_type=event.type,
                location=event.location,
                severity=severity,
                confidence=event.confidence,
                evidence_url=evidence_url
            )

        # Audit Logger (Detection Ingest)
        log_system_event(
            AuditEventType.DETECTION,
            f"Edge AI detection ingested: {event.type} ({event.confidence:.1f}%) on {event.bus_id} at {event.location}",
            severity="INFO" if severity != "CRITICAL" else "WARNING",
            source="AI_EDGE_PIPELINE",
            metadata={
                "incident_id": target_incident_id,
                "detection_id": detection_uuid,
                "bus_id": event.bus_id,
                "type": event.type,
                "severity": severity,
                "consensus_count": consensus_count
            }
        )

        return {
            "success": True,
            "incident_id": target_incident_id,
            "detection_id": detection_uuid,
            "consensus_count": consensus_count,
            "status": "VERIFIED" if consensus_count >= settings.CONSENSUS_VERIFICATION_THRESHOLD else "RECORDED",
            "severity": severity,
            "severity_reason": severity_reason,
            "evidence_url": evidence_url
        }

    except Exception as e:
        logger.error("Error processing detection event: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
