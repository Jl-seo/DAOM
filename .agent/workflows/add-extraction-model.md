---
description: How to add a new extraction model with schema, UI, and permissions
---

# Adding New Extraction Model

## 1. Backend: Model Schema
Model is defined dynamically in CosmosDB, but ensure schema follows pattern:

```python
# Field structure
{
    "name": "field_name",
    "type": "string|number|date|array|object",
    "description": "Field description for LLM",
    "required": True/False,
    "validation": "regex pattern (optional)"
}
```

## 2. Frontend: Model Studio
- Use Model Studio (`/model-studio`) to create via UI
- Or call `modelsApi.create()` programmatically

## 3. LLM Prompt Optimization
- Include clear field descriptions
- Add example values in description
- Set proper validation patterns

## 4. Permission Setup
- Create or update Group with model access
- Set role (Admin = can edit, User = view only)

## 5. Testing
```bash
# Test extraction endpoint
curl -X POST /api/v1/extraction/start-job \
  -F "file=@sample.pdf" \
  -F "model_id=MODEL_ID"
```

## 6. Verification
- [ ] Model appears in Model Gallery
- [ ] Model visible to permitted users only
- [ ] Extraction produces expected fields
- [ ] Confidence scores display correctly
