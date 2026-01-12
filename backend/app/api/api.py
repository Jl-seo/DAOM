from fastapi import APIRouter
from app.api.endpoints import documents, models, settings, templates, audit, users, groups, graph, menus, extraction_preview, site_settings

api_router = APIRouter()
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(site_settings.router, tags=["site-settings"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(menus.router, prefix="/menus", tags=["menus"])
api_router.include_router(extraction_preview.router, prefix="/extraction", tags=["extraction"])
from app.api.endpoints.extraction import logs
api_router.include_router(logs.router, prefix="/extraction", tags=["extraction"])

