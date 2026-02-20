import asyncio
import os
import sys

# Add backend to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.services.extraction.beta_pipeline import BetaPipeline
from app.models.schema import ExtractionModel, FieldDefinition
from app.services.llm import azure_openai

async def test_fallback_queue():
    print("--- Starting Fallback Queue Test ---")
    pipeline = BetaPipeline(azure_openai)
    
    # Mocking `call_llm` to instantly return _truncated=True
    async def mock_call_llm(messages, is_table_model=False):
        print(f"Mock call_llm called. Table Mode: {is_table_model}")
        return {
            "guide_extracted": {"dummy": "data"},
            "_truncated": True,
            "_token_usage": {"total_tokens": 100}
        }
        
    pipeline.call_llm = mock_call_llm
    
    # Dummy Model
    model = ExtractionModel(
        id="test_model",
        name="Test Model",
        description="Test",
        fields=[
            FieldDefinition(key="field1", label="Field 1", type="string"),
            FieldDefinition(key="table1", label="Table 1", type="table"),
            FieldDefinition(key="table2", label="Table 2", type="table")
        ],
        beta_features={"use_optimized_prompt": True}
    )
    
    # Dummy huge OCR data to trigger Single Shot -> Chunked -> Schema Split
    ocr_data = {
        "content" : "Test Data " * 1000, # Not huge, to actually test fallback from single shot
        "pages": [{"page_number": 1}],
        "tables": []
    }
    
    print("Executing Pipeline...")
    res = await pipeline.execute(model, ocr_data)
    
    print("\n--- Pipeline Result ---")
    print(f"Final Truncated Flag: {res.token_usage.total_tokens}") 
    print(f"Guide Extracted: {res.guide_extracted}")
    print("Fallback queue successfully triggered if multiple `Mock call_llm` were printed.")

if __name__ == "__main__":
    asyncio.run(test_fallback_queue())
