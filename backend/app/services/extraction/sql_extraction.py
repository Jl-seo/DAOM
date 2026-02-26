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

async def run_sql_extraction(file: UploadFile, model: ExtractionModel) -> Dict[str, Any]:
    """
    Beta Feature: Excel Text-to-SQL Extraction via DuckDB.
    Instead of passing data to LLM, loads Excel to InMemory DB and generates SQL.
    """
    logger.info(f"Starting SQL Extraction (DuckDB) for {file.filename}")
    
    file_content = await file.read()
    await file.seek(0)
    
    # 1. Load Excel into Pandas (Handle basic empty rows to find header)
    try:
        df = pd.read_excel(io.BytesIO(file_content))
        df = df.dropna(how='all') # Remove entirely empty rows
        
        # Clean column names aggressively to prevent ANY SQL Binder errors
        # Convert spaces, special chars, brackets to underscores. Keep Korean, English, Numbers.
        clean_cols = []
        for col in df.columns:
            if pd.isna(col) or 'Unnamed' in str(col):
                clean_cols.append(str(col))
                continue
            
            c = str(col).strip()
            # Replace all non-alphanumeric/Korean characters with underscores
            c = re.sub(r'[^a-zA-Z0-9가-힣_]', '_', c)
            # Remove multiple consecutive underscores
            c = re.sub(r'_+', '_', c)
            c = c.strip('_')
            
            # If the column name becomes completely empty after stripping, give it a generic name
            if not c:
                c = f"col_{len(clean_cols)}"
                
            clean_cols.append(c)
            
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
        
        # ROOT CAUSE FIX: Provide actual data sample because Excel headers might be A, B, C
        data_sample_df = df.head(15)
        # Convert all columns to string and truncate to prevent token bloat
        data_sample_df = data_sample_df.fillna("").astype(str).map(lambda x: x[:100] + "..." if len(x) > 100 else x)
        data_sample_csv = data_sample_df.to_csv(index=False)
        
        logger.info(f"Loaded Schema: {schema_info}")
        logger.debug(f"Data Sample:\n{data_sample_csv}")
        
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

        # 5. Prompt LLM for SQL Query
        system_prompt = f"""
        You are an expert Data Engineer writing standard SQL queries (DuckDB compatible) to extract structured data from an Excel file.
        
        We have loaded the Excel file into a virtual DuckDB table named `raw_data`. 
        Here is the Database Schema:
        {schema_info}
        
        Here is a SAMPLE of the actual data inside `raw_data` (Look at this to find where headers actually are!):
        {data_sample_csv}
        
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
        
        # OOM Defense removed: The frontend virtualization handles 10K+ rows efficiently now.
            
        json_results = result_df.to_dict(orient="records")
        print("RAW JSON RESULTS FROM DUCKDB:")
        print(json_results)
        
        # Post-Processing: Collapse rows into a single hierarchical document mapping the model schema
        table_keys = {f.key for f in model.fields if f.type == 'table'}
        
        # Determine fallback parsing confidence
        if "field_confidence" not in locals():
            field_confidence = {}
            
        collapsed_result = {}
        for row in json_results:
            for k, v in row.items():
                if pd.isna(v) or v is None:
                    continue
                    
                # Handle Table Fields (Aggregate arrays across rows)
                if k in table_keys:
                    if k not in collapsed_result:
                        collapsed_result[k] = []
                    
                    if isinstance(v, str):
                        try:
                            parsed_v = json.loads(v)
                            if isinstance(parsed_v, list):
                                collapsed_result[k].extend(parsed_v)
                            else:
                                collapsed_result[k].append(parsed_v)
                        except json.JSONDecodeError:
                            collapsed_result[k].append({"value": v, "confidence": field_confidence.get(k, 1.0), "validation_status": "valid"})
                    elif isinstance(v, list):
                        collapsed_result[k].extend(v)
                    else:
                        collapsed_result[k].append(v)
                
                # Handle Text/Scalar Fields (Take first valid value)
                else:
                    if k not in collapsed_result or collapsed_result[k] == "" or collapsed_result[k] is None:
                        if v:
                            # Automatically wrap scalar string outputs into DAOM field dictionary
                            collapsed_result[k] = {
                                "value": v,
                                "original_value": v,
                                "confidence": field_confidence.get(k, 1.0),
                                "validation_status": "valid",
                                "bbox": None,
                                "page_number": 1
                            }
                            
        # Ensure all model fields are present in the final payload
        for f in model.fields:
            if f.key not in collapsed_result:
                if f.type == 'table':
                    collapsed_result[f.key] = [] 
                else:
                    collapsed_result[f.key] = {
                        "value": "",
                        "original_value": "",
                        "confidence": 0.0,
                        "validation_status": "valid"
                    }
        
        # Build Final Payload using the standard expected format
        if "reasoning" not in locals():
            reasoning = "DuckDB SQL Query executed successfully."
            
        final_payload = {
            "guide_extracted": collapsed_result,
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
