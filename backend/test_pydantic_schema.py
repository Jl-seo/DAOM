from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from typing import List, Optional, Any
import json

class PAFileItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    contentBytes: Optional[Any] = None
    content: Optional[Any] = None

class PABatchUploadRequest(BaseModel):
    model_id: str
    metadata: Optional[str] = None
    files: List[PAFileItem]

    @model_validator(mode='before')
    @classmethod
    def parse_stringified_files(cls, data: Any) -> Any:
        if isinstance(data, dict):
            files_val = data.get("files")
            if isinstance(files_val, str):
                try:
                    data["files"] = json.loads(files_val)
                except json.JSONDecodeError:
                    pass
        return data

def run_test():
    payload = {
        "model_id": "5bfef7a7-aa72-4087-9117-f42364276a1d",
        "files": '[{"name": "test.xlsx", "contentBytes": {"$content": "base64"}}]'
    }
    
    try:
        model = PABatchUploadRequest(**payload)
        print("Success! Parsed payload:")
    except ValidationError as e:
        print("Validation Error!")
        print(e.json())

if __name__ == "__main__":
    run_test()
