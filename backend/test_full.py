import asyncio
import os
import json
import logging
import pandas as pd
from io import BytesIO
from fastapi import UploadFile

from app.services.extraction.sql_extraction import run_sql_extraction
from app.schemas.model import ExtractionModel, FieldDefinition
from app.core.config import settings
from unittest.mock import patch

logging.basicConfig(level=logging.INFO)

async def run_test():
    # 1. Create a dummy Excel file in memory
    df1 = pd.DataFrame({
        "POL": ["PUSAN", "INCHEON"],
        "POD": ["USWC", "USEC"],
        "20DC": [1000, 1200],
        "40DC": [1500, 1800]
    })
    
    df_empty_sheet = pd.DataFrame()
    
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df1.to_excel(writer, sheet_name="Schedule", index=False)
        # Write an empty sheet to test robustness
        pd.DataFrame({"A": []}).to_excel(writer, sheet_name="EmptySheet", index=False)
        
    excel_buffer.seek(0)
    
    # Mock UploadFile
    upload_file = UploadFile(filename="test.xlsx", file=excel_buffer, headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    
    # 2. Mock ExtractionModel
    model = ExtractionModel(
        id="test-id",
        name="Test",
        mapper_llm="gpt-4o-mini",
        extractor_llm="gpt-4o",
        fields=[
            FieldDefinition(key="rate_list", label="Rate List", type="table", sub_fields=[
                {"key": "pol", "label": "POL", "type": "string"},
                {"key": "pod", "label": "POD", "type": "string"},
                {"key": "20dc", "label": "20DC", "type": "number"},
                {"key": "40dc", "label": "40DC", "type": "number"}
            ]),
            FieldDefinition(key="summary", label="Document Summary", type="string", description="Provide a 1 sentence summary of what this document is about.")
        ]
    )
    
    # Ensure env vars are set
    os.environ["AZURE_OPENAI_API_KEY"] = settings.AZURE_OPENAI_API_KEY
    os.environ["AZURE_OPENAI_ENDPOINT"] = settings.AZURE_OPENAI_ENDPOINT
    
    print("--- Running Full Extractor Pipeline ---")
    
    from app.services.extraction_service import ExtractionService
    try:
        service = ExtractionService()
        
        with patch('app.services.extraction_service.get_model_by_id', return_value=model):
            result = await service.run_extraction_pipeline(
                file_content=excel_buffer.getvalue(),
                model_id="test-id",
                filename="test.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        print("Extraction Result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
