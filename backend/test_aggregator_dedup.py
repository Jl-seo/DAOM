import sys, os, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

pipe = BetaPipeline(None)

payload = {
    "chunk_0": {
        "my_table": [
            {"col1": {"value": "row 1"}, "col2": {"value": "A"}},
            {"col1": {"value": "row 2"}, "col2": {"value": "B"}}
        ]
    },
    "chunk_1": {
        "my_table": [
            {"col1": {"value": "row 3"}, "col2": {"value": "C"}},
            {"col1": {"value": "row 4"}, "col2": {"value": "D"}}
        ]
    },
    "chunk_2": {
        "my_table": [
            {"col1": {"value": "row 2"}, "col2": {"value": "B"}}, # Duplicate from chunk 0
            {"col1": {"value": "row 5"}, "col2": {"value": "E"}}
        ]
    }
}

res = pipe._run_aggregator_python_fallback(payload)
print(json.dumps(res["guide_extracted"], indent=2))
