"""
Prompt Service - Manage system prompts in database
"""
import logging
from typing import Optional, Dict
from datetime import datetime
from app.db.cosmos import get_container

logger = logging.getLogger(__name__)

PROMPTS_CONTAINER = "prompts"

# Default prompts - used when DB is empty
DEFAULT_PROMPTS = {
    "extraction_system": {
        "content": """You are a document data extractor.

Given this document data extracted by Document Intelligence:
{ocr_data}

Extract values for these specific fields:
{field_descriptions}
{global_rules}

INSTRUCTIONS:
1. Analyze the document structure. If it looks like a table/grid, respect the columns.
2. For specific fields like 'Item' or 'Amount', look for corresponding headers in the table.
3. If a field represents a list of items (e.g. line items in a table), extract it as a JSON Array of objects with relevant keys.
4. Distinguish between 'Item' (product code/name) and 'Description' (details).
5. **Key-Value Tables**: If a table has a structure like [Field Name | Value], map the 'Value' column to the corresponding requested field.
6. **Complex Tables**: Identify headers first. Ensure values are aligned under their respective headers. Do NOT merge neighboring columns (e.g. Description + Width).
7. **CRITICAL**: Extract values EXACTLY as they appear in the text. Do not reformat dates or numbers.
8. **CRITICAL**: You MUST include the 'bbox' (bounding box) for every extracted value. Copy it exactly from source.
8. **CRITICAL**: You MUST include the 'page_number' (1-based index) for every extracted value.

Return a JSON object with TWO parts:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value exactly as in text
   - "confidence": Your confidence level from 0.0 to 1.0
   - "bbox": The bounding box [x1, y1, x2, y2] from the source data (REQUIRED)
   - "page_number": The page number (1-based integer) (REQUIRED)

2. "other_data": Array of other data found that wasn't matched to fields.

IMPORTANT:
- Use exact field keys.
- If value is not found, set value to null.
- Return ONLY valid JSON.
{focus_instruction}""",
        "description": "Main extraction prompt for LLM data extraction",
        "variables": ["ocr_data", "field_descriptions", "global_rules", "focus_instruction"]
    },
    "extraction_system_role": {
        "content": "You are a precise document data extractor. Return only valid JSON.",
        "description": "System role message for extraction LLM",
        "variables": []
    },
    "template_chat": {
        "content": """You are a data output template designer.
Listen to user requests and generate/modify TemplateConfig JSON.

## Available fields:
{model_fields}

## TemplateConfig Schema:
{{
  "layout": "table" | "card" | "report" | "summary",
  "header": {{
    "logo": boolean,
    "title": string,
    "subtitle": string
  }},
  "footer": {{
    "showDate": boolean,
    "pageNumbers": boolean,
    "customText": string
  }},
  "columns": [
    {{
      "field": "field_key",
      "label": "Display Label",
      "align": "left" | "center" | "right",
      "format": "text" | "currency" | "date" | "percent" | "number",
      "style": {{ "color": "#colorcode", "bold": boolean }}
    }}
  ],
  "aggregation": {{
    "showTotal": boolean,
    "showAverage": boolean,
    "showCount": boolean,
    "groupBy": "field_key"
  }},
  "style": {{
    "theme": "modern" | "classic" | "minimal",
    "primaryColor": "#colorcode",
    "fontSize": number
  }}
}}

## Rules:
1. Modify current config based on user request
2. Only respond with changed parts (delta, not full)
3. Respond friendly and ask confirmation questions
4. JSON must be valid

## Response format (must use this JSON format):
{{
  "message": "Friendly message to show user",
  "config": {{ ... updated settings ... }}
}}""",
        "description": "Template chat AI system prompt",
        "variables": ["model_fields"]
    }
}


# Simple in-memory cache
_prompt_cache: Dict[str, dict] = {}
_cache_time: Dict[str, datetime] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_container():
    return get_container(PROMPTS_CONTAINER, "/id")


async def get_prompt(key: str, tenant_id: str = "default") -> Optional[dict]:
    """Get a prompt by key, with caching"""
    cache_key = f"{tenant_id}:{key}"

    # Check cache
    if cache_key in _prompt_cache:
        cached_time = _cache_time.get(cache_key)
        if cached_time and (datetime.utcnow() - cached_time).seconds < CACHE_TTL_SECONDS:
            return _prompt_cache[cache_key]

    # Try DB
    container = _get_container()
    if container:
        try:
            items = list(container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": key}],
                enable_cross_partition_query=True
            ))
            if items:
                result = items[0]
                _prompt_cache[cache_key] = result
                _cache_time[cache_key] = datetime.utcnow()
                return result
        except Exception as e:
            logger.debug(f"Error fetching prompt from DB: {e}")

    # Return default
    if key in DEFAULT_PROMPTS:
        default = {
            "id": key,
            "tenant_id": tenant_id,
            **DEFAULT_PROMPTS[key],
            "is_default": True
        }
        _prompt_cache[cache_key] = default
        _cache_time[cache_key] = datetime.utcnow()
        return default

    return None


async def get_prompt_content(key: str, tenant_id: str = "default") -> str:
    """Get just the prompt content string"""
    prompt = await get_prompt(key, tenant_id)
    if prompt:
        return prompt.get("content", "")
    return ""


async def get_all_prompts(tenant_id: str = "default") -> list:
    """Get all prompts (from DB + defaults for missing)"""
    result = {}

    # Start with defaults
    for key, value in DEFAULT_PROMPTS.items():
        result[key] = {
            "id": key,
            "tenant_id": tenant_id,
            **value,
            "is_default": True
        }

    # Override with DB values
    container = _get_container()
    if container:
        try:
            items = list(container.query_items(
                query="SELECT * FROM c",
                enable_cross_partition_query=True
            ))
            for item in items:
                key = item.get("id")
                if key:
                    item["is_default"] = False
                    result[key] = item
        except Exception as e:
            logger.debug(f"Error fetching prompts from DB: {e}")

    return list(result.values())


async def save_prompt(
    key: str,
    content: str,
    description: str = "",
    tenant_id: str = "default",
    updated_by: str = "admin"
) -> bool:
    """Save or update a prompt"""
    container = _get_container()
    if not container:
        logger.error("Prompts container not available")
        return False

    try:
        # Get variables from default if exists
        variables = []
        if key in DEFAULT_PROMPTS:
            variables = DEFAULT_PROMPTS[key].get("variables", [])

        doc = {
            "id": key,
            "tenant_id": tenant_id,
            "content": content,
            "description": description,
            "variables": variables,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": updated_by
        }
        container.upsert_item(body=doc)

        # Invalidate cache
        cache_key = f"{tenant_id}:{key}"
        _prompt_cache.pop(cache_key, None)
        _cache_time.pop(cache_key, None)

        logger.info(f"Saved prompt: {key}")
        return True

    except Exception as e:
        logger.error(f"Error saving prompt: {e}")
        return False


async def reset_prompt(key: str, tenant_id: str = "default") -> bool:
    """Reset a prompt to default by deleting from DB"""
    container = _get_container()
    if not container:
        return False

    try:
        container.delete_item(item=key, partition_key=key)

        # Invalidate cache
        cache_key = f"{tenant_id}:{key}"
        _prompt_cache.pop(cache_key, None)
        _cache_time.pop(cache_key, None)

        logger.info(f"Reset prompt to default: {key}")
        return True

    except Exception as e:
        logger.debug(f"Error resetting prompt (may not exist): {e}")
        return True  # Not an error if it doesn't exist


def clear_cache():
    """Clear prompt cache (for testing)"""
    _prompt_cache.clear()
    _cache_time.clear()
