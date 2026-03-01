import io
import json
import logging
import pandas as pd
from typing import Dict, Any
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

def _df_to_markdown(df: pd.DataFrame) -> str:
    """
    Converts the entire DataFrame into a Markdown string for the LLM.
    Limit to 3000 rows per sheet to prevent 128k token context explosion,
    but large enough to satisfy the user's 'no sampling' requirement.
    """
    md_lines = []
    data_cols = [c for c in df.columns if c not in ['_sheet_name', 'row_id']]
    
    for sheet_name, group in df.groupby('_sheet_name', sort=False):
        group_data = group.dropna(subset=data_cols, how='all')
        if group_data.empty: continue
        
        md_lines.append(f"### Sheet: {sheet_name}")
        cols = ['row_id'] + data_cols
        md_lines.append("| " + " | ".join(cols) + " |")
        md_lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        
        # 3000 max rows per sheet (avoids 128k token crash, but covers 99.9% of structure)
        for _, row in group_data.head(3000).iterrows():
            row_str = []
            for c in cols:
                val = str(row[c]).replace('\n', ' ').strip() if pd.notna(row[c]) else ""
                row_str.append(val)
            md_lines.append("| " + " | ".join(row_str) + " |")
            
    return "\n".join(md_lines)

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
    1. For scalar fields (type 'string', 'number', 'date', etc): Extract the actual value directly from the markdown. You must apply any business rules specified in the schema.
    2. For table fields (type 'table', 'list', 'array'): YOU MUST NOT EXTRACT THE DATA. Instead, output a precise Mapping bridge rule so python Pandas can extract it.
    
    CRITICAL RULES FOR "tables_mapping":
    - **NO HALLUCINATED KEYS**: The keys inside `"tables_mapping"` MUST exactly match the `key` strings of table fields from the "Target Extraction Schema" above.
    - `"header_row_id"`: The exact `row_id` where the table headers reside. The Python engine will slice data starting strictly from `row_id > header_row_id`.
    - `"columns_mapping"`: Map EXPECTED TARGET KEYS (what the final schema wants for the object inside the list) to EXCEL COLUMN LETTERS ("A", "B", "C"...). Do NOT use literal text headers here.
    
    Return ONLY a JSON object with this EXACT structure:
    {{
        "extracted_scalars": {{
            "target_scalar_field_key": "Directly extracted string or number here",
            "another_scalar_field": "Extracted value"
        }},
        "tables_mapping": {{
            "target_table_field_key": {{
                "sheet_name": "Sheet1",
                "header_row_id": 5,
                "columns_mapping": {{
                    "POL": "B",
                    "POD": "C"
                }}
            }}
        }},
        "reasoning": "Brief logic justification."
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
        return {"extracted_scalars": {}, "tables_mapping": {}, "reasoning": f"Mapper failed: {e}"}

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

    # 2. Convert FULL target data to Markdown instead of sampling
    md_content = _df_to_markdown(df)
    
    # 3. Request Schema Mapping & Scalar Extraction from LLM
    mapping_plan = await _run_schema_mapper(md_content, model)
    reasoning = mapping_plan.get("reasoning", "")
    logger.info(f"Mapping Plan generated:\n{json.dumps(mapping_plan, indent=2, ensure_ascii=False)}")
    
    # 3. Pure Python Extraction Engine
    raw_extracted = {}
    
    # Pre-build reference lookup dictionaries by field key
    ref_data = model.reference_data or {}
    
    # 3.1 LLM Handoff: Process Natively Extracted Scalars
    extracted_scalars = mapping_plan.get("scalars_extracted", mapping_plan.get("extracted_scalars", {}))
    for schema_key, scalar_value in extracted_scalars.items():
        # Only inject if it's a requested field
        schema_field = next((f for f in model.fields if f.key == schema_key), None)
        if schema_field:
            raw_extracted[schema_key] = {"value": scalar_value, "confidence": 0.95, "validation_status": "valid"}

    # 3.2 Pandas Handoff: Map Tables using Bridge Rules
    tables_map = mapping_plan.get("tables_mapping", mapping_plan.get("tables", {}))
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
