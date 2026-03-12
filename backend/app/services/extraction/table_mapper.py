import re
import json
import logging
from typing import List, Dict, Any, Tuple

from app.core.config import settings
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

class DirectTableMapper:
    """
    Handles robust extraction of table data directly from Markdown grids,
    bypassing the token-intensive LLM extraction for row-level iteration.
    """

    @staticmethod
    def extract_markdown_tables_with_context(tagged_text: str, preamble_lines_count: int = 50) -> List[Dict[str, str]]:
        """Finds all markdown tables in the tagged text and captures their preceding text as preamble context."""
        lines = tagged_text.split('\n')
        tables_with_context = []
        current_table = []
        in_table = False
        recent_text_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('|'):
                in_table = True
                current_table.append(line)
            else:
                if in_table:
                    # Table just finished processing
                    tables_with_context.append({
                        "md_table": "\n".join(current_table),
                        "preamble": "\n".join(recent_text_lines)
                    })
                    current_table = []
                    in_table = False
                    # Do not reset recent_text_lines immediately, in case multiple tables are glued together
                
                # Keep accumulating valid non-blank text lines for history
                if stripped:
                    # Avoid accumulating markdown table noise like empty row tags into the preamble context
                    clean_text = re.sub(r'\^C[0-9A-Fa-f]+', '', stripped).strip()
                    if clean_text:
                        recent_text_lines.append(stripped)
                        if len(recent_text_lines) > preamble_lines_count:
                            recent_text_lines.pop(0)

        if current_table:
            tables_with_context.append({
                "md_table": "\n".join(current_table),
                "preamble": "\n".join(recent_text_lines)
            })
            
        return tables_with_context

    @staticmethod
    def parse_markdown_table(md_table: str) -> Tuple[List[str], List[List[Dict[str, str]]]]:
        """Parses a markdown table into headers and rows of {text, ref}."""
        lines = md_table.strip().split('\n')
        if len(lines) < 3:
            return [], [] # Not a valid table with data
            
        header_line = lines[0]
        # lines[1] is the separator |---|---|
        data_lines = lines[2:]
        
        def parse_row(line):
            clean_line = line.strip()
            if clean_line.startswith('|'): clean_line = clean_line[1:]
            if clean_line.endswith('|'): clean_line = clean_line[:-1]
            return [c.strip() for c in clean_line.split('|')]
            
        headers = [re.sub(r'\^C[0-9A-Fa-f]+', '', h).strip() for h in parse_row(header_line)]
        
        parsed_rows = []
        for line in data_lines:
            cells = parse_row(line)
            parsed_cells = []
            for cell in cells:
                # Find tag e.g., ^C1 or ^C1A
                ref_match = re.search(r'\^(C[0-9A-Fa-f]+)', cell)
                ref = ref_match.group(1) if ref_match else None
                
                # Strip tag to get value
                text = re.sub(r'\^C[0-9A-Fa-f]+', '', cell).strip()
                text = text.replace('\\|', '|')
                
                parsed_cells.append({"value": text if text else None, "ref": ref})
            parsed_rows.append(parsed_cells)
            
        return headers, parsed_rows

    @staticmethod
    async def deduce_table_relationships(work_order: dict, tagged_text: str, tables_data: List[Dict[str, str]]) -> dict:
        """
        Document-Aware Designer Phase:
        Asks the LLM to deduce relationships between the physical markdown tables 
        and the expected schema.
        """
        if not tables_data:
            return {}
            
        client = get_openai_client()
        model_name = get_current_model()
        
        # We only need the table fields from the schema
        table_schema = work_order.get("table_fields", [])
        if not table_schema:
            return {}
            
        # Give a truncated view of the document to save tokens, just focusing on where tables are
        # Let's extract headers of all tables to give the LLM a structural digest
        table_digest = ""
        for i, t_data in enumerate(tables_data):
            headers, rows = DirectTableMapper.parse_markdown_table(t_data["md_table"])
            sample_row = " | ".join([c.get("value", "") or "" for c in rows[0]]) if rows else "Empty or No Data"
            # Give max 150 chars of context so prompt doesn't explode
            preamble_preview = t_data["preamble"][-150:].replace("\n", " ").strip() if t_data["preamble"] else "None"
            
            table_digest += f"Table {i}:\n- Preceding Context: {preamble_preview}\n- Headers: {' | '.join(headers)}\n- Row 1 Sample: {sample_row}\n- Total Rows: {len(rows)}\n\n"
            
        system_prompt = f"""You are a Table Relationship Architecture LLM.
You must analyze the structural digest of tables found in a document and the target schema.
Your goal is to categorize the physical tables (Table 0, Table 1, etc.) into the Target Schema.

TARGET SCHEMA (Table Fields):
{json.dumps(table_schema, ensure_ascii=False, indent=2)}

DETECTED TABLES IN DOCUMENT:
{table_digest}

RELATIONSHIP CATEGORIES:
1. `continuation`: Physical tables that are logically the exact same table split across pages. They share the same headers.
2. `independent`: Physical tables that belong to different schema fields.

OUTPUT JSON FORMAT:
{{
  "schema_field_key": {{
    "assigned_table_indices": [0, 1],
    "relationship_reason": "Table 0 and Table 1 share the exact same headers and are continuations."
  }}
}}
Return ONLY valid JSON.
"""
        try:
            temp = getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Analyze the tables and output the mapping strategy JSON."}
                ],
                response_format={"type": "json_object"},
                temperature=temp,
            )
            result_content = response.choices[0].message.content
            return json.loads(result_content)
        except Exception as e:
            logger.warning(f"[DirectTableMapper] Failed to deduce relationships: {e}")
            return {}

    @staticmethod
    async def map_columns_and_extract_constants(headers: List[str], schema_columns: dict, preamble: str) -> dict:
        """
        Engineer Phase: Maps physical headers to schema keys AND extracts missing context
        as table-level constants (e.g., Validity Date stated above the grid).
        """
        client = get_openai_client()
        model_name = get_current_model()
        
        schema_summary = {}
        for k, v in schema_columns.items():
            schema_summary[k] = v.get("instruction", "")
            
        system_prompt = f"""You are an Expert Table Extractor and Column Mapper.
Your job is twofold:
1. Map physical OCR table headers to the defined Schema Keys.
2. If a required Schema Key is obviously not a column header but IS present in the PRECEDING TEXT, extract its value as a constant.

PRECEDING TEXT (Preamble):
{preamble[-600:] if preamble else "No preceding text."}

OCR Headers (by index):
"""
        for i, h in enumerate(headers):
            system_prompt += f"[{i}] {h}\n"
            
        system_prompt += f"""
TARGET SCHEMA KEYS AND INSTRUCTIONS:
{json.dumps(schema_summary, ensure_ascii=False, indent=2)}

OUTPUT JSON FORMAT:
{{
  "column_mapping": {{
    "0": "target_schema_key_1",
    "1": "another_schema_key_2"
  }},
  "constants": {{
    "missing_schema_key_3": "extracted value from preceding text (e.g. 12/1 ~ 12/7)"
  }}
}}
Rules:
- In "column_mapping", the key must be the exact string index (e.g. "0").
- If a schema key maps to an OCR header, put it in "column_mapping".
- If a schema key has no corresponding OCR header BUT the information is clearly found in the PRECEDING TEXT, put it in "constants".
- Do NOT map columns to completely unrelated keys.
Return ONLY valid JSON.
"""
        try:
            temp = getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Map the columns."}
                ],
                response_format={"type": "json_object"},
                temperature=temp,
            )
            result_content = response.choices[0].message.content
            # Validate output structure
            response_json = json.loads(result_content)
            mapping = response_json.get("column_mapping", {})
            constants = response_json.get("constants", {})
            
            # Ensure mapping keys are index strings that exist
            valid_mapping = {}
            for k, v in mapping.items():
                if k.isdigit() and int(k) < len(headers):
                    if v in schema_columns:
                        valid_mapping[int(k)] = v
            
            # Ensure constants belong to the schema
            valid_constants = {}
            for k, v in constants.items():
                if k in schema_columns and v:
                    valid_constants[k] = v
                    
            return {
                "column_mapping": valid_mapping,
                "constants": valid_constants
            }
        except Exception as e:
            logger.warning(f"[DirectTableMapper] Failed to map columns: {e}")
            return {}

    @staticmethod
    async def extract_tables(work_order: dict, tagged_text: str) -> dict:
        """
        Main entry point for the direct table extraction.
        Returns a dict of extracted tables ready for merging with common_fields.
        """
        tables_data = DirectTableMapper.extract_markdown_tables_with_context(tagged_text)
        if not tables_data:
            return {}
            
        # 1. Deduce relationships
        strategy = await DirectTableMapper.deduce_table_relationships(work_order, tagged_text, tables_data)
        if not strategy:
            return {}
            
        final_results = {}
        schema_table_fields = {f["key"]: f for f in work_order.get("table_fields", [])}
        
        # 2. Extract mapped tables
        for schema_key, mapping_info in strategy.items():
            if schema_key not in schema_table_fields:
                continue
                
            assigned_indices = mapping_info.get("assigned_table_indices", [])
            schema_columns = schema_table_fields[schema_key].get("columns", {})
            
            combined_rows = []
            
            for table_idx in assigned_indices:
                if table_idx >= len(tables_data):
                    continue
                t_data = tables_data[table_idx]
                md_table = t_data["md_table"]
                preamble = t_data["preamble"]
                
                headers, parsed_rows = DirectTableMapper.parse_markdown_table(md_table)
                
                if not headers or not parsed_rows:
                    continue
                    
                # Ask LLM to map columns AND extract constants for this specific table block
                mapping_res = await DirectTableMapper.map_columns_and_extract_constants(headers, schema_columns, preamble)
                col_mapping = mapping_res.get("column_mapping", {})
                constants = mapping_res.get("constants", {})
                
                # Deterministic assembly
                for row_cells in parsed_rows:
                    row_obj = {}
                    has_data = False
                    # First inject constants (text extracted from preamble context)
                    for target_key, constant_val in constants.items():
                        row_obj[target_key] = {"value": str(constant_val), "ref": None}
                        has_data = True # Constants count as data presence
                        
                    # Then loop over mapped physical columns
                    for col_idx, target_key in col_mapping.items():
                        if col_idx < len(row_cells):
                            cell_data = row_cells[col_idx]
                            row_obj[target_key] = cell_data # {"value": "...", "ref": "C1"}
                            if cell_data.get("value"):
                                has_data = True
                        else:
                            # Only set to None if it wasn't already filled by a constant
                            if target_key not in row_obj:
                                row_obj[target_key] = {"value": None, "ref": None}
                            
                    # Ensure schema completeness (null-fill completely missing keys)
                    for schema_col_key in schema_columns.keys():
                        if schema_col_key not in row_obj:
                            row_obj[schema_col_key] = {"value": None, "ref": None}
                            
                    if has_data: # Skip completely empty rows
                        combined_rows.append(row_obj)
                        
            if combined_rows:
                final_results[schema_key] = combined_rows
                
        return final_results
