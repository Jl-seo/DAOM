"""
Migration Script: Add beta_features defaults to existing models
DEX Consulting Standard: Ensure all Model items have beta_features with proper defaults.

Usage:
    python -m app.scripts.migrate_beta_features

This script:
1. Scans all items in the 'models' container
2. For items missing beta_features or with incomplete flags:
   - Adds missing keys with default False values
   - Preserves existing True values (doesn't override)
3. Performs conditional update (only if changes needed)
"""
import asyncio
import logging
from typing import Dict, Any
from azure.cosmos import CosmosClient
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default beta features - must match schema default_beta_features()
DEFAULT_BETA_FEATURES = {
    "use_optimized_prompt": False,
    "use_virtual_excel_ocr": False
}


def merge_beta_features(existing: Dict[str, bool] | None) -> tuple[Dict[str, bool], bool]:
    """
    Merge existing beta_features with defaults.
    Returns (merged_dict, has_changes).
    Only adds missing keys, never overwrites existing True values.
    """
    if existing is None:
        return DEFAULT_BETA_FEATURES.copy(), True
    
    merged = existing.copy()
    has_changes = False
    
    for key, default_value in DEFAULT_BETA_FEATURES.items():
        if key not in merged:
            merged[key] = default_value
            has_changes = True
    
    return merged, has_changes


async def migrate_models():
    """
    Migrate all models in Cosmos DB to have proper beta_features.
    """
    logger.info("Starting beta_features migration...")
    
    # Initialize Cosmos client
    client = CosmosClient(settings.COSMOS_ENDPOINT, settings.COSMOS_KEY)
    database = client.get_database_client(settings.COSMOS_DATABASE)
    models_container = database.get_container_client("DocumentModels")
    
    # Track stats
    total = 0
    updated = 0
    skipped = 0
    errors = 0
    
    # Query all models
    query = "SELECT * FROM c"
    items = list(models_container.query_items(query=query, enable_cross_partition_query=True))
    
    logger.info(f"Found {len(items)} models to process")
    
    for item in items:
        total += 1
        model_id = item.get("id", "unknown")
        model_name = item.get("name", "unknown")
        
        try:
            existing_features = item.get("beta_features")
            merged_features, has_changes = merge_beta_features(existing_features)
            
            if not has_changes:
                logger.debug(f"[SKIP] {model_name} ({model_id}) - already has all beta_features")
                skipped += 1
                continue
            
            # Update the item
            item["beta_features"] = merged_features
            
            # Upsert (replace) the item
            models_container.upsert_item(item)
            
            logger.info(f"[UPDATED] {model_name} ({model_id}) - added missing beta_features")
            updated += 1
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to update {model_name} ({model_id}): {e}")
            errors += 1
    
    # Summary
    logger.info("=" * 50)
    logger.info("Migration Complete!")
    logger.info(f"  Total:   {total}")
    logger.info(f"  Updated: {updated}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"  Errors:  {errors}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(migrate_models())
