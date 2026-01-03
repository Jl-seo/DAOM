import os
import shutil
from abc import ABC, abstractmethod
from typing import BinaryIO
from fastapi import UploadFile
from app.core.config import settings

class FileStorage(ABC):
    @abstractmethod
    async def save_upload_file(self, file: UploadFile, filename: str) -> str:
        """Save UploadFile and return public/accessible URL"""
        pass

    @abstractmethod
    def get_file_url(self, filename: str) -> str:
        """Get public URL for a filename"""
        pass
    
    @abstractmethod
    def get_file_path(self, filename: str) -> str:
        """Get internal file path (if applicable)"""
        pass

class LocalFileStorage(FileStorage):
    def __init__(self, upload_dir: str = "temp_uploads"):
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_upload_file(self, file: UploadFile, filename: str) -> str:
        file_path = os.path.join(self.upload_dir, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return self.get_file_url(filename)

    def get_file_url(self, filename: str) -> str:
        # Assuming main.py mounts self.upload_dir at /static
        # In production with a real domain, this might need full URL
        return f"/static/{filename}"
    
    def get_file_path(self, filename: str) -> str:
        return os.path.join(self.upload_dir, filename)

class AzureBlobStorage(FileStorage):
    def __init__(self):
        # Initialize BlobServiceClient here if needed
        pass

    async def save_upload_file(self, file: UploadFile, filename: str) -> str:
        # Placeholder for Azure Blob implementation
        # Would upload and return SAS URL or Public URL
        raise NotImplementedError("Azure Blob Storage not yet fully implemented")

    def get_file_url(self, filename: str) -> str:
        # Placeholder
        return ""
    
    def get_file_path(self, filename: str) -> str:
        return filename

def get_file_storage() -> FileStorage:
    """Factory to get configured storage backend"""
    # Simple logic: if connection string exists, could use Blob.
    # For now, stick to Local as per 'Cleanup' phase, preparing the interface.
    return LocalFileStorage()
