from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from app.core.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key from header"""
    settings = get_settings()
    expected_key = getattr(settings, "AI_SERVICE_API_KEY", None)
    
    if not expected_key:
        # If no API key is set, allow all requests (for development)
        return True
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header."
        )
    
    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    
    return True


