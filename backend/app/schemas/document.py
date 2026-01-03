from pydantic import BaseModel
from typing import Optional, Dict, Any

class DocumentUploadResponse(BaseModel):
    filename: str
    url: str
    message: str

class AnalysisRequest(BaseModel):
    file_url: str
    language: str = "en"
    model_id: Optional[str] = None

class AnalysisResponse(BaseModel):
    status: str
    extracted_text: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
