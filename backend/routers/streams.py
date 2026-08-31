import httpx
from fastapi import APIRouter
from backend.config import settings

router = APIRouter(prefix="/streams", tags=["MediaMTX Video Streams"])

@router.get("/")
async def list_active_streams():
    """
    List all active MediaMTX RTSP and WebRTC streams mapped to city buses.
    """
    buses = ["BUS-07", "BUS-12", "BUS-15", "BUS-21"]
    stream_list = []
    
    for b in buses:
        stream_path = b.lower().replace("-", "")
        stream_list.append({
            "bus_id": b,
            "stream_path": stream_path,
            "rtsp_url": f"{settings.MEDIAMTX_RTSP_URL}/{stream_path}",
            "webrtc_url": f"{settings.MEDIAMTX_WEBRTC_URL}/{stream_path}/whep",
            "hls_url": f"{settings.MEDIAMTX_HLS_URL}/{stream_path}/index.m3u8",
            "status": "READY"
        })
        
    return {
        "streams": stream_list,
        "mediamtx_api": settings.MEDIAMTX_API_URL
    }
