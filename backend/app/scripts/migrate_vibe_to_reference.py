"""
Migrate vibe_dictionaries → reference_data (unified container).

Converts existing Vibe Dictionary entries into the unified schema:
  entry_type: "synonym"
  category: "vibe"

Usage:
    cd backend
    python3 -m app.scripts.migrate_vibe_to_reference --dry-run
    python3 -m app.scripts.migrate_vibe_to_reference
"""
import sys
import asyncio
import logging
import hashlib
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")


async def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("🔍 DRY RUN MODE\n")

    from app.db.cosmos import init_cosmos, get_vibe_dictionary_container, get_reference_data_container
    
    logger.info("⏳ Connecting to Cosmos DB...")
    await init_cosmos()

    vibe_container = get_vibe_dictionary_container()
    ref_container = get_reference_data_container()

    if not vibe_container:
        logger.error("❌ vibe_dictionaries container not found!")
        return
    if not ref_container:
        logger.error("❌ reference_data container not found!")
        return

    # 1. Read all vibe entries
    logger.info("📖 Reading vibe_dictionaries...")
    entries = []
    query = "SELECT * FROM c"
    async for item in vibe_container.query_items(query=query, enable_cross_partition_query=True):
        entries.append(item)

    logger.info(f"   Found {len(entries)} entries")

    if not entries:
        logger.info("✅ No entries to migrate.")
        return

    # 2. Convert to unified schema
    converted = []
    for item in entries:
        model_id = item.get("model_id", "__global__")
        field_name = item.get("field_name", "default")
        raw_val = item.get("raw_val", "")
        standard_val = item.get("value", "")

        if not raw_val or not standard_val:
            continue

        # Generate deterministic ID
        doc_id = hashlib.md5(
            f"{model_id}_synonym_{field_name}_{raw_val}".encode()
        ).hexdigest()

        doc = {
            "id": doc_id,
            "model_id": model_id,
            "category": "vibe",
            "entry_type": "synonym",
            "field_name": field_name,
            "raw_val": raw_val,
            "value": standard_val,
            "standard_code": standard_val,
            "standard_label": raw_val,
            "aliases": [raw_val.lower()],
            "source": item.get("source", "MANUAL"),
            "is_verified": item.get("is_verified", False),
            "hit_count": item.get("hit_count", 0),
            "extra": {},
            "created_at": item.get("created_at", datetime.utcnow().isoformat())
        }
        converted.append(doc)

    logger.info(f"\n📊 Converted: {len(converted)} entries")
    
    # Show samples
    for doc in converted[:3]:
        logger.info(f"   [{doc['model_id'][:8]}] {doc['field_name']}: '{doc['raw_val']}' → '{doc['value']}' ({doc['source']})")

    if dry_run:
        logger.info(f"\n🔍 DRY RUN — re-run without --dry-run to migrate.")
        return

    # 3. Upsert into reference_data
    logger.info(f"\n📤 Migrating {len(converted)} entries → reference_data...")
    ok = 0
    for doc in converted:
        try:
            await ref_container.upsert_item(body=doc)
            ok += 1
        except Exception as e:
            logger.error(f"   ❌ {doc['raw_val']}: {e}")

    logger.info(f"\n✅ Done! {ok}/{len(converted)} migrated to reference_data")
    logger.info("   Original vibe_dictionaries container preserved (rollback safe)")


if __name__ == "__main__":
    asyncio.run(main())
