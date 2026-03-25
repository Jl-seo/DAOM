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
    from app.db.cosmos import init_cosmos, close_cosmos
    from app.services import startup_service
    from app.core.rate_limit import setup_rate_limiting

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Initialize Rate Limiting
    setup_rate_limiting(app)

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
            expose_headers=["Content-Disposition"],
        )

    # ── Global Exception Handler ──
    # Ensures ALL error responses (500, etc.) include CORS headers.
    # Without this, unhandled exceptions bypass CORSMiddleware and the
    # browser interprets the missing Access-Control-Allow-Origin as a CORS violation.
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"[GlobalHandler] Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal Server Error: {type(exc).__name__}"}
        )

    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Mount static files for uploaded documents
    os.makedirs("temp_uploads", exist_ok=True)
    app.mount("/static", StaticFiles(directory="temp_uploads"), name="static")

    @app.on_event("startup")
    async def startup_event():
        """Initialize connections and seed data on startup"""
        try:
            await init_cosmos()
            # Run startup tasks (seed menus, create System Admins group, etc.)
            # OPTIMIZATION: Run in background to prevent Container App Startup Probe timeout
            import asyncio
            asyncio.create_task(startup_service.run_startup_tasks())
        except Exception as e:
            logging.error(f"CRITICAL: Startup failed: {e}")
            # Do not raise exception to keep container running for debugging
            # Forced redeploy trigger: 2026-01-06 08:30

    @app.on_event("shutdown")
    async def shutdown_event():
        """Close async connections on shutdown"""
        await close_cosmos()

    @app.get("/")
    def root():
        return {"message": "Welcome to DAOM API v1.0.2", "build": "2026-02-07T18:53-blob-unified"}

except Exception as e:
    print("!!! CRITICAL STARTUP ERROR !!!", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("main:app", host="0.0.0.0", port=args.port, reload=True)
