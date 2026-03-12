import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

async def mock_call_llm(*args, **kwargs):
    print("MOCK LLM CALLED")
    return {"guide_extracted": {"my_table": [{"val": 1}]}, "_truncated": True} # Force truncation

class DummyPipeline(BetaPipeline):
    def __init__(self):
        self.semaphore = asyncio.Semaphore(20)
    async def call_llm(self, *args, **kwargs):
        return await mock_call_llm(*args, **kwargs)
        
    async def _run_designer(self, *args, **kwargs):
        return {"work_order": {"table_fields": [{"key": "my_table"}], "common_fields": []}}

async def test():
    pipe = DummyPipeline()
    
    ocr_data = {
        "_is_direct_markdown": True,
        "content": "| A | B |\n|---|---|\n" + "| 1 | 2 |\n" * 10
    }
    class MockModel:
        name = "test"
        global_rules = ""
        reference_data = {}
        fields = []
        temperature = 0.0
    
    try:
        await pipe.execute(MockModel(), ocr_data)
        print("EXECUTE COMPLETED")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
