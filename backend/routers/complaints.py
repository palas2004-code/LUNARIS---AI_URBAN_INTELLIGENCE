import logging
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from backend.database import get_supabase

logger = logging.getLogger("lunaris.complaints")
router = APIRouter(prefix="/complaints", tags=["Complaints & Grievances"])

class ComplaintCreate(BaseModel):
    incident_id: Optional[str] = None
    department_id: Optional[str] = None
    priority: str = "HIGH"
    title: str
    description: Optional[str] = None
    evidence: Optional[str] = None
    location: str

class ComplaintUpdate(BaseModel):
    status: str
    remarks: Optional[str] = None

@router.get("/")
async def list_complaints(status: Optional[str] = None, limit: int = 50):
    try:
        supabase = get_supabase()
        query = supabase.from_("complaints").select("*").order("created_at", desc=True).limit(limit)
        if status:
            query = query.eq("status", status.upper())
        res = query.execute()
        return {"complaints": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def create_complaint(c: ComplaintCreate):
    try:
        supabase = get_supabase()
        c_id = f"C-{uuid.uuid4().hex[:4].upper()}"
        data = {
            "id": c_id,
            "incident_id": c.incident_id,
            "department_id": c.department_id,
            "priority": c.priority.upper(),
            "title": c.title,
            "description": c.description or f"Automated grievance dispatch for {c.title}",
            "evidence": c.evidence or "Attached in Supabase Storage",
            "location": c.location,
            "status": "OPEN",
            "created_at": datetime.utcnow().isoformat()
        }
        res = supabase.from_("complaints").insert(data).execute()

        # Audit Log
        from backend.logger import log_system_event, AuditEventType
        log_system_event(
            AuditEventType.COMPLAINT_CREATE,
            f"Municipal complaint #{c_id} created for incident {c.incident_id or 'GENERAL'} ({c.title}).",
            severity="INFO",
            source="COMPLAINT_ROUTER",
            metadata={"complaint_id": c_id, "incident_id": c.incident_id, "priority": c.priority}
        )

        return {"success": True, "complaint": res.data[0] if res.data else data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{complaint_id}")
async def update_complaint(complaint_id: str, update: ComplaintUpdate):
    try:
        supabase = get_supabase()
        supabase.from_("complaints").update({
            "status": update.status.upper(),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", complaint_id).execute()

        # Audit Log
        from backend.logger import log_system_event, AuditEventType
        log_system_event(
            AuditEventType.STATUS_UPDATE,
            f"Complaint #{complaint_id} updated to status '{update.status.upper()}'.",
            severity="INFO",
            source="COMPLAINT_ROUTER",
            metadata={"complaint_id": complaint_id, "status": update.status.upper()}
        )

        return {"success": True, "complaint_id": complaint_id, "status": update.status.upper()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
