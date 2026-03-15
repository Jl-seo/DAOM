"""
Migration Script: Create reference_data Container in Cosmos DB

Creates the 'reference_data' container with partition key '/model_id'
and optimized indexing policy for dictionary lookup queries.

Usage:
    cd backend
    python3 -m app.scripts.migrate_reference_data [--dry-run]

Requires:
    COSMOS_ENDPOINT, COSMOS_KEY, COSMOS_DATABASE env vars (or .env file)
"""
import sys
import logging
from azure.cosmos import CosmosClient, PartitionKey

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")
from app.core.config import settings

CONTAINER_NAME = "reference_data"
PARTITION_KEY = "/model_id"

# Optimized indexing: only index fields used in WHERE/ORDER BY queries
INDEXING_POLICY = {
    "indexingMode": "consistent",
    "automatic": True,
    "includedPaths": [{"path": "/*"}],
    "excludedPaths": [
        {"path": "/aliases/*"},        # Array of strings — not queried directly
        {"path": "/extra/*"},          # Free-form extra fields
        {"path": '/"_etag"/?'},
    ],
    "compositeIndexes": [
        # Primary query: WHERE model_id AND category
        [
            {"path": "/model_id", "order": "ascending"},
            {"path": "/category", "order": "ascending"}
        ],
    ]
}


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

    logger.info(f"\n{'='*60}")
    logger.info(f"📦 Container: {CONTAINER_NAME}")
    logger.info(f"   Partition Key: {PARTITION_KEY}")

    # Check if container already exists
    existing = [c["id"] for c in database.list_containers()]
    
    if CONTAINER_NAME in existing:
        logger.info(f"   ⚠️  Container already exists")
        
        if dry_run:
            logger.info(f"   🔍 [DRY RUN] Would update indexing policy")
        else:
            # Update indexing policy on existing container
            try:
                database.replace_container(
                    container=CONTAINER_NAME,
                    partition_key=PartitionKey(path=PARTITION_KEY),
                    indexing_policy=INDEXING_POLICY,
                )
                logger.info(f"   ✅ Indexing policy updated!")
            except Exception as e:
                logger.error(f"   ❌ Update failed: {e}")
    else:
        if dry_run:
            logger.info(f"   🔍 [DRY RUN] Would create container")
        else:
            try:
                database.create_container(
                    id=CONTAINER_NAME,
                    partition_key=PartitionKey(path=PARTITION_KEY),
                    indexing_policy=INDEXING_POLICY,
                )
                logger.info(f"   ✅ Container created!")
            except Exception as e:
                logger.error(f"   ❌ Creation failed: {e}")

    logger.info(f"\n{'='*60}")
    logger.info("Done!" if not dry_run else "Dry run complete — re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
