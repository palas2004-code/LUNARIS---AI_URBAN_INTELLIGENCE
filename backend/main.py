import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.routers import detections, fleet, incidents, streams, complaints, analytics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("lunaris.main")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FastAPI Central Server for LUNARIS Mobile Urban AI Platform (SIH 2026 SIH26124)",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware to allow LUNARIS dashboard and local/remote clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(detections.router, prefix=settings.API_V1_PREFIX)
app.include_router(fleet.router, prefix=settings.API_V1_PREFIX)
app.include_router(incidents.router, prefix=settings.API_V1_PREFIX)
app.include_router(streams.router, prefix=settings.API_V1_PREFIX)
app.include_router(complaints.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)

@app.get("/")
def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "OPERATIONAL",
        "supabase": settings.SUPABASE_URL,
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "edge_ai_ready": True,
        "database": "supabase_postgresql",
        "mediamtx_rtsp": settings.MEDIAMTX_RTSP_URL,
        "mediamtx_webrtc": settings.MEDIAMTX_WEBRTC_URL
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
