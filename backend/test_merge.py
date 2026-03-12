import sys, os, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

class DummyClient:
    pass

pipeline = BetaPipeline(DummyClient())

chunks_payload = {
    "chunk_0": {
        "items": [
            {"col1": {"value": "A"}, "col2": {"value": 1}},
            {"col1": {"value": "B"}, "col2": {"value": 2}},
        ]
    },
    "chunk_1": {
        "items": [
            {"col1": {"value": "C"}, "col2": {"value": 3}},
            {"col1": {"value": "D"}, "col2": {"value": 4}},
        ]
    },
    "chunk_2": {
        "items": [
            {"col1": {"value": "E"}, "col2": {"value": 5}},
            {"col1": {"value": "A"}, "col2": {"value": 1}}, # Duplicate
        ]
    }
}

res = pipeline._run_aggregator_python_fallback(chunks_payload)
print(json.dumps(res, indent=2, ensure_ascii=False))
