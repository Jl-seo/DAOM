"""
Excel Block Parser — Python-only structural pre-parser for Excel extraction.

Architecture: Block-first + Validator-first
LLM sees structure summaries, not raw data. Python validates all LLM suggestions.

Pipeline:
  1. detect_blocks()       → physical block segmentation
  2. classify_rows()       → row role classification (header/data/group/context/remark)
  3. profile_columns()     → column type hints + samples
  4. extract_block_context()→ inheritable metadata (POL, Currency, Date)
  5. validate_column_mapping() → verify LLM mapping against data patterns
  6. field_aware_expand()  → type-checked delimiter expansion
"""
import re
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class BlockInfo:
    sheet_name: str
    block_id: int
    row_start: int          # row_id (global)
    row_end: int            # row_id (global, inclusive)
    block_type: str         # "table" | "metadata" | "note" | "blank"
    col_count: int          # count of non-empty columns
    numeric_ratio: float    # ratio of numeric values in data cells
    row_count: int = 0

@dataclass
class RowClassification:
    row_id: int
    row_type: str           # "header" | "data" | "group_label" | "context" | "remark"
    confidence: float = 0.8

@dataclass
class ColumnProfile:
    column_letter: str
    type_hint: str          # "port_code" | "money" | "date" | "text" | "mixed"
    sample: List[str] = field(default_factory=list)
    non_empty_count: int = 0
    numeric_ratio: float = 0.0

# ──────────────────────────────────────────────
# Pattern Detectors
# ──────────────────────────────────────────────

# Port codes: 2-5 uppercase letters (USLAX, KRPUS, CNSHA, CAVAN)
PORT_PATTERN = re.compile(r'^[A-Z]{2,5}$')
# Multi-port: USLAX/USLGB or USLAX, USLGB
MULTI_PORT_PATTERN = re.compile(r'^[A-Z]{2,5}[/,]\s*[A-Z]{2,5}')
# Date patterns: 2025/12/1, 2025-12-01, 12/1/2025, etc
DATE_PATTERN = re.compile(r'^\d{1,4}[/\-\.]\d{1,2}([/\-\.]\d{1,4})?$')
# Excel serial date (e.g., 43651 = 2019-07-01)
SERIAL_DATE_PATTERN = re.compile(r'^\d{5}$')
# Money: pure numbers, possibly with commas/decimals (1480, 1,200.50)
MONEY_PATTERN = re.compile(r'^[\d,]+\.?\d*$')
# Currency codes
CURRENCY_PATTERN = re.compile(r'^(USD|KRW|EUR|JPY|CNY|GBP|CAD|AUD|SGD|HKD|TWD)$', re.IGNORECASE)
# Service mode: CY/CY, CY-CY, CFS/CY etc
SERVICE_MODE_PATTERN = re.compile(r'^(CY|CFS|SD|DR)[/\-](CY|CFS|SD|DR)$', re.IGNORECASE)
# Remark keywords
REMARK_KEYWORDS = {'note', 'remark', 'remarks', '※', 'n/a', 'subject to', 'inclusive', 'excluded', 'validity', 'above rate'}
# Context keywords (metadata rows)
CONTEXT_KEYWORDS = {'effective', 'expiry', 'validity', 'currency', 'carrier', 'service', 'vessel', 'voyage', 'contract', 'amendment'}
# Group label keywords
GROUP_KEYWORDS = {'ipi', 'local', 'mlb', 'inland', 'transit', 'direct', 'transship'}

# PORT_LIKE_FIELDS: fields that contain port CODES (5-letter UN/LOCODE).
# NOTE: "destination" is NOT here — it contains city names (e.g., "CHICAGO,IL"), not port codes.
PORT_LIKE_FIELDS = frozenset({"pol", "pod", "por", "pvy", "pvd", "port", "origin",
                               "port_of_loading", "port_of_discharge", "hub_port"})

# GEOGRAPHY_TEXT_FIELDS: fields that contain geographic names (cities/regions), not codes.
# These are expandable by delimiter (slash/comma) but are NOT validated as port codes.
GEOGRAPHY_TEXT_FIELDS = frozenset({"destination", "commodity"})


def is_port_like(val: str) -> bool:
    """Check if value looks like a port code or multi-port."""
    val = str(val).strip()
    if PORT_PATTERN.match(val):
        return True
    if MULTI_PORT_PATTERN.match(val):
        return True
    return False


def is_date_like(val: str) -> bool:
    """Check if value looks like a date (including Excel serial dates)."""
    val = str(val).strip()
    if DATE_PATTERN.match(val):
        return True
    if SERIAL_DATE_PATTERN.match(val):
        try:
            n = int(val)
            return 30000 < n < 60000  # ~1982 to ~2063 in Excel serial
        except ValueError:
            return False
    return False


def is_money_like(val: str) -> bool:
    """Check if value looks like a monetary amount."""
    val = str(val).strip().replace(',', '').replace(' ', '')
    if not val:
        return False
    try:
        float(val)
        return True
    except ValueError:
        return False


def is_currency_code(val: str) -> bool:
    return bool(CURRENCY_PATTERN.match(str(val).strip()))


def is_service_mode(val: str) -> bool:
    return bool(SERVICE_MODE_PATTERN.match(str(val).strip()))


# ──────────────────────────────────────────────
# Step 1: Block Detection
# ──────────────────────────────────────────────

def detect_blocks(df: pd.DataFrame, sheet_name: str) -> List[BlockInfo]:
    """
    Segment a sheet into physical blocks separated by blank rows.
    
    A block boundary is detected when 2+ consecutive rows have ALL data columns empty.
    """
    sheet_df = df[df["_sheet_name"] == sheet_name].copy() if "_sheet_name" in df.columns else df.copy()
    
    if sheet_df.empty:
        return []
    
    data_cols = [c for c in sheet_df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]
    
    blocks: List[BlockInfo] = []
    current_start = None
    consecutive_blanks = 0
    block_id = 1
    
    row_ids = sheet_df["row_id"].tolist()
    
    for i, (_, row) in enumerate(sheet_df.iterrows()):
        rid = int(row["row_id"])
        # Check if row is blank (all data columns are NaN or empty string)
        row_vals = [str(row[c]).strip() if pd.notna(row[c]) else "" for c in data_cols]
        is_blank = all(v == "" or v.lower() == "nan" for v in row_vals)
        
        if is_blank:
            consecutive_blanks += 1
            if consecutive_blanks >= 2 and current_start is not None:
                # Close current block
                block_end = row_ids[i - consecutive_blanks] if (i - consecutive_blanks) >= 0 else rid
                block_rows = sheet_df[(sheet_df["row_id"] >= current_start) & (sheet_df["row_id"] <= block_end)]
                blocks.append(_build_block_info(sheet_name, block_id, current_start, block_end, block_rows, data_cols))
                block_id += 1
                current_start = None
        else:
            if current_start is None:
                current_start = rid
            consecutive_blanks = 0
    
    # Close last block
    if current_start is not None:
        block_end = row_ids[-1]
        block_rows = sheet_df[(sheet_df["row_id"] >= current_start) & (sheet_df["row_id"] <= block_end)]
        blocks.append(_build_block_info(sheet_name, block_id, current_start, block_end, block_rows, data_cols))
    
    logger.info(f"[BlockParser] Sheet '{sheet_name}': detected {len(blocks)} blocks")
    return blocks


def _build_block_info(sheet_name: str, block_id: int, row_start: int, row_end: int,
                      block_rows: pd.DataFrame, data_cols: list) -> BlockInfo:
    """Build a BlockInfo from a slice of the DataFrame."""
    # Count non-empty columns
    non_empty_cols = 0
    for c in data_cols:
        if block_rows[c].apply(lambda x: pd.notna(x) and str(x).strip() not in ("", "nan")).any():
            non_empty_cols += 1
    
    # Calculate numeric ratio (what fraction of non-empty cells are numeric)
    total_cells = 0
    numeric_cells = 0
    for c in data_cols:
        for val in block_rows[c]:
            if pd.notna(val) and str(val).strip() not in ("", "nan"):
                total_cells += 1
                if is_money_like(str(val)):
                    numeric_cells += 1
    
    numeric_ratio = numeric_cells / max(1, total_cells)
    row_count = len(block_rows)
    
    # Determine block type
    if row_count <= 3 and non_empty_cols <= 3:
        block_type = "metadata"
    elif numeric_ratio > 0.2 and non_empty_cols >= 3 and row_count >= 3:
        block_type = "table"
    elif row_count <= 5:
        block_type = "note"
    else:
        block_type = "table"  # Default to table for larger blocks
    
    return BlockInfo(
        sheet_name=sheet_name,
        block_id=block_id,
        row_start=row_start,
        row_end=row_end,
        block_type=block_type,
        col_count=non_empty_cols,
        numeric_ratio=round(numeric_ratio, 3),
        row_count=row_count
    )


# ──────────────────────────────────────────────
# Step 2: Row Classification
# ──────────────────────────────────────────────

def classify_rows(df: pd.DataFrame, block: BlockInfo) -> List[RowClassification]:
    """
    Classify each row in a block as header/data/group_label/context/remark.
    
    Rules:
    - header: mostly short strings, low numeric ratio, in first 3 rows of block
    - data: has numeric values + structured patterns (ports, codes)
    - group_label: only 1-2 cells filled, rest empty
    - context: contains date ranges, currency, validity keywords
    - remark: long text, remark keywords
    """
    data_cols = [c for c in df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]
    block_df = df[(df["row_id"] >= block.row_start) & (df["row_id"] <= block.row_end)]
    
    classifications: List[RowClassification] = []
    header_found = False
    
    for _, row in block_df.iterrows():
        rid = int(row["row_id"])
        row_vals = []
        for c in data_cols:
            v = str(row[c]).strip() if pd.notna(row[c]) else ""
            if v.lower() != "nan":
                row_vals.append(v)
            else:
                row_vals.append("")
        
        non_empty = [v for v in row_vals if v]
        non_empty_count = len(non_empty)
        
        if non_empty_count == 0:
            classifications.append(RowClassification(rid, "remark", 0.5))
            continue
        
        # Calculate properties
        numeric_count = sum(1 for v in non_empty if is_money_like(v))
        numeric_ratio = numeric_count / max(1, non_empty_count)
        avg_len = sum(len(v) for v in non_empty) / max(1, non_empty_count)
        has_remark_kw = any(kw in " ".join(non_empty).lower() for kw in REMARK_KEYWORDS)
        has_context_kw = any(kw in " ".join(non_empty).lower() for kw in CONTEXT_KEYWORDS)
        has_group_kw = any(kw in " ".join(non_empty).lower() for kw in GROUP_KEYWORDS)
        
        # Classification logic
        row_type = "data"
        confidence = 0.7
        
        # Header: mostly text, short values, within first 3 rows of block
        if not header_found and (rid - block.row_start) <= 2:
            if numeric_ratio < 0.3 and non_empty_count >= 3:
                row_type = "header"
                confidence = 0.9
                header_found = True
        
        # Group label: only 1-2 cells filled out of many columns
        if non_empty_count <= 2 and len(data_cols) >= 5 and row_type == "data":
            if has_group_kw or (non_empty_count == 1 and avg_len < 30):
                row_type = "group_label"
                confidence = 0.8
        
        # Context: date/currency/validity keywords
        if has_context_kw and row_type == "data":
            row_type = "context"
            confidence = 0.8
        
        # Remark: long text or remark keywords
        if has_remark_kw and row_type == "data":
            row_type = "remark"
            confidence = 0.7
        
        # Data validation: must have at least some numeric or port-like content
        if row_type == "data":
            has_ports = any(is_port_like(v) for v in non_empty)
            if numeric_ratio > 0.2 or has_ports:
                confidence = 0.9
            else:
                confidence = 0.6
        
        classifications.append(RowClassification(rid, row_type, round(confidence, 2)))
    
    return classifications


# ──────────────────────────────────────────────
# Step 3: Column Profiling
# ──────────────────────────────────────────────

def profile_columns(df: pd.DataFrame, block: BlockInfo, row_classifications: List[RowClassification]) -> Dict[str, ColumnProfile]:
    """
    Profile each column's data type based on actual data rows only.
    Returns column letter → ColumnProfile mapping.
    """
    data_cols = [c for c in df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]
    data_row_ids = {rc.row_id for rc in row_classifications if rc.row_type == "data"}
    block_df = df[(df["row_id"].isin(data_row_ids))]
    
    profiles: Dict[str, ColumnProfile] = {}
    
    for col in data_cols:
        values = []
        for val in block_df[col]:
            if pd.notna(val):
                s = str(val).strip()
                if s and s.lower() != "nan":
                    values.append(s)
        
        if not values:
            continue
        
        # Count types
        port_count = sum(1 for v in values if is_port_like(v))
        date_count = sum(1 for v in values if is_date_like(v))
        money_count = sum(1 for v in values if is_money_like(v))
        currency_count = sum(1 for v in values if is_currency_code(v))
        service_count = sum(1 for v in values if is_service_mode(v))
        total = len(values)
        
        # Determine type hint based on dominant pattern
        ratios = {
            "port_code": port_count / total,
            "date": date_count / total,
            "money": money_count / total,
            "currency": currency_count / total,
            "service_mode": service_count / total,
        }
        
        best_type = max(ratios, key=ratios.get)
        best_ratio = ratios[best_type]
        
        if best_ratio < 0.3:
            type_hint = "text"
        elif best_type == "money" and best_ratio > 0.5:
            # Could be money or just numeric IDs, check values
            type_hint = "money"
        else:
            type_hint = best_type
        
        # Collect sample (first 5 unique values)
        sample = list(dict.fromkeys(values))[:5]
        
        profiles[col] = ColumnProfile(
            column_letter=col,
            type_hint=type_hint,
            sample=sample,
            non_empty_count=total,
            numeric_ratio=round(money_count / max(1, total), 3)
        )
    
    return profiles


# ──────────────────────────────────────────────
# Step 4: Block Context Extraction
# ──────────────────────────────────────────────

def extract_block_context(df: pd.DataFrame, block: BlockInfo,
                          row_classifications: List[RowClassification]) -> Dict[str, str]:
    """
    Extract inheritable context values from metadata/context/group_label rows.
    These values will be applied to data rows that are missing them.
    
    Returns: {"POL": "PUSAN", "Currency": "USD", "Start_Date": "2025-12-01", ...}
    """
    context_row_ids = {rc.row_id for rc in row_classifications if rc.row_type in ("context", "group_label")}
    data_cols = [c for c in df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]
    
    context = {}
    
    for _, row in df[df["row_id"].isin(context_row_ids)].iterrows():
        for c in data_cols:
            val = str(row[c]).strip() if pd.notna(row[c]) else ""
            if not val or val.lower() == "nan":
                continue
            
            val_lower = val.lower()
            
            # Port detection
            if is_port_like(val) and "POL" not in context:
                context["POL"] = val
            
            # Currency detection
            if is_currency_code(val):
                context["Currency"] = val.upper()
            
            # Date detection from key-value pairs
            if "effective" in val_lower or "start" in val_lower:
                # Look at next column for the value
                col_idx = data_cols.index(c)
                if col_idx + 1 < len(data_cols):
                    next_val = str(row[data_cols[col_idx + 1]]).strip() if pd.notna(row[data_cols[col_idx + 1]]) else ""
                    if next_val and is_date_like(next_val):
                        context["Start_Date"] = _normalize_date(next_val)
            
            if "expiry" in val_lower or "end" in val_lower:
                col_idx = data_cols.index(c)
                if col_idx + 1 < len(data_cols):
                    next_val = str(row[data_cols[col_idx + 1]]).strip() if pd.notna(row[data_cols[col_idx + 1]]) else ""
                    if next_val and is_date_like(next_val):
                        context["End_Date"] = _normalize_date(next_val)
            
            # Carrier detection
            if "carrier" in val_lower:
                col_idx = data_cols.index(c)
                if col_idx + 1 < len(data_cols):
                    next_val = str(row[data_cols[col_idx + 1]]).strip() if pd.notna(row[data_cols[col_idx + 1]]) else ""
                    if next_val and next_val.lower() != "nan":
                        context["Carrier"] = next_val
    
    if context:
        logger.info(f"[BlockParser] Block {block.block_id} context: {context}")
    
    return context


def _normalize_date(val: str) -> str:
    """Normalize date value, including Excel serial dates."""
    val = val.strip()
    # Excel serial date
    if SERIAL_DATE_PATTERN.match(val):
        try:
            from datetime import datetime, timedelta
            serial = int(val)
            # Excel epoch: 1899-12-30
            dt = datetime(1899, 12, 30) + timedelta(days=serial)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return val
    # Already formatted date
    return val


# ──────────────────────────────────────────────
# Step 5: Column Mapping Validator
# ──────────────────────────────────────────────

def validate_column_mapping(
    df: pd.DataFrame,
    block: BlockInfo,
    llm_mapping: Dict[str, str],  # {sub_field_key: excel_column_letter}
    row_classifications: List[RowClassification],
    column_profiles: Dict[str, ColumnProfile]
) -> Dict[str, Any]:
    """
    Validate LLM's column mapping against actual data patterns.
    
    Returns: {
        "validated_mapping": {...},  # accepted mappings
        "rejected": [...],          # rejected with reason
        "warnings": [...]
    }
    """
    data_row_ids = {rc.row_id for rc in row_classifications if rc.row_type == "data"}
    block_df = df[df["row_id"].isin(data_row_ids)]
    
    validated = {}
    rejected = []
    warnings = []
    
    for sub_field_key, excel_col in llm_mapping.items():
        sf_lower = sub_field_key.strip().lower()
        
        # Check column exists
        if excel_col not in df.columns:
            rejected.append({"field": sub_field_key, "col": excel_col, "reason": f"Column {excel_col} does not exist"})
            continue
        
        # Get column profile
        profile = column_profiles.get(excel_col)
        if not profile:
            warnings.append({"field": sub_field_key, "col": excel_col, "reason": "No profile data (column may be empty)"})
            validated[sub_field_key] = excel_col  # Accept with warning
            continue
        
        # Validate based on expected field type
        is_valid = True
        reason = ""
        
        # Port fields should have port-like data
        if sf_lower in PORT_LIKE_FIELDS:
            if profile.type_hint == "money" and profile.numeric_ratio > 0.8:
                is_valid = False
                reason = f"Expected port/location data but column is {profile.numeric_ratio:.0%} numeric. Sample: {profile.sample[:3]}"
        
        # Rate fields (20DC, 40DC, 40HC, etc.) should have numeric data
        rate_patterns = {"20dc", "40dc", "40hc", "40hq", "20rf", "45hq", "40rq", "20gp", "40gp", "rate", "amount"}
        if sf_lower in rate_patterns or any(rp in sf_lower for rp in ("dc", "hc", "hq", "rf", "rq", "gp")):
            if profile.numeric_ratio < 0.3:
                is_valid = False
                reason = f"Expected numeric rate data but column is only {profile.numeric_ratio:.0%} numeric. Sample: {profile.sample[:3]}"
        
        # Date fields should have date-like data
        date_fields = {"start_date", "end_date", "effective_date", "expiry_date", "validity"}
        if sf_lower in date_fields:
            date_count = sum(1 for s in profile.sample if is_date_like(s))
            if date_count == 0 and profile.type_hint != "date":
                is_valid = False
                reason = f"Expected date data but found type '{profile.type_hint}'. Sample: {profile.sample[:3]}"
        
        # Currency field should have currency codes
        if sf_lower == "currency":
            if profile.type_hint not in ("currency", "text"):
                warnings.append({"field": sub_field_key, "col": excel_col, "reason": f"Currency column has type '{profile.type_hint}'"})
        
        if is_valid:
            validated[sub_field_key] = excel_col
        else:
            rejected.append({"field": sub_field_key, "col": excel_col, "reason": reason})
            logger.warning(f"[Validator] Rejected mapping {sub_field_key} → {excel_col}: {reason}")
    
    result = {
        "validated_mapping": validated,
        "rejected": rejected,
        "warnings": warnings
    }
    
    logger.info(f"[Validator] Block {block.block_id}: accepted={len(validated)}, rejected={len(rejected)}")
    return result


# ──────────────────────────────────────────────
# Step 6: Field-Aware Expansion
# ──────────────────────────────────────────────

def should_expand_value(field_key: str, value: str) -> bool:
    """
    Determine if a cell value should be expanded into multiple rows.
    Only geography-type fields with multi-code patterns are expandable.
    """
    # Expandable fields: port codes AND geography text (destination, commodity)
    expandable = PORT_LIKE_FIELDS | GEOGRAPHY_TEXT_FIELDS
    if field_key.strip().lower() not in expandable:
        return False
    
    val = str(value).strip()
    if not val or "/" not in val:
        return False
    
    # Never expand dates
    if is_date_like(val):
        return False
    
    # Never expand if value looks like money
    if is_money_like(val.replace("/", "")):
        return False
    
    # Never expand service modes (CY/CY)
    if is_service_mode(val):
        return False
    
    # Split and check: at least some parts must be non-numeric
    parts = [p.strip() for p in val.split("/") if p.strip()]
    if len(parts) <= 1:
        return False
    
    # If ALL parts are purely numeric → don't expand (date fragments)
    if all(re.match(r'^[\d\.,\s]+$', p) for p in parts):
        return False
    
    return True


def field_aware_expand(rows: List[Dict], sub_field_keys: List[str]) -> List[Dict]:
    """
    Expand rows where geography-type sub_fields contain slash-separated values.
    Non-geography fields are never expanded.
    
    Args:
        rows: list of row dicts {sub_field_key: {"value": "...", ...}}
        sub_field_keys: list of all sub_field keys for this table
    
    Returns: expanded list of rows
    """
    import copy
    
    expanded = []
    expansion_count = 0
    
    for row_data in rows:
        slash_fields = {}
        max_parts = 1
        
        for sk in sub_field_keys:
            if sk not in row_data or not isinstance(row_data[sk], dict):
                continue
            cell_val = row_data[sk].get("value", "")
            if isinstance(cell_val, str) and should_expand_value(sk, cell_val):
                parts = [p.strip() for p in cell_val.split("/") if p.strip()]
                slash_fields[sk] = parts
                max_parts = max(max_parts, len(parts))
        
        if not slash_fields:
            expanded.append(row_data)
        else:
            for i in range(max_parts):
                new_row = copy.deepcopy(row_data)
                for sk, parts in slash_fields.items():
                    idx = min(i, len(parts) - 1)
                    new_row[sk]["value"] = parts[idx]
                    new_row[sk]["_modifier"] = "Expanded from delimiter"
                    new_row[sk]["_modified_from"] = row_data[sk].get("value", "")
                expanded.append(new_row)
            expansion_count += 1
    
    if expansion_count > 0:
        logger.info(f"[Expander] Expanded {expansion_count} rows → {len(expanded)} total")
    
    return expanded


# ──────────────────────────────────────────────
# Utility: Build Block Summary for LLM
# ──────────────────────────────────────────────

def build_block_summary(
    block: BlockInfo,
    row_classifications: List[RowClassification],
    column_profiles: Dict[str, ColumnProfile],
    block_context: Dict[str, str],
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Build a structured summary of a block for the LLM to interpret.
    LLM sees this summary instead of raw data.
    """
    data_cols = [c for c in df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]
    
    # Get header row values
    header_rows = [rc for rc in row_classifications if rc.row_type == "header"]
    header_values = {}
    if header_rows:
        h_rid = header_rows[0].row_id
        h_row = df[df["row_id"] == h_rid]
        if not h_row.empty:
            for c in data_cols:
                val = str(h_row.iloc[0][c]).strip() if pd.notna(h_row.iloc[0][c]) else ""
                if val and val.lower() != "nan":
                    header_values[c] = val
    
    # Get first 3 data rows as sample
    data_rows = [rc for rc in row_classifications if rc.row_type == "data"]
    sample_rows = []
    for rc in data_rows[:3]:
        row = df[df["row_id"] == rc.row_id]
        if not row.empty:
            row_dict = {}
            for c in data_cols:
                val = str(row.iloc[0][c]).strip() if pd.notna(row.iloc[0][c]) else ""
                if val and val.lower() != "nan":
                    row_dict[c] = val
            sample_rows.append(row_dict)
    
    return {
        "sheet": block.sheet_name,
        "block_id": block.block_id,
        "row_range": f"{block.row_start}-{block.row_end}",
        "row_count": block.row_count,
        "block_type": block.block_type,
        "header_candidates": {c: v for c, v in header_values.items()},
        "data_sample": sample_rows,
        "column_profiles": {
            c: {"type_hint": p.type_hint, "sample": p.sample[:3]}
            for c, p in column_profiles.items()
        },
        "detected_context": block_context,
        "row_classification_summary": {
            "header": len([r for r in row_classifications if r.row_type == "header"]),
            "data": len([r for r in row_classifications if r.row_type == "data"]),
            "group_label": len([r for r in row_classifications if r.row_type == "group_label"]),
            "context": len([r for r in row_classifications if r.row_type == "context"]),
            "remark": len([r for r in row_classifications if r.row_type == "remark"]),
        }
    }
