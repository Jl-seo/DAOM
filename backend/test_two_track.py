import asyncio
import io
import pandas as pd
from fastapi import UploadFile

from app.schemas.model import ExtractionModel, FieldDefinition
from app.services.extraction.sql_extraction import run_sql_extraction
from app.services.extraction.excel_parser import ExcelParser

async def test():
    # 1. Create dummy Excel in memory
    df = pd.DataFrame({
        "IgnoreThis": ["HeaderRow", "Data1", "Data2", "Data3"],
        "ColB": ["Target_POL", "KRPUS", "CNSHA", "HKHKG"],
        "ColC": ["Target_POD", "USLAX", "USLGB", "USOAK"],
        "ColD": ["Price_20DC", "1500", "1600", "1700"]
    })
    
    # Also add a scalar at the very top
    df.loc[0, "ColD"] = "Contract: 123456"
    
    excel_io = io.BytesIO()
    with pd.ExcelWriter(excel_io, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Schedule")
    excel_bytes = excel_io.getvalue()
    excel_io.seek(0)
    
    upload_file = UploadFile(filename="dummy.xlsx", file=excel_io)
    
    # Generate md_content like extraction_service.py does
    parsed_sheets = ExcelParser.from_bytes(excel_bytes, "xlsx")
    md_content = "\n\n".join([s.get("content", "") for s in parsed_sheets])
    
    # 2. Create Model
    model = ExtractionModel(
        id="test-model",
        name="Test",
        document_type="schedule",
        fields=[
            FieldDefinition(key="contract_no", type="string", label="Contract No", description="Find the 6 digit contract number"),
            FieldDefinition(key="rates", type="table", label="Rates Table", description="Table with POL, POD, and Price for 20DC container")
        ],
        reference_data={}
    )
    
    # 3. Run extraction
    print("Running Extraction...")
    res = await run_sql_extraction(upload_file, model, md_content=md_content)
    print("\nExtraction Result:")
    import json
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test())
