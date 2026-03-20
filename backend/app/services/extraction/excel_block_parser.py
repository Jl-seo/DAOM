"""
Excel Block Parser V2 — Python-only structural pre-parser for Excel extraction.

Architecture: Block-first + Validator-first
LLM sees structure summaries, not raw data. Python validates all LLM suggestions.

Pipeline:
  1. detect_blocks()       → 2D physical block segmentation (blank rows + structure transitions)
  2. classify_rows()       → row role classification with multi-row header cluster
  3. profile_columns()     → column type hints + samples (strict + loose)
  4. extract_block_context()→ multi-level context with label proximity
  5. validate_column_mapping() → field-semantic aware validation
  6. field_aware_expand()  → multi-delimiter type-checked expansion
"""
import re
import copy
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Set, Tuple
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
    block_type: str         # "table" | "metadata" | "note"
    col_count: int          # count of non-empty columns
    numeric_ratio: float    # ratio of numeric values in data cells
    row_count: int = 0
    col_start: str = ""         # first active column letter (e.g., "B")
    col_end: str = ""           # last active column letter (e.g., "N")
    active_columns: list = field(default_factory=list)  # ["B", "C", "D", ...]

@dataclass
class RowClassification:
    row_id: int
    row_type: str           # "header" | "data" | "group_label" | "context" | "remark" | "continuation"
    confidence: float = 0.8
    group_label: str = ""   # for group_label rows, the label value

@dataclass
class ColumnProfile:
    column_letter: str
    type_hint: str          # "port_code" | "money" | "date" | "text" | "mixed" | "currency" | "service_mode"
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
# Validity range: "12/1~12/7", "2025.12.01 - 2025.12.31"
VALIDITY_RANGE_PATTERN = re.compile(
    r'(\d{1,4}[/\-\.]\d{1,2}[/\-\.]?\d{0,4})\s*[~\-–—to]+\s*(\d{1,4}[/\-\.]\d{1,2}[/\-\.]?\d{0,4})',
    re.IGNORECASE
)
# Route phrase: FROM PUSAN, → USWC
ROUTE_PATTERN = re.compile(r'(FROM|→|->|⟶|TO)\s+', re.IGNORECASE)
VIA_PATTERN = re.compile(r'(VIA|T/S|TRANSSHIP|RELAY)\s+', re.IGNORECASE)

# Keyword sets
REMARK_KEYWORDS = frozenset({'note', 'remark', 'remarks', '※', 'n/a', 'subject to', 'inclusive',
                              'excluded', 'validity', 'above rate', 'surcharge'})
CONTEXT_KEYWORDS = frozenset({'effective', 'expiry', 'validity', 'currency', 'carrier', 'service',
                              'vessel', 'voyage', 'contract', 'amendment', 'rate', 'scope'})
GROUP_KEYWORDS = frozenset({'ipi', 'local', 'mlb', 'inland', 'transit', 'direct', 'transship',
                            'canada', 'mexico', 'europe', 'asia'})
# Labels that indicate POL/POD/etc
POL_LABELS = frozenset({'origin', 'pol', 'port of loading', 'loading port', '출발항', '적항', 'from'})
POD_LABELS = frozenset({'pod', 'port of discharge', 'discharge port', '양하항', '도착항'})
DEST_LABELS = frozenset({'destination', 'dest', 'final destination', '최종목적지', 'delivery', 'del'})

# Semantic type mapping from dictionary attribute
DICTIONARY_TO_SEMANTIC = {
    "port": "port_code",
    "charge": "money",
    "currency": "currency",
    "country": "text",
    "commodity": "text",
    "service": "text",
}


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


def _get_data_cols(df: pd.DataFrame) -> list:
    """Return data columns (exclude metadata columns)."""
    return [c for c in df.columns if c not in ('row_id', 'local_row_id', '_sheet_name', '_sheet_name_lower')]


def _row_values(row, data_cols: list) -> list:
    """Extract non-empty string values from a row."""
    vals = []
    for c in data_cols:
        v = str(row[c]).strip() if pd.notna(row[c]) else ""
        vals.append("" if v.lower() == "nan" else v)
    return vals


def _row_signature(vals: list) -> dict:
    """Compute a fingerprint of a row for transition detection."""
    non_empty = [v for v in vals if v]
    non_empty_count = len(non_empty)
    if non_empty_count == 0:
        return {"empty": True, "numeric_ratio": 0, "non_empty_count": 0, "non_empty_cols": set()}
    numeric_count = sum(1 for v in non_empty if is_money_like(v))
    non_empty_cols = {i for i, v in enumerate(vals) if v}
    return {
        "empty": False,
        "numeric_ratio": numeric_count / non_empty_count,
        "non_empty_count": non_empty_count,
        "non_empty_cols": non_empty_cols,
        "avg_len": sum(len(v) for v in non_empty) / non_empty_count,
    }


# ──────────────────────────────────────────────
# Step 1: Block Detection (V2 — structure-aware)
# ──────────────────────────────────────────────

def detect_blocks(df: pd.DataFrame, sheet_name: str, start_block_id: int = 1) -> List[BlockInfo]:
    """
    Segment a sheet into physical blocks using multiple signals:
    1. 2+ consecutive blank rows (original criterion)
    2. Header signature re-detection (text-dominant row after data rows)
    3. Active column set change (>50% different columns)
    4. Numeric ratio sharp break (>0.5 delta)

    Args:
        start_block_id: Starting block_id counter (use global counter across sheets
                        to prevent ID collisions in all_blocks_meta dict).
    """
    sheet_df = df[df["_sheet_name"] == sheet_name].copy() if "_sheet_name" in df.columns else df.copy()
    if sheet_df.empty:
        return []

    data_cols = _get_data_cols(sheet_df)
    blocks: List[BlockInfo] = []
    block_id = start_block_id

    # Pre-compute all row signatures
    row_sigs = []
    row_ids = []
    for _, row in sheet_df.iterrows():
        vals = _row_values(row, data_cols)
        row_ids.append(int(row["row_id"]))
        row_sigs.append(_row_signature(vals))

    current_start_idx = None
    consecutive_blanks = 0

    # Running stats for transition detection
    recent_numeric_ratios = []  # last 5 data rows
    recent_col_sets = []        # last 3 active column sets

    for i, sig in enumerate(row_sigs):
        if sig["empty"]:
            consecutive_blanks += 1
            if consecutive_blanks >= 2 and current_start_idx is not None:
                # Close block before blank region
                block_end_idx = i - consecutive_blanks
                if block_end_idx >= current_start_idx:
                    blocks.append(_build_block_info_v2(
                        sheet_name, block_id, current_start_idx, block_end_idx,
                        row_ids, row_sigs, sheet_df, data_cols
                    ))
                    block_id += 1
                current_start_idx = None
                recent_numeric_ratios.clear()
                recent_col_sets.clear()
            continue

        # Non-blank row
        if current_start_idx is None:
            current_start_idx = i
            consecutive_blanks = 0
            recent_numeric_ratios.clear()
            recent_col_sets.clear()
            recent_numeric_ratios.append(sig["numeric_ratio"])
            recent_col_sets.append(sig["non_empty_cols"])
            continue

        consecutive_blanks = 0

        # Check structure transition signals
        should_split = False

        # Signal A: Header re-detection
        # A text-dominant row (low numeric, ≥3 non-empty) appearing after data rows
        if (len(recent_numeric_ratios) >= 3
                and sum(recent_numeric_ratios[-3:]) / 3 > 0.3  # recent rows were data-like
                and sig["numeric_ratio"] < 0.2
                and sig["non_empty_count"] >= 3
                and sig.get("avg_len", 0) < 20):  # header cells tend to be short
            should_split = True
            logger.debug(f"[BlockDetect] Header re-detected at row {row_ids[i]}")

        # Signal B: Active column set change (>50% different)
        if recent_col_sets and not should_split:
            prev_cols = recent_col_sets[-1]
            curr_cols = sig["non_empty_cols"]
            if prev_cols and curr_cols:
                overlap = len(prev_cols & curr_cols)
                union = len(prev_cols | curr_cols)
                jaccard = overlap / max(1, union)
                if jaccard < 0.4 and len(curr_cols) >= 3:
                    should_split = True
                    logger.debug(f"[BlockDetect] Column shift at row {row_ids[i]} (jaccard={jaccard:.2f})")

        # Signal C: Numeric ratio sharp break
        if recent_numeric_ratios and not should_split:
            avg_recent = sum(recent_numeric_ratios[-5:]) / len(recent_numeric_ratios[-5:])
            delta = abs(sig["numeric_ratio"] - avg_recent)
            if delta > 0.5 and sig["non_empty_count"] >= 3:
                # Only split if this isn't a single outlier — check next row too
                if i + 1 < len(row_sigs) and not row_sigs[i + 1]["empty"]:
                    next_delta = abs(row_sigs[i + 1]["numeric_ratio"] - avg_recent)
                    if next_delta > 0.3:
                        should_split = True
                        logger.debug(f"[BlockDetect] Numeric break at row {row_ids[i]} (delta={delta:.2f})")

        if should_split:
            # Close current block at previous row
            block_end_idx = i - 1
            if block_end_idx >= current_start_idx:
                blocks.append(_build_block_info_v2(
                    sheet_name, block_id, current_start_idx, block_end_idx,
                    row_ids, row_sigs, sheet_df, data_cols
                ))
                block_id += 1
            current_start_idx = i
            recent_numeric_ratios.clear()
            recent_col_sets.clear()

        recent_numeric_ratios.append(sig["numeric_ratio"])
        recent_col_sets.append(sig["non_empty_cols"])

    # Close last block
    if current_start_idx is not None:
        block_end_idx = len(row_ids) - 1
        blocks.append(_build_block_info_v2(
            sheet_name, block_id, current_start_idx, block_end_idx,
            row_ids, row_sigs, sheet_df, data_cols
        ))

    logger.info(f"[BlockParser] Sheet '{sheet_name}': detected {len(blocks)} blocks")
    return blocks


def merge_similar_blocks(blocks: List[BlockInfo], df: pd.DataFrame) -> List[BlockInfo]:
    """Post-detection merge pass: combine adjacent table blocks with similar structure.

    Problem: detect_blocks splits on blank rows. Rate tables with region separators
    get fragmented (e.g., Main Ports: 24 blocks for one logical table).

    Key insight: blank-row separators become 1-row 'note' or 'metadata' blocks.
    We skip these separators and merge the table blocks around them.

    Merge conditions:
      - Same sheet, both block_type == 'table'
      - Similar active columns (Jaccard >= 0.5)
      - Gap between them is ≤ 10 rows (may include separator blocks)
    """
    if len(blocks) <= 1:
        return blocks

    merged: List[BlockInfo] = []
    current = None  # current merging candidate (table block)

    i = 0
    while i < len(blocks):
        b = blocks[i]

        # If no active merge candidate, start one
        if current is None:
            current = b
            i += 1
            continue

        # Only merge table-type blocks
        if current.block_type != "table":
            merged.append(current)
            current = b
            i += 1
            continue

        # If this block is a small separator (note/metadata, ≤2 rows), skip it
        # Scan forward through ALL consecutive separators to find next table block
        if b.block_type != "table" and b.row_count <= 2 and b.sheet_name == current.sheet_name:
            # Scan ahead for next table block, skipping all separators
            j = i + 1
            while j < len(blocks) and blocks[j].block_type != "table" and blocks[j].row_count <= 2 and blocks[j].sheet_name == current.sheet_name:
                j += 1
            if j < len(blocks) and blocks[j].block_type == "table" and blocks[j].sheet_name == current.sheet_name:
                i = j  # skip all separators, process next table block
                continue
            else:
                # No next table block, finalize current
                merged.append(current)
                current = b
                i += 1
                continue

        # Both are table blocks — check merge conditions
        if b.block_type == "table" and b.sheet_name == current.sheet_name:
            gap = b.row_start - current.row_end
            if gap <= 10:
                cols_a = set(current.active_columns)
                cols_b = set(b.active_columns)
                if cols_a and cols_b:
                    overlap = len(cols_a & cols_b)
                    union_size = len(cols_a | cols_b)
                    jaccard = overlap / max(1, union_size)

                    if jaccard >= 0.5:
                        # Merge
                        merged_cols = sorted(set(current.active_columns) | set(b.active_columns))
                        current = BlockInfo(
                            sheet_name=current.sheet_name,
                            block_id=current.block_id,
                            row_start=current.row_start,
                            row_end=b.row_end,
                            block_type="table",
                            col_count=len(merged_cols),
                            numeric_ratio=round((current.numeric_ratio + b.numeric_ratio) / 2, 3),
                            row_count=(b.row_end - current.row_start + 1),
                            col_start=merged_cols[0] if merged_cols else "",
                            col_end=merged_cols[-1] if merged_cols else "",
                            active_columns=merged_cols,
                        )
                        i += 1
                        continue

        # No merge — finalize current, start new candidate
        merged.append(current)
        current = b
        i += 1

    if current is not None:
        merged.append(current)

    if len(merged) < len(blocks):
        logger.info(f"[BlockMerge] {blocks[0].sheet_name}: {len(blocks)} blocks → {len(merged)} after merge")

    return merged


def _build_block_info_v2(sheet_name: str, block_id: int, start_idx: int, end_idx: int,
                         row_ids: list, row_sigs: list, sheet_df: pd.DataFrame,
                         data_cols: list) -> BlockInfo:
    """Build BlockInfo with active column span detection."""
    row_start = row_ids[start_idx]
    row_end = row_ids[end_idx]
    row_count = end_idx - start_idx + 1

    # Compute active columns across the block
    all_active_cols: Set[int] = set()
    total_cells = 0
    numeric_cells = 0

    for idx in range(start_idx, end_idx + 1):
        sig = row_sigs[idx]
        if not sig["empty"]:
            all_active_cols |= sig["non_empty_cols"]

    # Count numeric cells from actual data
    block_df = sheet_df[(sheet_df["row_id"] >= row_start) & (sheet_df["row_id"] <= row_end)]
    for c in data_cols:
        for val in block_df[c]:
            if pd.notna(val) and str(val).strip() not in ("", "nan"):
                total_cells += 1
                if is_money_like(str(val)):
                    numeric_cells += 1

    numeric_ratio = numeric_cells / max(1, total_cells)
    col_count = len(all_active_cols)

    # Map column indices to column letters
    active_col_letters = []
    for ci in sorted(all_active_cols):
        if ci < len(data_cols):
            active_col_letters.append(data_cols[ci])

    col_start = active_col_letters[0] if active_col_letters else ""
    col_end = active_col_letters[-1] if active_col_letters else ""

    # Determine block type
    if row_count <= 3 and col_count <= 3:
        block_type = "metadata"
    elif numeric_ratio > 0.2 and col_count >= 3 and row_count >= 3:
        block_type = "table"
    elif row_count <= 5:
        block_type = "note"
    else:
        block_type = "table"

    return BlockInfo(
        sheet_name=sheet_name,
        block_id=block_id,
        row_start=row_start,
        row_end=row_end,
        block_type=block_type,
        col_count=col_count,
        numeric_ratio=round(numeric_ratio, 3),
        row_count=row_count,
        col_start=col_start,
        col_end=col_end,
        active_columns=active_col_letters,
    )


# ──────────────────────────────────────────────
# Step 2: Row Classification (V2 — multi-row header)
# ──────────────────────────────────────────────

def classify_rows(df: pd.DataFrame, block: BlockInfo) -> List[RowClassification]:
    """
    Classify each row in a block.

    V2 improvements:
    - Multi-row header cluster (consecutive text-dominant rows at block start)
    - Continuation row type (1-2 cells, adjacent to data row, same columns)
    - Group label inheritance tracking
    """
    data_cols = _get_data_cols(df)
    block_df = df[(df["row_id"] >= block.row_start) & (df["row_id"] <= block.row_end)]

    classifications: List[RowClassification] = []
    header_cluster_ended = False
    last_row_type = None
    current_group_label = ""

    for row_idx, (_, row) in enumerate(block_df.iterrows()):
        rid = int(row["row_id"])
        vals = _row_values(row, data_cols)
        non_empty = [v for v in vals if v]
        non_empty_count = len(non_empty)

        if non_empty_count == 0:
            classifications.append(RowClassification(rid, "remark", 0.5))
            last_row_type = "remark"
            continue

        # Compute row properties
        numeric_count = sum(1 for v in non_empty if is_money_like(v))
        numeric_ratio = numeric_count / non_empty_count
        avg_len = sum(len(v) for v in non_empty) / non_empty_count
        has_remark_kw = any(kw in " ".join(non_empty).lower() for kw in REMARK_KEYWORDS)
        has_context_kw = any(kw in " ".join(non_empty).lower() for kw in CONTEXT_KEYWORDS)
        has_group_kw = any(kw in " ".join(non_empty).lower() for kw in GROUP_KEYWORDS)
        has_ports = any(is_port_like(v) for v in non_empty)

        row_type = "data"
        confidence = 0.7

        # ── Header cluster detection ──
        # Within first 5 rows: text-dominant, ≥3 non-empty, short values
        if not header_cluster_ended and row_idx <= 4:
            if numeric_ratio < 0.2 and non_empty_count >= 3 and avg_len < 25:
                row_type = "header"
                confidence = 0.9
            elif numeric_ratio < 0.3 and non_empty_count >= 2 and avg_len < 20 and row_idx <= 1:
                # Possible sub-header (merged title above actual columns)
                row_type = "header"
                confidence = 0.75
            else:
                header_cluster_ended = True
        elif not header_cluster_ended:
            header_cluster_ended = True

        # ── Group label: 1-2 cells filled, rest empty ──
        if row_type == "data" and non_empty_count <= 2 and len(data_cols) >= 5:
            if has_group_kw or (non_empty_count == 1 and avg_len < 30 and numeric_ratio == 0):
                row_type = "group_label"
                confidence = 0.85
                current_group_label = " ".join(non_empty).strip()

        # ── Context: date/currency/validity keywords ──
        if row_type == "data" and has_context_kw and numeric_ratio < 0.3:
            row_type = "context"
            confidence = 0.8

        # ── Remark: long text or remark keywords ──
        if row_type == "data" and has_remark_kw and avg_len > 30:
            row_type = "remark"
            confidence = 0.7

        # ── Continuation: 1-2 cells, previous was data ──
        if (row_type == "data" and non_empty_count <= 2
                and last_row_type == "data" and not has_ports
                and numeric_ratio == 0 and avg_len > 15):
            row_type = "continuation"
            confidence = 0.7

        # ── Data validation ──
        if row_type == "data":
            if numeric_ratio > 0.2 or has_ports:
                confidence = 0.9
            else:
                confidence = 0.6

        cls = RowClassification(rid, row_type, round(confidence, 2))
        if row_type == "group_label":
            cls.group_label = current_group_label
        classifications.append(cls)
        last_row_type = row_type

    return classifications


# ──────────────────────────────────────────────
# Step 3: Column Profiling (V2 — strict + loose)
# ──────────────────────────────────────────────

def profile_columns(df: pd.DataFrame, block: BlockInfo,
                    row_classifications: List[RowClassification]) -> Dict[str, ColumnProfile]:
    """
    Profile each column's data type.

    V2: Produces profiles from data rows primarily, but uses block-wide
    sampling as fallback to prevent total collapse if row classification
    slightly misses.
    """
    data_cols = block.active_columns if block.active_columns else _get_data_cols(df)
    data_row_ids = {rc.row_id for rc in row_classifications if rc.row_type == "data"}

    # Strict: data rows only. Loose: entire block (fallback).
    block_df = df[(df["row_id"] >= block.row_start) & (df["row_id"] <= block.row_end)]
    data_df = block_df[block_df["row_id"].isin(data_row_ids)] if data_row_ids else block_df

    profiles: Dict[str, ColumnProfile] = {}

    for col in data_cols:
        if col not in df.columns:
            continue

        # Collect values from strict data rows
        values = []
        for val in data_df[col]:
            if pd.notna(val):
                s = str(val).strip()
                if s and s.lower() != "nan":
                    values.append(s)

        # Fallback: if strict gives < 3 values, also sample from block-wide
        if len(values) < 3:
            for val in block_df[col]:
                if pd.notna(val):
                    s = str(val).strip()
                    if s and s.lower() != "nan" and s not in values:
                        values.append(s)
                        if len(values) >= 5:
                            break

        if not values:
            continue

        # Count types
        total = len(values)
        port_count = sum(1 for v in values if is_port_like(v))
        date_count = sum(1 for v in values if is_date_like(v))
        money_count = sum(1 for v in values if is_money_like(v))
        currency_count = sum(1 for v in values if is_currency_code(v))
        service_count = sum(1 for v in values if is_service_mode(v))

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
        else:
            type_hint = best_type

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
# Step 4: Block Context Extraction (V2 — label proximity)
# ──────────────────────────────────────────────

def extract_block_context(df: pd.DataFrame, block: BlockInfo,
                          row_classifications: List[RowClassification]) -> Dict[str, Any]:
    """
    Extract inheritable context values from metadata/context/group_label rows.

    V2 improvements:
    - Label proximity for port assignment (not blind "first port = POL")
    - Validity range parsing (date~date patterns)
    - Route phrase detection (FROM/TO/VIA)
    - Group row inheritance tracking
    """
    context_row_ids = {rc.row_id for rc in row_classifications if rc.row_type in ("context", "group_label")}
    data_cols = _get_data_cols(df)

    context: Dict[str, Any] = {}
    group_labels = []

    # Collect group labels
    for rc in row_classifications:
        if rc.row_type == "group_label" and rc.group_label:
            group_labels.append(rc.group_label)

    if group_labels:
        context["_group_labels"] = group_labels

    # Scan ONLY context + group_label rows for key-value pairs.
    # IMPORTANT: Do NOT scan header rows — they contain column names side-by-side
    # (e.g., POL | POD | POR), which causes label proximity to read the next
    # header text as a value (POL → "POD").
    scan_row_ids = context_row_ids
    for _, row in df[df["row_id"].isin(scan_row_ids)].iterrows():
        for ci, c in enumerate(data_cols):
            val = str(row[c]).strip() if pd.notna(row[c]) else ""
            if not val or val.lower() == "nan":
                continue

            val_lower = val.lower()

            # ── Label proximity: look at THIS cell as label, NEXT cell as value ──
            next_val = ""
            if ci + 1 < len(data_cols):
                nv = row[data_cols[ci + 1]] if data_cols[ci + 1] in row.index else None
                next_val = str(nv).strip() if pd.notna(nv) else ""
                if next_val.lower() == "nan":
                    next_val = ""

            # Port assignment via label proximity
            if val_lower in POL_LABELS and next_val:
                context["POL"] = next_val
            elif val_lower in POD_LABELS and next_val:
                context["POD"] = next_val
            elif val_lower in DEST_LABELS and next_val:
                context["Destination"] = next_val

            # Currency detection
            if is_currency_code(val):
                context["Currency"] = val.upper()
            elif "currency" in val_lower and next_val and is_currency_code(next_val):
                context["Currency"] = next_val.upper()

            # Date key-value pairs
            if ("effective" in val_lower or "start" in val_lower) and next_val and is_date_like(next_val):
                context["Start_Date"] = _normalize_date(next_val)
            if ("expiry" in val_lower or "end" in val_lower) and next_val and is_date_like(next_val):
                context["End_Date"] = _normalize_date(next_val)

            # Validity range inline: "VALIDITY : 12/1~12/7"
            range_match = VALIDITY_RANGE_PATTERN.search(val)
            if range_match:
                context["Start_Date"] = _normalize_date(range_match.group(1))
                context["End_Date"] = _normalize_date(range_match.group(2))

            # Carrier
            if "carrier" in val_lower and next_val and next_val.lower() != "nan":
                context["Carrier"] = next_val

            # Service / Scope
            if ("service" in val_lower or "scope" in val_lower) and next_val:
                context["Service"] = next_val

            # Route phrase: "FROM PUSAN" / "PUSAN → USWC"
            route_match = ROUTE_PATTERN.search(val)
            if route_match:
                after = val[route_match.end():].strip()
                if after and "POL" not in context:
                    if "from" in route_match.group(1).lower():
                        context["POL"] = after
                    elif "to" in route_match.group(1).lower():
                        context["Destination"] = after

            # VIA / T/S detection
            via_match = VIA_PATTERN.search(val)
            if via_match:
                after = val[via_match.end():].strip()
                if after:
                    context["Via_Port"] = after

        # Also check standalone port values ONLY if no label-based assignment happened
        for ci, c in enumerate(data_cols):
            val = str(row[c]).strip() if pd.notna(row[c]) else ""
            if not val or val.lower() == "nan":
                continue
            if is_port_like(val) and "POL" not in context and "POD" not in context:
                # Only assign to _unresolved — let LLM decide
                if "_unresolved_ports" not in context:
                    context["_unresolved_ports"] = []
                if val not in context["_unresolved_ports"]:
                    context["_unresolved_ports"].append(val)

    if context:
        logger.info(f"[BlockParser] Block {block.block_id} context: {context}")

    return context


def _normalize_date(val: str) -> str:
    """Normalize date value, including Excel serial dates."""
    val = val.strip()
    if SERIAL_DATE_PATTERN.match(val):
        try:
            from datetime import datetime, timedelta
            serial = int(val)
            dt = datetime(1899, 12, 30) + timedelta(days=serial)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return val
    return val


# ──────────────────────────────────────────────
# Step 5: Column Mapping Validator (V2 — field-semantic aware)
# ──────────────────────────────────────────────

def validate_column_mapping(
    df: pd.DataFrame,
    block: BlockInfo,
    llm_mapping: Dict[str, str],
    row_classifications: List[RowClassification],
    column_profiles: Dict[str, ColumnProfile],
    sub_field_defs: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Validate LLM's column mapping against actual data patterns.

    V2: Uses sub_field dictionary attributes for field-semantic validation.

    Args:
        sub_field_defs: List of sub_field dicts from model schema,
                        e.g. [{"key": "pol", "dictionary": "port"}, ...]
    """
    data_row_ids = {rc.row_id for rc in row_classifications if rc.row_type == "data"}
    block_df = df[df["row_id"].isin(data_row_ids)]

    validated = {}
    rejected = []
    warnings = []

    # Build expected-type map from sub_field definitions
    expected_types = {}
    if sub_field_defs:
        for sf in sub_field_defs:
            sf_key = sf.get("key", "").strip().lower()
            dictionary = sf.get("dictionary", "")
            sf_type = sf.get("type", "string")
            if dictionary:
                expected_types[sf_key] = DICTIONARY_TO_SEMANTIC.get(dictionary, "text")
            elif sf_type == "date":
                expected_types[sf_key] = "date"
            elif sf_type in ("number", "integer", "float"):
                expected_types[sf_key] = "money"

    for sub_field_key, excel_col in llm_mapping.items():
        sf_lower = sub_field_key.strip().lower()

        # Check column exists
        if excel_col not in df.columns:
            rejected.append({"field": sub_field_key, "col": excel_col,
                           "reason": f"Column {excel_col} does not exist"})
            continue

        profile = column_profiles.get(excel_col)
        if not profile:
            warnings.append({"field": sub_field_key, "col": excel_col,
                           "reason": "No profile data (column may be empty)"})
            validated[sub_field_key] = excel_col
            continue

        is_valid = True
        reason = ""

        # ── Field-semantic cross-validation ──
        expected = expected_types.get(sf_lower)
        if expected:
            actual = profile.type_hint

            # port_code expected but column is all money → REJECT
            if expected == "port_code" and actual == "money" and profile.numeric_ratio > 0.8:
                is_valid = False
                reason = (f"Expected port/geography data (dictionary=port) "
                         f"but column is {profile.numeric_ratio:.0%} numeric. "
                         f"Sample: {profile.sample[:3]}")

            # money expected but column is all text/port → REJECT
            elif expected == "money" and actual in ("port_code", "text") and profile.numeric_ratio < 0.3:
                is_valid = False
                reason = (f"Expected numeric rate data (dictionary=charge) "
                         f"but column is only {profile.numeric_ratio:.0%} numeric. "
                         f"Sample: {profile.sample[:3]}")

            # date expected but no dates found → REJECT
            elif expected == "date" and actual != "date":
                date_count = sum(1 for s in profile.sample if is_date_like(s))
                if date_count == 0:
                    is_valid = False
                    reason = f"Expected date data but found type '{actual}'. Sample: {profile.sample[:3]}"

            # currency expected but wrong type → WARN
            elif expected == "currency" and actual not in ("currency", "text"):
                warnings.append({"field": sub_field_key, "col": excel_col,
                               "reason": f"Currency column has type '{actual}'"})

        else:
            # No schema info — fall back to data-driven anomaly detection
            if profile.type_hint == "port_code" and profile.numeric_ratio > 0.8:
                warnings.append({"field": sub_field_key, "col": excel_col,
                               "reason": f"Column typed as port_code but {profile.numeric_ratio:.0%} numeric"})

            if profile.type_hint == "money" and profile.numeric_ratio > 0.8:
                if profile.sample and all(is_port_like(s) for s in profile.sample[:3] if s):
                    is_valid = False
                    reason = f"Column is {profile.numeric_ratio:.0%} numeric but samples are port-like: {profile.sample[:3]}"

        if is_valid:
            validated[sub_field_key] = excel_col
        else:
            rejected.append({"field": sub_field_key, "col": excel_col, "reason": reason})
            logger.warning(f"[Validator] Rejected {sub_field_key} → {excel_col}: {reason}")

    # ── Cross-field semantic validation (domain-specific) ──
    # Rule 1: POD ≠ Destination — same column means LLM conflated them
    pod_col = validated.get("pod") or validated.get("POD")
    dest_col = validated.get("destination") or validated.get("Destination") or validated.get("dest")
    if pod_col and dest_col and pod_col == dest_col:
        # Keep POD (more common), warn about Destination
        dest_key = next(k for k in validated if k.lower() in ("destination", "dest"))
        warnings.append({"field": dest_key, "col": dest_col,
                        "reason": "POD and Destination mapped to same column — removing Destination"})
        del validated[dest_key]

    # Rule 2: Equipment header detection — consecutive money columns with equipment-like headers
    #         suggests a rate matrix layout, log for future matrix executor use
    money_mapped = [(sf, col) for sf, col in validated.items()
                    if column_profiles.get(col, ColumnProfile("", "")).type_hint == "money"]
    if len(money_mapped) >= 3:
        header_rows_data = [rc for rc in row_classifications if rc.row_type == "header"]
        if header_rows_data:
            h_row = df[df["row_id"] == header_rows_data[-1].row_id]  # Use lowest header row
            if not h_row.empty:
                equip_pattern = re.compile(r'^\d{2}(GP|HC|DC|RF|OT|FR|TK|NOR)\b', re.IGNORECASE)
                equip_cols = []
                for sf, col in money_mapped:
                    if col in h_row.columns:
                        header_val = str(h_row.iloc[0][col]).strip() if pd.notna(h_row.iloc[0][col]) else ""
                        if equip_pattern.match(header_val):
                            equip_cols.append((sf, col, header_val))
                if equip_cols:
                    logger.info(f"[Validator] Rate matrix detected: {len(equip_cols)} equipment columns: "
                               f"{[(c[2]) for c in equip_cols]}")

    return {"validated_mapping": validated, "rejected": rejected, "warnings": warnings}


# ──────────────────────────────────────────────
# Step 6: Field-Aware Expansion (V2 — multi-delimiter)
# ──────────────────────────────────────────────

def should_expand_value(field_key: str, value: str) -> bool:
    """
    Determine if a cell value should be expanded into multiple rows.
    Decision is DATA-DRIVEN — no hardcoded field name lists.
    Supports / and , as delimiters.
    """
    val = str(value).strip()
    if not val:
        return False

    # Pick delimiter
    delimiter = None
    if "/" in val:
        delimiter = "/"
    elif "," in val and not re.match(r'^[A-Z\s]+,\s*[A-Z]{2}$', val):
        # Comma — but skip "CITY, STATE" patterns (e.g., "LOS ANGELES, CA")
        delimiter = ","
    else:
        return False

    # Never expand dates
    if is_date_like(val):
        return False

    # Never expand money
    if is_money_like(val.replace(delimiter, "").replace(" ", "")):
        return False

    # Never expand service modes (CY/CY)
    if is_service_mode(val):
        return False

    # Split and analyze
    parts = [p.strip() for p in val.split(delimiter) if p.strip()]
    if len(parts) <= 1:
        return False

    # All numeric → don't expand
    if all(re.match(r'^[\d\.,\s]+$', p) for p in parts):
        return False

    # ── Address-like guard ──
    # "Oakland, Alameda, California, United States" → address, NOT multiple ports
    # Pattern: most parts are long words (≥5 chars), capitalized, no port codes
    if delimiter == ",":
        long_word_parts = sum(1 for p in parts if len(p) >= 5 and re.match(r'^[A-Z][a-z]', p))
        if long_word_parts >= len(parts) * 0.6:
            return False
        # Also reject if total char count is high (address descriptions)
        if sum(len(p) for p in parts) > 60:
            return False

    # ── Surcharge/inclusion list guard ──
    # "ACC, CAF, DDC, FCR" → abbreviation list, not expandable ports
    if delimiter == ",":
        all_short_upper = all(re.match(r'^[A-Z]{2,5}$', p) for p in parts)
        if all_short_upper and len(parts) >= 3:
            return False

    # Check: do parts look like port codes or geographic text?
    has_port_codes = sum(1 for p in parts if PORT_PATTERN.match(p)) >= 2
    # For slash delimiter, require port code matches
    if delimiter == "/":
        return has_port_codes

    # For comma, require at least 2 port codes
    return has_port_codes


def field_aware_expand(rows: List[Dict], sub_field_keys: List[str]) -> List[Dict]:
    """
    Expand rows where sub_fields contain delimiter-separated values.
    Supports / and , delimiters. Data-driven, no hardcoded field lists.
    """
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
                # Detect delimiter
                if "/" in cell_val:
                    parts = [p.strip() for p in cell_val.split("/") if p.strip()]
                elif "," in cell_val:
                    parts = [p.strip() for p in cell_val.split(",") if p.strip()]
                else:
                    continue
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
# Utility: Consecutive Money Column Counter
# ──────────────────────────────────────────────

def _count_consecutive_money(column_profiles: Dict[str, ColumnProfile], data_cols: list) -> int:
    """Count the longest run of consecutive money-type columns.
    A high count (≥3) is a strong signal for a rate matrix layout."""
    max_run = 0
    current_run = 0
    for col in data_cols:
        p = column_profiles.get(col)
        if p and p.type_hint == "money":
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


# ──────────────────────────────────────────────
# Sheet Classification — workbook "table of contents"
# ──────────────────────────────────────────────

# Keywords for sheet role inference (case-insensitive)
_ROLE_KEYWORDS = {
    "primary_rate": ["main", "rate", "운임", "basic", "ocean", "freight", "o/f", "tariff"],
    "surcharge": ["surcharge", "sur", "add", "add-on", "addon", "optional", "eu ", "ets"],
    "reefer": ["rf", "reefer", "냉동", "냉장"],
    "dangerous": ["dg", "dangerous", "위험물", "imdg", "hazard"],
    "special_equipment": ["ot", "flat", "pct", "special", "soc", "oog"],
    "summary": ["summary", "brief", "요약", "overview", "index"],
    "transshipment": ["tpt", "t/s", "transship", "transit", "feeder"],
    "freetime": ["free", "demurrage", "detention", "d&d", "dm/dt"],
}


def classify_sheets(
    df: pd.DataFrame,
    all_block_summaries: list,
) -> List[Dict[str, Any]]:
    """Create a per-sheet summary for LLM context — like a workbook table of contents.

    Each sheet gets:
      - name, row_count, block_count
      - key_headers: top header values seen across blocks
      - data_sample: first data row values
      - dominant_types: most common column type_hints
      - sheet_role: inferred role based on name + content
      - sheet_index: 0-based position (first sheet often = primary)

    This does NOT restrict mapping. It provides LLM with document-level orientation.
    """
    sheet_names = df["_sheet_name"].unique().tolist() if "_sheet_name" in df.columns else []
    sheet_classifications = []

    # Group block summaries by sheet (lowered for matching)
    blocks_by_sheet: Dict[str, list] = {}
    for bs in all_block_summaries:
        sn = str(bs.get("sheet", "")).strip().lower()
        blocks_by_sheet.setdefault(sn, []).append(bs)

    for idx, sheet_name in enumerate(sheet_names):
        sn_lower = str(sheet_name).strip().lower()
        sheet_df = df[df["_sheet_name"] == sheet_name]
        blocks = blocks_by_sheet.get(sn_lower, [])

        # Collect headers from all blocks in this sheet
        all_headers = []
        all_type_hints = []
        for bs in blocks:
            all_headers.extend(bs.get("header_candidates", []))
            profile_summary = bs.get("column_profile_summary", "")
            # Extract type hints like "A:port_code, B:text, C:money"
            for part in profile_summary.split(","):
                part = part.strip()
                if ":" in part:
                    hint = part.split(":", 1)[1].strip()
                    all_type_hints.append(hint)

        # First data row sample
        data_sample = []
        meta_cols = {"row_id", "local_row_id", "_sheet_name", "_sheet_name_lower"}
        data_cols = [c for c in sheet_df.columns if c not in meta_cols]
        if len(sheet_df) > 1:  # skip header row
            first_data = sheet_df.iloc[min(2, len(sheet_df) - 1)]
            data_sample = [
                str(first_data[c])[:25] for c in data_cols[:8]
                if c in first_data.index and pd.notna(first_data[c])
            ]

        # Infer sheet role from name keywords
        sheet_role = "unknown"
        best_score = 0
        for role, keywords in _ROLE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in sn_lower)
            if score > best_score:
                best_score = score
                sheet_role = role
        # Boost first sheet if no strong match
        if idx == 0 and best_score == 0:
            sheet_role = "primary_rate"

        # Count dominant column types
        type_counts: Dict[str, int] = {}
        for t in all_type_hints:
            type_counts[t] = type_counts.get(t, 0) + 1
        dominant_types = sorted(type_counts.items(), key=lambda x: -x[1])[:3]

        sheet_classifications.append({
            "sheet_name": str(sheet_name),
            "sheet_index": idx,
            "row_count": len(sheet_df),
            "block_count": len(blocks),
            "sheet_role": sheet_role,
            "key_headers": list(dict.fromkeys(all_headers))[:10],  # dedupe, first 10
            "data_sample": data_sample[:6],
            "dominant_col_types": [f"{t}({c})" for t, c in dominant_types],
        })

    return sheet_classifications


# ──────────────────────────────────────────────
# Utility: Build Block Summary for LLM
# ──────────────────────────────────────────────

def build_block_summary(
    block: BlockInfo,
    row_classifications: List[RowClassification],
    column_profiles: Dict[str, ColumnProfile],
    block_context: Dict[str, Any],
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Build a structured summary of a block for the LLM to interpret.

    Size limits to prevent prompt bloat:
    - header_candidates: top 20 columns
    - column_profiles: top 15 columns (by non_empty_count)
    - data_sample: 3 rows max
    - sample values per column: 3 max
    """
    data_cols = block.active_columns if block.active_columns else _get_data_cols(df)

    # Get ALL header row values (multi-row cluster)
    header_rows = [rc for rc in row_classifications if rc.row_type == "header"]
    header_values = {}
    for h_rc in header_rows[:3]:  # max 3 header rows
        h_row = df[df["row_id"] == h_rc.row_id]
        if not h_row.empty:
            count = 0
            for c in data_cols:
                if count >= 20 or c not in df.columns:
                    break
                val = str(h_row.iloc[0][c]).strip() if pd.notna(h_row.iloc[0][c]) else ""
                if val and val.lower() != "nan":
                    # For multi-row headers, concatenate with existing
                    if c in header_values:
                        header_values[c] = f"{header_values[c]} | {val}"
                    else:
                        header_values[c] = val
                    count += 1

    # Get first 3 data rows as sample
    data_rows = [rc for rc in row_classifications if rc.row_type == "data"]
    sample_rows = []
    for rc in data_rows[:3]:
        row = df[df["row_id"] == rc.row_id]
        if not row.empty:
            row_dict = {}
            for c in data_cols:
                if c not in df.columns:
                    continue
                val = str(row.iloc[0][c]).strip() if pd.notna(row.iloc[0][c]) else ""
                if val and val.lower() != "nan":
                    row_dict[c] = val
            sample_rows.append(row_dict)

    # Header rows raw — each header row preserved separately for LLM
    header_rows_raw = []
    for h_rc in header_rows[:3]:
        h_row_df = df[df["row_id"] == h_rc.row_id]
        if not h_row_df.empty:
            row_dict = {}
            for c in data_cols:
                if c not in df.columns:
                    continue
                val = str(h_row_df.iloc[0][c]).strip() if pd.notna(h_row_df.iloc[0][c]) else ""
                if val and val.lower() != "nan":
                    row_dict[c] = val
            if row_dict:
                header_rows_raw.append(row_dict)

    # Group label values
    group_rows = [rc for rc in row_classifications if rc.row_type == "group_label" and rc.group_label]
    group_labels = list(dict.fromkeys(rc.group_label for rc in group_rows))[:5]

    # Column profiles: top 15 by non_empty_count
    sorted_profiles = sorted(column_profiles.items(), key=lambda x: x[1].non_empty_count, reverse=True)[:15]

    # Measure column hints — money/port column clusters for rate matrix detection
    measure_column_hints = {
        "money_columns": [c for c, p in column_profiles.items() if p.type_hint == "money"],
        "port_columns": [c for c, p in column_profiles.items() if p.type_hint == "port_code"],
        "consecutive_money_count": _count_consecutive_money(column_profiles, data_cols),
    }

    return {
        "sheet": block.sheet_name,
        "block_id": block.block_id,
        "row_range": f"{block.row_start}-{block.row_end}",
        "row_count": block.row_count,
        "block_type": block.block_type,
        "column_span": f"{block.col_start}-{block.col_end}" if block.col_start else "unknown",
        "active_columns": block.active_columns[:20],
        "header_candidates": header_values,
        "header_rows_raw": header_rows_raw,
        "data_sample": sample_rows,
        "group_labels": group_labels,
        "column_profiles": {
            c: {"type_hint": p.type_hint, "sample": p.sample[:3]}
            for c, p in sorted_profiles
        },
        "measure_column_hints": measure_column_hints,
        "detected_context": {k: v for k, v in block_context.items() if not k.startswith("_")},
        "row_classification_summary": {
            "header": len([r for r in row_classifications if r.row_type == "header"]),
            "data": len([r for r in row_classifications if r.row_type == "data"]),
            "group_label": len([r for r in row_classifications if r.row_type == "group_label"]),
            "context": len([r for r in row_classifications if r.row_type == "context"]),
            "remark": len([r for r in row_classifications if r.row_type == "remark"]),
            "continuation": len([r for r in row_classifications if r.row_type == "continuation"]),
        }
    }
