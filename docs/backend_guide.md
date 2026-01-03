# Backend Integration Guide for DAOM

This guide outlines how the Backend Agent handles data using the shared schema.

## Data Validation
All document processing endpoints must validate output against `shared/schema.json`.

### Pydantic Model (Reference)
When implementing Pydantic models in FastAPI, ensure they adhere to strict types:

```python
from pydantic import BaseModel, UUID4, Field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

class ProcessStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"

class DaomDocument(BaseModel):
    id: UUID4
    filename: str
    uploadTimestamp: datetime
    status: ProcessStatus
    unstructuredContent: Optional[str] = None
    structuredData: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    errorMessage: Optional[str] = None
```

## Processing Workflow
1. **Upload**: Initialize document with status `pending`.
2. **Analysis**: Update status to `processing`.
3. **Completion**:
    - On success: Set status to `completed`, populate `structuredData` and `unstructuredContent`.
    - On failure: Set status to `failed`, populate `errorMessage`.

## Error Handling
Always return a valid `DaomDocument` object even in error states where possible, so the frontend can display the error message gracefully.
