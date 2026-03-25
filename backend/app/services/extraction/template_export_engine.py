import os
import io
import openpyxl
from openpyxl.utils import column_index_from_string
from typing import Dict, Any, List
from app.schemas.model import CustomExportTemplateDef

def generate_custom_excel(template_def: CustomExportTemplateDef, flat_data: List[Dict[str, Any]]) -> bytes:
    """
    Injects flat_data into the custom Excel template based on mappings.
    Returns the generated Excel file as a byte stream.
    """
    if not template_def.template_file_path or not os.path.exists(template_def.template_file_path):
        raise FileNotFoundError(f"Template file not found at {template_def.template_file_path}")

    # Load workbook preserving all non-data elements (styles, formats, multiple headers)
    wb = openpyxl.load_workbook(template_def.template_file_path)
    sheet = wb.active

    start_row = template_def.data_start_row

    for row_idx, row_data in enumerate(flat_data):
        current_row = start_row + row_idx
        
        for mapping in template_def.mappings:
            if mapping.type == "column":
                if mapping.field_key and mapping.field_key in row_data:
                    col_letter = mapping.target
                    val = row_data[mapping.field_key]
                    if val is not None:
                         sheet[f"{col_letter}{current_row}"] = val
                         
            elif mapping.type == "repeat_block":
                # Find dynamic blocks based on pivoted fields like {ChargeType}_20DC
                charge_types = set()
                for key, val in row_data.items():
                    if val is not None and "_" in key:
                        prefix = key.split("_")[0]
                        # Super simple heuristic: if it has an underscore, assume prefix is a Charge Type
                        # In production this could use mapping.list_field_key (e.g., Surcharges_Rate_List)
                        charge_types.add(prefix)
                
                sorted_charges = sorted(list(charge_types))
                
                block_width = mapping.block_width or 6
                max_blocks = mapping.max_blocks or 10
                start_col_letter = mapping.target
                start_col_idx = column_index_from_string(start_col_letter)
                
                for i, charge_key in enumerate(sorted_charges[:max_blocks]):
                    base_col_idx = start_col_idx + (i * block_width)
                    
                    for block_map in (mapping.block_mappings or []):
                        offset = block_map.get("offset", 0)
                        target_col_idx = base_col_idx + offset
                        field_template = block_map.get("field_key", "")
                        
                        val = None
                        if field_template == "Charge_Type":
                            val = charge_key
                        elif "{category_name}" in field_template:
                            actual_key = field_template.replace("{category_name}", charge_key)
                            val = row_data.get(actual_key)
                        else:
                            val = field_template
                            
                        if val is not None:
                            try:
                                cell = sheet.cell(row=current_row, column=target_col_idx)
                                cell.value = val
                            except Exception:
                                pass

    output_stream = io.BytesIO()
    wb.save(output_stream)
    output_stream.seek(0)
    return output_stream.read()
