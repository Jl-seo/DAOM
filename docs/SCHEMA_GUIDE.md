# Shared Schema Guide

This guide describes how to use `shared/schema.json` to ensure data consistency between the Backend (AI Extraction) and Frontend (Display).

## Schema Overview

The schema defines the full document object (`DaomDocument`), including the envelope (ID, status) and the `structuredData` payload.

**Key Extraction Fields (`structuredData`):**
- **merchantName** (String): 업체명
- **businessLicenseNumber** (String): 사업자번호 (Format: 000-00-00000)
- **date** (String): Date (YYYY-MM-DD)
- **supplyValue** (Integer): 공급가액
- **surtax** (Integer): 부가세
- **totalAmount** (Integer): 총금액

## Backend Usage (FastAPI & OpenAI)

The backend uses this schema to instruct GPT-5.1 on exactly what JSON structure to output.

### 1. Loading the Schema
Load the schema and extract the `structuredData` property definition to use as the `response_format` or system prompt instruction for the AI.

```python
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "shared" / "schema.json"

def get_extraction_schema():
    with open(SCHEMA_PATH, "r") as f:
        full_schema = json.load(f)
    # Extract only the structuredData part for the AI
    return full_schema["properties"]["structuredData"]

# Example usage with OpenAI
# messages=[
#     {"role": "system", "content": f"Extract data following this schema: {json.dumps(get_extraction_schema())}"},
#     ...
# ]
```

## Frontend Usage (React & TypeScript)

The frontend uses this schema to generate TypeScript interfaces, ensuring type safety when displaying the data.

### 1. Generating Types
We recommend using `json-schema-to-typescript` to automatically generate `types/schema.d.ts`.

**Command:**
```bash
# Install tool
npm install -D json-schema-to-typescript

# Generate types
npx json2ts ../shared/schema.json > src/types/schema.d.ts
```

### 2. Using the Types
Import the generated types in your components.

```typescript
import { DaomDocument } from '../types/schema';

function DocumentRow({ doc }: { doc: DaomDocument }) {
  return (
    <div>
       <div>{doc.structuredData?.merchantName}</div>
       <div>{doc.structuredData?.totalAmount}</div>
    </div>
  );
}
```
