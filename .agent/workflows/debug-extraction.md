---
description: Debugging extraction and PDF highlighting issues
---

# Debugging Extraction Issues

## Common Issue: LLM Returns Empty Values

### 1. Check LLM Prompt
Review prompt in `extraction_service.py`:
```python
# Enable debug logging
logger.setLevel(logging.DEBUG)
```

### 2. Check OCR Output
Verify OCR parsed text correctly:
```python
# In extraction endpoint, log OCR result
logger.debug(f"OCR result: {ocr_text[:500]}")
```

### 3. Check Model Schema
Ensure field descriptions are clear for LLM

---

## Common Issue: Highlights Not Showing

### 1. Verify bbox Data Flow
```
Backend extraction → response.extracted_data → 
Frontend ExtractionContext → ExtractionPreview → PDFViewer
```

### 2. Check bbox Format
```json
{
  "field_name": {
    "value": "extracted text",
    "confidence": 0.95,
    "bbox": [x1, y1, x2, y2],
    "page": 1
  }
}
```

### 3. Common Issues
| Issue | Cause | Fix |
|-------|-------|-----|
| Highlights on wrong page | Missing `page` in bbox | Add page number to extraction output |
| No highlights | bbox is null | Check LLM response parsing |
| Highlights offset | Coordinate normalization | Verify PDF dimensions match |

---

## Common Issue: Confidence Not Displaying

### 1. Check Backend Response
```python
# Ensure confidence is included
{
    "value": result_value,
    "confidence": confidence_score  # 0.0 - 1.0
}
```

### 2. Check Frontend Display
```tsx
// Verify ExtractionPreview reads confidence
const { value, confidence } = fieldData
```

---

## Debug Tools

### Backend Logging
```python
import logging
logging.getLogger("app.services.extraction").setLevel(logging.DEBUG)
```

### Frontend Console
```tsx
// In ExtractionContext
console.log("Extraction result:", extractedData)
```
