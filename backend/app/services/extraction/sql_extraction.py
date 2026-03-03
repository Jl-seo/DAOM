import io
import json
import logging
import pandas as pd
from typing import Dict, Any
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)


async def _run_schema_mapper(markdown_text: str, model: ExtractionModel) -> Dict[str, Any]:
    """
    Phase 1: LLM Schema Mapper & Scalar Extractor
    The LLM inspects the FULL markdown text of the Excel file.
    It extracts Scalar values directly, and outputs Mapping JSON for Tables.
    """
    client = get_openai_client()
    deployment = get_current_model()
    
    fields_context = [{"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules, "sub_fields": f.sub_fields} for f in model.fields]
    
    # Truncate markdown_text to prevent context overload and save tokens
    lines = markdown_text.split("\n")
    if len(lines) > 50:
        markdown_text = "\n".join(lines[:50]) + "\n... [TRUNCATED - EXCEL CONTENT TOO LARGE, MAPPING BY HEADERS ONLY]"
    
    prompt = f"""
    You are an expert Data Extractor interpreting Excel files. You are given a sample of the Excel content as a Markdown table (first 50 rows).
    The table contains columns: `row_id` (global row number), and `A`, `B`, `C`, `D`... (representing Excel columns).
    
    Data Content (Markdown):
    {markdown_text}
    
    Target Extraction Schema & Business Rules:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Identify tables and scalars. Fields of type 'table', 'list', 'array' expect a list of objects. Fields of type 'string', 'number' are usually scalars but might be within a table if they map to repeating rows. Look at the description/rules/sub_fields to find the expected keys inside the table objects.
    2. Find the REAL headers for the table(s) in the Excel grid to map the columns properly.
    3. Output a precise Mapping JSON array format.
    
    CRITICAL RULES:
    - **NO HALLUCINATED KEYS**: The keys `field_key` and `sub_field_key` MUST exactly match the `key` strings from the "Target Extraction Schema" above. Do NOT invent your own keys.
    - `"first_data_row_id"`: The exact `row_id` from the JSON where the ACTUAL DATA records begin. If headers span multiple rows (e.g. row 0 is main header, row 1 is sub-header), you MUST output `first_data_row_id: 2`. The Python engine will slice data starting strictly from `row_id >= first_data_row_id`.
    - `"columns_mapping"`: Map EXPECTED TARGET KEYS (what the final schema wants, specified in `sub_fields`) to EXCEL COLUMN LETTERS ("A", "B", "C"...). Do NOT use literal text headers here, ONLY the mapped column letter.
    - **SCALARS VALUE COORDINATE**: For scalars, the `"col"` MUST point to the column containing the actual VALUE, not the text label. For example, if row 3 Column A says "VesselName" and Column B says "MSC ALICE", you MUST return `{{"col": "B"}}`.
    - **SCALAR FALLBACK**: For scalars, also output `"exact_value"` containing the raw text you see in the cell, as a fallback backup.
    """
    
    response_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "excel_mapping",
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
                                "sheet_name": {"type": "string"},
                                "first_data_row_id": {"type": "integer"},
                                "columns_mapping": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "sub_field_key": {"type": "string"},
                                            "excel_column": {"type": "string"}
                                        },
                                        "required": ["sub_field_key", "excel_column"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["field_key", "sheet_name", "first_data_row_id", "columns_mapping"],
                            "additionalProperties": False
                        }
                    },
                    "scalars": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_key": {"type": "string"},
                                "sheet_name": {"type": "string"},
                                "row_id": {"type": "integer"},
                                "col": {"type": "string"},
                                "exact_value": {"type": ["string", "null"]}
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
        logger.error(f"Schema Mapper failed: {e}")
        return {"scalars": {}, "tables": {}, "reasoning": f"Mapper failed: {e}"}

async def run_sql_extraction(file: UploadFile, model: ExtractionModel, md_content: str = "") -> Dict[str, Any]:
    """
    Two-Track Excel Extraction (Python Engine Mode, replaces DuckDB SQL logic).
    Uses LLM for lightweight schema mapping and Heavyweight Pandas for execution.
    """
    logger.info(f"Starting Two-Track Extraction for {file.filename}")
    
    file_content = await file.read()
    await file.seek(0)
    
    # 1. Load Excel or CSV into Pandas
    try:
        filename_lower = file.filename.lower()
        if filename_lower.endswith('.csv') or file.content_type == 'text/csv':
            content_str = None
            for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]:
                try:
                    content_str = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if content_str is None:
                raise ValueError("Failed to decode CSV file with supported encodings")
                
            # Read CSV perfectly aligned with Excel Parser behavior
            import csv
            reader = csv.reader(io.StringIO(content_str))
            csv_rows = list(reader)
            combined_df = pd.DataFrame(csv_rows)
            combined_df = combined_df.dropna(how='all')
            if not combined_df.empty:
                combined_df.insert(0, '_sheet_name', 'Data')
                combined_df.insert(0, 'row_id', range(0, len(combined_df)))
        else:
            try:
                excel_data = pd.read_excel(io.BytesIO(file_content), sheet_name=None, header=None, engine="calamine")
            except ImportError:
                excel_data = pd.read_excel(io.BytesIO(file_content), sheet_name=None, header=None, engine="openpyxl")
            
            combined_df = pd.DataFrame()
            row_offset = 0
            for sheet_name, sheet_df in excel_data.items():
                sheet_df = sheet_df.dropna(how='all') 
                if not sheet_df.empty:
                    sheet_df.insert(0, '_sheet_name', str(sheet_name))
                    # Add row_id before concat to preserve true row indexing per sheet or globally.
                    sheet_df.insert(0, 'row_id', range(row_offset, row_offset + len(sheet_df)))
                    row_offset += len(sheet_df)
                    combined_df = pd.concat([combined_df, sheet_df], ignore_index=True)
                
        if combined_df.empty:
            raise ValueError("All sheets are empty.")
            
        df = combined_df
        
        # Standardize column names (A, B, C...)
        clean_cols = ['row_id', '_sheet_name']
        for i in range(len(df.columns) - 2):
            name = ""
            n = i
            while n >= 0:
                name = chr(n % 26 + 65) + name
                n = n // 26 - 1
            clean_cols.append(name)
            
        df.columns = clean_cols
        
    except Exception as e:
        logger.error(f"Failed to load Excel with pandas: {e}")
        raise ValueError(f"지원하지 않거나 손상된 엑셀 구조입니다. 파일 로딩 실패: {e}")

    # 2. Use the provided Markdown content from ExcelParser
    if not md_content:
        # Fallback if md_content is empty
        logger.warning("md_content is empty, this shouldn't happen in native mode.")
        md_content = "Empty Excel Content"
    
    # 3. Request Schema Mapping & Scalar Extraction from LLM
    mapping_plan = await _run_schema_mapper(md_content, model)
    reasoning = mapping_plan.get("reasoning", "")
    token_usage = mapping_plan.pop("_token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    logger.info(f"Mapping Plan generated:\n{json.dumps(mapping_plan, indent=2, ensure_ascii=False)}")
    
    # 3. Pure Python Extraction Engine
    raw_extracted = {}
    
    # Pre-build reference lookup dictionaries by field key
    ref_data = model.reference_data or {}
    
    # 3.1 LLM Handoff: Process Natively Extracted Scalars
    raw_scalars = mapping_plan.get("scalars", [])
    if not isinstance(raw_scalars, list):
        logger.warning(f"LLM returned invalid scalars schema type: {type(raw_scalars)}. Defaulting to empty list.")
        raw_scalars = []
        
    scalars_mapping = {s["field_key"]: s for s in raw_scalars if "field_key" in s}
        
    for target_key, s_map in scalars_mapping.items():
        sheet = s_map.get("sheet_name")
        row_id = s_map.get("row_id")
        col = s_map.get("col")
        exact_value = s_map.get("exact_value")
        
        # Fallback tracking
        val = None
        raw_val = None
        
        # 1. Try Coordinate-based pure Pandas lookup
        if sheet and row_id is not None and col:
            try:
                r_id = int(row_id)
                val_df = df[(df["_sheet_name"] == sheet) & (df["row_id"] == r_id)]
                if not val_df.empty and col in val_df.columns:
                    raw_val = val_df.iloc[0][col]
                    if pd.notna(raw_val):
                        val = str(raw_val).strip()
            except Exception as e:
                logger.debug(f"Failed to extract scalar {target_key} via coordinates: {e}")
                
        # 2. Fallback to Exact Value provided by LLM if Pandas lookup failed or was empty
        if not val and exact_value and str(exact_value).strip():
            logger.info(f"Using LLM exact_value fallback for {target_key} = {exact_value}")
            val = str(exact_value).strip()
            raw_val = val

        # 3. Apply reference data and save
        if val:
            if target_key in ref_data and val in ref_data[target_key]:
                val = ref_data[target_key][val]
                
            raw_extracted[target_key] = {
                "value": val,
                "original_value": str(raw_val),
                "confidence": 0.90,
                "validation_status": "valid",
                "page_number": 1
            }
        else:
            logger.debug(f"Skipping empty scalar {target_key}")

    # 3.2 Pandas Handoff: Map Tables using Bridge Rules
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
        
        tables_map[t["field_key"]] = {
            "sheet_name": t.get("sheet_name", "Sheet1"),
            "first_data_row_id": t.get("first_data_row_id", 1),
            "columns_mapping": col_map_dict
        }
        
    for target_key, t_map in tables_map.items():
        sheet = t_map.get("sheet_name", "Sheet1")
        first_data_row_id = t_map.get("first_data_row_id", 1)
        col_map = t_map.get("columns_mapping", {})
        
        if not isinstance(col_map, dict) or not sheet:
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
        
        sheet_df = df[df["_sheet_name"] == sheet]
        if sheet_df.empty:
            sheet_df = df # Fallback
            
        try:
            h_id = int(first_data_row_id)
        except (ValueError, TypeError):
            h_id = 1
            
        data_rows = sheet_df[sheet_df["row_id"] >= h_id]
        
        extracted_table_rows = []
        
        # 1. Look up the expected schema for this table
        expected_sub_keys = []
        for f in model.fields:
            if f.key == target_key and getattr(f, 'sub_fields', None):
                expected_sub_keys = [sf.key for sf in getattr(f, 'sub_fields')]
                break
                
        # Fallback if no schema is strictly defined or found
        if not expected_sub_keys:
            expected_sub_keys = list(col_map.keys())

        for _, row in data_rows.iterrows():
            row_has_meaningful_data = False
            row_data = {}
            
            # 2. Iterate over universally expected keys based on schema
            for inner_key in expected_sub_keys:
                excel_col = col_map.get(inner_key)
                
                # Check if we have mapped column and the cell has data
                if excel_col and excel_col in row and pd.notna(row[excel_col]):
                    val = str(row[excel_col]).strip()
                    if val and val.lower() != "nan":
                        row_has_meaningful_data = True
                        
                        # Apply Reference Data Mapping
                        if inner_key in ref_data and val in ref_data[inner_key]:
                            val = ref_data[inner_key][val]
                        elif target_key in ref_data and val in ref_data[target_key]:  # Nested fallback
                            val = ref_data[target_key][val]
                            
                        # Wrap cells for validation formatting
                        row_data[inner_key] = {
                            "value": val,
                            "confidence": 0.95,
                            "validation_status": "valid",
                            "original_value": str(row[excel_col]).strip()
                        }
                    else:
                        # Empty but mapped string
                        row_data[inner_key] = {
                            "value": None,
                            "confidence": 0.0,
                            "validation_status": "flagged",
                            "original_value": ""
                        }
                else:
                    # Unmapped Column, or completely empty NaN cell
                    row_data[inner_key] = {
                        "value": None,
                        "confidence": 0.0,
                        "validation_status": "flagged",
                        "original_value": None
                    }
            
            if row_has_meaningful_data:
                extracted_table_rows.append(row_data)
                
        raw_extracted[target_key] = {
            "value": extracted_table_rows,
            "confidence": 0.95 if extracted_table_rows else 0.0,
            "validation_status": "valid" if extracted_table_rows else "flagged",
            "page_number": 1
        }

    # 4. Fill entirely missing fields with empty schemas
    for f in model.fields:
        if f.key not in raw_extracted:
            if f.type in ("table", "list", "array", "object"):
                raw_extracted[f.key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            else:
                raw_extracted[f.key] = {"value": "", "original_value": "", "confidence": 0.0, "validation_status": "flagged", "page_number": 1}

    # 5. Build Final Payload
    final_payload = {
        "guide_extracted": raw_extracted,
        "_token_usage": token_usage,
        "logs": [
            {"step": "Mapper Reasoning", "message": reasoning},
            {"step": "Python Engine Exec", "message": f"Tables extracted: {len(tables_map)}, Scalars extracted: {len(scalars_mapping)}"}
        ],
        "_beta_metadata": {
            "parsed_content": f"Python Engine Mode.\n\n[LLM Mapping Reasoning]\n{reasoning}\n\n[Mapped Object Count]\nTables = {len(tables_map)}, Scalars = {len(scalars_mapping)}",
            "ref_map": {}
        }
    }
    
    with open("/tmp/excel_debug.json", "w", encoding="utf-8") as f:
        json.dump({
            "mapping_plan": mapping_plan,
            "raw_extracted": raw_extracted,
            "file_columns": list(df.columns) if 'df' in locals() else []
        }, f, ensure_ascii=False, indent=2)

    return final_payload
