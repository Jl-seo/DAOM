"""
Bulk delete extraction logs
"""
from typing import List

def delete_logs(log_ids: List[str]) -> int:
    """Delete multiple extraction logs by IDs"""
    container = get_extractions_container()
    
    if not container:
        return 0
    
    deleted_count = 0
    for log_id in log_ids:
        try:
            # Get the log first to get the partition key (model_id)
            log = get_log(log_id)
            if log:
                container.delete_item(item=log_id, partition_key=log.model_id)
                deleted_count += 1
                logger.info(f"[ExtractionLogs] Deleted log {log_id}")
        except Exception as e:
            logger.error(f"[ExtractionLogs] Failed to delete log {log_id}: {e}")
    
    return deleted_count
