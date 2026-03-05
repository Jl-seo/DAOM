import asyncio
import os
import json
import logging
import pandas as pd
from app.services.extraction.sql_extraction import _normalize_headers_via_llm, _run_schema_mapper
from app.schemas.model import ExtractionModel, FieldDefinition
from app.core.config import settings
from unittest.mock import patch, MagicMock

logging.basicConfig(level=logging.INFO)

async def run_test():
    # 1. Mock ExtractionModel
    model = ExtractionModel(
        id="test-id",
        name="Test",
        fields=[
            FieldDefinition(key="rate_list", label="Rate List", type="table", sub_fields=[
                {"key": "pol", "label": "POL", "type": "string"},
                {"key": "pod", "label": "POD", "type": "string"},
                {"key": "20dc", "label": "20DC", "type": "number"},
                {"key": "40dc", "label": "40DC", "type": "number"}
            ])
        ]
    )
    
    # 2. Mock HTML Header
    html_content = """
    <table>
        <tr><th colspan="2">Ports</th><th colspan="2">Rates</th></tr>
        <tr><th>POL</th><th>POD</th><th>20DC</th><th>40DC</th></tr>
        <tr><td>PUSAN</td><td>USWC</td><td>1000</td><td>1500</td></tr>
    </table>
    """
    
    # Run the real Mapper
    print("--- Running Mapper LLM ---")
    os.environ["AZURE_OPENAI_API_KEY"] = settings.AZURE_OPENAI_API_KEY
    os.environ["AZURE_OPENAI_ENDPOINT"] = settings.AZURE_OPENAI_ENDPOINT
    
    mapped_headers = await _normalize_headers_via_llm(html_content, "gpt-4o-mini")
    print("Normalizer Output:", mapped_headers)
    
    # Run the real Extractor
    print("--- Running Extractor LLM ---")
    markdown_text = """
### Sheet: Schedule
| row_id | A | B | C | D |
|---|---|---|---|---|
| 0 | POL | POD | 20DC | 40DC |
| 1 | PUSAN | USWC | 1000 | 1500 |
"""
    mapping_plan = await _run_schema_mapper(markdown_text, mapped_headers, model, "gpt-4o")
    print("Mapping Plan Output:")
    print(json.dumps(mapping_plan, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(run_test())
