"""
Startup Service - Initialize system defaults on application startup
"""
import logging
from app.core.config import settings
from app.db.cosmos import get_container
from app.services import menu_service
from app.services.llm import initialize_llm_settings

logger = logging.getLogger(__name__)

SYSTEM_ADMIN_GROUP_ID = "system-admins"
SYSTEM_ADMIN_GROUP_NAME = "System Admins"


def get_initial_admin_emails() -> list[str]:
    """Get list of initial admin emails from env"""
    if not settings.INITIAL_ADMIN_EMAILS:
        return []
    return [e.strip().lower() for e in settings.INITIAL_ADMIN_EMAILS.split(",") if e.strip()]


async def seed_system_admin_group(tenant_id: str, current_user_email: str = None, current_user_id: str = None, current_user_name: str = None) -> bool:
    """Create System Admins group if not exists and add initial admins"""
    container = get_container("groups", "/tenant_id")
    if not container:
        return False

    try:
        # Check if System Admins group exists for this tenant
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.id = @id AND c.tenant_id = @tenant_id",
            parameters=[
                {"name": "@id", "value": SYSTEM_ADMIN_GROUP_ID},
                {"name": "@tenant_id", "value": tenant_id}
            ],
            enable_cross_partition_query=True
        )]

        if items:
            group_data = items[0]
        else:
            # Create System Admins group
            from datetime import datetime
            group_data = {
                "id": SYSTEM_ADMIN_GROUP_ID,
                "name": SYSTEM_ADMIN_GROUP_NAME,
                "description": "시스템 관리자 그룹 - 모든 권한",
                "tenant_id": tenant_id,
                "members": [],
                "permissions": {
                    "superAdmin": True,
                    "models": [],
                    "menus": []
                },
                "created_by": "system",
                "created_at": datetime.utcnow().isoformat()
            }
            await container.create_item(body=group_data)
            logger.info(f"Created System Admins group for tenant {tenant_id}")

        # If current user's email is in INITIAL_ADMIN_EMAILS, add them
        initial_admins = get_initial_admin_emails()
        if current_user_email and current_user_email.lower() in initial_admins:
            members = group_data.get("members", [])
            user_id = current_user_id or current_user_email

            if not any(m.get("id") == user_id for m in members):
                members.append({
                    "type": "user",
                    "id": user_id,
                    "displayName": current_user_name or current_user_email
                })
                group_data["members"] = members
                await container.upsert_item(body=group_data)
                logger.info(f"Added {current_user_email} to System Admins group")

        return True

    except Exception as e:
        logger.error(f"Error seeding System Admins group: {e}")
        return False

async def run_startup_tasks(tenant_id: str = "default", current_user_email: str = None, current_user_id: str = None, current_user_name: str = None):
    """Run all startup tasks"""
    logger.info(f"Running startup tasks for tenant {tenant_id}...")

    # Initialize LLM settings from DB
    initialize_llm_settings()

    # Seed menus
    await menu_service.seed_menus(tenant_id)

    # Seed System Admins group
    await seed_system_admin_group(tenant_id, current_user_email, current_user_id, current_user_name)

    # Seed default models
    await seed_default_models(tenant_id)

    logger.info("Startup tasks completed")


async def seed_default_models(tenant_id: str):
    """Seed default extraction models if none exist"""
    container = get_container("DocumentModels", "/tenant_id")
    if not container:
        return

    try:
        # Check if any models exist
        items = [item async for item in container.query_items(
            query="SELECT * FROM c WHERE c.tenant_id = @tenant_id",
            parameters=[{"name": "@tenant_id", "value": tenant_id}],
            enable_cross_partition_query=True,
            max_item_count=1
        )]

        if items:
            return  # Models already exist

        # Create default Invoice model
        invoice_model = {
            "id": "ca8d5c48-95d6-44ea-9d50-76fc353f1bd1",
            "name": "인보이스",
            "description": "인보이스에서 정보를 추출",
            "global_rules": "모든 금액은 천원단위로 , 붙여서 구분함 그리고 금액단위가 원화가 아닌 경우 원화로 환전함",
            "data_structure": "table",
            "tenant_id": tenant_id,
            "created_at": "2024-01-01T00:00:00.000000",
            "fields": [
                {
                    "key": "invoice_no",
                    "label": "인보이스 번호",
                    "description": "인보이스 번호",
                    "rules": "",
                    "type": "string"
                },
                {
                    "key": "issuer_name",
                    "label": "발행회사명",
                    "description": "인보이스 발행한 회사 이름",
                    "rules": "",
                    "type": "string"
                },
                {
                    "key": "total_amount",
                    "label": "금액",
                    "description": "인보이스 금액(세금 포함)",
                    "rules": "",
                    "type": "number"
                },
                {
                    "key": "vat",
                    "label": "부가세",
                    "description": "인보이스 금액에 붙은 부가세",
                    "rules": "",
                    "type": "number"
                }
            ]
        }

        await container.upsert_item(body=invoice_model)
        logger.info(f"Seeded default 'Invoice' model for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Error seeding default models: {e}")

