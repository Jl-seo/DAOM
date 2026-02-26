import requests
import base64
import json

url = "http://localhost:8000/api/v1/connectors/upload"

# Create a dummy tiny base64 pdf
pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Outlines 2 0 R\n/Pages 3 0 R\n>>\nendobj\n"
b64_content = base64.b64encode(pdf_content).decode("utf-8")

payload = {
    "model_id": "test-model-1234",
    "file": {
        "name": "test.pdf",
        "contentBytes": b64_content
    }
}

try:
    # Use headers that simulate Power Automate / Postman and bypass auth for testing if possible or just get the 401/500
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(res.text)
except Exception as e:
    print(f"Error: {e}")
