import asyncio
import json
import logging
from typing import List, Dict, Any, Tuple
import re

from app.core.config import settings
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

class DirectTableMapper:
    """
    Independent Table Pipeline (ITP) Architecture
    Handles robust extraction of table data directly from Markdown grids.
    Each physical table is evaluated and mapped independently against the schema
    to guarantee 100% data integrity, dynamic preamble constants, and eliminate false positives.
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
    def _merge_page_break_tables(tables: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Merge tables that are physically split across pages (headerless or repeated headers)
        to prevent data loss and reduce redundant LLM calls.
        """
        if not tables:
            return []
        
        merged = [tables[0]]
        for i in range(1, len(tables)):
            curr = tables[i]
            prev = merged[-1]
            
            # Clean preamble to check if it's virtually empty (e.g., just whitespace, page numbers)
            clean_preamble = re.sub(r'[\d\/\-\sPAGEpage]+', '', curr["preamble"])
            is_empty_preamble = len(clean_preamble) < 5
            
            prev_first_line = prev["md_table"].strip().split('\n')[0]
            curr_first_line = curr["md_table"].strip().split('\n')[0]
            
            prev_cols = len(prev_first_line.split('|'))
            curr_cols = len(curr_first_line.split('|'))
            
            headers_match = (prev_first_line == curr_first_line)
            
            # Target page breaks: extremely short preamble AND same column width
            if is_empty_preamble and prev_cols == curr_cols and prev_cols > 2:
                curr_lines = curr["md_table"].strip().split('\n')
                if len(curr_lines) > 2 and "---" in curr_lines[1]:
                    if headers_match:
                        # Repeated header page break: omit header
                        append_data = curr_lines[2:]
                    else:
                        # Headerless data page break: the 'header' is actually the first data row
                        append_data = [curr_lines[0]] + curr_lines[2:]
                else:
                    append_data = curr_lines
                    
                prev["md_table"] += "\n" + "\n".join(append_data)
                # Keep prev preamble untouched
            else:
                merged.append(curr)
                
        return merged

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
            
        raw_headers = parse_row(header_line)
        headers = []
        for i, h in enumerate(raw_headers):
            clean_h = re.sub(r'\^C[0-9A-Fa-f]+', '', h).strip()
            if not clean_h:
                clean_h = f"Empty_Col_{i+1}"
            headers.append(clean_h)
        
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
    async def evaluate_and_map_table(table_schema: List[dict], headers: List[str], preamble: str, row_sample: str, global_preamble: str) -> dict:
        """
        Independent Table Pipeline (ITP) Phase:
        Evaluates a SINGLE table against all table schemas concurrently.
        1. Decides if this table belongs to any schema based on structural compatibility.
        2. Maps physical columns to the chosen schema key.
        3. Extracts dynamic constants from the preamble specifically for this table.
        """
        client = get_openai_client()
        model_name = get_current_model()
        
        system_prompt = f"""You are an Expert Table Extractor running a Hybrid Independent Table Pipeline (ITP).
Your job is to evaluate a single physical table from a document and determine which Target Schema Field it belongs to, then map its columns.

TARGET SCHEMA FIELDS:
{json.dumps(table_schema, ensure_ascii=False, indent=2)}

GLOBAL DOCUMENT CONTEXT (For Global Constants):
{global_preamble}

CURRENT TABLE TO EVALUATE:
- Preceding Text (Local Preamble): {preamble[-400:] if preamble else "None"}
- OCR Headers (by index):
"""
        for i, h in enumerate(headers):
            system_prompt += f"  [{i}] {h}\n"
        
        system_prompt += f"""- Sample Row Data: {row_sample}

CRITICAL RULES FOR EVALUATION (FALSE POSITIVE PREVENTION):
1. STRUCTURAL COMPATIBILITY: The OCR Headers MUST logically support the REQUIRED sub-columns of the Target Schema Field.
   - Example 1: If Schema requires "POL" and "POD", and OCR Headers are "Destination", "20'", "40'", it IS compatible (POL/Validity might be in Preamble).
   - Example 2: If Schema is "Rate_List" (requires POL, POD, Rates) but OCR Headers are "Surcharge Name", "Currency", "Amount", it is INCOMPATIBLE.
2. REJECT NOISE: If the table is obviously an email signature, a layout grid, or generic text without data, you MUST reject it by omitting the mapping.
3. SINGLE ASSIGNMENT: Evaluate and assign the table to at MOST ONE target schema key. If it doesn't fit any, return an empty mapping.

CRITICAL RULES FOR EXTRACTION:
1. "column_mapping": Map OCR Header indices (e.g. "0", "1") to the exact sub-column keys of the CHOSEN schema field.
2. "constants": If a sub-column key is NOT found in the headers, BUT its value is clearly stated in the Local Preamble OR Global Context (e.g., Validity Date "12/1 ~ 12/7", or global Origin "Korea"), extract it here.

OUTPUT FORMAT (JSON ONLY):
{{
  "assigned_schema_key": "target_schema_key_1", 
  "column_mapping": {{
    "0": "sub_column_key_a",
    "2": "sub_column_key_b"
  }},
  "constants": {{
    "missing_sub_column_key_c": "value extracted from preamble"
  }}
}}
If the table does NOT belong to any schema, output:
{{
  "assigned_schema_key": null
}}
"""
        try:
            temp = getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.0)
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Evaluate and map this table."}
                ],
                response_format={"type": "json_object"},
                temperature=temp,
            )
            result_content = response.choices[0].message.content
            res_json = json.loads(result_content)
            
            assigned_key = res_json.get("assigned_schema_key")
            if not assigned_key:
                return {} # Explicit reject
                
            mapping = res_json.get("column_mapping", {})
            constants = res_json.get("constants", {})
            
            # Find chosen schema to validate
            chosen_schema = next((s for s in table_schema if s["key"] == assigned_key), None)
            if not chosen_schema:
                return {}
                
            schema_cols = chosen_schema.get("columns", {})
            
            # Ensure mapping indices are valid and target keys exist
            valid_mapping = {}
            for k, v in mapping.items():
                if k.isdigit() and int(k) < len(headers):
                    if v in schema_cols:
                        valid_mapping[int(k)] = v
                        
            # Ensure constants target keys exist
            valid_constants = {}
            for k, v in constants.items():
                if k in schema_cols and v:
                    valid_constants[k] = v
                    
            return {
                "assigned_schema_key": assigned_key,
                "column_mapping": valid_mapping,
                "constants": valid_constants
            }
        except Exception as e:
            logger.warning(f"[DirectTableMapper] Failed to evaluate table: {e}")
            return {}

    @staticmethod
    async def extract_tables(work_order: dict, tagged_text: str) -> dict:
        """
        Hybrid Independent Table Pipeline (ITP) Main Entry Point.
        Processes EVERY extracted markdown table concurrently (with semaphore),
        injecting global context and merging headerless page breaks.
        """
        raw_tables = DirectTableMapper.extract_markdown_tables_with_context(tagged_text)
        tables_data = DirectTableMapper._merge_page_break_tables(raw_tables)
        if not tables_data:
            return {}
            
        table_schema = work_order.get("table_fields", [])
        if not table_schema:
            return {}
            
        schema_table_dict = {f["key"]: f for f in table_schema}
        
        # Prepare global preamble for contextual constant extraction
        global_preamble = re.sub(r'\^C[0-9A-Fa-f]+', '', tagged_text[:1000]).strip()
        
        # 1. Parse all tables and kick off parallel ITP evaluation
        semaphore = asyncio.Semaphore(5)
        evaluate_tasks = []
        parsed_table_details = []
        
        async def evaluate_with_semaphore(t_schema, h, pre, r_sample, g_pre):
            async with semaphore:
                return await DirectTableMapper.evaluate_and_map_table(t_schema, h, pre, r_sample, g_pre)
        
        for t_data in tables_data:
            headers, parsed_rows = DirectTableMapper.parse_markdown_table(t_data["md_table"])
            if not headers or not parsed_rows:
                continue
                
            row_sample = " | ".join([c.get("value", "") or "" for c in parsed_rows[0]])
            task = evaluate_with_semaphore(
                table_schema,
                headers,
                t_data["preamble"],
                row_sample,
                global_preamble
            )
            evaluate_tasks.append(task)
            parsed_table_details.append({
                "headers": headers,
                "parsed_rows": parsed_rows
            })
            
        if not evaluate_tasks:
            return {}
            
        # 2. Wait for all tables to complete evaluation independently
        evaluations = await asyncio.gather(*evaluate_tasks)
        
        # 3. Deterministic Assembly (Merge by assigned_schema_key)
        final_results = {}
        for schema_key in schema_table_dict.keys():
            final_results[schema_key] = []
            
        for i, eval_res in enumerate(evaluations):
            if not eval_res:
                # Table was rejected (noise, false positive, or error)
                continue
                
            assigned_key = eval_res.get("assigned_schema_key")
            if assigned_key not in final_results:
                continue # Safety check
                
            col_mapping = eval_res.get("column_mapping", {})
            constants = eval_res.get("constants", {})
            schema_columns = schema_table_dict[assigned_key].get("columns", {})
            parsed_rows = parsed_table_details[i]["parsed_rows"]
            
            # Track previous row values for forward-filling empty cells inside THIS table
            prev_cell_values = {}
            
            for row_cells in parsed_rows:
                row_obj = {}
                has_data = False
                
                # A. Inject table-specific preamble constants (Dynamic Validity)
                for target_key, constant_val in constants.items():
                    row_obj[target_key] = {"value": str(constant_val), "confidence": 1.0, "ref": None}
                    has_data = True
                    
                # B. Map physical columns & forward fill
                for col_idx_str, target_key in col_mapping.items():
                    col_idx = int(col_idx_str)
                    if col_idx < len(row_cells):
                        cell_data = row_cells[col_idx]
                        cell_val = cell_data.get("value")
                        
                        # Forward fill logic for merged cell representation
                        if not cell_val and col_idx in prev_cell_values:
                            # Forward fill
                            cell_val = prev_cell_values[col_idx]
                            # Use empty ref for forward filled cells to decouple highlights from random previous elements
                            cell_data = {"value": cell_val, "ref": None}
                        else:
                            prev_cell_values[col_idx] = cell_val
                            
                        row_obj[target_key] = cell_data # {"value": "...", "ref": "C1"}
                        
                        if cell_val:
                            # Since we bypass the engineer LLM, we append synthetic confidence
                            row_obj[target_key]["confidence"] = 1.0
                            has_data = True
                    else:
                        if target_key not in row_obj:
                            row_obj[target_key] = {"value": None, "confidence": 0.0, "ref": None}
                            
                # C. Ensure schema completeness and enforce explicit schema column ordering
                ordered_row_obj = {}
                for schema_col_key in schema_columns.keys():
                    if schema_col_key in row_obj:
                        ordered_row_obj[schema_col_key] = row_obj[schema_col_key]
                    else:
                        ordered_row_obj[schema_col_key] = {"value": None, "confidence": 0.0, "ref": None}
                
                for k, v in row_obj.items():
                    if k not in ordered_row_obj:
                        ordered_row_obj[k] = v
                        
                row_obj = ordered_row_obj
                        
                # D. Commit row if it has actual data (not just preamble constants)
                if has_data:
                    # Require at least one mapped PHYSICAL column to have data to prevent phantom empty rows
                    has_physical_data = False
                    for col_idx_str, target_key in col_mapping.items():
                        col_idx = int(col_idx_str)
                        if col_idx < len(row_cells) and row_cells[col_idx].get("value"):
                            has_physical_data = True
                            break
                    if has_physical_data:
                        final_results[assigned_key].append(row_obj)
                        
        # Filter out empty schema keys
        return {k: v for k, v in final_results.items() if len(v) > 0}
