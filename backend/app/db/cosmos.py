"""
Azure Cosmos DB Client for DAOM

Provides database and container access for:
- DocumentModels: Extraction models and correction rules
- ExtractedData: Extraction results and logs
"""
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
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

# Singleton client instance
_client: Optional[CosmosClient] = None
_database = None
_containers: dict = {}


def get_cosmos_client() -> Optional[CosmosClient]:
    """Get or create Cosmos DB client singleton"""
    global _client
    
    if _client is not None:
        return _client
    
    if not settings.COSMOS_ENDPOINT or not settings.COSMOS_KEY:
        logger.warning("[Cosmos] No credentials configured, using local JSON fallback")
        return None
    
    try:
        _client = CosmosClient(
            url=settings.COSMOS_ENDPOINT,
            credential=settings.COSMOS_KEY
        )
        logger.info(f"[Cosmos] Connected to {settings.COSMOS_ENDPOINT}")
        return _client
    except Exception as e:
        logger.error(f"[Cosmos] Connection failed: {e}")
        return None


def get_database():
    """Get or create DAOM database"""
    global _database
    
    if _database is not None:
        return _database
    
    client = get_cosmos_client()
    if not client:
        return None
    
    try:
        _database = client.create_database_if_not_exists(id=settings.COSMOS_DATABASE)
        logger.info(f"[Cosmos] Database '{settings.COSMOS_DATABASE}' ready")
        return _database
    except Exception as e:
        logger.error(f"[Cosmos] Database creation failed: {e}")
        return None


def get_container(container_name: str, partition_key_path: str = "/id", indexing_policy: dict = None):
    """Get or create a container by name with optional indexing policy"""
    global _containers
    
    if container_name in _containers:
        return _containers[container_name]
    
    database = get_database()
    if not database:
        return None
    
    try:
        kwargs = {
            "id": container_name,
            "partition_key": PartitionKey(path=partition_key_path),
        }
        if indexing_policy:
            kwargs["indexing_policy"] = indexing_policy
        
        container = database.create_container_if_not_exists(**kwargs)
        _containers[container_name] = container
        logger.info(f"[Cosmos] Container '{container_name}' ready")
        return container
    except Exception as e:
        logger.error(f"[Cosmos] Container '{container_name}' creation failed: {e}")
        return None


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


def get_models_container():
    """Get or create DocumentModels container"""
    return get_container(MODELS_CONTAINER, "/id")


def get_extractions_container():
    """Get or create ExtractedData container with composite indexes"""
    return get_container(EXTRACTIONS_CONTAINER, "/model_id", _EXTRACTIONS_INDEX_POLICY)


def get_audit_container():
    """Get or create audit_logs container with composite indexes"""
    return get_container(AUDIT_CONTAINER, "/user_id", _AUDIT_INDEX_POLICY)


def get_users_container():
    """Get or create users container"""
    return get_container(USERS_CONTAINER, "/tenant_id")


def get_groups_container():
    """Get or create groups container"""
    return get_container(GROUPS_CONTAINER, "/tenant_id")


def init_cosmos():
    """Initialize Cosmos DB connection and containers"""
    logger.info("[Cosmos] Initializing...")
    get_models_container()
    get_extractions_container()
    get_audit_container()
    get_users_container()
    get_groups_container()
    get_config_container()
    logger.info("[Cosmos] Initialization complete")


CONFIG_CONTAINER = "system_config"

def get_config_container():
    """Get or create system_config container"""
    return get_container(CONFIG_CONTAINER, "/id")

