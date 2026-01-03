import os
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
        
        print(f"[Storage] Successfully uploaded blob: {blob_client.url}")
        return blob_client.url
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Storage] Error uploading to blob: {e}")
        raise e
