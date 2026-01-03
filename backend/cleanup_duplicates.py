"""
Cleanup script: Keep only 1 record per file_url (prefer confirmed > success > others)
"""
import sys
sys.path.insert(0, '/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend')

from app.db.cosmos import get_extractions_container
from collections import defaultdict

container = get_extractions_container()
items = list(container.query_items('SELECT * FROM c', enable_cross_partition_query=True))

# Group by file_url
by_url = defaultdict(list)
for item in items:
    url = item.get('file_url', '')
    if url:
        by_url[url].append(item)

# Priority: confirmed > success > preview_ready > others
def priority(status):
    order = ['confirmed', 'success', 'preview_ready', 'error', 'P100', 'P200', 'P300', 'P400', 'P500']
    try:
        return order.index(status)
    except ValueError:
        return 99

to_delete = []
for url, records in by_url.items():
    if len(records) > 1:
        # Sort by priority, then by created_at (latest first)
        records.sort(key=lambda r: (priority(r['status']), r.get('created_at', '')))
        records.reverse()  # Best first
        # Keep first (best), delete rest
        for r in records[1:]:
            to_delete.append((r['id'], r['model_id']))

print(f"Records to delete: {len(to_delete)}")
print("\nDeleting...")

deleted = 0
for item_id, model_id in to_delete:
    try:
        container.delete_item(item=item_id, partition_key=model_id)
        deleted += 1
        print(f"  Deleted: {item_id[:12]}...")
    except Exception as e:
        print(f"  Failed to delete {item_id[:12]}: {e}")

print(f"\n=== Done! Deleted {deleted} duplicate records ===")
