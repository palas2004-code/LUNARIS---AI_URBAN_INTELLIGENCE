import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.models import BusTelemetry
from backend.database import get_supabase

logger = logging.getLogger("lunaris.fleet")
router = APIRouter(prefix="/fleet", tags=["Bus Fleet Telemetry"])

@router.post("/telemetry")
async def update_bus_telemetry(telemetry: BusTelemetry):
    """
    Ingest live GPS coordinates, camera health, and AI inference FPS from an active bus node.
    Updates public.buses and inserts into public.bus_locations time-series.
    """
    try:
        supabase = get_supabase()
        
        # 1. Update Bus Registry in public.buses
        bus_payload = {
            "bus_code": telemetry.bus_id,
            "registration_number": telemetry.plate,
            "route_name": telemetry.route,
            "status": "ACTIVE" if telemetry.camera_status == "Online" else "IDLE",
            "last_latitude": telemetry.lat,
            "last_longitude": telemetry.lng,
            "last_seen_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        supabase.from_("buses").upsert(bus_payload, on_conflict="bus_code").execute()

        # 2. Insert High-Frequency RTK Location in public.bus_locations
        loc_payload = {
            "bus_id": telemetry.bus_id,
            "latitude": telemetry.lat,
            "longitude": telemetry.lng,
            "speed_kmh": telemetry.speed,
            "recorded_at": datetime.utcnow().isoformat()
        }
        supabase.from_("bus_locations").insert(loc_payload).execute()

        return {"success": True, "bus_id": telemetry.bus_id, "updated": True}
    except Exception as e:
        logger.error("Failed to update bus telemetry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_all_buses():
    """Retrieve all bus sensors and active edge states."""
    try:
        supabase = get_supabase()
        res = supabase.from_("buses").select("*, cameras(*), camera_streams(*)").order("bus_id").execute()
        return {"buses": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
