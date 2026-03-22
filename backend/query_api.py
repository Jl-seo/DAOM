import asyncio
import json
import httpx

async def get_latest_log_from_api():
    # We found OOCL earlier, but let's query the jobs endpoint to get the ID for Maersk if possible,
    # or just any log from DB. Actually let's use the db to get the log ID then hit API
    import os
    from azure.cosmos import CosmosClient
    from dotenv import load_dotenv

    load_dotenv()
    endpoint = os.environ.get("AZURE_COSMOS_DB_ENDPOINT")
    key = os.environ.get("AZURE_COSMOS_DB_KEY")
    db_name = os.environ.get("AZURE_COSMOS_DB_DATABASE", "DaomDB")

    client = CosmosClient(endpoint, key)
    db = client.get_database_client(db_name)
    container = db.get_container_client("extraction_logs")
    
    query = "SELECT TOP 1 * FROM c WHERE (c.model_name = 'OOCL_INV' OR c.model_name = '머스크' OR CONTAINS(c.model_name, 'Maersk')) ORDER BY c._ts DESC"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    if not items:
        print("No logs in DB.")
        return
        
    log_id = items[0]["id"]
    model_id = items[0]["model_id"]
    print(f"Testing API for log ID: {log_id}")
    
    async with httpx.AsyncClient() as hc:
        res = await hc.get(f"http://localhost:8000/api/v1/extraction/logs/{log_id}?model_id={model_id}", timeout=60.0)
        
        if res.status_code == 200:
            data = res.json()
            # print(data)
            has_preview = "preview_data" in data and data["preview_data"] is not None
            has_raw = has_preview and "raw_extracted" in data["preview_data"]
            has_guide = has_preview and "guide_extracted" in data["preview_data"]
            
            print(f"Has preview_data: {has_preview}")
            if has_preview:
                preview = data["preview_data"]
                print(f"guide_extracted type: {type(preview.get('guide_extracted'))}")
                if type(preview.get("guide_extracted")) is dict:
                    print(f"Keys in guide_extracted: {list(preview['guide_extracted'].keys())[:10]}")
                    if "source" in preview["guide_extracted"]:
                        print(f"guide_extracted is BLOB OFFOLOAD format: {preview['guide_extracted']}")
                
                print(f"raw_extracted type: {type(preview.get('raw_extracted'))}")
                
            with open("api_response.json", "w") as f:
                json.dump(data, f, indent=2)
            print("Response saved to api_response.json")
        else:
            print(f"Failed to fetch API. Status Code: {res.status_code}, Body: {res.text}")

if __name__ == "__main__":
    asyncio.run(get_latest_log_from_api())
