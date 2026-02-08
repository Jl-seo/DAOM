from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class OCRBoundingRegion(BaseModel):
    page_number: int
    polygon: List[float]

class OCRSpan(BaseModel):
    offset: int
    length: int

class OCRWord(BaseModel):
    content: str
    polygon: Optional[List[float]] = None
    confidence: Optional[float] = None
    span: Optional[OCRSpan] = None

class OCRLine(BaseModel):
    content: str
    polygon: Optional[List[float]] = None
    spans: Optional[List[OCRSpan]] = None

class OCRCell(BaseModel):
    row_index: int
    column_index: int
    content: str
    bounding_regions: Optional[List[OCRBoundingRegion]] = None
    spans: Optional[List[Dict[str, int]]] = None # Keep as dict for now to match raw output structure or strictly typed?
    # Let's use strict typing if possible, but Azure SDK returns dicts sometimes.
    # We'll stick to permissive types for spans as they are often just passed through.

class OCRTable(BaseModel):
    row_count: int
    column_count: int
    cells: List[OCRCell]
    bounding_regions: Optional[List[OCRBoundingRegion]] = None
    spans: Optional[List[Dict[str, int]]] = None

class OCRSelectionMark(BaseModel):
    state: str
    polygon: Optional[List[float]] = None

class OCRPage(BaseModel):
    page_number: int
    width: Optional[float] = None
    height: Optional[float] = None
    unit: Optional[str] = None
    words: List[OCRWord] = Field(default_factory=list)
    lines: List[OCRLine] = Field(default_factory=list)
    selection_marks: List[OCRSelectionMark] = Field(default_factory=list)
    spans: Optional[List[OCRSpan]] = None # Synthetic pages might have spans

class OCRResult(BaseModel):
    """Standardized OCR Output from Document Intelligence"""
    content: str
    model_id: Optional[str] = None
    api_version: Optional[str] = None
    pages: List[OCRPage] = Field(default_factory=list)
    paragraphs: List[Dict[str, Any]] = Field(default_factory=list) # Keep paragraphs flexible for now
    tables: List[OCRTable] = Field(default_factory=list)
    key_value_pairs: List[Dict[str, Any]] = Field(default_factory=list) # Flexible
    documents: List[Dict[str, Any]] = Field(default_factory=list) # Flexible high-level fields
    
    # Metadata
    _cache_blob_path: Optional[str] = None
