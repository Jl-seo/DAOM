import asyncio
import json
from app.db.cosmos import init_cosmos, get_extractions_container, get_models_container
from app.services.masking import _get_pii_paths

async def main():
    await init_cosmos()
    
    container = get_extractions_container()
    m_container = get_models_container()
    
    if not container or not m_container:
        print("Containers not initialized.")
        return

    query = "SELECT TOP 1 * FROM c WHERE is_defined(c.extracted_data) ORDER BY c.created_at DESC"
    items = container.query_items(query=query, enable_cross_partition_query=True)
    logs = [item async for item in items]
    
    if not logs:
        print("No logs found.")
        return
        
    log = logs[0]
    model_id = log.get("model_id")
    
    m_query = f"SELECT * FROM c WHERE c.id = '{model_id}'"
    m_items = m_container.query_items(query=m_query, enable_cross_partition_query=True)
    models = [item async for item in m_items]
    
    if models:
        model = models[0]
        from app.schemas.model import _BaseExtractionModel
        m_obj = _BaseExtractionModel(**model)
        
        print(f"Log ID: {log['id']}")
        print(f"Model ID: {model_id}")
        
        pii = _get_pii_paths(m_obj)
        print("PII Paths expected:", pii)
        
        ex_data = log.get("extracted_data")
        print("\nLog Extracted Data keys:", ex_data.keys() if ex_data else None)
        if "other_data" in (ex_data or {}):
            print("Extracted Data HAS other_data!")
            
        pr_data = log.get("preview_data")
        print("\nLog Preview Data keys:", pr_data.keys() if pr_data else None)
        if "other_data" in (pr_data or {}):
            print("Preview Data HAS other_data!")

if __name__ == "__main__":
    asyncio.run(main())
