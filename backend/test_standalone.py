import os
import asyncio
from app.services.extraction.sql_extraction import run_sql_extraction
from app.db.cosmos import init_cosmos
from app.schemas.model import ExtractionModel, FieldDefinition
from app.core.config import settings
import json

async def fetch_test_file():
    pass

async def main():
    print("Testing extraction on test.xlsx locally...")
    await init_cosmos()
    
    test_file_path = "dummy_gc_rates.xlsx"
    if not os.path.exists(test_file_path):
        print(f"{test_file_path} not found.")
        return
        
    class MockFile:
        filename = "dummy_gc_rates.xlsx"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        def __init__(self, c):
            import io
            self.file = io.BytesIO(c)
            self.content = c
            
        async def read(self):
            return self.file.read()

        async def seek(self, offset):
            return self.file.seek(offset)
            
    with open(test_file_path, "rb") as f:
        content = f.read()
    mock_file = MockFile(content)
    
    model = ExtractionModel(
        id="test-mock",
        name="test",
        extractor_llm=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
        mapper_llm=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
        fields=[
            FieldDefinition(key="Trade", label="Trade", type="string", description="", rules=""),
            FieldDefinition(key="Rate List", label="Rate List", type="table", description="", rules="", sub_fields=[
                {"key": "POL", "label": "POL", "type": "string", "description": "", "rules": "", "format": "Text"},
                {"key": "POD", "label": "POD", "type": "string", "description": "", "rules": "", "format": "Text"},
                {"key": "Currency", "label": "Currency", "type": "number", "description": "Currency or Amount", "rules": "", "format": "Text"},
                {"key": "20DC", "label": "20DC", "type": "number", "description": "20FT Rate", "rules": "", "format": "Number"},
                {"key": "40DC", "label": "40DC", "type": "number", "description": "40FT Rate", "rules": "", "format": "Number"},
                {"key": "40HC", "label": "40HC", "type": "number", "description": "40HC Rate", "rules": "", "format": "Number"}
            ]),
        ],
        reference_data={}
    )
    
    print("Running Python Engine Extraction...")
    try:
        result = await run_sql_extraction(mock_file, model)
        print("\n--- EXTRACTION RESULT ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n--- Internal JSON Logs ---")
        if os.path.exists("excel_debug.json"):
            with open("excel_debug.json", "r") as f:
                debug_data = json.load(f)
                for log in debug_data.get('logs', []):
                    if log.get('step') == 'Mapper Reasoning':
                        print("\n--- MAPPER REASONING ---")
                        print(log.get('message'))
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
