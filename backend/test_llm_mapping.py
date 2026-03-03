import asyncio
import os
import json
from azure.cosmos import CosmosClient
from app.core.config import settings
from app.services.storage import load_json_from_blob
from app.services.extraction.sql_extraction import _run_schema_mapper
from app.schemas.model import ExtractionModel

async def main():
    client = CosmosClient(settings.COSMOS_ENDPOINT, settings.COSMOS_KEY)
    db = client.get_database_client(settings.COSMOS_DATABASE)
    container = db.get_container_client("ExtractedData")
    
    # Get the specific Excel/CSV file with the bad mapping
    query = "SELECT TOP 1 * from c WHERE CONTAINS(c.filename, '.xls') OR CONTAINS(c.filename, '.csv') ORDER BY c.created_at DESC"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    
    if not items:
        print("No items found.")
        return
        
    item = items[0]
    print(f"File: {item.get('filename')}")
    
    # 1. Fetch Schema Model (we need the actual schema definition)
    model_id = item.get('model_id')
    model_container = db.get_container_client("DocumentModels")
    m_items = list(model_container.query_items(query=f"SELECT * FROM c WHERE c.id='{model_id}'", enable_cross_partition_query=True))
    model_dict = m_items[0] if m_items else None
    
    if not model_dict:
        print("Model not found in DB!")
        return
    model = ExtractionModel(**model_dict)
    
    # 2. Fetch Raw Content (Markdown form)
    pd_data = item.get("preview_data", {})
    md_source = pd_data.get("raw_content", {})
    
    if isinstance(md_source, dict) and md_source.get("source") == "blob_storage":
        blob_path = md_source.get("blob_path")
        print(f"Downloading from Blob: {blob_path}")
        # Need to use the async compatible version inside sync env, or just use the storage.py function which is now a sync wrapper
        import urllib.request
        # Actually storage.py does not need API, it uses Azure Blob. Let's just use load_json_from_blob
        raw_json_list = await load_json_from_blob(blob_path)
        if isinstance(raw_json_list, list) and len(raw_json_list) > 0 and "content" in raw_json_list[0]:
            md_content = "\n\n".join([str(s.get("content", "")) for s in raw_json_list])
        else:
            md_content = str(raw_json_list)
    else:
        md_content = str(md_source)

    print("\n=== Fetched Markdown Snippet (Headers & Data) ===")
    lines = md_content.split('\n')
    for line in lines:
        if line.startswith('| 42 |') or line.startswith('| 43 |') or line.startswith('| 41 |') or line.startswith('| 40 |') or line.startswith('| 44 |'):
            print(line)
    
    # 3. Re-run identical Schema Mapper simulation on actual payload
    print("\n\n=== RUNNING SCHEMA MAPPER (OPENAI) ===")
    result = await _run_schema_mapper(md_content, model)
    print("\n=== LLM OUTPUT ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
