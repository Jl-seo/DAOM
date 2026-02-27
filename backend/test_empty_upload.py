import asyncio
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient
from typing import List

app = FastAPI()

@app.post("/test-upload")
async def test_upload(files: List[UploadFile] = File(...)):
    results = []
    for f in files:
        # Check properties
        size = getattr(f, "size", None)
        filename = getattr(f, "filename", None)
        
        # Original filter logic
        # Note: in python 3, None > 0 throws TypeError, so if size is None, it crashes
        try:
            is_valid = f is not None and filename and getattr(f, "size", 1) > 0
        except TypeError:
            is_valid = "TypeError"
            
        # Safer filter
        safe_valid = f.filename and len(f.filename.strip()) > 0
        file_content = await f.read()
        content_len = len(file_content)
        
        results.append({
            "filename": filename,
            "filename_type": str(type(filename)),
            "size_attr": size,
            "read_len": content_len,
            "old_filter_valid": is_valid
        })
    return results

client = TestClient(app)

def test_empty_upload():
    # Simulate a multipart request with one real file and one empty/null file slot
    files_payload = [
        ("files", ("real.pdf", b"hello world", "application/pdf")),
        ("files", ("", b"", "application/octet-stream")), # Empty part, typical of null IF slots
        ("files", ("null", b"", "application/octet-stream")), # Literal string null
    ]
    
    response = client.post("/test-upload", files=files_payload)
    print(response.json())

if __name__ == "__main__":
    test_empty_upload()
