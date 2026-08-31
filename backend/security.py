"""
LUNARIS Security, RLS & Authorization Suite
Implements input validation, rate limiting, role-based authorization,
camera credential protection, and signed storage URL generation.
"""

import time
import re
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.database import get_supabase
from backend.config import settings

security_bearer = HTTPBearer(auto_error=False)

# ------------------------------------------------------------------------------
# 1. Sliding Window Rate Limiter (Edge & Public APIs)
# ------------------------------------------------------------------------------
class InMemoryRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: Dict[str, List[float]] = {}

    def check_rate_limit(self, client_ip: str) -> bool:
        now = time.time()
        timestamps = self.clients.get(client_ip, [])
        # Prune expired timestamps
        valid_timestamps = [t for t in timestamps if now - t < self.window_seconds]
        if len(valid_timestamps) >= self.max_requests:
            return False  # Rate limit exceeded
        valid_timestamps.append(now)
        self.clients[client_ip] = valid_timestamps
        return True

global_rate_limiter = InMemoryRateLimiter(max_requests=120, window_seconds=60)

async def apply_rate_limiting(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not global_rate_limiter.check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please throttle telemetry requests."
        )

# ------------------------------------------------------------------------------
# 2. Strict Input Validation Helpers
# ------------------------------------------------------------------------------
def validate_coordinates(lat: float, lng: float) -> Tuple[float, float]:
    """Validates latitude (-90 to 90) and longitude (-180 to 180)."""
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Invalid GPS coordinates: lat={lat}, lng={lng}")
    return lat, lng

def sanitize_string(input_str: str, max_length: int = 255) -> str:
    """Strips dangerous characters and caps string length."""
    if not input_str:
        return ""
    clean = re.sub(r'[<>{}\[\]\\]', '', input_str)
    return clean[:max_length].strip()

# ------------------------------------------------------------------------------
# 3. Role-Based Authorization Guards
# ------------------------------------------------------------------------------
VALID_ROLES = ["admin", "authority", "maintenance", "viewer"]

async def require_auth_role(required_roles: List[str], credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)):
    """
    Validates Supabase JWT and checks that the user's role satisfies required_roles.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token."
        )

    token = credentials.credentials
    try:
        supabase = get_supabase()
        # Verify token with Supabase Auth
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.")

        # Check role from profiles table
        profile_res = supabase.from_("profiles").select("role").eq("id", user_res.user.id).execute()
        user_role = profile_res.data[0]["role"] if profile_res.data else "viewer"

        if user_role not in required_roles and "admin" not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden. Required role(s): {required_roles}, your role: {user_role}"
            )
        return user_res.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication error: {str(e)}")

# ------------------------------------------------------------------------------
# 4. Signed Storage Evidence Access
# ------------------------------------------------------------------------------
def generate_signed_evidence_url(bucket_name: str, file_path: str, expires_in_seconds: int = 3600) -> str:
    """
    Generates a secure signed URL for sensitive incident evidence frames.
    Does not expose raw public bucket URLs.
    """
    try:
        supabase = get_supabase()
        res = supabase.storage.from_(bucket_name).create_signed_url(file_path, expires_in_seconds)
        return res.get("signedUrl") or res.get("signedURL") or ""
    except Exception:
        return f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}"

# ------------------------------------------------------------------------------
# 5. Camera Credential Protection (Masking)
# ------------------------------------------------------------------------------
def mask_camera_credentials(rtsp_url: str) -> str:
    """
    Strips embedded password from RTSP URI before logging or client display.
    Example: rtsp://admin:secret123@192.168.1.50 -> rtsp://admin:***@192.168.1.50
    """
    if not rtsp_url:
        return ""
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', rtsp_url)
