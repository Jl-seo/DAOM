from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.core.config import settings
from app.api.api import api_router
from app.db.cosmos import init_cosmos
from app.services import startup_service
import os

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) from Azure Container Apps
# This fixes HTTPS redirect issues when behind a reverse proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Set all CORS enabled origins
cors_origins = settings.cors_origins
# Add both versions (with and without trailing slash) to handle browser variations
cors_origins_expanded = []
for origin in cors_origins:
    cors_origins_expanded.append(origin)
    if origin.endswith('/'):
        cors_origins_expanded.append(origin.rstrip('/'))
    else:
        cors_origins_expanded.append(origin + '/')

if cors_origins_expanded:
    print(f"[MAIN] Enabling CORS for origins: {cors_origins_expanded}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_expanded,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files for uploaded documents
os.makedirs("temp_uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="temp_uploads"), name="static")


@app.on_event("startup")
async def startup_event():
    """Initialize connections and seed data on startup"""
    """Initialize connections and seed data on startup"""
    try:
        init_cosmos()
        # Run startup tasks (seed menus, create System Admins group, etc.)
        await startup_service.run_startup_tasks()
    except Exception as e:
        import logging
        logging.error(f"CRITICAL: Startup failed: {e}")
        # Do not raise exception to keep container running for debugging


@app.get("/")
def root():
    return {"message": "Welcome to DAOM API v1.0.2"}
