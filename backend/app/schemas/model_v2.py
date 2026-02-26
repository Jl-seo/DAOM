from typing import Optional
from pydantic import ConfigDict
from app.schemas.model import ExtractionModel, ExtractionModelCreate


class VersionedExtractionModel(ExtractionModel):
    """
    V2 Extended Model Schema for DAOM Platform Renovation.
    Inherits all base fields from ExtractionModel but adds versioning & publishing metadata
    without breaking the legacy schema.
    """
    model_config = ConfigDict(extra="ignore")

    # --- Model Versioning & Publishing ---
    version: str = "v1.0.0"
    status: str = "PUBLISHED"  # ENUM: "DRAFT", "TESTING", "PUBLISHED", "ARCHIVED"
    parent_model_id: Optional[str] = None
    published_at: Optional[str] = None
    changelog: Optional[str] = None


class VersionedExtractionModelCreate(ExtractionModelCreate):
    """
    V2 Extended Create Schema.
    """
    model_config = ConfigDict(extra="ignore")

    # --- Model Versioning & Publishing ---
    version: Optional[str] = "v1.0.0"
    status: Optional[str] = "DRAFT"  # New models default to DRAFT
    parent_model_id: Optional[str] = None
    published_at: Optional[str] = None
    changelog: Optional[str] = None
