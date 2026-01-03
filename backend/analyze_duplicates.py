"""
Script to analyze and clean duplicate extraction logs
"""
import sys
sys.path.insert(0, '/Users/seojeonglee/.gemini/antigravity/scratch/daom/backend')

from app.services.extraction_logs import get_logs_by_model, get_all_logs
from collections import defaultdict

# Get all logs
logs = get_all_logs(limit=200)

print(f"Total logs: {len(logs)}")
print()

# Group by filename to find duplicates
by_file = defaultdict(list)
for log in logs:
    by_file[log.filename].append(log)

# Show duplicates
print("=== Potential Duplicates (same filename) ===")
for filename, file_logs in by_file.items():
    if len(file_logs) > 1:
        print(f"\n{filename}: {len(file_logs)} records")
        for log in file_logs:
            print(f"  ID: {log.id[:16]}... | Status: {log.status:12} | Created: {log.created_at[:19]}")
