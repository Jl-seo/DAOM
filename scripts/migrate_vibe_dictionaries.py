#!/usr/bin/env python3
import sys
import os
import uuid
from typing import Dict, Any

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from azure.cosmos import CosmosClient
from app.core.config import settings
import json

def migrate_vibe_dictionaries():
    """
    Migrate existing reference_data from the DocumentModels container
    into the new standalone vibe_dictionaries container.
    """
    if not settings.COSMOS_ENDPOINT or not settings.COSMOS_KEY:
        print("Cosmos DB credentials missing in env.")
        return

    print("Connecting to Cosmos DB...")
    client = CosmosClient(url=settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
    database = client.get_database_client(settings.COSMOS_DATABASE)
    
    # Get container clients (sync)
    models_container = database.get_container_client("DocumentModels")

    # Create the new container if it doesn't exist
    print("Ensuring vibe_dictionaries container exists...")
    try:
        vibe_container = database.create_container_if_not_exists(
            id="vibe_dictionaries",
            partition_key={"paths": ["/model_id"], "kind": "Hash"},
            indexing_policy={
               "indexingMode": "consistent",
               "automatic": True,
               "includedPaths": [{"path": "/*"}],
               "excludedPaths": [{"path": '/"_etag"/?'}]
            }
        )
    except Exception as e:
        print(f"Failed to create/get container: {e}")
        vibe_container = database.get_container_client("vibe_dictionaries")

    print("Fetching active extraction models...")
    query = "SELECT c.id, c.name, c.reference_data FROM c WHERE c.model_type = 'extraction' AND c.is_active = true"
    
    try:
        models = list(models_container.query_items(query=query, enable_cross_partition_query=True))
    except Exception as e:
        print(f"Failed to query models: {e}")
        return

    migrated_count = 0
    
    for model in models:
        model_id = model.get("id")
        ref_data = model.get("reference_data")
        
        if not ref_data or not isinstance(ref_data, dict):
            continue
            
        print(f"Processing model: {model.get('name')} ({model_id})")
        
        for field_name, mappings in ref_data.items():
            if not isinstance(mappings, dict):
                continue
                
            for raw_val, data in mappings.items():
                if isinstance(data, dict):
                    # Has existing VibeDictionary structure
                    doc = {
                        "id": str(uuid.uuid4()),
                        "model_id": model_id,
                        "field_name": field_name,
                        "raw_val": raw_val,
                        "value": data.get("value", ""),
                        "source": data.get("source", "MANUAL"),
                        "is_verified": data.get("is_verified", True),
                        "hit_count": data.get("hit_count", 1)
                    }
                else:
                    # Legacy flat string mapping
                    doc = {
                        "id": str(uuid.uuid4()),
                        "model_id": model_id,
                        "field_name": field_name,
                        "raw_val": raw_val,
                        "value": str(data),
                        "source": "MIGRATION",
                        "is_verified": True,
                        "hit_count": 1
                    }
                    
                # Insert into new container
                try:
                    vibe_container.upsert_item(doc)
                    migrated_count += 1
                except Exception as e:
                    print(f"Failed to insert doc {doc}: {e}")

    print(f"Migration complete. Total {migrated_count} dictionary entries migrated to vibe_dictionaries container.")
    # Note: We are NOT deleting the old reference_data from DocumentModels yet for safe revert.

if __name__ == "__main__":
    migrate_vibe_dictionaries()
