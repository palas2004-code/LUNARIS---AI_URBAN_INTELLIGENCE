from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class BoundingBox(BaseModel):
    class_name: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    area_cm2: Optional[float] = None
    estimated_depth_cm: Optional[float] = None

class DetectionEvent(BaseModel):
    bus_id: str = Field(..., example="BUS-07")
    bus_plate: Optional[str] = "WB-04-E-2910"
    type: str = Field(..., example="Pothole") # Pothole, Road Damage, Waterlogging, Traffic, Pedestrian Hazard
    category: Optional[str] = None
    location: str = Field(..., example="Park Street, Kolkata")
    lat: float = Field(..., example=22.5512)
    lng: float = Field(..., example=88.3524)
    severity: str = Field("MEDIUM", example="HIGH") # CRITICAL, HIGH, MEDIUM, LOW
    confidence: float = Field(..., example=98.4)
    bounding_boxes: Optional[List[BoundingBox]] = []
    evidence_image_base64: Optional[str] = None
    evidence_image_url: Optional[str] = None
    details: Optional[str] = None
    timestamp: Optional[datetime] = None

class BusTelemetry(BaseModel):
    bus_id: str = Field(..., example="BUS-07")
    plate: str = Field(..., example="WB-04-E-2910")
    route: str = Field(..., example="Park Street → Esplanade")
    camera_status: str = Field("Online", example="Online") # Online, Offline
    gps_status: str = Field("Active", example="Active")     # Active, Inactive
    ai_status: str = Field("Active", example="Active")       # Active, Inactive
    lat: float = Field(..., example=22.5512)
    lng: float = Field(..., example=88.3524)
    speed: float = Field(34.2, example=34.2)
    fps: float = Field(98.2, example=98.2)
    last_location: str = Field("Park Street", example="Park Street")

class IncidentStatusUpdate(BaseModel):
    status: str = Field(..., example="IN PROGRESS") # UNRESOLVED, IN PROGRESS, RESOLVED
    assigned_team: Optional[str] = None
    resolution_notes: Optional[str] = None

class StreamInfo(BaseModel):
    stream_id: str
    bus_id: str
    rtsp_url: str
    webrtc_url: str
    hls_url: str
    status: str
