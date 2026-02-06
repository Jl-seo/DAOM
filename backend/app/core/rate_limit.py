"""
Rate Limiting middleware for API protection
Prevents DoS attacks and API abuse
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger(__name__)


def get_tenant_id(request: Request) -> str:
    """
    Rate limit key function - uses tenant_id if available, otherwise IP address.
    This ensures rate limits are per-tenant, not per-user.
    """
    # Try to get tenant from JWT (if available in state)
    if hasattr(request.state, "user") and hasattr(request.state.user, "tenant_id"):
        return f"tenant:{request.state.user.tenant_id}"
    
    # Fallback to IP address
    return get_remote_address(request)


# Create limiter instance with tenant-aware key function
limiter = Limiter(key_func=get_tenant_id)


def setup_rate_limiting(app):
    """
    Configure rate limiting for the FastAPI application.
    Call this in main.py after app creation.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    logger.info("[Security] Rate limiting middleware enabled")
