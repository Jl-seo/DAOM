import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app

def run_test():
    client = TestClient(app)

    payload = {
        "model_id": "5bfef7a7-aa72-4087-9117-f42364276a1d",
        "files": [
            {
                "name": "QuoteOutputFile.xlsx",
                "contentBytes": {"$content-type": "application/octet-stream", "$content": "base64"}
            }
        ]
    }
    
    print("Testing payload 2 (Array Variable Native String format):")
    response2 = client.post("/api/v1/connectors/batch-upload", json=payload)
    print(f"Status Code: {response2.status_code}")
    print(f"Response: {response2.text}")

if __name__ == "__main__":
    run_test()
