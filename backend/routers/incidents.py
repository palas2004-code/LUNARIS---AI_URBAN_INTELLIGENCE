import logging
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from backend.database import get_supabase
from backend.logger import log_system_event, AuditEventType
from backend.security import apply_rate_limiting, sanitize_string, validate_coordinates

logger = logging.getLogger("lunaris.incidents")
router = APIRouter(prefix="/incidents", tags=["Incidents & Maintenance"])

class IncidentCreate(BaseModel):
    title: str = Field(..., max_length=200)
    category: str = Field(..., max_length=50)
    severity: str = "MEDIUM"
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: str = Field(..., max_length=300)
    bus_id: str = "BUS-07"
    confidence: float = Field(96.0, ge=0.0, le=100.0)
    before_evidence: Optional[str] = None

class IncidentAssign(BaseModel):
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    priority: str = "HIGH"
    notes: Optional[str] = None

class IncidentStatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None
    changed_by: Optional[str] = None
    after_evidence: Optional[str] = None

@router.get("/")
async def list_incidents(status: Optional[str] = None, severity: Optional[str] = None, limit: int = 100):
    try:
        supabase = get_supabase()
        query = supabase.from_("incidents").select("*, evidence(*), assignments(*)").order("created_at", desc=True).limit(limit)
        if status and status != "ALL":
            query = query.eq("status", status.upper())
        if severity and severity != "ALL":
            query = query.eq("severity", severity.upper())
        res = query.execute()
        return {"incidents": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", dependencies=[Depends(apply_rate_limiting)])
async def create_incident(inc: IncidentCreate):
    try:
        supabase = get_supabase()
        inc_id = f"RD-{uuid.uuid4().hex[:4].upper()}"
        lat, lng = validate_coordinates(inc.latitude, inc.longitude)
        
        data = {
            "incident_id": inc_id,
            "title": sanitize_string(inc.title),
            "category": sanitize_string(inc.category),
            "severity": inc.severity.upper(),
            "status": "DETECTED",
            "latitude": lat,
            "longitude": lng,
            "address": sanitize_string(inc.address),
            "confidence_score": inc.confidence,
            "verified_by_buses": [sanitize_string(inc.bus_id)],
            "before_evidence": inc.before_evidence,
            "created_at": datetime.utcnow().isoformat()
        }
        res = supabase.from_("incidents").insert(data).execute()

        # Audit Logger
        log_system_event(
            AuditEventType.INCIDENT_CREATE,
            f"Created new incident {inc_id} ({data['category']} - {data['severity']}) at {data['address']}",
            severity="INFO" if data['severity'] != "CRITICAL" else "WARNING",
            source="INCIDENT_ROUTER",
            metadata={"incident_id": inc_id, "category": data['category'], "bus_id": inc.bus_id}
        )

        return {"success": True, "incident": res.data[0] if res.data else data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    try:
        supabase = get_supabase()
        res = supabase.from_("incidents").select("*, evidence(*), assignments(*), incident_status_history(*)").eq("incident_id", incident_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{incident_id}/verify")
async def verify_incident(incident_id: str):
    try:
        supabase = get_supabase()
        supabase.from_("incidents").update({
            "status": "VERIFIED",
            "duplicate_status": "confirmed_duplicate",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("incident_id", incident_id).execute()

        # Audit History
        supabase.from_("incident_status_history").insert({
            "incident_id": incident_id,
            "old_status": "DETECTED",
            "new_status": "VERIFIED",
            "comment": "Multi-Bus consensus verified"
        }).execute()

        # Auto-create complaint
        c_id = f"C-{uuid.uuid4().hex[:4].upper()}"
        supabase.from_("complaints").insert({
            "id": c_id,
            "incident_id": incident_id,
            "priority": "HIGH",
            "title": f"Verified Road Defect {incident_id}",
            "description": f"Automated grievance dispatch for verified incident {incident_id}",
            "location": "Kolkata Transit Network",
            "status": "OPEN"
        }).execute()

        # Structured Audit Log
        log_system_event(
            AuditEventType.INCIDENT_CREATE,
            f"Incident {incident_id} verified via multi-bus consensus. Automated complaint {c_id} created.",
            severity="INFO",
            source="VERIFICATION_ENGINE",
            metadata={"incident_id": incident_id, "complaint_id": c_id}
        )

        return {"success": True, "incident_id": incident_id, "status": "VERIFIED", "complaint_id": c_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{incident_id}/merge")
async def merge_incident(incident_id: str, merge_with_id: Optional[str] = None):
    try:
        supabase = get_supabase()
        supabase.from_("incidents").update({
            "duplicate_status": "confirmed_duplicate",
            "consensus_count": 3,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("incident_id", incident_id).execute()

        # Audit Log
        log_system_event(
            AuditEventType.DUPLICATE_MERGE,
            f"Merged spatial duplicate incident {incident_id} into verified cluster.",
            severity="INFO",
            source="DEDUPLICATION_ENGINE",
            metadata={"incident_id": incident_id, "merged_with": merge_with_id}
        )

        return {"success": True, "incident_id": incident_id, "merged": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{incident_id}/assign")
async def assign_incident(incident_id: str, assign_data: IncidentAssign):
    try:
        supabase = get_supabase()
        dept_name = assign_data.department_name or "Road Maintenance Department"
        team_id = assign_data.team_id or "a0000000-0000-0000-0000-000000000001"

        supabase.from_("assignments").insert({
            "incident_id": incident_id,
            "team_id": team_id,
            "priority": assign_data.priority,
            "status": "ASSIGNED",
            "work_notes": assign_data.notes or f"Assigned to {dept_name}"
        }).execute()

        supabase.from_("incidents").update({
            "status": "ASSIGNED",
            "assigned_authority": dept_name,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("incident_id", incident_id).execute()

        supabase.from_("incident_status_history").insert({
            "incident_id": incident_id,
            "old_status": "VERIFIED",
            "new_status": "ASSIGNED",
            "comment": f"Dispatched to {dept_name}"
        }).execute()

        # Audit Log
        log_system_event(
            AuditEventType.ASSIGNMENT,
            f"Incident {incident_id} assigned to authority '{dept_name}' with priority {assign_data.priority}.",
            severity="INFO",
            source="DISPATCH_ROUTER",
            metadata={"incident_id": incident_id, "department": dept_name, "team_id": team_id}
        )

        return {"success": True, "incident_id": incident_id, "status": "ASSIGNED", "authority": dept_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{incident_id}/status")
async def update_incident_status(incident_id: str, update: IncidentStatusUpdate):
    try:
        supabase = get_supabase()
        current_res = supabase.from_("incidents").select("status").eq("incident_id", incident_id).execute()
        prev_status = current_res.data[0]["status"] if current_res.data else "DETECTED"

        patch_data = {
            "status": update.status.upper(),
            "updated_at": datetime.utcnow().isoformat()
        }
        if update.after_evidence:
            patch_data["after_evidence"] = update.after_evidence

        supabase.from_("incidents").update(patch_data).eq("incident_id", incident_id).execute()

        # Audit History
        supabase.from_("incident_status_history").insert({
            "incident_id": incident_id,
            "old_status": prev_status,
            "new_status": update.status.upper(),
            "changed_by": update.changed_by,
            "comment": update.comment or f"Transitioned to {update.status.upper()}"
        }).execute()

        # Audit Log
        is_resolved = update.status.upper() in ["RESOLVED", "VERIFIED_RESOLUTION"]
        log_system_event(
            AuditEventType.RESOLUTION if is_resolved else AuditEventType.STATUS_UPDATE,
            f"Incident {incident_id} status transitioned from {prev_status} to {update.status.upper()}.",
            severity="INFO",
            source="STATUS_ROUTER",
            metadata={"incident_id": incident_id, "previous_status": prev_status, "new_status": update.status.upper()}
        )

        return {"success": True, "incident_id": incident_id, "previous_status": prev_status, "new_status": update.status.upper()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
