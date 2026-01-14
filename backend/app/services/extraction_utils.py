"""
Extraction Utility Functions

Pure helper functions for data parsing and normalization.
These have no external dependencies and can be safely reused.
"""
import re
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def parse_number(value: Any) -> Optional[float]:
    """
    Strict number parsing.
    Removes currency symbols and formats, returns float or None.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove currency symbols and commas
        clean = value.replace(",", "").replace("₩", "").replace("$", "").replace("원", "").strip()
        try:
            return float(clean)
        except ValueError:
            return None
    return None


def parse_date(value: Any) -> Optional[str]:
    """
    Strict date parsing to ISO8601 YYYY-MM-DD format.
    Handles Korean and common international date formats.
    """
    if not isinstance(value, str) or not value:
        return None
    
    value = value.strip()
    
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return value
    
    # Common Korean formats: YYYY년 MM월 DD일
    match = re.match(r'^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', value)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    
    # YYYY.MM.DD or YYYY/MM/DD
    match = re.match(r'^(\d{4})[./](\d{1,2})[./](\d{1,2})', value)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    
    # DD/MM/YYYY or MM/DD/YYYY (assume MM/DD/YYYY for US format)
    match = re.match(r'^(\d{1,2})[./](\d{1,2})[./](\d{4})', value)
    if match:
        return f"{match.group(3)}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"
    
    # If nothing matched, return original
    return value


def normalize_bbox(bbox: Any, page_width: float = 0, page_height: float = 0) -> Optional[List[float]]:
    """
    Normalize bbox to percentage coordinates (0-100) for frontend rendering.
    Accepts various formats:
    - [x1, y1, x2, y2] (4-point)
    - 8-point polygon
    - Dict {x1, y1, x2, y2} or {x, y, w, h}
    
    Returns [x1, y1, x2, y2] in percentages.
    """
    if not bbox or not isinstance(bbox, (list, tuple, dict)):
        return None
    
    try:
        # Handle 8-point polygon or dict
        if isinstance(bbox, dict):
            x1 = float(bbox.get("x1", bbox.get("x", 0)))
            y1 = float(bbox.get("y1", bbox.get("y", 0)))
            x2 = float(bbox.get("x2", bbox.get("w", 0) + x1))
            y2 = float(bbox.get("y2", bbox.get("h", 0) + y1))
        elif len(bbox) >= 8:
            xs = bbox[0::2]
            ys = bbox[1::2]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        else:
            x1, y1, x2, y2 = [float(b) for b in bbox[:4]]
        
        # Case 1: Page dimensions provided - calculate percentages
        if page_width > 0 and page_height > 0:
            return [
                (x1 / page_width) * 100,
                (y1 / page_height) * 100,
                (x2 / page_width) * 100,
                (y2 / page_height) * 100
            ]
        
        # Case 2: Coordinates look like inches (Azure Doc Intelligence, typically 0-11)
        if all(0 <= v <= 20 for v in [x1, y1, x2, y2]):
            default_page_width = 8.5
            default_page_height = 11.0
            return [
                (x1 / default_page_width) * 100,
                (y1 / default_page_height) * 100,
                (x2 / default_page_width) * 100,
                (y2 / default_page_height) * 100
            ]
        
        # Case 3: Coordinates might be in pixels
        if x2 > 100 or y2 > 100:
            estimated_width = max(x2 * 1.1, 612)
            estimated_height = max(y2 * 1.1, 792)
            return [
                (x1 / estimated_width) * 100,
                (y1 / estimated_height) * 100,
                (x2 / estimated_width) * 100,
                (y2 / estimated_height) * 100
            ]
        
        # Fallback: Already looks like percentages
        return [x1, y1, x2, y2]

    except (ValueError, TypeError) as e:
        logger.error(f"[normalize_bbox] Error: {e}, bbox: {bbox}")
        return None
