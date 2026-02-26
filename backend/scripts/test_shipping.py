import asyncio
import pandas as pd
from app.services.extraction.sql_extraction import run_sql_extraction
from app.schemas.model import ExtractionModel, FieldDefinition

async def main():
    df = pd.DataFrame([
        {"A": "Maersk General Disclaimer:", "B": None, "C": None},
        {"A": "POL_CODE", "B": "POL_NAME", "C": "20DC", "D": "40DC", "E": "40HC"},
        {"A": "CNSHA", "B": "Shanghai", "C": "1000", "D": "2000", "E": "2000"},
        {"A": "KRPUS", "B": "Busan", "C": "500", "D": "1000", "E": "1000"},
        {"A": "FAQ (Frequently Asked Questions)", "B": None, "C": None}
    ])
    
    # We must match actual fields the user might be using.
    mock_model = ExtractionModel(
        id="test",
        name="Test",
        fields=[
            FieldDefinition(key="remark", label="비고", type="string", description="Remarks/Disclaimer text at top/bottom"),
            FieldDefinition(key="shipping_rates_extracted", label="테이블 데이터", type="table", description="Table of rates. Map POL_CODE, 20DC, 40DC, etc.")
        ]
    )
    
    class FakeUploadFile:
        def __init__(self, buffer):
            self.filename = "test.xlsx"
            self.file = buffer
        async def read(self):
            return self.file.read()
        async def seek(self, offset):
            self.file.seek(offset)

    import io
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)
    fake_file = FakeUploadFile(excel_buffer)

    import logging
    logging.basicConfig(level=logging.INFO)
    
    res = await run_sql_extraction(fake_file, mock_model)
    import json
    print("OUTPUT----------")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
