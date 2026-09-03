"""
LUNARIS AI Service Entrypoint (FastAPI + YOLOv8 + LUNEX-POTHOLE-V1)
Port: 8001
"""

import cv2
import numpy as np
import base64
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from stream_processor import StreamProcessor
from yolo_detector import LunarisYOLODetector

logger = logging.getLogger("lunaris.ai.service")
logging.basicConfig(level=logging.INFO)

detector = LunarisYOLODetector(confidence_threshold=0.65)
processors = {
    "BUS-07": StreamProcessor(bus_id="BUS-07", stream_url="rtsp://localhost:8554/bus07", detector=detector),
    "BUS-12": StreamProcessor(bus_id="BUS-12", stream_url="rtsp://localhost:8554/bus12", detector=detector),
    "BUS-15": StreamProcessor(bus_id="BUS-15", stream_url="rtsp://localhost:8554/bus15", detector=detector),
    "BUS-21": StreamProcessor(bus_id="BUS-21", stream_url="rtsp://localhost:8554/bus21", detector=detector)
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Processors are ready to stream on demand
    yield
    # Shutdown
    for p in processors.values():
        p.stop()

app = FastAPI(
    title="LUNARIS Edge AI Service",
    version="2.6.4",
    description="High-Throughput YOLOv8 Pothole & Road Intelligence Pipeline for Smart Cities",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "service": "LUNARIS Edge AI Service",
        "status": "ONLINE",
        "model": detector.model_name,
        "supported_classes": {
            "primary": detector.primary_classes,
            "secondary": detector.secondary_classes,
            "advanced": detector.advanced_classes
        }
    }

@app.get("/api/ai/health")
async def ai_health():
    return {
        "status": "ONLINE",
        "model_loaded": detector.is_loaded,
        "model_name": detector.model_name,
        "resolved_model_path": detector.resolved_model_path,
        "confidence_threshold": detector.confidence_threshold,
        "required_confirmation_frames": LunarisYOLODetector.REQUIRED_CONFIRMATION_FRAMES,
        "fps_capability": 24.0,
        "average_latency_ms": 115.0,
        "primary_classes": detector.primary_classes,
        "secondary_classes": detector.secondary_classes
    }

@app.get("/api/ai/stream/{bus_id}")
async def video_feed(bus_id: str):
    """
    Live MJPEG video stream with real-time YOLO bounding boxes.
    """
    processor = processors.get(bus_id.upper())
    if not processor:
        processor = processors["BUS-07"]

    if not processor.is_running:
        await processor.start()

    async def frame_generator():
        while True:
            frame_bytes = processor.get_latest_jpeg()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            import asyncio
            await asyncio.sleep(1.0 / 24.0)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/api/ai/detect")
async def detect_image(file: UploadFile = File(...)):
    """
    Direct single image inference endpoint.
    Returns detected objects with real confidence %, severity, physical depth, and annotated base64 image.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image encoding")

        detections, annotated = detector.detect_frame(img, debug=True)
        
        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "model_version": detector.model_name,
            "confidence_threshold": detector.confidence_threshold,
            "required_confirmation_frames": LunarisYOLODetector.REQUIRED_CONFIRMATION_FRAMES,
            "detections": detections,
            "count": len(detections),
            "annotated_image_base64": f"data:image/jpeg;base64,{annotated_b64}"
        }
    except Exception as e:
        logger.error(f"Detection API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
