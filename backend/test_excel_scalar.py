import asyncio
import json
import os

# Override to ensure API call works locally
os.environ["AZURE_OPENAI_API_KEY"] = "fake"  # Replace if needed

from app.schemas.model import ExtractionModel, FieldDefinition
from app.services.extraction.sql_extraction import _run_schema_mapper

async def main():
    model = ExtractionModel(
        id="test_m",
        name="test",
        type="test",
        fields=[
            FieldDefinition(key="booking_no", label="Booking Number", type="string", description="The booking or b/l number"),
            FieldDefinition(key="vessel_name", label="Vessel Name", type="string", description="Name of the vessel"),
            FieldDefinition(key="shipping_rates", label="Rates", type="table", description="Table", sub_fields=[
                FieldDefinition(key="POL", label="POL", type="string"),
                FieldDefinition(key="POD", label="POD", type="string"),
            ])
        ]
    )
    
    md_content = """| row_id | A | B | C | D |
|---|---|---|---|---|
| 0 | BOOKING NO: | BKG12345 | | |
| 1 | VESSEL: | MSC ALICE | | |
| 2 | | | | |
| 3 | POL | POD | RATE | |
| 4 | USNYK | KRPUS | 1200 | |"""
    
    res = await _run_schema_mapper(md_content, model)
    print("MAPPING PLAN:")
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
