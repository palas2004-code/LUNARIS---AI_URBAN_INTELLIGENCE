"""
LUNARIS AI Service Entrypoint (FastAPI + YOLOv8 + OpenCV)
Port: 8001
"""

import cv2
import numpy as np
import base64
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from stream_processor import StreamProcessor
from yolo_detector import LunarisYOLODetector

app = FastAPI(
    title="LUNARIS Edge AI Service",
    version="2.6.4",
    description="High-Throughput YOLOv8 & OpenCV Video Inference Pipeline for Smart Cities"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

detector = LunarisYOLODetector()
processors = {
    "BUS-07": StreamProcessor(bus_id="BUS-07", stream_url="rtsp://localhost:8554/bus07"),
    "BUS-12": StreamProcessor(bus_id="BUS-12", stream_url="rtsp://localhost:8554/bus12"),
    "BUS-15": StreamProcessor(bus_id="BUS-15", stream_url="rtsp://localhost:8554/bus15"),
    "BUS-21": StreamProcessor(bus_id="BUS-21", stream_url="rtsp://localhost:8554/bus21")
}

@app.on_event("startup")
async def startup_event():
    # Start stream processors in background
    for p in processors.values():
        await p.start()

@app.on_event("shutdown")
def shutdown_event():
    for p in processors.values():
        p.stop()

@app.get("/")
def root():
    return {
        "service": "LUNARIS Edge AI Service",
        "status": "ONLINE",
        "model": "YOLOv8 + OpenCV Surface Depth Engine",
        "supported_classes": {
            "primary": detector.primary_classes,
            "secondary": detector.secondary_classes,
            "advanced": detector.advanced_classes
        }
    }

@app.get("/api/ai/health")
def ai_health():
    return {
        "status": "ONLINE",
        "model_loaded": detector.is_loaded,
        "model_name": detector.model_name,
        "fps_capability": 24.0,
        "average_latency_ms": 120.0,
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
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        detections, annotated = detector.detect_frame(img)
        
        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "detections": detections,
            "count": len(detections),
            "annotated_image_base64": f"data:image/jpeg;base64,{annotated_b64}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
