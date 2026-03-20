import io
import re
import json
import time
import logging
import pandas as pd
from typing import Dict, Any
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)


async def _run_block_mapper(block_summaries: list, model: ExtractionModel, extractor_llm: str, sheet_classifications: list = None) -> Dict[str, Any]:
    """
    Phase B: LLM Semantic Mapper (reduced role).
    
    ARCHITECTURE: LLM receives pre-analyzed block summaries (NOT raw CSV data).
    Python has already:
      - Detected physical blocks (blank-row segmentation)
      - Classified rows (header/data/group/context/remark)
      - Profiled columns (type_hint: port_code/money/date/text)
      - Extracted context (POL, Currency, dates from metadata rows)
    
    LLM only needs to:
      1. Match each block to a logical table field from the schema
      2. Suggest column-to-sub_field mappings (as CANDIDATES, validated by Python)
      3. Extract scalar values from metadata context
    """
    client = get_openai_client()
    deployment = extractor_llm or get_current_model()
    
    TABLE_TYPES = ("table", "list", "array", "object")
    fields_context = []
    for f in model.fields:
        entry = {"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules}
        if f.type in TABLE_TYPES:
            # Ensure sub_fields are plain dicts for JSON serialization
            raw_subs = f.sub_fields or []
            entry["sub_fields"] = [
                sf.model_dump() if hasattr(sf, 'model_dump') else (sf if isinstance(sf, dict) else vars(sf))
                for sf in raw_subs
            ]
        fields_context.append(entry)
    
    # Build sheet overview section for LLM
    sheet_overview = ""
    if sheet_classifications:
        sheet_overview = f"""
    WORKBOOK STRUCTURE (Sheet-level overview — read this FIRST):
    {json.dumps(sheet_classifications, ensure_ascii=False, indent=2)}
    
    SHEET ROLE GUIDE:
    - sheet_role="primary_rate" → Main freight rate table. Map Basic_Rate_List / primary rate fields here FIRST.
    - sheet_role="surcharge" → Surcharge/add-on rates. Map Optional_Rate_List / Add_On_Rate_List here.
    - sheet_role="reefer" / "dangerous" / "special_equipment" → Specialized cargo rates.
    - sheet_role="transshipment" → Transshipment/feeder rates (secondary, often duplicates main rates for specific routes).
    - sheet_role="summary" → Overview/brief tables (avoid mapping primary data here).
    - Prefer sheets with higher row_count and sheet_index=0 for primary rate data.
    - A "transshipment" sheet may contain valid rate data, but prefer "primary_rate" sheet if both exist.
    """

    prompt = f"""
    You are an expert Data Extractor. You are given PRE-ANALYZED block summaries from an Excel file.
    Python has already segmented the sheet into blocks, classified rows, and profiled column data types.
    
    Your job is ONLY to provide semantic interpretation — match blocks to schema fields and suggest column mappings.
    Your suggestions will be VALIDATED by a Python validator, so provide your best guess.
    {sheet_overview}
    PRE-ANALYZED BLOCK SUMMARIES:
    {json.dumps(block_summaries, ensure_ascii=False, indent=2)}
    
    TARGET EXTRACTION SCHEMA:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Review the WORKBOOK STRUCTURE first to understand each sheet's role.
    2. For each "table" type schema field, pick the block from the most appropriate sheet.
       - For primary rate fields (e.g., Basic_Rate_List), prefer blocks from sheets with role="primary_rate".
       - For surcharge fields, prefer blocks from sheets with role="surcharge".
    3. Suggest column_mapping: sub_field_key → excel_column_letter based on header_candidates and column_profiles.
    4. For scalar fields, extract values from detected_context or data patterns.
    5. For each table block, classify its table_kind:
       - "rate_matrix": Rows are lanes (POL/POD), columns are container types (20GP, 40HC) — values are rates.
         HINT: check measure_column_hints.consecutive_money_count ≥ 3 and header names matching equipment codes.
       - "surcharge_table": Each row is a charge type with an amount column.
       - "freetime_table": Each row is a container type with free days.
       - "flat_table": Standard row-per-record table (default).
       - "summary_table": Aggregated totals or overview data.
    
    CRITICAL RULES:
    - ALWAYS consult the WORKBOOK STRUCTURE before choosing a block. Sheet role is a strong signal.
    - Use column_profiles type_hints to guide mapping. A column with type_hint "money" is likely a rate.
    - Use header_candidates to match column letters to field names.
    - Use header_rows_raw to understand multi-row header hierarchy (upper row = group, lower row = detail).
    - If a block has detected_context (e.g., POL, Currency), those values are already extracted by Python.
    - DO NOT hallucinate columns. Only map columns that appear in header_candidates or column_profiles.
    - Semantic equivalence is encouraged: "Origin" → POL, "O/F" → Ocean Freight rate, etc.
    - IMPORTANT: POD (Port of Discharge, e.g. USLAX) and Destination (final delivery city, e.g. CHICAGO,IL) are DIFFERENT fields. Do NOT conflate them.
    - For row boundaries, use the block's row_range. Python has already classified header vs data rows.
    - For scalars, provide the value if available in detected_context. Otherwise use null.
    """
    
    response_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "block_mapping",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string"},
                    "tables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_key": {"type": "string"},
                                "block_id": {"type": "integer"},
                                "sheet_name": {"type": "string"},
                                "header_row_id": {"type": "integer"},
                                "first_data_row_id": {"type": "integer"},
                                "last_data_row_id": {"type": "integer"},
                                "table_kind": {
                                    "type": "string",
                                    "enum": ["flat_table", "rate_matrix", "surcharge_table", "freetime_table", "summary_table"]
                                },
                                "columns_mapping": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "sub_field_key": {"type": "string"},
                                            "excel_column": {"type": "string"},
                                            "excel_header_name": {"type": "string"}
                                        },
                                        "required": ["sub_field_key", "excel_column", "excel_header_name"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["field_key", "block_id", "sheet_name", "header_row_id", "first_data_row_id", "last_data_row_id", "table_kind", "columns_mapping"],
                            "additionalProperties": False
                        }
                    },
                    "scalars": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_key": {"type": "string"},
                                "sheet_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                "row_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                                "col": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                "exact_value": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "null"}
                                    ]
                                }
                            },
                            "required": ["field_key", "sheet_name", "row_id", "col", "exact_value"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["reasoning", "tables", "scalars"],
                "additionalProperties": False
            }
        }
    }
    
    try:
        res = await client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_schema,
            temperature=0.0  # Schema mapper must be deterministic for consistent results
        )
        content = res.choices[0].message.content
        result_json = json.loads(content)
        
        token_usage = {}
        if res.usage:
            token_usage = {
                "prompt_tokens": res.usage.prompt_tokens,
                "completion_tokens": res.usage.completion_tokens,
                "total_tokens": res.usage.total_tokens
            }
        result_json["_token_usage"] = token_usage
        return result_json
    except Exception as e:
        logger.error(f"Schema Mapper failed: {e}")
        return {"scalars": [], "tables": [], "reasoning": f"Mapper failed: {e}"}


async def _run_markdown_scalar_extraction(
    md_content: str,
    missing_fields: list,
    model: ExtractionModel,
    extractor_llm: str
) -> Dict[str, Any]:
    """
    Phase 2: Markdown Context-based Scalar Extraction.
    Fills gaps left by the coordinate-based _run_schema_mapper by feeding
    the full Excel markdown text to the LLM for non-table fields.
    """
    client = get_openai_client()
    deployment = extractor_llm or get_current_model()

    fields_context = [{
        "key": f["key"],
        "label": f.get("label", f["key"]),
        "type": f.get("type", "string"),
        "description": f.get("description", ""),
        "rules": f.get("rules", "")
    } for f in missing_fields]

    # Smart truncation: keep first 8000 chars of markdown to fit context window
    truncated_md = md_content[:8000] if len(md_content) > 8000 else md_content

    prompt = f"""
You are an expert Data Extractor. Below is an Excel file converted to Markdown format.
Your task is to extract the values for the following fields from this content.

These are NON-TABLE fields (scalars) — they are typically found in headers, titles,
metadata sections, summary rows, or free-text areas of the Excel file.
If not found as standalone text, INFER the value from patterns in the table data.

Excel Content (Markdown):
{truncated_md}

Target Fields to Extract:
{json.dumps(fields_context, ensure_ascii=False, indent=2)}

CRITICAL RULES:
1. Return ONLY valid JSON matching this EXACT schema.
2. For each field, return the extracted value as a string. If not found, return null.
3. Look for values in sheet titles, header rows, metadata cells, summary sections, and any non-table text.
4. Do NOT extract table row data — only extract standalone scalar/summary values.
5. Keep the original language. Do NOT translate unless a field rule says so.
6. INFERENCE RULE: If a field cannot be found as explicit text but can be LOGICALLY INFERRED from the table data, do so.
   Examples: If all Origin/POL values are 'PUSAN' and all POD values are US port codes, the trade route is 'Korea → USA' or '한국 → 미국'.
   If column 'Commodity' shows product codes, summarize the commodity type."""

    # Build strict structured output schema
    properties = {}
    required_keys = []
    for f in fields_context:
        properties[f["key"]] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        required_keys.append(f["key"])

    response_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "markdown_scalar_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required_keys,
                "additionalProperties": False
            }
        }
    }

    try:
        res = await client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_schema,
            temperature=model.temperature
        )
        content = res.choices[0].message.content
        result_json = json.loads(content)

        token_usage = {}
        if res.usage:
            token_usage = {
                "prompt_tokens": res.usage.prompt_tokens,
                "completion_tokens": res.usage.completion_tokens,
                "total_tokens": res.usage.total_tokens
            }
        result_json["_token_usage"] = token_usage
        return result_json
    except Exception as e:
        logger.error(f"Markdown Scalar Extraction failed: {e}")
        return {}


async def run_sql_extraction(file: UploadFile, model: ExtractionModel, md_content: str = "") -> Dict[str, Any]:
    """
    Two-Track Excel Extraction (Python Engine Mode).
    Phase 13: Single Source of Truth Architecture using pure Pandas.
    """
    _t_total = time.monotonic()
    logger.info(f"Starting Two-Track Extraction for {file.filename}")
    
    file_content = await file.read()
    await file.seek(0)
    
    filename_lower = file.filename.lower()
    content_type = file.content_type
    
    # 1. Load Excel or CSV into Pandas (CPU BOUND - Run in Threadpool)
    def _load_excel_sync(fc: bytes, fname: str, ctype: str) -> pd.DataFrame:
        import io
        import csv
        
        if fname.endswith('.csv') or ctype == 'text/csv':
            content_str = None
            for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]:
                try:
                    content_str = fc.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if content_str is None:
                raise ValueError("Failed to decode CSV file with supported encodings")
                
            # Read CSV perfectly aligned with Excel Parser behavior
            reader = csv.reader(io.StringIO(content_str))
            csv_rows = list(reader)
            combined_df = pd.DataFrame(csv_rows)
            combined_df = combined_df.dropna(how='all')
            if not combined_df.empty:
                combined_df.insert(0, '_sheet_name', 'Data')
                combined_df.insert(0, 'local_row_id', range(0, len(combined_df)))
                combined_df.insert(0, 'row_id', range(0, len(combined_df)))
        else:
            fc_io = io.BytesIO(fc) if isinstance(fc, bytes) else fc
            try:
                excel_data = pd.read_excel(fc_io, sheet_name=None, header=None, engine="calamine")
            except ImportError:
                fc_io.seek(0) if hasattr(fc_io, 'seek') else None
                excel_data = pd.read_excel(fc_io, sheet_name=None, header=None, engine="openpyxl")
            
            combined_df = pd.DataFrame()
            row_offset = 0
            for sheet_name, sheet_df in excel_data.items():
                sheet_df = sheet_df.dropna(how='all') 
                if not sheet_df.empty:
                    sheet_df.insert(0, '_sheet_name', str(sheet_name))
                    sheet_df.insert(0, 'local_row_id', range(0, len(sheet_df)))
                    # Add row_id before concat to preserve true row indexing per sheet or globally.
                    sheet_df.insert(0, 'row_id', range(row_offset, row_offset + len(sheet_df)))
                    row_offset += len(sheet_df)
                    combined_df = pd.concat([combined_df, sheet_df], ignore_index=True)
                
        if combined_df.empty:
            raise ValueError("All sheets are empty.")
            
        df = combined_df
        
        # Revert to standard Excel letters (A, B, C) as LLMs have strong priors
        clean_cols = ['row_id', 'local_row_id', '_sheet_name']
        for i in range(len(df.columns) - 3):
            name = ""
            n = i
            while n >= 0:
                name = chr(n % 26 + 65) + name
                n = n // 26 - 1
            clean_cols.append(name)
            
        df.columns = clean_cols
        return df

    from fastapi.concurrency import run_in_threadpool
    try:
        df = await run_in_threadpool(_load_excel_sync, file_content, filename_lower, content_type)
    except Exception as e:
        logger.error(f"Failed to load Excel with pandas: {e}")
        raise ValueError(f"지원하지 않거나 손상된 엑셀 구조입니다. 파일 로딩 실패: {e}")

    _t_load = time.monotonic() - _t_total
    logger.info(f"⏱️ [TIMER] Excel Load: {_t_load:.2f}s")

    # ── Phase A: Python Grid Parser ──────────────────────────────────────
    _t_phase_a = time.monotonic()
    from app.services.extraction.excel_block_parser import (
        detect_blocks, classify_rows, profile_columns,
        extract_block_context, validate_column_mapping,
        field_aware_expand, build_block_summary, classify_sheets
    )
    from dataclasses import asdict
    
    all_block_summaries = []
    all_blocks_meta = {}  # block_id → {block, row_classifications, column_profiles, context}
    
    sheet_names = df['_sheet_name'].unique().tolist() if '_sheet_name' in df.columns else ['Default']
    
    global_block_id = 1  # Global counter across sheets to prevent ID collisions
    for sheet_name in sheet_names:
        blocks = detect_blocks(df, str(sheet_name), start_block_id=global_block_id)
        for block in blocks:
            row_cls = classify_rows(df, block)
            col_profiles = profile_columns(df, block, row_cls)
            block_ctx = extract_block_context(df, block, row_cls)
            
            # Build summary for LLM
            summary = build_block_summary(block, row_cls, col_profiles, block_ctx, df)
            all_block_summaries.append(summary)
            
            # Store metadata for later extraction
            all_blocks_meta[block.block_id] = {
                "block": block,
                "row_classifications": row_cls,
                "column_profiles": col_profiles,
                "context": block_ctx
            }
        global_block_id += len(blocks)  # Advance counter by number of blocks found
    
    logger.info(f"[Phase A] Detected {len(all_block_summaries)} blocks across {len(sheet_names)} sheets")
    logs = [{"step": "Block Detection", "message": f"Detected {len(all_block_summaries)} blocks across {len(sheet_names)} sheets"}]
    
    # ── Phase A-2: Sheet Classification (workbook table of contents) ────
    sheet_classifications = classify_sheets(df, all_block_summaries)
    logs.append({"step": "Sheet Classification", "message": json.dumps([{"sheet": s['sheet_name'], "role": s['sheet_role'], "rows": s['row_count']} for s in sheet_classifications], ensure_ascii=False)})
    
    _t_phase_a_done = time.monotonic() - _t_phase_a
    logger.info(f"⏱️ [TIMER] Phase A (Block Parser): {_t_phase_a_done:.2f}s ({len(all_block_summaries)} blocks)")

    # ── Phase B: LLM Semantic Mapper (reduced role) ──────────────────────
    _t_phase_b = time.monotonic()
    extractor_llm = getattr(model, "extractor_llm", None)
    
    mapping_plan = await _run_block_mapper(all_block_summaries, model, extractor_llm, sheet_classifications=sheet_classifications)
    reasoning = mapping_plan.get("reasoning", "")
    token_usage = mapping_plan.pop("_token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    logger.info(f"Block Mapping Plan generated:\n{json.dumps(mapping_plan, indent=2, ensure_ascii=False)}")
    
    _t_phase_b_done = time.monotonic() - _t_phase_b
    logger.info(f"⏱️ [TIMER] Phase B (LLM Mapper): {_t_phase_b_done:.2f}s")

    # ── Phase D: Pure Python Extraction Engine ────────────────────────
    _t_phase_d = time.monotonic()
    raw_extracted = {}
    # NOTE: logs is initialized in Phase A above. Do NOT reinitialize here.
    
    # #7: Create _sheet_name_lower once upfront
    if '_sheet_name' in df.columns and '_sheet_name_lower' not in df.columns:
        df['_sheet_name_lower'] = df['_sheet_name'].astype(str).str.strip().str.lower()
    
    # Sheet list for page_number lookup
    sheet_list = df['_sheet_name'].unique().tolist() if '_sheet_name' in df.columns else []
    sheet_list_lower = [str(s).strip().lower() for s in sheet_list]
    
    # #6: Scalar context-first — collect all block contexts for scalar lookup
    all_detected_context = {}
    for bid, meta in all_blocks_meta.items():
        for ctx_key, ctx_val in meta.get('context', {}).items():
            if ctx_key not in all_detected_context:
                all_detected_context[ctx_key] = ctx_val
    
    # ── Scalar Extraction (Priority: Python context → LLM coordinate → LLM exact_value → markdown) ──
    TABLE_TYPES = ("table", "list", "array", "object")
    
    # #6: Fill scalars from Python detected context FIRST
    for f in model.fields:
        if f.type in TABLE_TYPES:
            continue
        fk = f.key
        fk_lower = fk.strip().lower()
        # Check if Python block context already detected this value
        ctx_val = all_detected_context.get(fk) or all_detected_context.get(fk_lower)
        if ctx_val and fk not in raw_extracted:
            raw_extracted[fk] = {
                "value": ctx_val,
                "original_value": ctx_val,
                "confidence": 0.85,
                "validation_status": "valid",
                "page_number": 1,
                "bbox": None,
                "_modifier": "Python Block Context"
            }
            logs.append({"step": f"Scalar [{fk}]", "message": f"Filled from Python block context: {ctx_val}"})
    
    # LLM scalar extraction (supplement Python results)
    raw_scalars = mapping_plan.get("scalars", [])
    if not isinstance(raw_scalars, list):
        logger.warning(f"LLM returned invalid scalars schema type: {type(raw_scalars)}. Defaulting to empty list.")
        raw_scalars = []
        
    scalars_mapping = {s["field_key"]: s for s in raw_scalars if "field_key" in s}
        
    for target_key, s_map in scalars_mapping.items():
        # Skip if Python context already filled this scalar
        if target_key in raw_extracted and raw_extracted[target_key].get("value"):
            continue
        
        sheet = s_map.get("sheet_name")
        row_id = s_map.get("row_id")
        col = s_map.get("col")
        exact_value = s_map.get("exact_value")
        
        # Fallback tracking
        val = None
        raw_val = None
        bbox = None
        
        # Virtual Grid constants (Sync with ExcelGridViewer.tsx)
        VIRTUAL_WIDTH = 1000
        CELL_HEIGHT = 50
        col_count = len(df.columns) - 2 if len(df.columns) > 2 else 26
        cell_width = VIRTUAL_WIDTH / max(1, col_count)
        
        # #8: page_number from precomputed sheet_list
        page_number = 1
        if sheet:
            search = str(sheet).strip().lower()
            if search in sheet_list_lower:
                page_number = sheet_list_lower.index(search) + 1
        
        # 1. Try Coordinate-based pure Pandas lookup
        if sheet and row_id is not None and col:
            try:
                r_id = int(row_id)
                val_df = df[(df["_sheet_name"] == sheet) & (df["row_id"] == r_id)]
                if not val_df.empty and col in val_df.columns:
                    raw_val = val_df.iloc[0][col]
                    if pd.notna(raw_val):
                        val = str(raw_val).strip()
                        
                        # Calculate virtual BBox for Scalar
                        try:
                            col_idx = df.columns.tolist().index(col) - 3  # Adjusted for metadata cols
                            row_idx = int(val_df.iloc[0]["local_row_id"]) if "local_row_id" in val_df.columns else 0
                            
                            x1 = col_idx * cell_width
                            y1 = row_idx * CELL_HEIGHT
                            x2 = x1 + cell_width
                            y2 = y1 + CELL_HEIGHT
                            bbox = [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Failed to extract scalar {target_key} via coordinates: {e}")
                
        # 2. Fallback to Exact Value provided by LLM if Pandas lookup failed or was empty
        if not val and exact_value is not None:
            if isinstance(exact_value, list):
                logger.info(f"Using LLM exact_value (List) callback for {target_key}")
                val = exact_value
                raw_val = exact_value
            elif str(exact_value).strip():
                logger.info(f"Using LLM exact_value fallback for {target_key} = {exact_value}")
                val = str(exact_value).strip()
                raw_val = val

        # #3: Save raw extraction ONLY — no ref_data normalization here.
        # Normalization happens in the common post-processing stage.
        if val is not None:
            payload = {
                "value": val,
                "original_value": str(raw_val),
                "confidence": 0.90,
                "validation_status": "valid",
                "page_number": page_number,
                "bbox": bbox
            }
            raw_extracted[target_key] = payload
        else:
            logger.debug(f"Skipping empty scalar {target_key}")

    _t_scalars_done = time.monotonic() - _t_phase_d
    logger.info(f"⏱️ [TIMER] Scalar Extraction: {_t_scalars_done:.2f}s")

    # ── Phase C: Python Validator + Table Map Construction ─────────────
    _t_phase_c = time.monotonic()
    raw_tables = mapping_plan.get("tables", [])
    if not isinstance(raw_tables, list):
        logger.warning(f"LLM returned invalid tables schema type: {type(raw_tables)}. Defaulting to empty list.")
        raw_tables = []
        
    tables_map = {}
    for t in raw_tables:
        if "field_key" not in t:
            continue
        col_map_array = t.get("columns_mapping", [])
        col_map_dict = {c["sub_field_key"]: c["excel_column"] for c in col_map_array if "sub_field_key" in c and "excel_column" in c} if isinstance(col_map_array, list) else {}
        
        block_id = t.get("block_id")
        block_meta = all_blocks_meta.get(block_id, {})
        
        # Resolve sub_field definitions from model schema for field-semantic validation
        sub_field_defs = None
        for f in model.fields:
            if f.key == t["field_key"] and getattr(f, 'sub_fields', None):
                raw_subs = getattr(f, 'sub_fields')
                sub_field_defs = [
                    sf if isinstance(sf, dict) else sf.model_dump() if hasattr(sf, 'model_dump') else vars(sf)
                    for sf in raw_subs if sf
                ]
                break
        
        # Phase C: Validate LLM mapping against actual data patterns
        if block_meta:
            validation_result = validate_column_mapping(
                df, block_meta["block"], col_map_dict,
                block_meta["row_classifications"],
                block_meta["column_profiles"],
                sub_field_defs=sub_field_defs
            )
            validated_mapping = validation_result["validated_mapping"]
            rejected = validation_result["rejected"]
            warnings_list = validation_result.get("warnings", [])
            
            if rejected:
                logs.append({"step": f"Validator [{t['field_key']}]", "message": f"Rejected {len(rejected)} mappings: {json.dumps(rejected, ensure_ascii=False)}"})
            if warnings_list:
                logs.append({"step": f"Validator [{t['field_key']}] Warnings", "message": f"{len(warnings_list)} warnings: {json.dumps(warnings_list, ensure_ascii=False)}"})
            
            col_map_dict = validated_mapping
        
        tables_map[t["field_key"]] = {
            "sheet_name": t.get("sheet_name", "Sheet1"),
            "first_data_row_id": t.get("first_data_row_id", 1),
            "last_data_row_id": t.get("last_data_row_id"),
            "columns_mapping": col_map_dict,
            "block_id": block_id,
            "block_context": block_meta.get("context", {}),
            "table_kind": t.get("table_kind", "flat_table"),
        }
        
    # #10: Unmapped table fields — Python header-matching fallback
    # If LLM mapper didn't map a table field, try to find the best block
    # by matching sub_field keys against block header_candidates.
    # This ensures all model-defined table fields get an extraction attempt.
    mapped_field_keys = set(tables_map.keys())
    for f in model.fields:
        if f.type not in TABLE_TYPES or f.key in mapped_field_keys:
            continue
        
        # Get sub_field keys for this unmapped table field
        sub_field_keys = set()
        raw_subs = getattr(f, 'sub_fields', None) or []
        for sf in raw_subs:
            sf_key = sf.get("key") if isinstance(sf, dict) else getattr(sf, "key", None)
            if sf_key:
                sub_field_keys.add(sf_key.lower())
        
        if not sub_field_keys:
            logs.append({"step": f"Unmapped [{f.key}]", "message": f"No sub_fields defined, cannot auto-map."})
            continue
        
        # Score each block by header match
        best_block_id = None
        best_score = 0
        best_col_map = {}
        
        for summary in all_block_summaries:
            block_id = summary.get("block_id")
            headers = summary.get("header_candidates", {})
            if not headers:
                continue
            
            # Match headers to sub_field keys (case-insensitive)
            col_map = {}
            for col_letter, header_text in headers.items():
                header_lower = str(header_text).strip().lower()
                # Direct key match
                if header_lower in sub_field_keys:
                    col_map[header_lower] = col_letter
                else:
                    # Try matching with underscores removed / spaces normalized
                    header_normalized = header_lower.replace(" ", "_").replace("-", "_")
                    for sk in sub_field_keys:
                        if sk == header_normalized or sk.replace("_", "") == header_normalized.replace("_", ""):
                            col_map[sk] = col_letter
                            break
            
            score = len(col_map) / max(1, len(sub_field_keys))
            if score > best_score:
                best_score = score
                best_block_id = block_id
                best_col_map = col_map
        
        # Threshold: at least 30% of sub_fields matched
        if best_block_id is not None and best_score >= 0.3:
            block_meta = all_blocks_meta.get(best_block_id, {})
            
            # Run validator on the auto-mapped columns
            sub_field_defs = [
                sf if isinstance(sf, dict) else sf.model_dump() if hasattr(sf, 'model_dump') else vars(sf)
                for sf in raw_subs if sf
            ]
            if block_meta:
                validation_result = validate_column_mapping(
                    df, block_meta["block"], best_col_map,
                    block_meta["row_classifications"],
                    block_meta["column_profiles"],
                    sub_field_defs=sub_field_defs
                )
                best_col_map = validation_result["validated_mapping"]
            
            tables_map[f.key] = {
                "sheet_name": all_block_summaries[[s["block_id"] for s in all_block_summaries].index(best_block_id)].get("sheet", "Sheet1"),
                "first_data_row_id": None,
                "last_data_row_id": None,
                "columns_mapping": best_col_map,
                "block_id": best_block_id,
                "block_context": block_meta.get("context", {}),
                "table_kind": "flat_table",  # Fallback auto-mapping always defaults to flat
            }
            logs.append({"step": f"Fallback [{f.key}]", "message": f"Auto-mapped to block {best_block_id} (score={best_score:.0%}, cols={list(best_col_map.keys())})"})
        else:
            logs.append({"step": f"Unmapped [{f.key}]", "message": f"No block matched (best_score={best_score:.0%}). Table field '{f.key}' will be empty."})
    
    _t_phase_c_done = time.monotonic() - _t_phase_c
    logger.info(f"⏱️ [TIMER] Phase C (Validator + Map): {_t_phase_c_done:.2f}s ({len(tables_map)} tables)")

    _t_table_exec = time.monotonic()
    for target_key, t_map in tables_map.items():
        _t_table_start = time.monotonic()
        sheet = t_map.get("sheet_name", "")
        if sheet:
            sheet = str(sheet).strip().lower()
        
        raw_col_map = t_map.get("columns_mapping", {})
        
        # Normalize LLM output column map keys (sub_field_key) to lowercase for safe matching
        col_map = {}
        if isinstance(raw_col_map, dict):
            for k, v in raw_col_map.items():
                if k and v:
                    col_map[str(k).strip().lower()] = str(v).strip().upper()
        
        # #8: page_number from precomputed sheet_list with sheet metadata
        page_number = 1
        sheet_index = 0
        if sheet:
            search = str(sheet).strip().lower()
            if search in sheet_list_lower:
                sheet_index = sheet_list_lower.index(search)
                page_number = sheet_index + 1
        
        if not col_map or not sheet:
            logs.append({"step": f"Table [{target_key}]", "message": f"Skipped: col_map or sheet is empty. Sheet={sheet}, Map={col_map}"})
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
        
        # #7: Use precomputed _sheet_name_lower
        sheet_df = df[df["_sheet_name_lower"] == sheet] if "_sheet_name_lower" in df.columns else df
        if sheet_df.empty:
            logs.append({"step": f"Table [{target_key}]", "message": f"Sheet '{sheet}' not found, falling back to full combined data."})
            sheet_df = df
        
        # #5: Block boundary from Python metadata (LLM as fallback only)
        block_id = t_map.get("block_id")
        block_meta = all_blocks_meta.get(block_id, {})
        
        if block_meta:
            block_obj = block_meta["block"]
            block_start = block_obj.row_start
            block_end = block_obj.row_end
            # Use Python's classified data rows within the block
            data_row_ids = {rc.row_id for rc in block_meta["row_classifications"] if rc.row_type == "data"}
            data_rows = sheet_df[sheet_df["row_id"].isin(data_row_ids)]
            logs.append({"step": f"Table [{target_key}] Target", "message": f"Sheet='{sheet}', block=[{block_start}..{block_end}], data_rows={len(data_rows)}, Mapping={json.dumps(col_map)}"})
        else:
            # Fallback: no block metadata, use LLM boundaries
            first_data_row_id = t_map.get("first_data_row_id", 1)
            last_data_row_id = t_map.get("last_data_row_id")
            try:
                h_id = int(first_data_row_id)
            except (ValueError, TypeError):
                h_id = 1
            try:
                last_id = int(last_data_row_id) if last_data_row_id is not None else None
            except (ValueError, TypeError):
                last_id = None
            
            if last_id is not None:
                data_rows = sheet_df[(sheet_df["row_id"] >= h_id) & (sheet_df["row_id"] <= last_id)]
            else:
                data_rows = sheet_df[sheet_df["row_id"] >= h_id]
            logs.append({"step": f"Table [{target_key}] Target", "message": f"Sheet='{sheet}', LLM fallback row_id=[{h_id}..{last_id}], Mapping={json.dumps(col_map)}"})
        
        logger.info(f"[{target_key}] Sheet='{sheet}', data_rows={len(data_rows)}")
        
        extracted_table_rows = []
        
        # 1. Look up the expected schema for this table
        expected_sub_keys = []
        for f in model.fields:
            if f.key == target_key and getattr(f, 'sub_fields', None):
                raw_subs = getattr(f, 'sub_fields')
                expected_sub_keys = [
                    sf.get('key') if isinstance(sf, dict) else getattr(sf, 'key') 
                    for sf in raw_subs if sf
                ]
                break
                
        # Fallback if no schema is strictly defined or found
        if not expected_sub_keys:
            expected_sub_keys = list(col_map.keys())

        # ── Executor Routing by table_kind ────────────────────────────────
        table_kind = t_map.get("table_kind", "flat_table")

        if table_kind == "rate_matrix":
            # ── Rate Matrix Executor ──────────────────────────────────────
            # Unpivot: rows are lanes, columns are equipment types (20GP, 40HC),
            # cells are rate values. Each row × equipment_col → one fact row.
            import copy as _copy

            # Identify equipment (money) columns by checking header values
            equip_pattern = re.compile(r'^\d{2}(GP|HC|DC|RF|OT|FR|TK|NOR)\b', re.IGNORECASE)
            block_meta_local = all_blocks_meta.get(t_map.get("block_id"), {})
            header_rows_cls = [rc for rc in block_meta_local.get("row_classifications", [])
                               if rc.row_type == "header"] if block_meta_local else []

            # Build equipment_cols: list of (excel_col_letter, header_name)
            equipment_cols = []
            non_equip_col_map = {}  # sub_field_key → excel_col for non-equipment fields

            if header_rows_cls:
                h_row = df[df["row_id"] == header_rows_cls[-1].row_id]
                if not h_row.empty:
                    for sf_key, excel_col in col_map.items():
                        if excel_col in h_row.columns:
                            hdr = str(h_row.iloc[0][excel_col]).strip() if pd.notna(h_row.iloc[0][excel_col]) else ""
                            if equip_pattern.match(hdr):
                                equipment_cols.append((excel_col, hdr))
                            else:
                                non_equip_col_map[sf_key] = excel_col
                        else:
                            non_equip_col_map[sf_key] = excel_col
            else:
                # No header info — fall through to flat_table
                non_equip_col_map = col_map
                logger.warning(f"[RateMatrix] No header rows for block, falling back to flat_table for {target_key}")

            if equipment_cols:
                # Determine target sub_field keys for container_type and rate
                ct_key = None
                rate_key = None
                for sk in expected_sub_keys:
                    sk_lower = str(sk).strip().lower()
                    if sk_lower in ("container_type", "equipment", "cntr_type", "eq_type", "container"):
                        ct_key = sk
                    elif sk_lower in ("rate", "freight", "amount", "charge", "o_f", "of"):
                        rate_key = sk

                if not ct_key:
                    ct_key = "container_type"
                if not rate_key:
                    rate_key = "rate"

                VIRTUAL_WIDTH = 1000
                CELL_HEIGHT = 50
                col_count = len(df.columns) - 3
                cell_width = VIRTUAL_WIDTH / max(1, col_count)

                for _, row in data_rows.iterrows():
                    # Extract non-equipment (dimension) values once
                    base_row = {}
                    has_any_data = False
                    for sf_key, excel_col in non_equip_col_map.items():
                        if excel_col and excel_col in row and pd.notna(row[excel_col]):
                            val = str(row[excel_col]).strip()
                            if val and val.lower() != "nan":
                                has_any_data = True
                                base_row[sf_key] = {
                                    "value": val,
                                    "confidence": 0.95,
                                    "validation_status": "valid",
                                    "original_value": val,
                                    "bbox": None
                                }
                            else:
                                base_row[sf_key] = {"value": "", "confidence": 0.0,
                                                    "validation_status": "flagged", "original_value": "", "bbox": None}
                        else:
                            base_row[sf_key] = {"value": "", "confidence": 0.0,
                                                "validation_status": "flagged", "original_value": "", "bbox": None}

                    if not has_any_data:
                        continue

                    # Unpivot: one fact row per equipment column
                    for eq_col, eq_header in equipment_cols:
                        if eq_col in row and pd.notna(row[eq_col]):
                            rate_val = str(row[eq_col]).strip()
                            if not rate_val or rate_val.lower() == "nan":
                                continue

                            fact_row = _copy.deepcopy(base_row)
                            fact_row[ct_key] = {
                                "value": eq_header,
                                "confidence": 0.95,
                                "validation_status": "valid",
                                "original_value": eq_header,
                                "bbox": None
                            }
                            fact_row[rate_key] = {
                                "value": rate_val,
                                "confidence": 0.95,
                                "validation_status": "valid",
                                "original_value": rate_val,
                                "bbox": None
                            }
                            # Fill any missing expected sub_fields
                            for sk in expected_sub_keys:
                                if sk not in fact_row:
                                    fact_row[sk] = {"value": "", "confidence": 0.0,
                                                    "validation_status": "flagged", "original_value": "", "bbox": None}

                            fact_row["_meta"] = {
                                "sheet_name": sheet,
                                "sheet_index": sheet_index,
                                "row_id": int(row["row_id"]),
                                "local_row_id": int(row["local_row_id"]) if "local_row_id" in row.index else 0
                            }
                            extracted_table_rows.append(fact_row)

                logs.append({"step": f"Table [{target_key}] RateMatrix",
                             "message": f"Unpivoted {len(data_rows)} source rows × {len(equipment_cols)} equipment cols → {len(extracted_table_rows)} fact rows"})
                logger.info(f"[RateMatrix] {target_key}: {len(extracted_table_rows)} fact rows from {len(data_rows)} source rows × {len(equipment_cols)} eq cols")

            else:
                # No equipment columns detected — fall through to generic executor below
                table_kind = "flat_table"

        _rate_matrix_handled = (table_kind == "rate_matrix" and len(extracted_table_rows) > 0)

        if not _rate_matrix_handled:
            # ── Generic Flat Table Executor ────────────────────────────────
            for _, row in data_rows.iterrows():
                row_has_meaningful_data = False
                row_data = {}

                for inner_key in expected_sub_keys:
                    lookup_key = str(inner_key).strip().lower() if inner_key else ""
                    excel_col = col_map.get(lookup_key)
                    # Virtual Grid constants (Sync with ExcelGridViewer.tsx)
                    VIRTUAL_WIDTH = 1000
                    CELL_HEIGHT = 50
                    col_count = len(df.columns) - 3  # Subtract metadata cols
                    cell_width = VIRTUAL_WIDTH / max(1, col_count)

                    # Check if we have mapped column and the cell has data
                    if excel_col and excel_col in row and pd.notna(row[excel_col]):
                        val = str(row[excel_col]).strip()
                        if val and val.lower() != "nan":
                            row_has_meaningful_data = True

                            # #3: NO ref_data normalization here — raw extraction only.
                            # Normalization happens in common post-processing stage.

                            # Calculate Virtual BBox
                            bbox = None
                            try:
                                col_idx = df.columns.tolist().index(excel_col) - 3
                                row_idx = int(row["local_row_id"])

                                x1 = col_idx * cell_width
                                y1 = row_idx * CELL_HEIGHT
                                x2 = x1 + cell_width
                                y2 = y1 + CELL_HEIGHT
                                bbox = [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]
                            except Exception:
                                pass

                            row_data[inner_key] = {
                                "value": val,
                                "confidence": 0.95,
                                "validation_status": "valid",
                                "original_value": str(row[excel_col]).strip(),
                                "bbox": bbox
                            }
                        else:
                            # Empty but mapped string
                            row_data[inner_key] = {
                                "value": "",
                                "confidence": 0.0,
                                "validation_status": "flagged",
                                "original_value": "",
                                "bbox": None
                            }
                    else:
                        # Unmapped Column, or completely empty NaN cell
                        row_data[inner_key] = {
                            "value": "",
                            "confidence": 0.0,
                            "validation_status": "flagged",
                            "original_value": "",
                            "bbox": None
                        }

                if row_has_meaningful_data:
                    # #4: Source trace as _meta bucket (not a sub_field)
                    row_data["_meta"] = {
                        "sheet_name": sheet,
                        "sheet_index": sheet_index,
                        "row_id": int(row["row_id"]),
                        "local_row_id": int(row["local_row_id"]) if "local_row_id" in row.index else 0
                    }
                    extracted_table_rows.append(row_data)
                
        # ── Phase E: Context Inheritance ──────────────────────────────────
        # Fill empty fields from block_context (POL, Currency, Start_Date, etc.)
        block_context = t_map.get("block_context", {})
        if block_context:
            for row_data in extracted_table_rows:
                for ctx_key, ctx_val in block_context.items():
                    # Find matching sub_field key (case-insensitive)
                    for inner_key in expected_sub_keys:
                        if str(inner_key).strip().lower() == ctx_key.strip().lower():
                            cell = row_data.get(inner_key, {})
                            if isinstance(cell, dict) and (not cell.get("value") or cell.get("value") == ""):
                                row_data[inner_key] = {
                                    "value": ctx_val,
                                    "confidence": 0.80,
                                    "validation_status": "valid",
                                    "original_value": ctx_val,
                                    "bbox": None,
                                    "_modifier": "Block Context Inheritance"
                                }
        
        # ── Phase E: Field-Aware Expansion ────────────────────────────────
        # Replace inline slash expansion with type-checked version
        _t_expand = time.monotonic()
        extracted_table_rows = field_aware_expand(extracted_table_rows, expected_sub_keys)
        _t_expand_done = time.monotonic() - _t_expand
        if _t_expand_done > 0.5:
            logger.warning(f"⏱️ [TIMER] field_aware_expand [{target_key}]: {_t_expand_done:.2f}s ({len(extracted_table_rows)} rows) ⚠️ SLOW")

        _t_table_done = time.monotonic() - _t_table_start
        logger.info(f"⏱️ [TIMER] Table [{target_key}] total: {_t_table_done:.2f}s ({len(extracted_table_rows)} rows from {len(data_rows)} source)")

        logs.append({"step": f"Table [{target_key}] Exec", "message": f"Extracted {len(extracted_table_rows)} rows out of {len(data_rows)} target data rows."})
        raw_extracted[target_key] = {
            "value": extracted_table_rows,
            "confidence": 0.95 if extracted_table_rows else 0.0,
            "validation_status": "valid" if extracted_table_rows else "flagged",
            "page_number": page_number,
            "_sheet_name": sheet,
            "_sheet_index": sheet_index
        }

    _t_table_exec_done = time.monotonic() - _t_table_exec
    logger.info(f"⏱️ [TIMER] All Table Extraction: {_t_table_exec_done:.2f}s")

    # ── Markdown Context-based Scalar Extraction for empty common fields ──
    _t_md_scalar = time.monotonic()
    missing_scalar_fields = []
    for f in model.fields:
        if f.type in TABLE_TYPES:
            continue
        existing = raw_extracted.get(f.key)
        # Consider a field "missing" if it hasn't been extracted or its value is empty
        if not existing or not existing.get("value"):
            missing_scalar_fields.append({
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "description": f.description,
                "rules": f.rules
            })

    if missing_scalar_fields and md_content:
        logger.info(f"[SQL Extraction] Phase 2: {len(missing_scalar_fields)} empty scalar fields detected. Running Markdown extraction...")
        extractor_llm = getattr(model, "extractor_llm", None)
        md_scalars = await _run_markdown_scalar_extraction(md_content, missing_scalar_fields, model, extractor_llm)

        # Accumulate token usage from 2nd pass
        md_token_usage = md_scalars.pop("_token_usage", {})
        if md_token_usage:
            token_usage["prompt_tokens"] = token_usage.get("prompt_tokens", 0) + md_token_usage.get("prompt_tokens", 0)
            token_usage["completion_tokens"] = token_usage.get("completion_tokens", 0) + md_token_usage.get("completion_tokens", 0)
            token_usage["total_tokens"] = token_usage.get("total_tokens", 0) + md_token_usage.get("total_tokens", 0)

        filled_count = 0
        for field_key, extracted_val in md_scalars.items():
            if extracted_val is not None and str(extracted_val).strip():
                val = str(extracted_val).strip()
                # Only fill if the field is still empty
                existing = raw_extracted.get(field_key)
                if not existing or not existing.get("value"):
                    raw_extracted[field_key] = {
                        "value": val,
                        "original_value": val,
                        "confidence": 0.85,
                        "validation_status": "valid",
                        "page_number": 1,
                        "bbox": None,
                        "_modifier": "Markdown Extraction"
                    }
                    filled_count += 1
        logger.info(f"[SQL Extraction] Phase 2: Filled {filled_count}/{len(missing_scalar_fields)} fields from markdown.")
        logs.append({"step": "Markdown Scalar Extraction", "message": f"Filled {filled_count}/{len(missing_scalar_fields)} empty scalar fields from Excel markdown."})

    _t_md_scalar_done = time.monotonic() - _t_md_scalar
    logger.info(f"⏱️ [TIMER] Markdown Scalar Pass: {_t_md_scalar_done:.2f}s")

    # 4. Fill entirely missing fields with empty schemas
    for f in model.fields:
        if f.key not in raw_extracted:
            if f.type in TABLE_TYPES:
                raw_extracted[f.key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            else:
                raw_extracted[f.key] = {"value": "", "original_value": "", "confidence": 0.0, "validation_status": "flagged", "page_number": 1}

    # 5. Apply Stage 3 Post-Processing Rules (Deterministic transformations)
    _t_post = time.monotonic()
    import copy
    unmodified_raw = copy.deepcopy(raw_extracted)
    try:
        from app.services.extraction.post_processor import apply_post_processing
        raw_extracted = apply_post_processing(raw_extracted, getattr(model, "post_process_rules", []), model.fields)
    except Exception as e:
        print(f"Post-processing error: {e}")
    _t_post_done = time.monotonic() - _t_post
    logger.info(f"⏱️ [TIMER] Post-Processing: {_t_post_done:.2f}s")

    # 6. Build Final Payload (#2: use accumulated logs, not overwrite)
    logs.insert(0, {"step": "Mapper Reasoning", "message": reasoning})
    logs.append({"step": "Python Engine Exec", "message": f"Tables extracted: {len(tables_map)}, Scalars extracted: {len(scalars_mapping)}"})
    
    final_payload = {
        "raw_extracted": unmodified_raw,
        "guide_extracted": raw_extracted,
        "_token_usage": token_usage,
        "logs": logs,
        "_beta_metadata": {
            "parsed_content": f"Python Engine Mode.\n\n[LLM Mapping Reasoning]\n{reasoning}\n\n[Mapped Object Count]\nTables = {len(tables_map)}, Scalars = {len(scalars_mapping)}",
            "ref_map": {}
        }
    }
    
    _t_total_done = time.monotonic() - _t_total
    logger.info(f"⏱️ [TIMER] █ TOTAL run_sql_extraction: {_t_total_done:.2f}s")
    
    return final_payload
