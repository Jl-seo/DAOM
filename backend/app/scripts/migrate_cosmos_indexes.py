"""
Cosmos DB Index Migration Script

Applies the indexing policies defined in cosmos.py to EXISTING containers.
create_container_if_not_exists does NOT update indexes on existing containers,
so this script uses replace_container to update them.

Usage:
    python3 -m app.scripts.migrate_cosmos_indexes [--dry-run]

Requires:
    COSMOS_ENDPOINT, COSMOS_KEY, COSMOS_DATABASE env vars (or .env file)
"""
import sys
import json
import logging
from azure.cosmos import CosmosClient, PartitionKey

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ─── Import index policies from cosmos.py ───
sys.path.insert(0, ".")
from app.db.cosmos import (
    _EXTRACTIONS_INDEX_POLICY,
    _AUDIT_INDEX_POLICY,
    EXTRACTIONS_CONTAINER,
    AUDIT_CONTAINER,
)
from app.core.config import settings


# Map: (container_name, partition_key_path, new_indexing_policy)
MIGRATIONS = [
    (EXTRACTIONS_CONTAINER, "/model_id", _EXTRACTIONS_INDEX_POLICY),
    (AUDIT_CONTAINER, "/user_id", _AUDIT_INDEX_POLICY),
]


def get_current_policy(container) -> dict:
    """Read current indexing policy from container properties"""
    props = container.read()
    return props.get("indexingPolicy", {})


def apply_index_policy(database, container_name: str, pk_path: str, new_policy: dict, dry_run: bool = False):
    """Replace container indexing policy"""
    try:
        container = database.get_container_client(container_name)
        current = get_current_policy(container)

        # Compare composite indexes
        current_composites = current.get("compositeIndexes", [])
        new_composites = new_policy.get("compositeIndexes", [])

        logger.info(f"\n{'='*60}")
        logger.info(f"📦 Container: {container_name}")
        logger.info(f"   Partition Key: {pk_path}")
        logger.info(f"   Current composite indexes: {len(current_composites)}")
        logger.info(f"   New composite indexes:     {len(new_composites)}")

        if current_composites == new_composites:
            logger.info(f"   ✅ Already up to date — skipping")
            return

        if dry_run:
            logger.info(f"   🔍 [DRY RUN] Would update indexing policy:")
            logger.info(f"   {json.dumps(new_policy, indent=2)}")
            return

        # Apply the new policy
        database.replace_container(
            container=container_name,
            partition_key=PartitionKey(path=pk_path),
            indexing_policy=new_policy,
        )
        logger.info(f"   ✅ Updated successfully!")

    except Exception as e:
        logger.error(f"   ❌ Failed: {e}")


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("🔍 DRY RUN MODE — no changes will be applied\n")

    if not settings.COSMOS_ENDPOINT or not settings.COSMOS_KEY:
        logger.error("❌ COSMOS_ENDPOINT and COSMOS_KEY must be set")
        sys.exit(1)

    logger.info(f"Connecting to: {settings.COSMOS_ENDPOINT}")
    logger.info(f"Database: {settings.COSMOS_DATABASE}")

    client = CosmosClient(url=settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
    database = client.get_database_client(settings.COSMOS_DATABASE)

    for container_name, pk_path, policy in MIGRATIONS:
        apply_index_policy(database, container_name, pk_path, policy, dry_run)

    logger.info(f"\n{'='*60}")
    logger.info("Done!" if not dry_run else "Dry run complete — re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
