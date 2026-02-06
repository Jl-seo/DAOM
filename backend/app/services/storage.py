import os
from typing import Optional
from fastapi import UploadFile
from azure.storage.blob import BlobServiceClient
from app.core.config import settings
import uuid
from pathlib import Path

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

        content = await file.read()
        blob_client.upload_blob(content)
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

    """Load JSON data from a blob"""
    import json
    from urllib.parse import urlparse, unquote

    # Handle if filename is actually a full URL
    if filename.startswith("http"):
        try:
            parsed = urlparse(filename)
            # path is like /container/blobname
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) >= 2:
                # container = path_parts[0] # We rely on settings.AZURE_CONTAINER_NAME usually
                # But if the URL is from a different container, we might have issues.
                # For now, assume consistent container and just get the blob name
                filename = unquote(path_parts[1])
            elif "static" in parsed.path: # Local fallback URL
                 filename = unquote(parsed.path.split("/")[-1])
        except Exception:
            pass # Fallback to using it as is

    client = get_blob_service_client()
    if not client:
        # Local fallback
        try:
            cache_dir = TEMP_DIR / "cache"
            # Filename is relative as passed from extraction_service
            # If it was a URL, we tried to parse it to a filename above
            local_path = cache_dir / filename
            if local_path.exists():
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            
            # Additional fallback: check if it matches temp upload format in root temp dir
            # (In case it's not in cache/ but in temp_uploads/ directly)
            temp_path = TEMP_DIR / filename
            if temp_path.exists():
                 with open(temp_path, "r", encoding="utf-8") as f:
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
