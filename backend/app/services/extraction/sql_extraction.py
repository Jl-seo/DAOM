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
                # Fix: Strip DISTINCT and ORDER BY from json_group_array/object (DuckDB limitation)
                macro_pattern = r"(?i)(json_group_array|json_group_object)\s*\(\s*(?:DISTINCT\s+)?(.*?)(?:\s+ORDER\s+BY.*?)?\s*\)"
                sql_query = re.sub(macro_pattern, r"\1(\2)", sql_query)
                
                # 6. Safety Check on Generated SQL (Strict Regex)
                if not re.match(r"(?i)^\s*SELECT\s", sql_query):
                    raise ValueError(f"Unsafe or Invalid Query generated (Must start with SELECT): {sql_query}")
                    
                if re.search(r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b", sql_query):
                    raise ValueError(f"Unsafe Query generated (Contains forbidden DML/DDL): {sql_query}")
                
                # 7. Execute Query
                result_df = con.execute(sql_query).df()
                break # Success! Break out of retry loop
                
            except (duckdb.BinderException, duckdb.InvalidInputException, duckdb.ParserException) as de:
                logger.warning(f"DuckDB Error on Attempt {attempt+1}: {de}")
                if attempt < max_retries:
                    logger.info("Auto-healing: Passing error back to LLM for correction...")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"The query failed with error: {de}\nFix the SQL syntax/macro usage and return the corrected SQL query in JSON format."})
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
        
        # Wrap the result imitating what DAOM expects
        # Multiple rows means multiple extractions or batch lines.
        # Since standard payload is single result per document, if multiple we return a list inside a list or wrap it.
        
        return {
            "guide_extracted": json_results,
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
