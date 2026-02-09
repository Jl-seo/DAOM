from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field

from app.schemas.model import ExtractionModel

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ExtractionResult(BaseModel):
    """
    Standardized Output Schema for ALL Extraction Modes.
    Ensures frontend consistency regardless of the underlying strategy.
    """
    # Main Data (Key-Value)
    guide_extracted: Dict[str, Any] = Field(default_factory=dict, description="Structured key-value pairs")
    
    # Table Data is NOW part of guide_extracted as List[Dict] values.
    # No separate table_rows / is_table fields anymore.
    
    # Raw Data (for debugging/fallback)
    raw_content: str = ""
    raw_tables: List[Any] = Field(default_factory=list)
    
    # Metadata
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    model_name: str = ""
    duration_seconds: float = 0.0
    
    # Beta Features Metadata
    beta_metadata: Dict[str, Any] = Field(default_factory=dict, description="parsed_content, ref_map, chunking_info etc.")
    
    # Designer-Engineer Pipeline
    work_order: Optional[Dict[str, Any]] = Field(default=None, description="Designer LLM output (work order for Engineer)")
    
    # Error Handling
    error: Optional[str] = None

class ExtractionPipeline(ABC):
    """
    Abstract Base Class for Extraction Strategies.
    Implementations: SingleShotPipeline, ChunkedPipeline, BetaLayoutPipeline
    """
    
    @abstractmethod
    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        """
        Execute the extraction logic and return a standardized result.
        """
        pass
    
    def normalize_bbox(self, bbox: List[float], page_width: int, page_height: int) -> List[float]:
        """Shared utility for coordinate normalization"""
        if not bbox or len(bbox) < 4: return None
        # ... logic ...
        return bbox # Placeholder
