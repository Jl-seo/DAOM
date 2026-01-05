import sys
import traceback
import os
import logging

# Configure logger early to catch startup errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    from app.core.config import settings
    from app.api.api import api_router
    from app.db.cosmos import init_cosmos
    from app.services import startup_service

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) from Azure Container Apps
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

    # Set all CORS enabled origins
    cors_origins = settings.cors_origins
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
        try:
            init_cosmos()
            # Run startup tasks (seed menus, create System Admins group, etc.)
            await startup_service.run_startup_tasks()
        except Exception as e:
            logging.error(f"CRITICAL: Startup failed: {e}")
            # Do not raise exception to keep container running for debugging

    @app.get("/")
    def root():
        return {"message": "Welcome to DAOM API v1.0.2"}

except Exception as e:
    print("!!! CRITICAL STARTUP ERROR !!!", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
