import asyncio
import json
from app.services.extraction.rule_engine import rule_engine
from app.services.dictionary_service import get_dictionary_service

# Mock dictionary service search
async def mock_search(query, category, top_k=1):
    class MockMatch:
        def __init__(self, code, score, cat):
            self.code = code
            self.score = score
            self.category = cat
    
    # Simple hardcoded mock logic for testing
    if query.lower() == "busan" and category == "port":
        return [MockMatch("KRPUS", 0.95, "port")]
    elif query.lower() == "jebel ali" and category == "port":
        return [MockMatch("AEJEA", 0.98, "port")]
    return []

dict_service = get_dictionary_service()
dict_service.search = mock_search

async def test_engine():
    # 1. Test Normalization
    raw_data = {
        "guide_extracted": {
            "pol": {"value": "Busan", "confidence": 0.9},
            "pod": {"value": "Jebel Ali", "confidence": 0.8},
            "unknown_field": {"value": "Some Random Value", "confidence": 0.5},
            "shipping_charges": {"value": [
                {"charge_code": "THC", "container_no": "TEST1234567"},
                {"charge_code": "THC", "container_no": "TEST1234567"}, # Duplicate
                {"charge_code": "DOC", "container_no": "TEST1234567"}
            ], "confidence": 0.9}
        }
    }
    
    print("--- RAW DATA ---")
    print(json.dumps(raw_data, indent=2))
    
    # Mock Field Schema Mapping
    mock_fields = [
        type('MockField', (object,), {"key": "pol", "dictionary": "port"}),
        type('MockField', (object,), {"key": "pod", "dictionary": "port"}),
        type('MockField', (object,), {"key": "unknown_field"}),
    ]

    # Apply normalization with "port" dictionary active
    normalized_data = await rule_engine.apply_dictionary_normalization(
        raw_result=raw_data, 
        dictionaries=["port"],
        fields=mock_fields
    )
    
    print("\n--- AFTER NORMALIZATION ---")
    print(json.dumps(normalized_data, indent=2))
    
    # 2. Test Validation
    reference_data = {
        "unique_constraints": [
            {"target_array": "shipping_charges", "unique_keys": ["container_no", "charge_code"]}
        ]
    }
    
    validated_data = rule_engine.apply_validation_rules(
        normalized_result=normalized_data,
        reference_data=reference_data
    )
    
    print("\n--- AFTER VALIDATION ---")
    print(json.dumps(validated_data, indent=2))

if __name__ == "__main__":
    asyncio.run(test_engine())
