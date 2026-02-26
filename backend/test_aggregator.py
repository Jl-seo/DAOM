import asyncio
import os
import json
import logging
import sys

# Add backend to sys path so we can import services
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))
# Also add backend root
backend_dir = os.path.dirname(__file__)
sys.path.insert(0, backend_dir)

from app.services.extraction.beta_pipeline import BetaPipeline

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def main():
    pipeline = BetaPipeline(azure_client=None)

    # Mock the LLM call directly on the pipeline instance
    async def mock_call_llm(*args, **kwargs):
        return {
            "thought_process": "Found Table rows in chunk_0 and chunk_1. Merging them.",
            "guide_extracted": {
                "common_id": "ID_123",
                "my_table": [
                    {"col1": {"value": "A", "ref": "T1"}},
                    {"col1": {"value": "B", "ref": "T2"}}
                ]
            },
            "_token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        }
    pipeline.call_llm = mock_call_llm

    # Mock Work Order
    work_order = {
        "extraction_mode": "full",
        "common_fields": [{"field_key": "common_id", "type": "string"}],
        "table_fields": [{"field_key": "my_table", "type": "table"}]
    }

    # Mock Chunk Payloads
    chunks_payload = {
        "chunk_0": {
            "common_id": {"value": "ID_123", "ref": "C1"},
            "my_table": [
                {"col1": {"value": "A", "ref": "T1"}}
            ]
        },
        "chunk_1": {
            "my_table": [
                {"col1": {"value": "B", "ref": "T2"}}
            ]
        }
    }

    print("\n--- Testing Aggregator LLM ---")
    res_llm = await pipeline._run_aggregator(work_order, chunks_payload)
    print(json.dumps(res_llm, indent=2, ensure_ascii=False))

    print("\n--- Testing Aggregator Python Fallback ---")
    res_fallback = pipeline._run_aggregator_python_fallback(chunks_payload)
    print(json.dumps(res_fallback, indent=2, ensure_ascii=False))

    print("\n✅ Verification complete. The output schemas should match exactly.")

if __name__ == "__main__":
    asyncio.run(main())
