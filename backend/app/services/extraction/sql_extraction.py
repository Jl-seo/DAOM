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
        
        # 3. Extract Schema Info
        schema_df = con.execute("DESCRIBE raw_data").df()
        columns = schema_df['column_name'].tolist()
        types = schema_df['column_type'].tolist()
        schema_info = ", ".join([f"{c} ({t})" for c, t in zip(columns, types)])
        
        logger.info(f"Loaded Schema: {schema_info}")
        
        # 4. Target Fields Info
        target_fields = []
        for field in model.fields:
            desc = field.description or ""
            target_fields.append(f"- {field.key} (label expected: {field.label}, type: {field.type}): {desc}")
        target_fields_str = "\n".join(target_fields)

        # 5. Prompt LLM for SQL Query
        system_prompt = f"""
        You are an expert Data Engineer writing standard SQL queries (DuckDB compatible).
        We have a table `raw_data` with the following columns:
        {schema_info}
        
        Your task is to write a single SELECT query that extracts data mapping to these specific fields:
        {target_fields_str}
        
        CRITICAL RULES:
        1. Write ONLY a SELECT query targeting the `raw_data` table.
        2. DO NOT write DROP, DELETE, INSERT, or UPDATE.
        3. Aliases in your SELECT clause MUST exactly match the requested target field names.
        4. If a field asks for derived data, use SQL functions (e.g. string concatenation, logic) to fulfill it.
        5. Return ONLY a JSON object containing a `sql_query` string key. Do not explain.
        6. DUCKDB SPECIFIC RULE: "json_group_array" and "json_group_object" are MACRO functions. You CANNOT use "DISTINCT", "FILTER", or "ORDER BY" inside them. 
           - WRONG: json_group_array(value ORDER BY value)
           - CORRECT: WITH ordered AS (SELECT * FROM raw_data ORDER BY value) SELECT json_group_array(value) FROM ordered
           
        7. DUCKDB SPECIFIC RULE FOR JSON OBJECTS:
           - To create a JSON object for a SINGLE ROW, use "json_object('key1', val1, 'key2', val2)".
           - To Aggregate MULTIPLE ROWS into a single JSON object, use "json_group_object(key_col, value_col)". It MUST take EXACTLY TWO arguments.
           - WRONG: json_group_object('k1', v1, 'k2', v2)
           - CORRECT: json_object('k1', v1, 'k2', v2)
           
        8. DUCKDB SPECIFIC RULE: "regexp_match" DOES NOT EXIST. You MUST use "regexp_matches(string, pattern)" for regex matching.
           - WRONG: CASE WHEN regexp_match(col, 'pattern') THEN ...
           - CORRECT: CASE WHEN regexp_matches(col, 'pattern') THEN ...
           
        MULTI-TABLE CORRELATION STRATEGY (CRITICAL FOR COMPLEX DOCUMENTS):
        - Raw Excel data often contains fragmented tables, stacked vertically, or split with repeating headers.
        - You MUST actively CROSS-REFERENCE and MERGE information from disconnected or fragmented sections if they map to the same target schema list.
        - Use advanced SQL (e.g., CTEs, UNION ALL, Window Functions, or JOINs) to stitch related tables back together.
        - DO NOT extract only the first visible table section if the document implies more data exists further down the raw dataset.
        """
        
        client = get_openai_client()
        deployment = get_current_model()
        
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Return the SQL query in JSON format."}
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
                logger.info(f"Generated SQL (Attempt {attempt+1}): {sql_query}")
                
                # Pre-Execution Safety Net: Auto-Fix common LLM mistakes
                # Fix 1: Strip DISTINCT and ORDER BY from json_group_array/object (DuckDB limitation)
                macro_pattern = r"(?i)(json_group_array|json_group_object)\s*\(\s*(?:DISTINCT\s+)?(.*?)(?:\s+ORDER\s+BY.*?)?\s*\)"
                sql_query = re.sub(macro_pattern, r"\1(\2)", sql_query)
                
                # Fix 2: Auto-correct regexp_match to regexp_matches
                sql_query = re.sub(r"(?i)regexp_match\s*\(", "regexp_matches(", sql_query)
                
                # 6. Safety Check on Generated SQL (Strict Regex)
                if not re.match(r"(?i)^\s*(SELECT|WITH)\s", sql_query):
                    raise ValueError(f"Unsafe or Invalid Query generated (Must start with SELECT or WITH): {sql_query}")
                    
                if re.search(r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b", sql_query):
                    raise ValueError(f"Unsafe Query generated (Contains forbidden DML/DDL): {sql_query}")
                
                # 7. Execute Query
                result_df = con.execute(sql_query).df()
                break # Success! Break out of retry loop
                
            except (duckdb.BinderException, duckdb.InvalidInputException, duckdb.ParserException) as de:
                logger.warning(f"DuckDB Error on Attempt {attempt+1}: {de}")
                if attempt < max_retries:
                    logger.info("Auto-healing: Passing error back to LLM for correction...")
                    error_guide = f"""
                    The query failed with DuckDB Error: {de}
                    
                    HOW TO FIX COMMON DUCKDB ERRORS:
                    - If "Macro json_group_object() does not support the supplied arguments": You probably passed more than 2 arguments. Use json_object('k1',v1,'k2',v2) for single rows, or exactly json_group_object(key_col, value_col) to aggregate rows.
                    - If "Scalar Function with name regexp_match does not exist": Change it to regexp_matches(string, pattern).
                    - If "json_group_array/object ... ORDER BY": Remove the ORDER BY inside the macro. Use a CTE to order data first, then select json_group_array(col) from the CTE.
                    - If column not found: Double check the schema provided. Aliases mapping to target fields must be exact.
                    
                    Fix the SQL syntax and return the corrected SQL query in JSON format.
                    """
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": error_guide})
                else:
                    raise Exception(f"SQL Execution Failed after {max_retries} retries. DuckDB Error: {de}")
            except Exception as e:
                # If it's a security/regex error or something else, don't blindly retry
                raise e
        
        # OOM Defense
        if len(result_df) > 5000:
            logger.warning("Result too large, limiting to 5000 rows.")
            result_df = result_df.head(5000)
            
        json_results = result_df.to_dict(orient="records")
        
        # Post-Processing: Collapse rows into a single hierarchical document mapping the model schema
        table_keys = {f.key for f in model.fields if f.type == 'table'}
        
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
                            collapsed_result[k].append({"value": v})
                    elif isinstance(v, list):
                        collapsed_result[k].extend(v)
                    else:
                        collapsed_result[k].append(v)
                
                # Handle Text/Scalar Fields (Take first valid value)
                else:
                    if k not in collapsed_result or collapsed_result[k] == "" or collapsed_result[k] is None:
                        if v:
                            collapsed_result[k] = v
                            
        # Ensure all model fields are present in the final payload
        for f in model.fields:
            if f.key not in collapsed_result:
                collapsed_result[f.key] = [] if f.type == 'table' else ""
        
        # Wrap the single collapsed dictionary in a list as the DAOM standard pipeline expects 
        # `guide_extracted` to be a list of results (even if it's length 1 for a single document)
        final_payload = [collapsed_result]
        
        return {
            "guide_extracted": final_payload,
            "logs": [],
            "error": None
        }

    except duckdb.BinderException as be:
        logger.error(f"SQL Binder Error: {be}")
        # Phase 2: Implement Auto-Healing retry here
        raise Exception(f"SQL Execution Failed due to LLM generating invalid column names. This feature is in beta. Error: {be}")
    except Exception as e:
        logger.error(f"SQL Extraction Error: {e}")
        raise e
    finally:
        con.close()
