import io
import json
import logging
import pandas as pd
from typing import Dict, Any
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)


async def _normalize_headers_via_llm(html_content: str, mapper_llm: str) -> str:
    """
    Phase 1.5: Header Normalizer
    Uses a fast LLM to flatten complex multi-row merged headers into a clean 1D array.
    """
    client = get_openai_client()
    
    prompt = f"""
    You are an expert Data Analyst processing Excel data. Below are the top 50 rows of EACH Sheet from an Excel file in HTML table format.
    The table headers include column letters like `A`, `B`, `C`.
    This HTML preserves `colspan` and `rowspan` which represent merged cells in Excel.
    
    Your goal is to flatten the hierarchical/merged headers into a single logical string for each column letter, FOR EACH SHEET.
    For example, if Sheet "Data" has a top header "20DC" spanning columns C and D, and sub-headers "Rate" and "Type", 
    you should output:
    {{ 
      "Data": {{ "C": "20DC - Rate", "D": "20DC - Type" }},
      "Sheet2": {{ "A": "Customer Name" }}
    }}
    
    HTML Content:
    {html_content}
    
    CRITICAL RULES:
    1. Output ONLY a valid JSON OBJECT where the top-level keys are the EXACT Sheet Names found in the HTML `<h3>` tags.
    2. The values must be a JSON object mapping the column letters (e.g., "A", "B", "C") to the flattened logical header strings.
    3. Do NOT output any markdown code blocks (e.g., ```json). Return just the raw JSON object.
    4. Ignore system columns like `row_id` if they exist. Focus purely on the data columns A, B, C, etc.
    """
    try:
        res = await client.chat.completions.create(
            model=mapper_llm,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2000
        )
        content = res.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return content
    except Exception as e:
        logger.error(f"Header Normalizer failed: {e}")
        return "[]"

async def _run_schema_mapper(csv_context: str, normalized_headers: str, model: ExtractionModel, extractor_llm: str) -> Dict[str, Any]:
    """
    Phase 1: LLM Schema Mapper & Scalar Extractor
    The LLM inspects the FULL CSV text of the Excel file generated directly from Pandas.
    It extracts Scalar values directly, and outputs Mapping JSON for Tables using absolute indices.
    """
    client = get_openai_client()
    deployment = extractor_llm or get_current_model()
    
    fields_context = [{"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules, "sub_fields": f.sub_fields} for f in model.fields]
    
    # Smart Truncation: Preserve the first N rows of *every* sheet found in the CSV
    lines = csv_context.split("\n")
    if len(lines) > 200:
        sheets_data = []
        current_sheet_lines = []
        
        for line in lines:
            if line.startswith("### Sheet:"):
                if current_sheet_lines:
                    sheets_data.append(current_sheet_lines)
                current_sheet_lines = [line]
            else:
                if current_sheet_lines is not None:
                    current_sheet_lines.append(line)
        if current_sheet_lines:
            sheets_data.append(current_sheet_lines)
            
        MAX_TOTAL_LINES = 500
        num_sheets = len(sheets_data)
        lines_per_sheet = max(50, min(150, MAX_TOTAL_LINES // max(1, num_sheets)))
        
        truncated_csv = []
        for sheet_lines in sheets_data:
            truncated_csv.extend(sheet_lines[:lines_per_sheet])
            if len(sheet_lines) > lines_per_sheet:
                truncated_csv.append(f"... [TRUNCATED - {len(sheet_lines) - lines_per_sheet} MORE ROWS HIDDEN]")
                
        csv_text = "\n".join(truncated_csv)
    else:
        csv_text = csv_context
    
    prompt = f"""
    You are an expert Data Extractor interpreting Excel files. You are given a sample of the Excel content as a CSV (first N rows).
    The table contains columns: `row_id` (global row number), and `A`, `B`, `C`, `D`... (representing Excel columns).
    
    CRITICAL ARCHITECTURE: The data you see has ALREADY been visually "flatened" and merged headers have been Forward-Filled (ffilled) by Python.
    This means if a cell was previously blank because it was merged, it now explicitly contains the header value.
    
    Data Content (CSV Format):
    {csv_text}
    
    Target Extraction Schema & Business Rules:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Identify tables and scalars based on the Target Schema.
    2. Find the REAL headers for the table(s) in the Excel grid to map the columns properly.
    3. Output a precise Mapping JSON.
    
    CRITICAL INSTRUCTIONS:
    - Return ONLY valid JSON matching the exact schema provided.
    - If `sub_fields` exists for a table field, you MUST map each `sub_field_key` to its corresponding `excel_column` LETTER (e.g., "A", "C", "F").
    - If `sub_fields` is missing, dynamically infer required `sub_field_key` names from the field description or rules.
    - `"header_row_id"`: The exact `row_id` where the actual column headers (titles) are located (e.g., the row containing "POL", "Description", "Amount").
    - `"first_data_row_id"`: The exact `row_id` where the ACTUAL DATA RECORDS begin, which MUST be GREATER THAN the `header_row_id`. Do NOT point this to the header row.
    - `"columns_mapping"`: Map EXPECTED TARGET KEYS (`sub_field_key`) to EXCEL COLUMN LETTERS ("A", "B", "C"...). 
      **SUPER CRITICAL SEMANTIC INFERENCE RULE**: 
      1. **Trust the Data Type over the Header Name**: In Ocean Freight PDFs/Excel, headers are often misaligned. For example, the rate `1240` might accidentally fall under the `Currency` column, and the text `GC` might fall under the `20DC` column. You MUST ignore the header name if the data type beneath it fundamentally mismatches what the schema requires.
      2. **Mathematical Data Matching**: If the schema expects a Rate/Cost (Number), scan the actual data rows to find the column containing the numbers (e.g., 1240, 2500, or mixed with units like "USD 1600", "EUR 700") and map to its COLUMN LETTER. Do NOT map a Rate field to a column containing ONLY standard ocean cargo text (e.g., 'GC', 'FAK' with no numbers).
      3. **Text Data Matching**: If the schema expects Cargo Type (Text), map to the column containing ONLY text (e.g., 'GC').
      4. **Allow Missing Columns (Merged Currency)**: If the CSV physically lacks an isolated column for a required field (e.g., the schema requires `Currency`, but the currency 'USD' is merged directly inside the rate cells like 'USD 1602'), simply SKIP the `Currency` column and DO NOT map it. Map the combined 'USD 1602' column to the Rate field instead.
      5. **Extract the Original Header Name**: Always extract the exact original header text into `excel_header_name`, even if it seems wrong or shifted (e.g., if you map the `1240` column to `20DC`, but its header says `Currency`, write `Currency` into `excel_header_name`).
    - **SCALARS VALUE COORDINATE**: For scalars, the `"col"` MUST point to the column letter ("A", "B") containing the actual VALUE, not the text label. 
      - **IF THE FIELD IS A GENERAL SUMMARY** or does not have a specific coordinate in the grid, output `null` for `sheet_name`, `row_id`, and `col`, and provide your extracted text natively in `exact_value`.
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
                                "header_row_id": {"type": "integer"},
                                "first_data_row_id": {"type": "integer"},
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
                            "required": ["field_key", "sheet_name", "header_row_id", "first_data_row_id", "columns_mapping"],
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

async def run_sql_extraction(file: UploadFile, model: ExtractionModel) -> Dict[str, Any]:
    """
    Two-Track Excel Extraction (Python Engine Mode).
    Phase 13: Single Source of Truth Architecture using pure Pandas.
    """
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

    # 2. Build Single Source of Truth Context from Pandas
    # We forward-fill (ffill) horizontally and vertically to resolve merged headers.
    csv_snippets = []
    if '_sheet_name' in df.columns:
        for sheet_name, group in df.groupby('_sheet_name', sort=False):
            top_rows = group.head(min(150, len(group))).copy()
            data_cols = top_rows.columns[3:]
            
            # 1. Cast data block to object to prevent numerical coercion errors when dragging text into float columns
            top_rows[data_cols] = top_rows[data_cols].astype("object")
            
            # 2. Forward Fill horizontally for top 30 rows (assumed header region)
            top_rows.loc[top_rows.index[:30], data_cols] = top_rows.loc[top_rows.index[:30], data_cols].ffill(axis=1)
            # 3. Forward Fill vertically for top 10 rows
            top_rows.loc[top_rows.index[:10], data_cols] = top_rows.loc[top_rows.index[:10], data_cols].ffill(axis=0)
            
            if '_sheet_name' in top_rows.columns:
                top_rows = top_rows.drop(columns=['_sheet_name'])
            if 'local_row_id' in top_rows.columns:
                top_rows = top_rows.drop(columns=['local_row_id'])
                
            csv_snippet = top_rows.to_csv(index=False)
            csv_snippets.append(f"### Sheet: {sheet_name}\n{csv_snippet}")
    else:
        top_rows = df.head(min(150, len(df))).copy()
        data_cols = top_rows.columns[3:]
        top_rows[data_cols] = top_rows[data_cols].astype("object")
        top_rows.loc[top_rows.index[:30], data_cols] = top_rows.loc[top_rows.index[:30], data_cols].ffill(axis=1)
        top_rows.loc[top_rows.index[:10], data_cols] = top_rows.loc[top_rows.index[:10], data_cols].ffill(axis=0)
        if 'local_row_id' in top_rows.columns:
            top_rows = top_rows.drop(columns=['local_row_id'])
        csv_snippet = top_rows.to_csv(index=False)
        csv_snippets.append(f"### Sheet: Default\n{csv_snippet}")
        
    unified_context = "\n\n".join(csv_snippets)
    
    # Bypass legacy LLM header normalizer since Pandas ffill dynamically solves it.
    normalized_headers_json = "[]"
    
    # 3. Request Schema Mapping & Scalar Extraction from LLM using our Unified Pandas Context
    mapper_llm = getattr(model, "mapper_llm", None)
    extractor_llm = getattr(model, "extractor_llm", None)
    
    mapping_plan = await _run_schema_mapper(unified_context, normalized_headers_json, model, extractor_llm)
    reasoning = mapping_plan.get("reasoning", "")
    token_usage = mapping_plan.pop("_token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    logger.info(f"Mapping Plan generated:\n{json.dumps(mapping_plan, indent=2, ensure_ascii=False)}")
    
    # 3. Pure Python Extraction Engine
    raw_extracted = {}
    logs = []
    
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
        bbox = None
        
        # Virtual Grid constants (Sync with ExcelGridViewer.tsx)
        VIRTUAL_WIDTH = 1000
        CELL_HEIGHT = 50
        col_count = len(df.columns) - 2 if 'df' in locals() and len(df.columns) > 2 else 26
        cell_width = VIRTUAL_WIDTH / max(1, col_count)
        
        page_number = 1
        if sheet and 'df' in locals() and '_sheet_name' in df.columns:
            try:
                s_list = df['_sheet_name'].unique().tolist()
                s_lower = [str(s).strip().lower() for s in s_list]
                search = str(sheet).strip().lower()
                if search in s_lower:
                    page_number = s_lower.index(search) + 1
            except Exception:
                pass
        
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

        # 3. Apply reference data and save
        if val is not None:
            if isinstance(val, str) and target_key in ref_data and val in ref_data[target_key]:
                val = ref_data[target_key][val]
            elif isinstance(val, list) and target_key in ref_data:
                val = [ref_data[target_key].get(str(v), v) for v in val]
                
            raw_extracted[target_key] = {
                "value": val,
                "original_value": str(raw_val),
                "confidence": 0.90,
                "validation_status": "valid",
                "page_number": page_number,
                "bbox": bbox
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
        sheet = t_map.get("sheet_name", "")
        if sheet:
            sheet = str(sheet).strip().lower()
        
        first_data_row_id = t_map.get("first_data_row_id", 1)
        raw_col_map = t_map.get("columns_mapping", {})
        
        # Normalize LLM output column map keys (sub_field_key) to lowercase for safe matching
        col_map = {}
        if isinstance(raw_col_map, dict):
            for k, v in raw_col_map.items():
                if k and v:
                    col_map[str(k).strip().lower()] = str(v).strip().upper()
        
        page_number = 1
        if sheet and 'df' in locals() and '_sheet_name' in df.columns:
            try:
                s_list = df['_sheet_name'].unique().tolist()
                s_lower = [str(s).strip().lower() for s in s_list]
                search = str(sheet).strip().lower()
                if search in s_lower:
                    page_number = s_lower.index(search) + 1
            except Exception:
                pass
        
        if not col_map or not sheet:
            logs.append({"step": f"Table [{target_key}]", "message": f"Skipped: col_map or sheet is empty. Sheet={sheet}, Map={col_map}"})
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
        
        # Case insensitive sheet name search
        df['_sheet_name_lower'] = df['_sheet_name'].str.strip().str.lower()
        sheet_df = df[df["_sheet_name_lower"] == sheet]
        if sheet_df.empty:
            logs.append({"step": f"Table [{target_key}]", "message": f"Sheet '{sheet}' not found, falling back to full combined data."})
            sheet_df = df # Fallback
            
        try:
            h_id = int(first_data_row_id)
        except (ValueError, TypeError):
            h_id = 1
            
        logger.info(f"[{target_key}] Slicing sheet '{sheet}': using `row_id >= {h_id}`")
        logs.append({"step": f"Table [{target_key}] Target", "message": f"Sheet='{sheet}', Starting row_id={h_id}, Mapping={json.dumps(col_map)}"})
        
        data_rows = sheet_df[sheet_df["row_id"] >= h_id]
        
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
                        
                        # Apply Reference Data Mapping
                        if inner_key in ref_data and val in ref_data[inner_key]:
                            val = ref_data[inner_key][val]
                        elif target_key in ref_data and val in ref_data[target_key]:  # Nested fallback
                            val = ref_data[target_key][val]
                            
                        # Calculate Virtual BBox
                        bbox = None
                        try:
                            # excel_col is A, B, C... Find its 0-based index
                            col_idx = df.columns.tolist().index(excel_col) - 3 # Adjusted for metadata cols
                            row_idx = int(row["local_row_id"])
                            
                            x1 = col_idx * cell_width
                            y1 = row_idx * CELL_HEIGHT
                            x2 = x1 + cell_width
                            y2 = y1 + CELL_HEIGHT
                            bbox = [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]
                        except Exception:
                            pass
                            
                        # Wrap cells for validation formatting
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
                extracted_table_rows.append(row_data)
                
        logs.append({"step": f"Table [{target_key}] Exec", "message": f"Extracted {len(extracted_table_rows)} rows out of {len(data_rows)} target data rows."})
        raw_extracted[target_key] = {
            "value": extracted_table_rows,
            "confidence": 0.95 if extracted_table_rows else 0.0,
            "validation_status": "valid" if extracted_table_rows else "flagged",
            "page_number": page_number
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
    
    with open("excel_debug.json", "w", encoding="utf-8") as f:
        json.dump({
            "mapping_plan": mapping_plan,
            "raw_extracted": raw_extracted,
            "file_columns": list(df.columns) if 'df' in locals() else []
        }, f, ensure_ascii=False, indent=2)

    return final_payload
