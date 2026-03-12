import asyncio
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.rule_engine import RuleEngine

# Mock dictionary service
class MockDictService:
    is_available = True
    async def search(self, *args, **kwargs):
        class Match:
            code = "123"
            score = 0.9
            category = "test"
        return [Match()]

# Override dependency injection
import app.services.dictionary_service as ds
ds.get_dictionary_service = lambda: MockDictService()

async def test():
    engine = RuleEngine()
    
    # Create a massive mock extracted guide
    # Simulating 50 rows, 26 columns = 1300 cells
    rows = []
    for _ in range(50):
        row = {}
        for c in range(26):
            row[f"col_{c}"] = {"value": f"text_{c}"}
        rows.append(row)
        
    raw_result = {
        "guide_extracted": {
            "massive_table": rows
        }
    }
    
    # Mock fields with dictionary mappings
    class MockField:
        def __init__(self, key, dictionary=None, sub_fields=None):
            self.key = key
            self.dictionary = dictionary
            self.sub_fields = sub_fields
            
    fields = [
        MockField("massive_table", sub_fields=[
            {"key": f"col_{c}", "dictionary": "some_dict"} for c in range(26)
        ])
    ]
    
    print("Starting RuleEngine normalization...")
    try:
        res = await asyncio.wait_for(
            engine.apply_dictionary_normalization(raw_result, "test_model", ["some_dict"], fields), 
            timeout=5.0
        )
        print("COMPLETED INSTANTLY")
    except asyncio.TimeoutError:
        print("HANG DETECTED: Timeout after 5 seconds")

if __name__ == "__main__":
    asyncio.run(test())
