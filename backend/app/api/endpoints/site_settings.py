"""
Site Settings API Endpoints
Manages site branding, theme, and configuration
Persists to Cosmos DB for durability across deployments
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.db.cosmos import get_config_container

router = APIRouter(prefix="/settings", tags=["settings"])

# Fixed document ID for singleton config
SITE_CONFIG_ID = "site_config"

class SiteColors(BaseModel):
    primary: str
    primaryForeground: str
    secondary: str
    secondaryForeground: str
    background: str
    foreground: str
    card: str
    cardForeground: str
    muted: str
    mutedForeground: str
    accent: str
    accentForeground: str
    destructive: str
    border: str
    input: str
    ring: str
    sidebar: str
    sidebarForeground: str
    sidebarPrimary: str
    sidebarPrimaryForeground: str
    sidebarAccent: str
    sidebarAccentForeground: str
    sidebarBorder: str

class ColorConfig(BaseModel):
    light: SiteColors
    dark: SiteColors

class SiteConfig(BaseModel):
    siteName: str = "DAOM"
    siteDescription: str = "문서 자동화"
    logoUrl: Optional[str] = None
    faviconUrl: Optional[str] = None
    theme: str = "system"
    colors: Optional[ColorConfig] = None
    fontFamily: str = "Inter, ui-sans-serif, system-ui, sans-serif"
    customCss: Optional[str] = None
    radius: Optional[float] = 0.5
    density: Optional[str] = "normal"

def load_config() -> dict:
    """Load site config from Cosmos DB"""
    container = get_config_container()
    if not container:
        return {}
    
    try:
        item = container.read_item(item=SITE_CONFIG_ID, partition_key=SITE_CONFIG_ID)
        # Remove Cosmos metadata
        item.pop('id', None)
        item.pop('_rid', None)
        item.pop('_self', None)
        item.pop('_etag', None)
        item.pop('_attachments', None)
        item.pop('_ts', None)
        return item
    except Exception:
        return {}

def save_config(config: dict):
    """Save site config to Cosmos DB"""
    container = get_config_container()
    if not container:
        raise HTTPException(status_code=500, detail="Database not available")
    
    try:
        doc = {"id": SITE_CONFIG_ID, **config}
        container.upsert_item(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")

@router.get("/site")
async def get_site_config():
    """Get current site configuration"""
    return load_config()

@router.put("/site")
async def update_site_config(config: SiteConfig):
    """Update site configuration"""
    config_dict = config.model_dump(exclude_none=True)
    save_config(config_dict)
    return config_dict

@router.post("/site/reset")
async def reset_site_config():
    """Reset site configuration to defaults"""
    default_config = SiteConfig()
    config_dict = default_config.model_dump(exclude_none=True)
    save_config(config_dict)
    return config_dict
