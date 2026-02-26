import asyncio
import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Load real environment variables from backend/.env
load_dotenv("backend/.env")

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

async def test_extraction():
    from app.services.doc_intel import extract_with_strategy, AzureModelType
    
    # Create a dummy Excel file that mimics the user's issue (sparse rows, multi-table)
    test_file_path = "dummy_test.xlsx"
    
    # Simulating standard "visual" grid data without explicit table formatting
    data = {
        'C1': ['Origin', '', '', '', 'Busan', 'Incheon', 'Busan'],
        'C2': ['Destination', '', '', '', 'KR', 'KR', 'KR'],
        'C3': ['Something', 'Total Amount', '', '', '100', '200', '150'],
        'C4': ['', '', '', '', '', '', '']
    }
    df = pd.DataFrame(data)
    df.to_excel(test_file_path, index=False, header=False)
    print(f"Created {test_file_path}")
    
    try:
        with open(test_file_path, "rb") as f:
            file_bytes = f.read()
            
        print("Sending to Azure DI Layout...")
        # Force layout to test table extraction
        result = await extract_with_strategy(
            file_source=file_bytes,
            model_type=AzureModelType.LAYOUT,
            filename=test_file_path,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        tables = result.get("tables", [])
        print(f"Azure DI returned {len(tables)} tables.")
        
        for idx, table in enumerate(tables):
            cells = table.get('cells', [])
            print(f"Table {idx+1} has {len(cells)} cells.")
            if cells:
                print(f"  First cell: row={cells[0].get('row_index', '?')}, col={cells[0].get('column_index', '?')}, content='{cells[0].get('content', '')}'")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(test_file_path):
            os.remove(test_file_path)

if __name__ == "__main__":
    asyncio.run(test_extraction())
