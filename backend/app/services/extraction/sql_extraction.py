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
    
    fields_context = [{"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules} for f in model.fields]
    
    prompt = f"""
    You are an expert Data Extractor interpreting Excel files. You are given the FULL Excel content as a Markdown table.
    The table contains columns: `row_id` (global row number), and `A`, `B`, `C`, `D`... (representing Excel columns).
    
    Data Content (Markdown):
    {markdown_text}
    
    Target Extraction Schema & Business Rules:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Identify tables and scalars. Fields of type 'table', 'list', 'array' expect a list of objects. Fields of type 'string', 'number' are usually scalars but might be within a table if they map to repeating rows. Look at the description/rules to find the expected keys inside the table objects.
    2. Find the REAL headers for the table(s) in the Excel grid to map the columns properly.
    3. Output a precise Mapping JSON.
    
    CRITICAL RULES:
    - **NO HALLUCINATED KEYS**: The keys inside `"tables"` and `"scalars"` MUST exactly match the `key` strings from the "Target Extraction Schema" above. Do NOT invent your own keys.
    - `"header_row_id"`: The exact `row_id` from the JSON where the table headers reside. The Python engine will slice data starting strictly from `row_id > header_row_id`.
    - `"columns_mapping"`: Map EXPECTED TARGET KEYS (what the final schema wants) to EXCEL COLUMN LETTERS ("A", "B", "C"...). Do NOT use literal text headers here, ONLY the mapped column letter.
    - Reference Data limits do NOT apply to you. You do not do data conversion. Just supply the coordinates (the Column letter).
    
    Return ONLY a JSON object with this EXACT structure:
    {{
        "tables": {{
            "target_table_field_key": {{
                "sheet_name": "Sheet1",
                "header_row_id": 5,
                "columns_mapping": {{
                    "POL": "B",
                    "POD": "C"
                }}
            }}
        }},
        "scalars": {{
            "target_scalar_field_key": {{"sheet_name": "Sheet1", "row_id": 1, "col": "D"}}
        }},
        "reasoning": "Brief mapping logic justification."
    }}
    """
    
    try:
        res = await client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )
        content = res.choices[0].message.content
        return json.loads(content)
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
    logger.info(f"Mapping Plan generated:\n{json.dumps(mapping_plan, indent=2, ensure_ascii=False)}")
    
    # 3. Pure Python Extraction Engine
    raw_extracted = {}
    
    # Pre-build reference lookup dictionaries by field key
    ref_data = model.reference_data or {}
    
    # 3.1 LLM Handoff: Process Natively Extracted Scalars
    scalars_mapping = mapping_plan.get("scalars", {})
    if not isinstance(scalars_mapping, dict):
        logger.warning(f"LLM returned invalid scalars schema type: {type(scalars_mapping)}. Defaulting to empty dict.")
        scalars_mapping = {}
        
    for target_key, s_map in scalars_mapping.items():
        sheet = s_map.get("sheet_name")
        row_id = s_map.get("row_id")
        col = s_map.get("col")
        
        if not all([sheet, row_id is not None, col]):
            continue
            
        try:
            r_id = int(row_id)
            val_df = df[(df["_sheet_name"] == sheet) & (df["row_id"] == r_id)]
            if not val_df.empty and col in val_df.columns:
                raw_val = val_df.iloc[0][col]
                if pd.notna(raw_val):
                    val = str(raw_val).strip()
                    
                    # Apply Reference Data Mapping
                    if target_key in ref_data and val in ref_data[target_key]:
                        val = ref_data[target_key][val]
                        
                    raw_extracted[target_key] = {
                        "value": val,
                        "original_value": str(raw_val),
                        "confidence": 0.90,
                        "validation_status": "valid",
                        "page_number": 1
                    }
        except Exception as e:
            logger.debug(f"Failed to extract scalar {target_key}: {e}")

    # 3.2 Pandas Handoff: Map Tables using Bridge Rules
    tables_map = mapping_plan.get("tables", {})
    if not isinstance(tables_map, dict):
        logger.warning(f"LLM returned invalid tables schema type: {type(tables_map)}. Defaulting to empty dict.")
        tables_map = {}
        
    for target_key, t_map in tables_map.items():
        sheet = t_map.get("sheet_name", "Sheet1")
        header_row_id = t_map.get("header_row_id", 0)
        col_map = t_map.get("columns_mapping", {})
        
        if not isinstance(col_map, dict) or not sheet:
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
        
        sheet_df = df[df["_sheet_name"] == sheet]
        if sheet_df.empty:
            sheet_df = df # Fallback
            
        try:
            h_id = int(header_row_id)
        except (ValueError, TypeError):
            h_id = 0
            
        data_rows = sheet_df[sheet_df["row_id"] > h_id]
        
        extracted_table_rows = []
        for _, row in data_rows.iterrows():
            row_is_empty = True
            row_data = {}
            for inner_key, excel_col in col_map.items():
                if excel_col in row and pd.notna(row[excel_col]):
                    val = str(row[excel_col]).strip()
                    if val and val.lower() != "nan":
                        row_is_empty = False
                        
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
            
            if not row_is_empty:
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
        "_beta_metadata": {
            "parsed_content": f"Python Engine Mode.\n\n[LLM Mapping Reasoning]\n{reasoning}\n\n[Mapped Object Count]\nTables = {len(tables_map)}, Scalars = {len(scalars_mapping)}",
            "ref_map": {}
        }
    }
    
    import json
    with open("/tmp/excel_debug.json", "w", encoding="utf-8") as f:
        json.dump({
            "mapping_schema": mapping_schema,
            "raw_extracted": raw_extracted,
            "file_columns": list(df.columns) if 'df' in locals() else []
        }, f, ensure_ascii=False, indent=2)

    return final_payload
