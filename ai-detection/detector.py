import os
import time
import base64
import logging
import cv2
import httpx
from datetime import datetime
from ai_worker.yolo_engine import RoadYOLODetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [AI Worker]: %(message)s")
logger = logging.getLogger("lunaris.ai_worker")

# Configuration
FASTAPI_BACKEND_URL = os.getenv("FASTAPI_BACKEND_URL", "http://localhost:8000/api/v1")
RTSP_STREAM_URL = os.getenv("RTSP_STREAM_URL", "rtsp://localhost:8554/bus07")
BUS_ID = os.getenv("BUS_ID", "BUS-07")
BUS_PLATE = os.getenv("BUS_PLATE", "WB-04-E-2910")
DETECTION_INTERVAL_SEC = 2.0 # Throttle detection pushes

def encode_image_base64(frame) -> str:
    """Encode OpenCV frame to base64 JPEG."""
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer).decode('utf-8')

def main():
    logger.info("Initializing LUNARIS AI Edge Worker for %s...", BUS_ID)
    logger.info("Connecting to MediaMTX RTSP stream: %s", RTSP_STREAM_URL)
    
    detector = RoadYOLODetector(model_weights="yolov8n.pt", confidence_threshold=0.5)
    last_event_time = 0

    # Kolkata simulated route trace
    route_coords = [
        {"loc": "Park Street, Kolkata", "lat": 22.5512, "lng": 88.3524},
        {"loc": "AJC Bose Road Crossing", "lat": 22.5415, "lng": 88.3578},
        {"loc": "Esplanade Bus Terminus", "lat": 22.5645, "lng": 88.3518},
        {"loc": "Sealdah Flyover Approach", "lat": 22.5670, "lng": 88.3715},
    ]
    coord_idx = 0

    cap = cv2.VideoCapture(RTSP_STREAM_URL)
    if not cap.isOpened():
        logger.warning("Could not open RTSP stream %s. Operating in synthetic video frame generator mode.", RTSP_STREAM_URL)

    try:
        while True:
            ret, frame = False, None
            if cap.isOpened():
                ret, frame = cap.read()
                
            if not ret or frame is None:
                # Generate synthetic 720p road frame
                frame = cv2.imread("scratch/sample_road.jpg")
                if frame is None:
                    # Synthetic black asphalt canvas with road markings
                    frame = 40 * np.ones((720, 1280, 3), dtype="uint8")
                    cv2.line(frame, (640, 360), (300, 720), (0, 255, 255), 4)
                    cv2.line(frame, (640, 360), (980, 720), (0, 255, 255), 4)

            # Run YOLO + OpenCV Detection
            detections, annotated_frame = detector.process_frame(frame)
            current_time = time.time()

            # Push Detection Event if defect found
            if detections and (current_time - last_event_time > DETECTION_INTERVAL_SEC):
                loc_info = route_coords[coord_idx % len(route_coords)]
                coord_idx += 1
                
                det = detections[0]
                base64_img = encode_image_base64(annotated_frame)

                event_payload = {
                    "bus_id": BUS_ID,
                    "bus_plate": BUS_PLATE,
                    "type": det["class_name"] if det["class_name"] in ["Pothole", "Road Damage", "Waterlogging", "Traffic"] else "Pothole",
                    "category": "Pothole",
                    "location": loc_info["loc"],
                    "lat": loc_info["lat"],
                    "lng": loc_info["lng"],
                    "severity": "HIGH" if det["estimated_depth_cm"] > 9.0 else "MEDIUM",
                    "confidence": det["confidence"],
                    "bounding_boxes": [det],
                    "evidence_image_base64": base64_img,
                    "details": f"Automated detection: {det['class_name']} with depth {det['estimated_depth_cm']}cm, area {det['area_cm2']}cm²",
                    "timestamp": datetime.utcnow().isoformat()
                }

                logger.info("⚡ Detected %s on %s (Confidence: %s%%, Depth: %scm)", 
                            event_payload["type"], loc_info["loc"], det["confidence"], det["estimated_depth_cm"])

                try:
                    with httpx.Client(timeout=4.0) as client:
                        resp = client.post(f"{FASTAPI_BACKEND_URL}/detections/event", json=event_payload)
                        if resp.status_code == 201:
                            logger.info("✅ Detection Event successfully posted to FastAPI Backend: %s", resp.json())
                except Exception as e:
                    logger.error("Failed to POST detection event to backend: %s", e)

                last_event_time = current_time

            # Update Bus Telemetry periodically
            try:
                loc_info = route_coords[coord_idx % len(route_coords)]
                telemetry_payload = {
                    "bus_id": BUS_ID,
                    "plate": BUS_PLATE,
                    "route": "Park Street → Esplanade",
                    "camera_status": "Online",
                    "gps_status": "Active",
                    "ai_status": "Active",
                    "lat": loc_info["lat"],
                    "lng": loc_info["lng"],
                    "speed": 32.5,
                    "fps": 98.4,
                    "last_location": loc_info["loc"].split(",")[0]
                }
                with httpx.Client(timeout=3.0) as client:
                    client.post(f"{FASTAPI_BACKEND_URL}/fleet/telemetry", json=telemetry_payload)
            except Exception:
                pass

            time.sleep(1.0)

    except KeyboardInterrupt:
        logger.info("AI Worker stopped by user.")
    finally:
        if cap.isOpened():
            cap.release()

if __name__ == "__main__":
    import numpy as np
    main()
