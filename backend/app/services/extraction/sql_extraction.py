import io
import json
import logging
import pandas as pd
from typing import Dict, Any
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

def _get_smart_excel_samples(df: pd.DataFrame) -> str:
    """
    Samples top 15 rows + top 10 most 'dense' rows per sheet so deeply buried headers are caught.
    """
    sample_dfs = []
    # Drop rows that are entirely empty across all data columns
    data_cols = [c for c in df.columns if c not in ['_sheet_name', 'row_id']]
    
    for sheet_name, group in df.groupby('_sheet_name', sort=False):
        group_data = group.dropna(subset=data_cols, how='all')
        
        # 1. Top 15 rows
        top_rows = group.head(15)
        
        # 2. Find dense rows (most non-null values) that are NOT in top 15
        remaining = group_data.iloc[15:]
        if not remaining.empty:
            dense_counts = remaining[data_cols].notna().sum(axis=1)
            # Get indices of top 10 densest rows
            dense_idx = dense_counts.nlargest(10).index
            dense_rows = remaining.loc[dense_idx].sort_index()
            combined = pd.concat([top_rows, dense_rows]).drop_duplicates(subset=['row_id']).sort_index()
        else:
            combined = top_rows
            
        sample_dfs.append(combined)
        
    data_sample_df = pd.concat(sample_dfs) if sample_dfs else pd.DataFrame()
    if len(data_sample_df) > 150:
        data_sample_df = data_sample_df.head(150)
        
    data_sample_df = data_sample_df.fillna("").astype(str).map(lambda x: x[:100] + "..." if len(x) > 100 else x)
    return data_sample_df.to_csv(index=False)

async def _run_schema_mapper(data_sample_csv: str, model: ExtractionModel) -> Dict[str, Any]:
    """
    Phase 1: LLM Schema Mapper
    The LLM visually inspects the sample csv (which has density-based rows) 
    and outputs a mapping JSON indicating where each target field is located.
    """
    client = get_openai_client()
    deployment = get_current_model()
    
    fields_context = [{"key": f.key, "label": f.label, "type": f.type, "description": f.description, "rules": f.rules} for f in model.fields]
    
    prompt = f"""
    You are an expert Data Mapper interpreting Excel structures. Your job is to scan an Excel file sample (converted to CSV) and output a Mapping JSON.
    The CSV contains columns: `row_id` (global row number), `_sheet_name` (Excel sheet), and `A`, `B`, `C`, `D`... (data columns).
    
    CSV Data Sample (Top & Dense Rows only):
    {data_sample_csv}
    
    Target Extraction Schema & Business Rules:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    YOUR TASKS:
    1. Identify tables and scalars. Fields of type 'table', 'list', 'array' expect a list of objects. Fields of type 'string', 'number' are usually scalars but might be within a table if they map to repeating rows. Look at the description/rules to find the expected keys inside the table objects.
    2. Find the REAL headers for the table(s) in the Excel grid to map the columns properly.
    3. Output a precise Mapping JSON.
    
    CRITICAL RULES:
    - **NO HALLUCINATED KEYS**: The keys inside `"tables"` and `"scalars"` MUST exactly match the `key` strings from the "Target Extraction Schema" above. Do NOT invent your own keys (e.g., do not use "Table1", "RateTable", "Information"). If the schema key is `shipping_rates_extracted`, use EXACTLY that.
    - `"header_row_id"`: The exact `row_id` from the CSV where the table headers reside. The Python engine will slice data starting strictly from `row_id > header_row_id`.
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
                    "POD": "C",
                    "20DC": "D"
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
        return {"tables": {}, "scalars": {}, "reasoning": f"Mapper failed: {e}"}

async def run_sql_extraction(file: UploadFile, model: ExtractionModel) -> Dict[str, Any]:
    """
    Two-Track Excel Extraction (Python Engine Mode, replaces DuckDB SQL logic).
    Uses LLM for lightweight schema mapping and Heavyweight Pandas for execution.
    """
    logger.info(f"Starting Two-Track Extraction for {file.filename}")
    
    file_content = await file.read()
    await file.seek(0)
    
    # 1. Load Excel into Pandas
    try:
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

    # 2. Smart Sampling and LLM Mapping
    data_sample_csv = _get_smart_excel_samples(df)
    logger.debug(f"Data Sample for LLM (Length: {len(data_sample_csv)})\n{data_sample_csv[:500]}")
    
    mapping_schema = await _run_schema_mapper(data_sample_csv, model)
    reasoning = mapping_schema.get("reasoning", "")
    logger.info(f"LLM Mapping Schema Reasoning: {reasoning}")
    
    # 3. Pure Python Extraction Engine
    raw_extracted = {}
    
    # Pre-build reference lookup dictionaries by field key
    ref_data = model.reference_data or {}
    
    # 3.1 Extract Tables
    tables_map = mapping_schema.get("tables", {})
    if not isinstance(tables_map, dict):
        logger.warning(f"LLM returned invalid tables schema type: {type(tables_map)}. Defaulting to empty dict.")
        tables_map = {}
        
    for target_key, t_map in tables_map.items():
        sheet = t_map.get("sheet_name")
        header_row_id = t_map.get("header_row_id", 0)
        col_map = t_map.get("columns_mapping", {})
        
        if not isinstance(col_map, dict) or not sheet:
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
        
        sheet_df = df[df["_sheet_name"] == sheet]
        if sheet_df.empty:
            raw_extracted[target_key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            continue
            
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
                    if val:
                        row_is_empty = False
                        # Apply Reference Data Mapping
                        if inner_key in ref_data and val in ref_data[inner_key]:
                            val = ref_data[inner_key][val]
                        elif target_key in ref_data and val in ref_data[target_key]:  # Nested fallback
                            val = ref_data[target_key][val]
                            
                        # _validate_and_format in service expects cells to be either raw values or DAOM dicts
                        # It iterates over cells. In DuckDB we wrapped cells. Here we wrap cells as well.
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

    # 3.2 Extract Scalars
    scalars_map = mapping_schema.get("scalars", {})
    if not isinstance(scalars_map, dict):
        logger.warning(f"LLM returned invalid scalars schema type: {type(scalars_map)}. Defaulting to empty dict.")
        scalars_map = {}
        
    for target_key, s_map in scalars_map.items():
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

    # 4. Fill entirely missing fields with empty schemas
    for f in model.fields:
        if f.key not in raw_extracted:
            if f.type == "table":
                raw_extracted[f.key] = {"value": [], "confidence": 0.0, "validation_status": "flagged", "page_number": 1}
            else:
                raw_extracted[f.key] = {"value": "", "original_value": "", "confidence": 0.0, "validation_status": "flagged", "page_number": 1}

    # 5. Build Final Payload
    final_payload = {
        "guide_extracted": raw_extracted,
        "_beta_metadata": {
            "parsed_content": f"Python Engine Mode.\n\n[LLM Mapping Reasoning]\n{reasoning}\n\n[Mapped Object Count]\nTables = {len(tables_map)}, Scalars = {len(scalars_map)}",
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
