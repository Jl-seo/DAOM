import io
import json
import logging
import re
from typing import Dict, Any, List

import duckdb
import pandas as pd
from fastapi import UploadFile

from app.schemas.model import ExtractionModel
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

async def _run_profiler(data_sample_csv: str, model: ExtractionModel) -> Dict[str, Any]:
    """Stage 1: Profile the data sample to find the correct sheet and header coordinates."""
    client = get_openai_client()
    deployment = get_current_model()
    
    # Just grab names and rules to give context
    fields_context = [{"key": f.key, "type": f.type, "rules": f.rules} for f in model.fields]
    
    prompt = f"""
    You are a Data Profiler. Your job is to scan a chaotic Excel file (converted to CSV) and find where the actual data starts.
    The CSV contains a special column `_sheet_name` indicating which Excel sheet the row came from.
    
    CSV Data Sample (First 15 rows of every active sheet):
    {data_sample_csv}
    
    Target Fields to Extract:
    {json.dumps(fields_context, ensure_ascii=False, indent=2)}
    
    Locate the target table headers (e.g. POL_CODE, POL_NAME).
    Return a JSON object:
    {{
        "target_sheet_name": "The exact string in _sheet_name where the table exists",
        "header_row_index": 2 (The row number where the table header starts, 0-indexed),
        "reasoning": "Explain why you chose this sheet and header row"
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
        logger.error(f"Profiler failed: {e}")
        return {"target_sheet_name": None, "header_row_index": 0, "reasoning": "Profiler failed"}

async def run_sql_extraction(file: UploadFile, model: ExtractionModel) -> Dict[str, Any]:
    """
    Beta Feature: Excel Text-to-SQL Extraction via DuckDB.
    Instead of passing data to LLM, loads Excel to InMemory DB and generates SQL.
    """
    logger.info(f"Starting SQL Extraction (DuckDB) for {file.filename}")
    
    file_content = await file.read()
    await file.seek(0)
    
    # 1. Load Excel into Pandas (Handle multiple sheets & missing headers gracefully)
    try:
        # Read ALL sheets, explicitly turning off header guessing so they all align natively
        excel_data = pd.read_excel(io.BytesIO(file_content), sheet_name=None, header=None)
        
        combined_df = pd.DataFrame()
        for sheet_name, sheet_df in excel_data.items():
            sheet_df = sheet_df.dropna(how='all') # Remove entirely empty rows
            if not sheet_df.empty:
                sheet_df.insert(0, '_sheet_name', str(sheet_name))
                combined_df = pd.concat([combined_df, sheet_df], ignore_index=True)
                
        if combined_df.empty:
            raise ValueError("All sheets are empty.")
            
        df = combined_df
        
        # Standardize column names (0 -> A, 1 -> B, ...)
        clean_cols = ['_sheet_name']
        for i in range(len(df.columns) - 1):
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

    # 2. Setup DuckDB InMemory DB
    con = duckdb.connect(database=':memory:')
    
    try:
        # Load df into duckdb (implicitly available)
        con.execute("CREATE TABLE raw_data AS SELECT * FROM df")
        
        # 3. Extract Schema Info and Data Sample
        schema_df = con.execute("DESCRIBE raw_data").df()
        columns = schema_df['column_name'].tolist()
        types = schema_df['column_type'].tolist()
        schema_info = ", ".join([f"{c} ({t})" for c, t in zip(columns, types)])
        
        # ROOT CAUSE FIX 2: Smart multi-sheet sampling (15 rows per sheet, up to 100 total max)
        sample_dfs = []
        # groupby preserves insertion order depending on sort=False, but duckdb data is row-bound anyway
        for sheet_name, group in df.groupby('_sheet_name', sort=False):
            sample_dfs.append(group.head(15))
            
        data_sample_df = pd.concat(sample_dfs)
        if len(data_sample_df) > 100:
            data_sample_df = data_sample_df.head(100)
            
        # Convert all columns to string and truncate to prevent token bloat
        data_sample_df = data_sample_df.fillna("").astype(str).map(lambda x: x[:100] + "..." if len(x) > 100 else x)
        data_sample_csv = data_sample_df.to_csv(index=False)
        
        logger.info(f"Loaded Schema: {schema_info}")
        logger.debug(f"Data Sample:\n{data_sample_csv}")
        
        # 3.5 Stage 1: Data Profiling
        data_profile = await _run_profiler(data_sample_csv, model)
        logger.info(f"Data Profile (Stage 1): {data_profile}")
        profile_text = json.dumps(data_profile, ensure_ascii=False, indent=2)
        
        # 4. Target Fields Info
        fields_info = []
        for f in model.fields:
            field_entry = {"key": f.key, "label": f.label, "type": f.type}
            if f.description:
                field_entry["description"] = f.description
            if f.rules:
                field_entry["rules"] = f.rules
            fields_info.append(field_entry)
        
        field_descriptions = json.dumps(fields_info, ensure_ascii=False, indent=2)
        
        global_rules_text = ""
        if model.global_rules:
            global_rules_text = f"\n\nGlobal Rules (apply to ALL fields):\n{model.global_rules}"
            
        ref_data_text = ""
        if model.reference_data:
            ref_json = json.dumps(model.reference_data, ensure_ascii=False, indent=2)
            ref_data_text = f"\n\nReference Data (use to map codes/names if needed):\n{ref_json}"

        # 5. Prompt LLM for SQL Query (Stage 2: SQL Engineer)
        system_prompt = f"""
        You are an expert Data Engineer writing standard SQL queries (DuckDB compatible) to extract structured data from an Excel file.
        
        We have loaded the Excel file into a virtual DuckDB table named `raw_data`. 
        Here is the Database Schema:
        {schema_info}
        
        Here is a SAMPLE of the actual data inside `raw_data`:
        {data_sample_csv}
        
        STAGE 1 DATA PROFILE (USE THIS AS YOUR GUIDE):
        Another AI has pre-scanned this data. Here is its assessment of where the actual target data lives:
        {profile_text}
        USE this profile to write targeted WHERE clauses (e.g. `WHERE _sheet_name = 'X'`).
        
        Your task is to write a single SELECT query that extracts data mapping to this exact JSON schema:
        {field_descriptions}
        {global_rules_text}
        {ref_data_text}
        
        CRITICAL RULES FOR SQL GENERATION:
        1. Write ONLY a SELECT query targeting the `raw_data` table.
        2. DO NOT write DROP, DELETE, INSERT, or UPDATE.
        3. Aliases in your SELECT clause MUST exactly match the requested target 'key' name in English.
        4. Use SQL functions if a field asks for derived data based on its 'rules'.
        5. DO NOT USE `LIMIT` for the table extraction logic (we need EVERY valid row from the 6000+ row file).
        6. DO NOT use overly strict `WHERE` filtering (e.g. demanding `AND col2 IS NOT NULL AND col3 IS NOT NULL`) because real-world Excel data is sparse. If you drop rows just because one value is missing, we lose critical data. Only filter out obvious noise/header rows.
        
        REQUIRED FORMATTING BY DATATYPE (VERY IMPORTANT):
        - For fields where `type: string`, `number`, or `date`: The SELECT alias MUST return a single primitive scalar value (string or number). DO NOT use `json_object` or arrays. (e.g., `SELECT (SELECT A FROM raw_data WHERE A IS NOT NULL LIMIT 1) AS remark`)
        - For fields where `type: table`: The SELECT alias MUST return a JSON Array string. You MUST use `json_group_array(json_object(...))` inside a scalar subquery to aggregate the rows.
          - CORRECT TABLE EXTRACTION: `(SELECT json_group_array(json_object('COL1', col1, 'COL2', col2)) FROM raw_data WHERE raw_data.col1 IS NOT NULL) AS my_table_field`
        
        MANDATORY OUTPUT OBJECT WRAPPING (DAOM JSON SCHEMA):
        - ALL table `json_object` properties MUST WRAP THEIR DATAPOINTS into exactly this shape so the frontend can display them: `json_object('value', actual_data, 'confidence', confidence_score_0_to_1, 'validation_status', 'valid', 'original_value', actual_data)`
        - WRONG: `json_object('POL_CODE', POL_CODE)`
        - CORRECT: `json_object('POL_CODE', json_object('value', POL_CODE, 'confidence', 0.95, 'validation_status', 'valid', 'original_value', POL_CODE))`
        - Assign an appropriate `confidence_score` (0.0 to 1.0) directly in your SQL string based on how well the column maps to the requirement.
        - If the extracted data is NULL, return NULL for `value` and `original_value`.
        
        DUCKDB SPECIFIC RULES:
        1. `json_group_array` and `json_group_object` are MACRO functions. You CANNOT use "DISTINCT", "FILTER", or "ORDER BY" inside them. Use CTEs to order data first if needed.
        2. "regexp_match" DOES NOT EXIST. Use "regexp_matches" or "regexp_extract".
        3. SAFE TYPE CASTING: Use `TRY_CAST(value AS target_type)`.
        
        OUTPUT FORMAT (JSON Object):
        - "reasoning": A step-by-step brief explanation (in Korean) of how you analyzed the `raw_data` SAMPLE to find the real headers, how you mapped the columns, and your justification for the confidence scores.
        - "sql_query": The final executable DuckDB SQL string.
        - "field_confidence": A key-value dictionary mapping EACH requested field key (e.g., "remark", "shipping_rates_extracted") to a float (0.0 - 1.0) indicating your overall confidence in mapping this specific field.
        """
        
        client = get_openai_client()
        deployment = get_current_model()
        
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Return the JSON object with your 'reasoning' and 'sql_query'."}
        ]
        
        # Phase 2: Implement Auto-Healing retry loop
        max_retries = 2
        sql_query = ""
        result_df = None
        raw_extracted = {}
        
        for attempt in range(max_retries + 1):
            try:
                res = await client.chat.completions.create(
                    model=deployment,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0
                )
                
                content = res.choices[0].message.content
                response_json = json.loads(content)
                sql_query = response_json.get("sql_query", "").strip()
                reasoning = response_json.get("reasoning", "")
                field_confidence = response_json.get("field_confidence", {})
                logger.info(f"Generated SQL (Attempt {attempt+1}): {sql_query}")
                logger.debug(f"LLM Reasoning: {reasoning}")
                logger.debug(f"Field Confidence: {field_confidence}")
                
                # Pre-Execution Safety Net: Auto-Fix common LLM mistakes
                # Fix 1: Strip DISTINCT and ORDER BY from json_group_array/object (DuckDB limitation)
                macro_pattern = r"(?i)(json_group_array|json_group_object)\s*\(\s*(?:DISTINCT\s+)?(.*?)(?:\s+ORDER\s+BY.*?)?\s*\)"
                sql_query = re.sub(macro_pattern, r"\1(\2)", sql_query)
                
                # Fix 2: Auto-correct regexp_match to regexp_matches
                sql_query = re.sub(r"(?i)regexp_match\s*\(", "regexp_matches(", sql_query)
                
                # Fix 3: Auto-correct dangerous CASTs to TRY_CAST to prevent ConversionError
                # Only replace CAST that isn't already TRY_CAST
                sql_query = re.sub(r"(?i)(?<!TRY_)CAST\s*\(", "TRY_CAST(", sql_query)
                
                # 6. Safety Check on Generated SQL (Strict Regex)
                if not re.match(r"(?i)^\s*(SELECT|WITH)\s", sql_query):
                    raise ValueError(f"Unsafe or Invalid Query generated (Must start with SELECT or WITH): {sql_query}")
                    
                if re.search(r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b", sql_query):
                    raise ValueError(f"Unsafe Query generated (Contains forbidden DML/DDL): {sql_query}")
                
                # 7. Execute Query
                result_df = con.execute(sql_query).df()
                
                # STAGE 3: Strict Python Data Formatter
                # Guarantee the output perfectly matches the requested schema to prevent UI crashes
                if not result_df.empty:
                    # DuckDB returns single row for this type of query
                    row = result_df.iloc[0].to_dict()
                    
                    for f in model.fields:
                        key = f.key
                        field_type = f.type
                        
                        # Apply Data Profiler's dynamic confidence or fallback to 0.8
                        conf = field_confidence.get(key, 0.8)
                        
                        if key in row and pd.notna(row[key]):
                            raw_val = row[key]
                            
                            if field_type == "table":
                                # Safely parse JSON array
                                try:
                                    if isinstance(raw_val, str):
                                        parsed = json.loads(raw_val)
                                        raw_extracted[key] = parsed if isinstance(parsed, list) else []
                                    else:
                                        raw_extracted[key] = raw_val if isinstance(raw_val, list) else []
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse table JSON for {key}: {raw_val}")
                                    raw_extracted[key] = []
                            else:
                                # Standard scalar mapping
                                raw_extracted[key] = {
                                    "value": str(raw_val),
                                    "original_value": str(raw_val),
                                    "confidence": conf,
                                    "validation_status": "valid",
                                    "bbox": None,
                                    "page_number": 1
                                }
                        else:
                            # 🛡️ STRICT FALLBACK: Inject empty schema if LLM missed it
                            if field_type == "table":
                                raw_extracted[key] = []
                            else:
                                raw_extracted[key] = {
                                    "value": "",
                                    "original_value": "",
                                    "confidence": 0.0,
                                    "validation_status": "flagged",
                                    "bbox": None,
                                    "page_number": 1
                                }
                else:
                    # Entire query failed to return rows, build empty skeleton
                    logger.warning("DuckDB query returned empty Dataframe. Generating skeleton fallback.")
                    for f in model.fields:
                        if f.type == "table":
                            raw_extracted[f.key] = []
                        else:
                            raw_extracted[f.key] = {
                                "value": "",
                                "original_value": "",
                                "confidence": 0.0,
                                "validation_status": "flagged",
                                "bbox": None,
                                "page_number": 1
                            }

                break # Success! Break out of retry loop
                
            except (RuntimeError, duckdb.Error, Exception) as de:
                # Catching generic duckdb.Error ensures we catch ConversionException, CatalogException, BinderException, etc.
                logger.warning(f"DuckDB Error on Attempt {attempt+1}: {de}")
                if attempt < max_retries:
                    logger.info("Auto-healing: Passing error back to LLM for correction...")
                    error_guide = f"""
                    The query failed with DuckDB Error: {de}
                    
                    HOW TO FIX COMMON DUCKDB ERRORS:
                    - "Macro json_group_object() does not support...": You passed >2 arguments. Use json_object('k1',v1,'k2',v2) for single rows, or exactly json_group_object(key, val) to aggregate rows.
                    - "Table Function with name regexp_matches does not exist": You used regexp_matches in the FROM clause like a table. WRONG. Use SELECT regexp_extract(col, 'pattern') FROM raw_data.
                    - "Conversion Error": You tried to CAST an empty string. Change CAST(x AS INT) to TRY_CAST(x AS INT).
                    - "json_group_array/object ... ORDER BY": Remove the ORDER BY inside the macro. Use a CTE to order data first.
                    - Column not found: Double check the schema provided.
                    
                    Fix the SQL syntax and return the corrected SQL query in JSON format.
                    """
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": error_guide})
                else:
                    raise Exception(f"SQL Execution Failed after {max_retries} retries. DuckDB Error: {de}")
            except Exception as e:
                # If it's a security/regex error or something else, don't blindly retry
                raise e
        
        # Build Final Payload using the standard expected format
        if "reasoning" not in locals():
            reasoning = "DuckDB SQL Query executed successfully."
            
        final_payload = {
            "guide_extracted": raw_extracted,
            "_beta_metadata": {
                "parsed_content": f"DuckDB SQL Generation Mode.\n\n[LLM Reasoning]\n{reasoning}\n\n[SQL Executed]\n{sql_query}",
                "ref_map": {}
            }
        }
        
        return final_payload

    except duckdb.BinderException as be:
        logger.error(f"SQL Binder Error: {be}")
        # Phase 2: Implement Auto-Healing retry here
        raise Exception(f"SQL Execution Failed due to LLM generating invalid column names. This feature is in beta. Error: {be}")
    except Exception as e:
        logger.error(f"SQL Extraction Error: {e}")
        raise e
    finally:
        con.close()
