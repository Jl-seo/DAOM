import asyncio
from app.services.extraction.post_processor import apply_post_processing

class DummyAction:
    def __init__(self, value):
        self.value = value

class DummyRule:
    def __init__(self, target_field, action):
        self.target_field = target_field
        self.action = DummyAction(action)

def test_subfield_post_processing():
    data = {
        "invoice_no": {"value": "INV-123", "confidence": 0.9},
        "items": {
            "value": [
                {
                    "item_code": {"value": "usd 100", "confidence": 0.9},
                    "description": {"value": "abc 123", "confidence": 0.9}
                },
                {
                    "item_code": {"value": "KRW 50000", "confidence": 0.9},
                    "description": {"value": "def 456", "confidence": 0.9}
                }
            ]
        }
    }
    
    rules = [
        DummyRule("items.item_code", "split_currency"),
        DummyRule("invoice_no", "uppercase"),
        DummyRule("items.description", "extract_digits")
    ]
    
    result = apply_post_processing(data, rules, [])
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_subfield_post_processing()
