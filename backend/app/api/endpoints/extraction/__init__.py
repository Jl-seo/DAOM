"""
Extraction endpoints package
Modularized from extraction_preview.py
"""
from fastapi import APIRouter
from .jobs import router as jobs_router
from .logs import router as logs_router

router = APIRouter()

# Include sub-routers
router.include_router(jobs_router, tags=["Extraction Jobs"])
router.include_router(logs_router, tags=["Extraction Logs"])
