import asyncio
import io
import pandas as pd
from uuid import uuid4
from fastapi import UploadFile

from app.schemas.model import ExtractionModel, FieldDefinition
from app.services.extraction.sql_extraction import run_sql_extraction
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)

async def test_sql_extraction():
    print("Creating mock excel file...")
    df = pd.DataFrame({
        "PatientName": ["Kim 철수", "Lee 영희", "Park 민수"],
        "Age": [30, 25, 45],
        "Hospital": ["Seoul", "Busan", "Seoul"]
    })
    
    excel_io = io.BytesIO()
    df.to_excel(excel_io, index=False)
    excel_bytes = excel_io.getvalue()
    
    upload_file = UploadFile(filename="test.xlsx", file=io.BytesIO(excel_bytes))
    
    print("Creating mock model...")
    mock_model = ExtractionModel(
        id=str(uuid4()),
        name="Test Model",
        document_type="Test Doc",
        description="Test desc",
        fields=[
            FieldDefinition(name="Patient", key="patient", label="환자", type="string", description="환자명 (PatientName 컬럼)"),
            FieldDefinition(name="HospitalName", key="hospital", label="병원", type="string", description="병원명 (Hospital 컬럼)"),
        ],
        rules=[],
        comparisons=[]
    )
    
    print("Running sql extraction...")
    try:
        res = await run_sql_extraction(upload_file, mock_model)
        print("Success!")
        print(res["guide_extracted"])
    except Exception as e:
        print("Failed:", type(e).__name__, e)

if __name__ == "__main__":
    asyncio.run(test_sql_extraction())
