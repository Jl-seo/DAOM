import os
from typing import Optional
from fastapi import UploadFile
from azure.storage.blob import BlobServiceClient
from app.core.config import settings
import uuid

def get_blob_service_client():
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        return None
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)

async def upload_file_to_blob(file: UploadFile) -> str:
    client = get_blob_service_client()
    
    # Mock behavior if client is not configured
    if not client:
        # Save locally for testing if no azure credentials
        os.makedirs("temp_uploads", exist_ok=True)
        filename = f"{uuid.uuid4()}_{file.filename}"
        local_path = f"temp_uploads/{filename}"
        with open(local_path, "wb") as f:
            content = await file.read()
            f.write(content)
        # Return a fake URL or simple path that the doc intel mock might need to handle?
        # Actually doc intel needs a public URL. 
        # For local dev without azure, we might struggle unless we tunnel.
        # But we will assume the user will configure it.
        return f"{settings.API_BASE_URL}/static/{filename}" 

    try:
        container_name = settings.AZURE_CONTAINER_NAME
        blob_name = f"{uuid.uuid4()}_{file.filename}"
        blob_client = client.get_blob_client(container=container_name, blob=blob_name)

        content = await file.read()
        blob_client.upload_blob(content)
        return blob_client.url

    except Exception as e:
        print(f"[Storage] Error uploading to blob: {e}")
        raise e
async def save_json_as_blob(data: dict, filename: str) -> Optional[str]:
    """Save JSON data to a blob"""
    import json
    client = get_blob_service_client()
    if not client:
        # Local fallback
        try:
            os.makedirs("temp_uploads/cache", exist_ok=True)
            local_path = f"temp_uploads/cache/{filename}"
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return local_path
        except Exception as e:
            print(f"[Storage] Local cache save failed: {e}")
            return None

    try:
        container_name = settings.AZURE_CONTAINER_NAME
        blob_client = client.get_blob_client(container=container_name, blob=filename)
        blob_client.upload_blob(json.dumps(data), overwrite=True)
        return blob_client.url
    except Exception as e:
        print(f"[Storage] Failed to save JSON blob: {e}")
        return None

async def load_json_from_blob(filename: str) -> Optional[dict]:
    """Load JSON data from a blob"""
    import json
    client = get_blob_service_client()
    if not client:
        # Local fallback
        try:
            local_path = f"temp_uploads/cache/{filename}"
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return None

    try:
        container_name = settings.AZURE_CONTAINER_NAME
        blob_client = client.get_blob_client(container=container_name, blob=filename)
        if not blob_client.exists():
            return None
            
        stream = blob_client.download_blob()
        data = stream.readall()
        return json.loads(data)
    except Exception as e:
        # Don't spam logs for cache miss
        return None
