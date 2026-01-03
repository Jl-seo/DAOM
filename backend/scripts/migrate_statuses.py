"""
Migration script to update all legacy status codes to P-series codes
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.cosmos import get_extractions_container
from app.core.enums import ExtractionStatus

# Status migration mapping
STATUS_MIGRATION = {
    'pending': ExtractionStatus.PENDING.value,           # P100
    'uploading': ExtractionStatus.UPLOADING.value,       # P200
    'analyzing': ExtractionStatus.ANALYZING.value,       # P300
    'refining': ExtractionStatus.REFINING.value,         # P400
    'preview_ready': ExtractionStatus.PREVIEW_READY.value,  # P500
    'success': ExtractionStatus.SUCCESS.value,           # S100
    'confirmed': ExtractionStatus.CONFIRMED.value,       # S200
    'error': ExtractionStatus.ERROR.value,               # E200
    'failed': ExtractionStatus.FAILED.value,             # E100
}

def migrate_statuses():
    container = get_extractions_container()
    if not container:
        print("ERROR: Could not connect to Cosmos DB")
        return
    
    # Query all items
    query = "SELECT * FROM c"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    
    migrated = 0
    skipped = 0
    
    for item in items:
        old_status = item.get('status', '')
        
        # Check if status needs migration
        if old_status in STATUS_MIGRATION:
            new_status = STATUS_MIGRATION[old_status]
            item['status'] = new_status
            
            try:
                container.upsert_item(item)
                print(f"✅ Migrated {item['id'][:8]}: {old_status} -> {new_status}")
                migrated += 1
            except Exception as e:
                print(f"❌ Failed {item['id'][:8]}: {e}")
        else:
            skipped += 1
    
    print(f"\n=== Migration Complete ===")
    print(f"Migrated: {migrated}")
    print(f"Skipped (already migrated): {skipped}")
    print(f"Total: {len(items)}")

if __name__ == "__main__":
    migrate_statuses()
