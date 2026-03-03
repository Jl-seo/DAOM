"""
Menu Service - Manage menus and menu permissions from database
"""
import logging
from dataclasses import dataclass, asdict
from typing import Optional
from app.db.cosmos import get_container

logger = logging.getLogger(__name__)

MENUS_CONTAINER = "menus"

# Default menus to seed on first run
# Note: 'name' field uses i18n keys - frontend translates these via t('menu.{id}')
DEFAULT_MENUS = [
    {"id": "upload", "name": "menu.upload", "icon": "Upload", "order": 1, "parent": None},
    {"id": "history", "name": "menu.history", "icon": "History", "order": 2, "parent": None},
    {"id": "models", "name": "menu.models", "icon": "Layers", "order": 3, "parent": None},
    {"id": "settings", "name": "menu.settings", "icon": "Settings", "order": 4, "parent": None},
    {"id": "settings-general", "name": "menu.settings_general", "icon": "Settings", "order": 1, "parent": "settings"},
    {"id": "settings-logs", "name": "menu.settings_logs", "icon": "ClipboardList", "order": 2, "parent": "settings"},
    {"id": "settings-permissions", "name": "menu.settings_permissions", "icon": "Shield", "order": 3, "parent": "settings"},
]


@dataclass
class Menu:
    id: str
    name: str
    icon: str
    order: int
    parent: Optional[str] = None  # None = top-level, else parent menu id

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Menu":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            icon=data.get("icon", ""),
            order=data.get("order", 0),
            parent=data.get("parent")
        )


async def seed_menus(tenant_id: str) -> bool:
    """Seed default menus for a tenant if not exists"""
    container = get_container(MENUS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        # Check if menus exist
        existing = [item async for item in container.query_items(
            query="SELECT c.id FROM c WHERE c.tenant_id = @tenant_id",
            parameters=[{"name": "@tenant_id", "value": tenant_id}],
        )]

        if len(existing) > 0:
            return True  # Already seeded

        # Seed default menus
        for menu_data in DEFAULT_MENUS:
            menu_doc = {
                **menu_data,
                "tenant_id": tenant_id
            }
            await container.create_item(body=menu_doc)

        logger.info(f"Seeded {len(DEFAULT_MENUS)} menus for tenant {tenant_id}")
        return True

    except Exception as e:
        logger.error(f"Error seeding menus: {e}")
        return False


async def get_all_menus(tenant_id: str) -> list[Menu]:
    """Get all menus for a tenant"""
    container = get_container(MENUS_CONTAINER, "/tenant_id")
    if not container:
        return []

    if not tenant_id:
        logger.warning("get_all_menus called with empty tenant_id")
        return []

    try:
        # Seed if needed
        await seed_menus(tenant_id)

        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.tenant_id = @tenant_id ORDER BY c.order",
            parameters=[{"name": "@tenant_id", "value": tenant_id}],
        )]
        return [Menu.from_dict(item) for item in items]

    except Exception as e:
        logger.error(f"Error getting menus for tenant '{tenant_id}': {e}")
        return []


async def get_accessible_menus(tenant_id: str, menu_ids: list[str], is_super_admin: bool = False) -> list[Menu]:
    """Get menus accessible by a user based on their permissions"""
    all_menus = await get_all_menus(tenant_id)

    if is_super_admin:
        return all_menus

    # Filter by allowed menu IDs
    # Also include parent menus if any child is accessible
    accessible = []
    accessible_ids = set(menu_ids)

    # Add parent menus for accessible children
    for menu in all_menus:
        if menu.id in accessible_ids:
            if menu.parent and menu.parent not in accessible_ids:
                accessible_ids.add(menu.parent)

    for menu in all_menus:
        if menu.id in accessible_ids:
            accessible.append(menu)

    return accessible


async def create_menu(
    menu_id: str,
    name: str,
    icon: str,
    order: int,
    tenant_id: str,
    parent: Optional[str] = None
) -> Optional[Menu]:
    """Create a custom menu"""
    container = get_container(MENUS_CONTAINER, "/tenant_id")
    if not container:
        return None

    try:
        menu = Menu(
            id=menu_id,
            name=name,
            icon=icon,
            order=order,
            parent=parent
        )
        doc = {**menu.to_dict(), "tenant_id": tenant_id}
        await container.create_item(body=doc)
        return menu

    except Exception as e:
        logger.error(f"Error creating menu: {e}")
        return None


async def update_menu(menu_id: str, tenant_id: str, name: str = None, icon: str = None, order: int = None) -> bool:
    """Update menu properties"""
    container = get_container(MENUS_CONTAINER, "/tenant_id")
    if not container:
        return False

    try:
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": menu_id},
                {"name": "@tenant_id", "value": tenant_id}
            ],
        )]

        if not items:
            return False

        doc = items[0]
        if name:
            doc["name"] = name
        if icon:
            doc["icon"] = icon
        if order is not None:
            doc["order"] = order

        await container.upsert_item(body=doc)
        return True

    except Exception as e:
        logger.error(f"Error updating menu: {e}")
        return False
