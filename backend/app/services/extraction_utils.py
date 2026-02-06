"""
Extraction Utility Functions

Pure helper functions for data parsing and normalization.
These have no external dependencies and can be safely reused.
"""
import re
import logging
from typing import Any, List, Optional, Tuple, Dict

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



def _merge_bboxes(bboxes: List[List[float]]) -> Optional[List[float]]:
    """
    Merges multiple bounding boxes into a single bounding box (Union).
    Expects normalized or raw [x1, y1, x2, y2].
    """
    if not bboxes:
        return None
        
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    valid_box_found = False
    
    for bbox in bboxes:
        if not bbox or len(bbox) < 4:
            continue
        valid_box_found = True
        # Handle 8-point polygon if necessary, but assume 4-point rect here
        # or pre-normalized. Let's handle 4-point rects.
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        min_x = min(min_x, x1)
        min_y = min(min_y, y1)
        max_x = max(max_x, x2)
        max_y = max(max_y, y2)
        
    if not valid_box_found:
        return None
        
    return [min_x, min_y, max_x, max_y]


def restore_bboxes(extracted_data: Any, ref_map: Dict[str, Any], fuzzy_callback: Optional[callable] = None) -> Any:
    """
    [Beta] Recursively traverses extracted dictionary, looking for 'indices'.
    If found, looks up ref_map, merges bboxes, and injects 'bbox' and 'page_number'.
    Also supports legacy 'ref_index' for backward compatibility.
    """
    if isinstance(extracted_data, dict):
        # 1. Check for 'indices' (New List Format)
        if "indices" in extracted_data:
            indices = extracted_data["indices"]
            if isinstance(indices, list) and indices:
                # Gather all bboxes
                collected_bboxes = []
                collected_pages = []
                
                for idx in indices:
                    ref_info = ref_map.get(str(idx))
                    if ref_info:
                        bbox = ref_info.get("bbox")
                        page = ref_info.get("page_number")
                        
                        if bbox:
                            collected_bboxes.append(bbox)
                        if page:
                            collected_pages.append(page)
                            
                # Merge BBoxes
                rect_bboxes = []
                for b in collected_bboxes:
                    if len(b) >= 8:
                         xs = b[0::2]; ys = b[1::2]
                         rect_bboxes.append([min(xs), min(ys), max(xs), max(ys)])
                    else:
                         rect_bboxes.append(b[:4])

                merged_bbox = _merge_bboxes(rect_bboxes)
                
                # Assign Page Number (Use Majority or First)
                final_page = collected_pages[0] if collected_pages else None
                
                # Assign File ID (New for Multi-file Support)
                # Look at the first index ref for file origin
                first_ref_idx = indices[0]
                first_ref_info = ref_map.get(str(first_ref_idx))
                file_id = first_ref_info.get("file_id") if first_ref_info else None
                
                extracted_data["bbox"] = merged_bbox
                extracted_data["page_number"] = final_page
                extracted_data["file_id"] = file_id # Propagate File ID
            else:
                 pass

        # 2. Check for 'ref_index' (Legacy Single Format)
        elif "ref_index" in extracted_data:
            ref_idx = str(extracted_data["ref_index"]).replace("^", "")
            ref_info = ref_map.get(ref_idx)
            if ref_info:
                extracted_data["bbox"] = ref_info.get("bbox")
                extracted_data["page_number"] = ref_info.get("page_number")
            else:
                extracted_data["bbox"] = None
                extracted_data["page_number"] = None
        
        # [Soft Matching Fallback] If bbox is still None, try to find text match
        if extracted_data.get("bbox") is None and extracted_data.get("value"):
             val = str(extracted_data["value"])
             if len(val) > 2 and fuzzy_callback:
                  # Optimization: Use existing page_number logic is handled inside service/callback usually
                  # But here passing page_limit if available in data
                  pg = extracted_data.get("page_number")
                  if isinstance(pg, int):
                      found_bbox = fuzzy_callback(val, page_limit=pg)
                  else:
                      found_bbox = fuzzy_callback(val, page_limit=None)
                      
                  if found_bbox:
                       logger.info(f"[SoftMatch] Recovered bbox for value: '{val[:10]}...'")
                       extracted_data["bbox"] = found_bbox
                       if pg: extracted_data["page_number"] = pg
        
        # 3. Recurse into all values
        for key, value in extracted_data.items():
            # Pass fuzzy_callback recursively
            extracted_data[key] = restore_bboxes(value, ref_map, fuzzy_callback)
            
        return extracted_data

    elif isinstance(extracted_data, list):
        return [restore_bboxes(item, ref_map, fuzzy_callback) for item in extracted_data]
        
    else:
        return extracted_data
