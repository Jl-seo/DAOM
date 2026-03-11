import asyncio
import traceback
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.extraction.beta_pipeline import BetaPipeline
from app.schemas.model import ExtractionModel, ModelField
from openai import AsyncAzureOpenAI
import json

async def test():
    model = ExtractionModel(
        id="test-123",
        name="Test",
        document_type="receipt",
        fields=[ModelField(key="total", type="string", label="Total", description="", rules="", is_dex_target=False)],
        prompts={"designer": "system prompt", "engineer": "system prompt"},
        beta_features={"use_optimized_prompt": True}
    )
    
    ocr_data = {
        "content": "Total: $100.00",
        "pages": [{"page_number": 1, "width": 800, "height": 600}],
        "paragraphs": [{"content": "Total: $100.00", "boundingRegions": [{"pageNumber": 1}]}]
    }
    
    # Mocking Azure OpenAI Client
    class MockClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*args, **kwargs):
                    class MockChoice:
                        class MockMessage:
                            content = json.dumps({"guide_extracted": {"total": {"value": "$100.00", "confidence": 0.9}}, "_token_usage": {"total_tokens": 10}})
                        message = MockMessage()
                    class MockResponse:
                        choices = [MockChoice()]
                    return MockResponse()
    
    pipeline = BetaPipeline(MockClient())
    
    # Mock designer output
    pipeline._run_designer = lambda m: asyncio.Future()
    pipeline._run_designer.get_loop = asyncio.get_running_loop
    f1 = asyncio.Future()
    f1.set_result(json.dumps({"schema": {}}))
    pipeline._run_designer = lambda m: f1

    try:
        res = await pipeline.execute(model, ocr_data)
        print("SUCCESS:", res)
    except Exception as e:
        print("FAILED WITH EXCEPTION:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
