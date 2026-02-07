"""
Extraction endpoints package
Modularized from extraction_preview.py
"""
from fastapi import APIRouter
from .logs import router as logs_router

router = APIRouter()

# Include sub-routers
# NOTE: jobs_router is NOT included here because extraction_preview.py
# already registers /start-job at the /extraction prefix in api.py.
# Including jobs_router would create a DUPLICATE /start-job route with
# incompatible params (files plural vs file singular), causing 422 errors.
router.include_router(logs_router, tags=["Extraction Logs"])

