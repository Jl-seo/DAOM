from fastapi import APIRouter
from app.api.endpoints import documents, models, settings, templates, audit, users, groups, graph, menus, extraction_preview, site_settings, prompts, power_automate, comparison

api_router = APIRouter()
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(site_settings.router, tags=["site-settings"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(menus.router, prefix="/menus", tags=["menus"])
api_router.include_router(extraction_preview.router, prefix="/extraction", tags=["extraction"])
from app.api.endpoints.extraction import logs
api_router.include_router(logs.router, prefix="/extraction", tags=["extraction"])

api_router.include_router(comparison.router, prefix="/comparison", tags=["comparison"])

# Power Automate Custom Connector
api_router.include_router(power_automate.router, prefix="/connectors", tags=["Power Automate Connector"])

# Dictionary Engine
from app.api.endpoints import dictionaries, vibe_dictionary
api_router.include_router(dictionaries.router, prefix="/dictionaries", tags=["dictionaries"])
api_router.include_router(vibe_dictionary.router, prefix="/vibe-dictionary", tags=["vibe_dictionary"])
