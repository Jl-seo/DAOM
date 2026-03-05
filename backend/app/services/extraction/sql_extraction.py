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

async def _run_schema_mapper(markdown_text: str, normalized_headers: str, model: ExtractionModel, extractor_llm: str) -> Dict[str, Any]:
    """
    Phase 1: LLM Schema Mapper & Scalar Extractor
    The LLM inspects the FULL markdown text of the Excel file.
    It extracts Scalar values directly, and outputs Mapping JSON for Tables.
    """
    client = get_openai_client()
    deployment = extractor_llm or get_current_model()
    
    fields_context = [{"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules, "sub_fields": f.sub_fields} for f in model.fields]
    
    # Smart Truncation: Preserve the first N rows of *every* sheet found in the markdown
    # instead of just blindly cutting the top 200 lines, which destroys multi-sheet visibility.
    lines = markdown_text.split("\n")
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
            
        # Maximum allowed lines across all headers to prevent token explosion
        # We try to keep it around 500 lines total, BUT we guarantee AT LEAST 50 rows per sheet.
        MAX_TOTAL_LINES = 500
        num_sheets = len(sheets_data)
        
        # Calculate fair share, but ALWAYS guarantee at least 50 rows, up to 150 rows.
        # This means if there are 20 sheets, total lines might be 1000, which is acceptable 
        # compared to missing headers.
        lines_per_sheet = max(50, min(150, MAX_TOTAL_LINES // max(1, num_sheets)))
        
        truncated_markdown = []
        for sheet_lines in sheets_data:
            truncated_markdown.extend(sheet_lines[:lines_per_sheet])
            if len(sheet_lines) > lines_per_sheet:
                truncated_markdown.append(f"... [TRUNCATED - {len(sheet_lines) - lines_per_sheet} MORE ROWS HIDDEN]")
                
        markdown_text = "\n".join(truncated_markdown)
    
    prompt = f"""
    You are an expert Data Extractor interpreting Excel files. You are given a sample of the Excel content as a Markdown table (first 1500 rows).
    The table contains columns: `row_id` (global row number), and `A`, `B`, `C`, `D`... (representing Excel columns).
    
    We have pre-processed the top 50 rows of EACH SHEET for you to resolve complex merged headers, provided via `Normalized Headers Mapping (JSON)`. 
    Use this JSON mapping as a HINT to understand top-level scalar fields or early tables.
    HOWEVER, if a table is located deeper in the document (e.g. at row 60), it will NOT be in the JSON mapping. For tables, you MUST ALWAYS READ THE MARKDOWN DIRECTLY to find the correct Excel Column Letters (`A`, `B`, `C`...) corresponding to the table's headers.
    
    Normalized Headers Mapping (JSON dictionary of SheetName -> Column Mapping, strictly top 50 rows per sheet):
    {normalized_headers}
    
    Data Content (Markdown):
    {markdown_text}
    
    Target Extraction Schema & Business Rules:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Identify tables and scalars based on the Target Schema.
    2. Find the REAL headers for the table(s) in the Excel grid to map the columns properly.
    3. Output a precise Mapping JSON.
    
    CRITICAL INSTRUCTIONS:
    - Return ONLY valid JSON matching the exact schema provided.
    - If `sub_fields` exists for a table field, you MUST map each `sub_field_key` to its corresponding `excel_column` letter (e.g., "A", "C", "F").
    - DO NOT guess or assume sequential columns (e.g., A, B, C). Read the actual Column Letters from the Markdown table, because empty columns may have been omitted (e.g., A, C, D).
    - If `sub_fields` is missing, dynamically infer required `sub_field_key` names from the field description or rules.
    - `"header_row_id"`: The exact `row_id` where the actual column headers (titles) are located (e.g., the row containing "POL", "Description", "Amount").
    - `"first_data_row_id"`: The exact `row_id` where the ACTUAL DATA RECORDS begin, which MUST be GREATER THAN the `header_row_id`. Do NOT point this to the header row.
    - `"columns_mapping"`: Map EXPECTED TARGET KEYS (`sub_field_key`) to EXCEL COLUMN LETTERS ("A", "B", "C"...). 
      **SUPER CRITICAL SEMANTIC INFERENCE RULE**: 
      1. NEVER blindly map columns sequentially just because they exist! 
      2. You MUST extract the exact text of the Excel header into `excel_header_name`. 
      3. If a schema field does not exist in the Excel table, DO NOT INCLUDE IT in the mapping array. Skip it. For example, if the schema asks for `sc_number` but the Excel table headers only have `Receipt`, `POL`, `POD`, `Delivery`, then DO NOT map `sc_number` to `Receipt`. Just omit `sc_number` entirely!
      4. **SUB-FIELD SEMANTICS & RULES (CRITICAL)**: You MUST read the `description` and `rules` of EVERY `sub_field` in the schema. The true meaning of what column to map is found in its `description` and `rules`, not just its `label`! If a sub-field rule says "Use the USD rate" or "Look for Freight", map it to the column that semantically matches that description and rule.
      5. **DATA TYPE MATCHING (CRITICAL)**: You MUST validate your mapping against the ACTUAL DATA ROWS below the header. 
         - If the schema expects a `number`, `금액`, `단가` or `운임` (Rates/Charges/Amounts), the mapped column's data MUST be numeric (e.g., 1500, $200). 
         - **NEVER** map a numeric schema field to a column where the data rows contain text (e.g., "GC", "DRY", "Unit", "Type").
         - If the schema expects text/string, map to the text column.
      6. **MULTI-ROW / MERGED HEADERS**: Excel tables often have 2-3 rows of hierarchical headers (e.g., Row 1: "20DC", Row 2: "Rate" | "Type"). If multiple columns share the same top-level header but have different sub-headers, use the DATA TYPE in the rows to decide which column corresponds to the schema field. If the schema asks for a rate (number), pick the sub-column containing numbers. If it asks for a type (string), pick the sub-column containing text.
    - **SCALARS VALUE COORDINATE**: For scalars, the `"col"` MUST point to the column containing the actual VALUE, not the text label. 
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
                                        {"type": "null"},
                                        {"type": "array", "items": {}}
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

async def run_sql_extraction(file: UploadFile, model: ExtractionModel, md_content: str = "") -> Dict[str, Any]:
    """
    Two-Track Excel Extraction (Python Engine Mode, replaces DuckDB SQL logic).
    Uses LLM for lightweight schema mapping and Heavyweight Pandas for execution.
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
                combined_df.insert(0, 'row_id', range(0, len(combined_df)))
        else:
            try:
                excel_data = pd.read_excel(io.BytesIO(fc), sheet_name=None, header=None, engine="calamine")
            except ImportError:
                excel_data = pd.read_excel(io.BytesIO(fc), sheet_name=None, header=None, engine="openpyxl")
            
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
        return df

    from fastapi.concurrency import run_in_threadpool
    try:
        df = await run_in_threadpool(_load_excel_sync, file_content, filename_lower, content_type)
    except Exception as e:
        logger.error(f"Failed to load Excel with pandas: {e}")
        raise ValueError(f"지원하지 않거나 손상된 엑셀 구조입니다. 파일 로딩 실패: {e}")

    # 2. Use the provided Markdown content from ExcelParser
    if not md_content:
        # Fallback if md_content is empty
        logger.warning("md_content is empty, this shouldn't happen in native mode.")
        md_content = "Empty Excel Content"
        
    # Phase 1.5: Header Normalization via Mapper LLM
    mapper_llm = getattr(model, "mapper_llm", None)
    extractor_llm = getattr(model, "extractor_llm", None)
    
    normalized_headers_json = "[]"
    if mapper_llm:
        logger.info(f"[Extraction] Running Header Normalizer with {mapper_llm}")
        try:
            # Extract top 50 rows *per sheet* for header normalization
            html_snippets = []
            if '_sheet_name' in df.columns:
                for sheet_name, group in df.groupby('_sheet_name', sort=False):
                    top_rows = group.head(min(50, len(group))).copy()
                    top_rows = top_rows.ffill(axis=1).ffill(axis=0)
                    if '_sheet_name' in top_rows.columns:
                        top_rows = top_rows.drop(columns=['_sheet_name'])
                    html_snippet = top_rows.to_html(index=False)
                    html_snippets.append(f"<h3>Sheet: {sheet_name}</h3>\n{html_snippet}")
            else:
                top_rows = df.head(min(50, len(df))).copy()
                top_rows = top_rows.ffill(axis=1).ffill(axis=0)
                html_snippet = top_rows.to_html(index=False)
                html_snippets.append(f"<h3>Sheet: Default</h3>\n{html_snippet}")
                
            combined_html = "\n\n".join(html_snippets)
            normalized_headers_json = await _normalize_headers_via_llm(combined_html, mapper_llm)
            logger.info(f"[Extraction] Normalized Headers: {normalized_headers_json}")
        except Exception as e:
            logger.warning(f"Failed to normalize headers: {e}")
    
    # 3. Request Schema Mapping & Scalar Extraction from LLM
    mapping_plan = await _run_schema_mapper(md_content, normalized_headers_json, model, extractor_llm)
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
                            "value": "",
                            "confidence": 0.0,
                            "validation_status": "flagged",
                            "original_value": ""
                        }
                else:
                    # Unmapped Column, or completely empty NaN cell
                    row_data[inner_key] = {
                        "value": "",
                        "confidence": 0.0,
                        "validation_status": "flagged",
                        "original_value": ""
                    }
            
            if row_has_meaningful_data:
                extracted_table_rows.append(row_data)
                
        logs.append({"step": f"Table [{target_key}] Exec", "message": f"Extracted {len(extracted_table_rows)} rows out of {len(data_rows)} target data rows."})
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
    
    with open("excel_debug.json", "w", encoding="utf-8") as f:
        json.dump({
            "mapping_plan": mapping_plan,
            "raw_extracted": raw_extracted,
            "file_columns": list(df.columns) if 'df' in locals() else []
        }, f, ensure_ascii=False, indent=2)

    return final_payload
