from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.api import api_router
from app.db.cosmos import init_cosmos
from app.services import startup_service
import os

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

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
    init_cosmos()
    # Run startup tasks (seed menus, create System Admins group, etc.)
    await startup_service.run_startup_tasks()


@app.get("/")
def root():
    return {"message": "Welcome to DAOM API"}
