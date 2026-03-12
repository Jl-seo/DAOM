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
    def extract_markdown_tables(tagged_text: str) -> List[str]:
        """Finds all markdown tables in the tagged text."""
        lines = tagged_text.split('\n')
        tables = []
        current_table = []
        in_table = False
        
        for line in lines:
            if line.strip().startswith('|'):
                in_table = True
                current_table.append(line)
            else:
                if in_table:
                    tables.append("\n".join(current_table))
                    current_table = []
                    in_table = False
        if current_table:
            tables.append("\n".join(current_table))
            
        return tables

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
    async def deduce_table_relationships(work_order: dict, tagged_text: str, tables: List[str]) -> dict:
        """
        Document-Aware Designer Phase:
        Asks the LLM to deduce relationships between the physical markdown tables 
        and the expected schema.
        """
        if not tables:
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
        for i, table in enumerate(tables):
            headers, rows = DirectTableMapper.parse_markdown_table(table)
            sample_row = " | ".join([c.get("value", "") or "" for c in rows[0]]) if rows else "Empty or No Data"
            table_digest += f"Table {i}:\n- Headers: {' | '.join(headers)}\n- Row 1 Sample: {sample_row}\n- Total Rows: {len(rows)}\n\n"
            
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
    async def map_columns_to_schema(headers: List[str], schema_columns: dict) -> dict:
        """
        Engineer Phase: Maps the physical table headers (List[str]) to the schema keys.
        """
        client = get_openai_client()
        model_name = get_current_model()
        
        schema_summary = {}
        for k, v in schema_columns.items():
            schema_summary[k] = v.get("instruction", "")
            
        system_prompt = f"""You are a Table Column Mapper.
Your job is to map physical OCR table headers to the defined Schema Keys.

OCR Headers (by index):
"""
        for i, h in enumerate(headers):
            system_prompt += f"[{i}] {h}\n"
            
        system_prompt += f"""
TARGET SCHEMA KEYS:
{json.dumps(schema_summary, ensure_ascii=False, indent=2)}

OUTPUT JSON FORMAT:
Map the OCR Index (string) to the TARGET SCHEMA KEY (string).
If a schema key is completely missing in the OCR headers, do NOT map it.
{{
  "0": "target_schema_key",
  "1": "another_schema_key"
}}
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
            # Validate output is dict of str -> str
            mapping = json.loads(result_content)
            # Ensure keys are index strings that exist
            valid_mapping = {}
            for k, v in mapping.items():
                if k.isdigit() and int(k) < len(headers):
                    if v in schema_columns:
                        valid_mapping[int(k)] = v
            return valid_mapping
        except Exception as e:
            logger.warning(f"[DirectTableMapper] Failed to map columns: {e}")
            return {}

    @staticmethod
    async def extract_tables(work_order: dict, tagged_text: str) -> dict:
        """
        Main entry point for the direct table extraction.
        Returns a dict of extracted tables ready for merging with common_fields.
        """
        tables = DirectTableMapper.extract_markdown_tables(tagged_text)
        if not tables:
            return {}
            
        # 1. Deduce relationships
        strategy = await DirectTableMapper.deduce_table_relationships(work_order, tagged_text, tables)
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
                if table_idx >= len(tables):
                    continue
                md_table = tables[table_idx]
                headers, parsed_rows = DirectTableMapper.parse_markdown_table(md_table)
                
                if not headers or not parsed_rows:
                    continue
                    
                # Ask LLM to map columns for this specific table header set
                # (cached or fast because it's tiny)
                col_mapping = await DirectTableMapper.map_columns_to_schema(headers, schema_columns)
                
                # Deterministic assembly
                for row_cells in parsed_rows:
                    row_obj = {}
                    has_data = False
                    for col_idx, target_key in col_mapping.items():
                        if col_idx < len(row_cells):
                            cell_data = row_cells[col_idx]
                            row_obj[target_key] = cell_data # {"value": "...", "ref": "C1"}
                            if cell_data.get("value"):
                                has_data = True
                        else:
                            row_obj[target_key] = {"value": None, "ref": None}
                            
                    if has_data: # Skip completely empty rows
                        combined_rows.append(row_obj)
                        
            if combined_rows:
                final_results[schema_key] = combined_rows
                
        return final_results
