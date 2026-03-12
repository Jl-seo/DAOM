import asyncio
import traceback
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.extraction.beta_pipeline import BetaPipeline
from app.schemas.model import ExtractionModel, FieldSchema
import json

async def test():
    model = ExtractionModel(
        id="test-123",
        name="Test",
        document_type="receipt",
        fields=[
            FieldSchema(key="total", type="string", label="Total"),
            FieldSchema(key="items", type="list", label="Items", sub_fields=[
                FieldSchema(key="name", type="string"),
                FieldSchema(key="price", type="number")
            ])
        ],
        prompts={"designer": "system prompt", "engineer": "system prompt"},
        beta_features={"use_optimized_prompt": True}
    )
    
    ocr_data = {
        "content": "Total: $100.00\n" + "\n".join([f"Item {i} | ${i}.00" for i in range(100)]),
        "pages": [{"page_number": 1, "width": 800, "height": 600}],
        "paragraphs": []
    }
    
    class MockClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*args, **kwargs):
                    class MockChoice:
                        class MockMessage:
                            content = json.dumps({
                                "guide_extracted": {
                                    "total": {"value": "$100.00", "confidence": 0.9},
                                    "items": [{"name": {"value": "Item 1", "confidence": 0.9}, "price": {"value": 1.0, "confidence": 0.9}}] * 3 # Only 3 rows!
                                }, 
                                "_token_usage": {"total_tokens": 10}
                            })
                        message = MockMessage()
                        finish_reason = "stop" # LLM gets lazy and stops completely
                    class MockResponse:
                        choices = [MockChoice()]
                        class Usage:
                            prompt_tokens = 10
                            completion_tokens = 10
                            total_tokens = 20
                        usage = Usage()
                    return MockResponse()
    
    pipeline = BetaPipeline(MockClient())
    
    pipeline._run_designer = lambda m: asyncio.Future()
    pipeline._run_designer.get_loop = asyncio.get_running_loop
    f1 = asyncio.Future()
    f1.set_result(json.dumps({"work_order": {"table_fields": [{"key": "items"}]}}))
    pipeline._run_designer = lambda m: f1

    try:
        res = await pipeline.execute(model, ocr_data)
        print("Extracted Items Count:", len(res.guide_extracted.get("items", [])))
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
