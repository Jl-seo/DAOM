import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

class DummyPipeline(BetaPipeline):
    def __init__(self):
        self.semaphore = asyncio.Semaphore(20)
        
    async def call_llm(self, *args, **kwargs):
        return {"guide_extracted": {"my_table": []}, "_truncated": True}

async def test():
    pipe = DummyPipeline()
    ocr_data = {
        "_is_direct_markdown": True,
        "content": "| A | B |\n|---|---|\n" + "| 1 | 2 |\n" * 1000
    }
    class MockModel:
        name = "test"
        global_rules = ""
        reference_data = {}
        fields = []
        temperature = 0.0
    
    # We will just test the chunking static method for Excel's 150_000 chunk size
    # With 1000 rows, it's about 12,000 chars. 150_000 chunk size will NOT chunk it.
    chunks = pipe._chunk_with_headers(ocr_data["content"], 150_000)
    print(f"Total chunks generated: {len(chunks)}")
    
if __name__ == "__main__":
    asyncio.run(test())
