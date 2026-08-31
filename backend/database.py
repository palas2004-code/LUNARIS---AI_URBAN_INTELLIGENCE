import logging
from supabase import create_client, Client
from backend.config import settings

logger = logging.getLogger("lunaris.database")

_supabase_client: Client | None = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        try:
            key_to_use = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
            _supabase_client = create_client(settings.SUPABASE_URL, key_to_use)
            logger.info("Connected to Supabase PostgreSQL at %s", settings.SUPABASE_URL)
        except Exception as e:
            logger.error("Failed to connect to Supabase: %s", e)
            raise e
    return _supabase_client
