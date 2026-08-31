"""
LUNARIS Central Structured Audit Logger
Records timestamps, system events, and security audits to console and Supabase public.system_logs.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from backend.database import get_supabase

# Configure root logger format with ISO timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z"
)

logger = logging.getLogger("lunaris.audit")

class AuditEventType:
    CAMERA_CONNECT = "CAMERA_CONNECT"
    AI_INFERENCE = "AI_INFERENCE"
    DETECTION = "DETECTION_EVENT"
    INCIDENT_CREATE = "INCIDENT_CREATED"
    DUPLICATE_MERGE = "DUPLICATE_MERGED"
    COMPLAINT_CREATE = "COMPLAINT_CREATED"
    ASSIGNMENT = "ASSIGNMENT_DISPATCHED"
    STATUS_UPDATE = "STATUS_UPDATED"
    RESOLUTION = "INCIDENT_RESOLVED"
    SECURITY_ALERT = "SECURITY_ALERT"

def log_system_event(
    event_type: str,
    message: str,
    severity: str = "INFO",
    source: str = "BACKEND_API",
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Logs structured audit event to stdout and writes record to Supabase public.system_logs.
    """
    timestamp_str = datetime.utcnow().isoformat() + "Z"
    meta = metadata or {}

    # 1. Console Output
    log_msg = f"[{event_type}] ({source}) {message} | meta={meta}"
    if severity == "ERROR" or severity == "CRITICAL":
        logger.error(log_msg)
    elif severity == "WARNING":
        logger.warning(log_msg)
    else:
        logger.info(log_msg)

    # 2. Asynchronous / Background Database Persist
    try:
        supabase = get_supabase()
        supabase.from_("system_logs").insert({
            "event_type": event_type,
            "severity": severity.upper(),
            "source_service": source,
            "message": message,
            "metadata": meta,
            "created_at": timestamp_str
        }).execute()
    except Exception as e:
        logger.debug(f"Audit log database persist note: {e}")
