from typing import Optional
from fastapi import UploadFile
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from app.core.config import settings
import uuid
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

        # Ensure container exists (Safety check)
        try:
            container_client = client.get_container_client(container_name)
            if not container_client.exists():
                logger.info(f"[Storage] Container '{container_name}' not found, creating...")
                container_client.create_container()
        except Exception as container_err:
             logger.warning(f"[Storage] Container check failed (non-fatal): {container_err}")

        # Fix DoS: Use streaming upload from SpooledTemporaryFile
        # file.file is the underlying Python file object
        try:
            file.file.seek(0)
        except Exception:
            pass # Seek might fail on some streams, ignore

        blob_client.upload_blob(file.file, overwrite=True)
        logger.info(f"[Storage] Uploaded blob: {blob_name}")
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

async def download_file_from_url(file_url: str) -> Optional[bytes]:
    """
    Download file content from a URL (Local or Azure Blob).
    Used to pass file stream to DocIntel when URL access is restricted.
    """
    client = get_blob_service_client()
    
    # 1. Local Fallback (for development)
    if not client:
        if "/static/" in file_url:
            from urllib.parse import unquote
            # Extract filename from local URL structure
            try:
                filename = unquote(file_url.split("/static/")[-1])
                local_path = TEMP_DIR / filename
                if local_path.exists():
                    with open(local_path, "rb") as f:
                        return f.read()
            except Exception as e:
                logger.error(f"[Storage] Local download failed: {e}")
        return None

    # 2. Azure Blob Storage
    try:
        container_name = settings.AZURE_CONTAINER_NAME
        # Verify URL belongs to our container
        if f"/{container_name}/" in file_url:
            from urllib.parse import unquote
            # Extract blob name after container/
            # Example: https://<account>.blob.core.windows.net/documents/folder/file.pdf
            blob_name = file_url.split(f"/{container_name}/", 1)[1]
            blob_name = unquote(blob_name)
            
            blob_client = client.get_blob_client(container=container_name, blob=blob_name)
            if blob_client.exists():
                return blob_client.download_blob().readall()
                
    except Exception as e:
        logger.error(f"[Storage] Blob download failed: {e}")
        
    return None

def generate_blob_sas_url(file_url: str, expiry_minutes: int = 60) -> str:
    """
    Generate a SAS URL for a private blob so external services (DocIntel) can access it.
    Parsing connection string manually to get AccountKey.
    """
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        return file_url

    try:
        # Parse connection string
        # Format: DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=...
        conn_str = settings.AZURE_STORAGE_CONNECTION_STRING
        creds = {item.split('=', 1)[0]: item.split('=', 1)[1] for item in conn_str.split(';') if '=' in item}
        
        account_name = creds.get('AccountName')
        account_key = creds.get('AccountKey')
        
        if not account_name or not account_key:
            logger.warning("[Storage] Could not parse AccountName/Key from connection string")
            return file_url
            
        container_name = settings.AZURE_CONTAINER_NAME
        
        # Check if URL belongs to our container
        if f"/{container_name}/" not in file_url:
            return file_url
            
        from urllib.parse import unquote
        # Extract blob name: https://<account>.blob.core.windows.net/<container>/<blob_name>
        blob_name = file_url.split(f"/{container_name}/", 1)[1]
        blob_name = unquote(blob_name)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        )
        
        # Append SAS token
        separator = "&" if "?" in file_url else "?"
        return f"{file_url}{separator}{sas_token}"
        
    except Exception as e:
        logger.error(f"[Storage] Failed to generate SAS: {e}")
        return file_url
