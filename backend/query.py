import json
import os
from azure.cosmos import CosmosClient
from dotenv import load_dotenv

load_dotenv()
endpoint = os.environ.get("AZURE_COSMOS_DB_ENDPOINT")
key = os.environ.get("AZURE_COSMOS_DB_KEY")
db_name = os.environ.get("AZURE_COSMOS_DB_DATABASE", "DaomDB")

def main():
    client = CosmosClient(endpoint, key)
    db = client.get_database_client(db_name)
    container = db.get_container_client("extraction_logs")
    
    query = "SELECT TOP 1 * FROM c WHERE (c.model_name = 'OOCL_INV' OR c.model_name = '머스크' OR CONTAINS(c.model_name, 'Maersk')) ORDER BY c._ts DESC"
    try:
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        if items:
            with open("latest_log.json", "w") as f:
                json.dump(items[0], f, indent=2)
            print(f"Saved to latest_log.json (log ID: {items[0].get('id')})")
        else:
            print("No items found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
