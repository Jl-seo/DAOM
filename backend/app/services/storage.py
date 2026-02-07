import os
from typing import Optional
from fastapi import UploadFile
from azure.storage.blob import BlobServiceClient
from app.core.config import settings
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve absolute path to backend root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_uploads"

def get_blob_service_client():
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        return None
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)

async def upload_file_to_blob(file: UploadFile) -> str:
    client = get_blob_service_client()
    
    # Mock behavior if client is not configured
    if not client:
        # Save locally for testing if no azure credentials
        # Use absolute path
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}_{file.filename}"
        local_path = TEMP_DIR / filename
        
        with open(local_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return f"{settings.API_BASE_URL}/static/{filename}" 

    try:
        container_name = settings.AZURE_CONTAINER_NAME
        blob_name = f"{uuid.uuid4()}_{file.filename}"
        blob_client = client.get_blob_client(container=container_name, blob=blob_name)

        # Fix DoS: Use streaming upload from SpooledTemporaryFile
        # file.file is the underlying Python file object
        blob_client.upload_blob(file.file, overwrite=True)
        return blob_client.url

    except Exception as e:
        logger.info(f"[Storage] Error uploading to blob: {e}")
        raise e

async def save_json_as_blob(data: dict, filename: str) -> Optional[str]:
    """Save JSON data to a blob"""
    import json
    client = get_blob_service_client()
    if not client:
        # Local fallback
        try:
            cache_dir = TEMP_DIR / "cache"
            local_path = cache_dir / filename
            # Ensure nested directories exist
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return str(local_path)
        except Exception as e:
            logger.info(f"[Storage] Local cache save failed: {e}")
            return None

    try:
        container_name = settings.AZURE_CONTAINER_NAME
        blob_client = client.get_blob_client(container=container_name, blob=filename)

        # Ensure container exists
        container_client = client.get_container_client(container_name)
        if not container_client.exists():
            try:
                container_client.create_container()
            except Exception:
                pass # Already created by another process

        blob_client.upload_blob(json.dumps(data), overwrite=True)
        return blob_client.url
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Storage] Cloud Blob Upload Failed: {e}")
        return None

async def load_json_from_blob(filename: str) -> Optional[dict]:
    """Load JSON data from a blob"""
    import json
    client = get_blob_service_client()
    if not client:
        # Local fallback
        try:
            cache_dir = TEMP_DIR / "cache"
            # Filename is relative as passed from extraction_service
            local_path = cache_dir / filename
            if local_path.exists():
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            # Log at debug level for cache miss (expected behavior)
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
