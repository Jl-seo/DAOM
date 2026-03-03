import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.model import ExtractionModel
from app.core.config import settings

logger = logging.getLogger(__name__)

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0

class PipelineResult(BaseModel):
    guide_extracted: List[Dict[str, Any]] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    error: Optional[str] = None
    other_data: Optional[List[Dict[str, Any]]] = None # To support key-value pairs (Beta compatibility)

class AdvancedTablePipeline:
    """
    [Experimental] Multi-Table Extraction Pipeline
    
    This pipeline is designed exclusively for documents that consist of multiple, structurally diverse tables
    (e.g., Complex Invoices, Bills of Lading).
    
    Instead of converting the document to a massive markdown string (which suffers from LLM context truncation
    and sequential zipper hallucinations), this pipeline takes the raw Azure Document Intelligence JSON `tables`
    and treats them like individual Excel spreadsheets.
    
    It re-uses the `_run_schema_mapper` deterministic concept:
    1. Reconstruct each table into a 2D JSON Grid.
    2. Prompt the AI with ONLY the table headers (first few rows) to map against our ExtractionModel fields.
    3. Use Python to deterministically sweep the data loop.
    """

    def __init__(self, azure_openai_client: Any):
        self.azure_openai = azure_openai_client
        self.total_tokens = TokenUsage()

    def _update_tokens(self, usage) -> None:
        """Helper to accumulate token usage from multiple LLM calls"""
        if not usage:
            return
        
        prompt = getattr(usage, "prompt_tokens", 0)
        comp = getattr(usage, "completion_tokens", 0)
        total = getattr(usage, "total_tokens", 0)
        
        self.total_tokens.prompt_tokens += prompt
        self.total_tokens.completion_tokens += comp
        self.total_tokens.total_tokens += total
        
        # GPT-4o pricing estimation
        p_cost = (prompt / 1000) * 0.005
        c_cost = (comp / 1000) * 0.015
        self.total_tokens.cost_estimate_usd += (p_cost + c_cost)

    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> PipelineResult:
        """
        Executes the Multi-Table Schema Mapping extraction strategy.
        """
        result = PipelineResult()
        
        try:
            logger.info(f"--- [Multi-Table Bypass] Starting Pipeline for {model.id} ---")
            
            # Step 1: Isolate Tables
            tables = ocr_data.get("tables", [])
            if not tables:
                logger.warning("[Multi-Table Bypass] No tables found in OCR data. LLM Mapping will skip.")
                result.error = "No tables detected in the document."
                return result
            
            logger.info(f"[Multi-Table Bypass] Processing {len(tables)} distinct tables.")
            
            # TODO: Implementation of Grid Conversion, Mapping, and Scraping
            # This is a structural skeleton. Future PRs will implement the core mapping logic here.
            
            # As a placeholder, we just return an empty success response
            # to verify routing works without crashing
            result.guide_extracted = []
            
            logger.info("--- [Multi-Table Bypass] Pipeline Completed ---")
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[Multi-Table Pipeline] Fatally failed: {e}\n{tb}")
            result.error = f"Pipeline Error: {str(e)}"
            
        return result
