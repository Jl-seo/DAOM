"""
Site Settings API Endpoints
Manages site branding, theme, and configuration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import os
from pathlib import Path

router = APIRouter(prefix="/settings", tags=["settings"])

# Config file path
CONFIG_FILE = Path(__file__).parent.parent.parent.parent / "site_config.json"

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

def load_config() -> dict:
    """Load site config from file"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(config: dict):
    """Save site config to file"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

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
