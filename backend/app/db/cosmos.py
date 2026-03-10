"""
Azure Cosmos DB Async Client for DAOM

Uses azure.cosmos.aio (async SDK) to prevent blocking the FastAPI event loop.
Container proxies are initialized once at startup and cached globally.
"""
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from app.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Container names
MODELS_CONTAINER = "DocumentModels"
EXTRACTIONS_CONTAINER = "ExtractedData"
AUDIT_CONTAINER = "audit_logs"
USERS_CONTAINER = "users"
GROUPS_CONTAINER = "groups"
MENUS_CONTAINER = "menus"
PROMPTS_CONTAINER = "prompts"
VIBE_DICTIONARY_CONTAINER = "vibe_dictionaries"

# Singleton client instance
_client: Optional[CosmosClient] = None
_database = None
_containers: dict = {}


def get_cosmos_client() -> Optional[CosmosClient]:
    """Get Cosmos DB async client singleton (created during init_cosmos)"""
    return _client


def get_database():
    """Get cached database proxy"""
    return _database


def get_container(container_name: str, partition_key_path: str = "/id", indexing_policy: dict = None):
    """Get a cached container proxy by name.
    Containers are pre-initialized during init_cosmos().
    If the container hasn't been initialized yet, returns None.
    """
    return _containers.get(container_name)


# ─── Indexing Policies ────────────────────────────────────────
# Composite indexes must match ORDER BY clauses in queries.
# NOTE: create_container_if_not_exists does NOT update indexes
# on existing containers. For existing deployments, apply these
# indexes via Azure Portal or a migration script.

_EXTRACTIONS_INDEX_POLICY = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [
        {"path": "/preview_data/*"},
        {"path": "/extracted_data/*"},
        {"path": "/debug_data/*"},
        {"path": '/"_etag"/?'},
    ],
    "compositeIndexes": [
        # get_logs_by_model: WHERE model_id ORDER BY created_at DESC
        [{"path": "/model_id", "order": "ascending"}, {"path": "/created_at", "order": "descending"}],
        # get_logs_by_user: WHERE user_id ORDER BY created_at DESC
        [{"path": "/user_id", "order": "ascending"}, {"path": "/created_at", "order": "descending"}],
        # tenant-filtered: WHERE tenant_id ORDER BY created_at DESC
        [{"path": "/tenant_id", "order": "ascending"}, {"path": "/created_at", "order": "descending"}],
        # type-filtered: WHERE type ORDER BY created_at DESC
        [{"path": "/type", "order": "ascending"}, {"path": "/created_at", "order": "descending"}],
    ]
}

_AUDIT_INDEX_POLICY = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [
        {"path": "/details/*"},
        {"path": "/changes/*"},
        {"path": '/"_etag"/?'},
    ],
    "compositeIndexes": [
        # get_audit_logs: WHERE tenant_id ORDER BY timestamp DESC
        [{"path": "/tenant_id", "order": "ascending"}, {"path": "/timestamp", "order": "descending"}],
        # user-filtered: WHERE user_id ORDER BY timestamp DESC
        [{"path": "/user_id", "order": "ascending"}, {"path": "/timestamp", "order": "descending"}],
        # resource-filtered: WHERE resource_type ORDER BY timestamp DESC
        [{"path": "/resource_type", "order": "ascending"}, {"path": "/timestamp", "order": "descending"}],
        # action-filtered: WHERE action ORDER BY timestamp DESC
        [{"path": "/action", "order": "ascending"}, {"path": "/timestamp", "order": "descending"}],
    ]
}


async def _init_container(database, name: str, partition_key_path: str = "/id", indexing_policy: dict = None):
    """Get a container proxy reference (no network call).
    The container must already exist in Cosmos DB.
    """
    global _containers
    try:
        container = database.get_container_client(name)
        _containers[name] = container
        logger.info(f"[Cosmos] Container '{name}' registered (async proxy)")
        return container
    except Exception as e:
        logger.error(f"[Cosmos] Container '{name}' proxy failed: {e}")
        return None


def get_models_container():
    """Get cached DocumentModels container"""
    return _containers.get(MODELS_CONTAINER)


def get_extractions_container():
    """Get cached ExtractedData container"""
    return _containers.get(EXTRACTIONS_CONTAINER)


def get_audit_container():
    """Get cached audit_logs container"""
    return _containers.get(AUDIT_CONTAINER)


def get_users_container():
    """Get cached users container"""
    return _containers.get(USERS_CONTAINER)


def get_groups_container():
    """Get cached groups container"""
    return _containers.get(GROUPS_CONTAINER)


CONFIG_CONTAINER = "system_config"

def get_config_container():
    """Get cached system_config container"""
    return _containers.get(CONFIG_CONTAINER)

def get_vibe_dictionary_container():
    """Get cached vibe_dictionaries container"""
    return _containers.get(VIBE_DICTIONARY_CONTAINER)


async def init_cosmos():
    """Initialize Cosmos DB async connection.
    
    Uses get_database_client() and get_container_client() which create
    local proxy objects WITHOUT making network calls. This avoids
    permission issues and startup failures. Actual DB calls
    happen lazily when endpoints are hit.
    """
    global _client, _database

    logger.info("[Cosmos] Initializing (async)...")

    if not settings.COSMOS_ENDPOINT or not settings.COSMOS_KEY:
        logger.warning("[Cosmos] No credentials configured, using local JSON fallback")
        return

    try:
        _client = CosmosClient(
            url=settings.COSMOS_ENDPOINT,
            credential=settings.COSMOS_KEY
        )
        logger.info(f"[Cosmos] Async client created for {settings.COSMOS_ENDPOINT}")

        # get_database_client: proxy only, no network call
        _database = _client.get_database_client(settings.COSMOS_DATABASE)
        logger.info(f"[Cosmos] Database '{settings.COSMOS_DATABASE}' proxy ready")

        # Pre-register all container proxies (no network calls)
        await _init_container(_database, MODELS_CONTAINER, "/id")
        await _init_container(_database, EXTRACTIONS_CONTAINER, "/model_id")
        await _init_container(_database, AUDIT_CONTAINER, "/user_id")
        await _init_container(_database, USERS_CONTAINER, "/tenant_id")
        await _init_container(_database, GROUPS_CONTAINER, "/tenant_id")
        await _init_container(_database, MENUS_CONTAINER, "/id")
        await _init_container(_database, CONFIG_CONTAINER, "/id")
        await _init_container(_database, PROMPTS_CONTAINER, "/id")
        await _init_container(_database, VIBE_DICTIONARY_CONTAINER, "/model_id")

        logger.info(f"[Cosmos] Initialization complete — {len(_containers)} containers registered")

    except Exception as e:
        logger.error(f"[Cosmos] Async initialization failed: {e}")
        _client = None
        _database = None


async def close_cosmos():
    """Close the async Cosmos client (call during shutdown)"""
    global _client
    if _client:
        try:
            await _client.close()
            logger.info("[Cosmos] Async client closed")
        except Exception as e:
            logger.warning(f"[Cosmos] Error closing client: {e}")
        finally:
            _client = None
