import io
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)

class ExcelParser:
    """
    Direct Excel/CSV to Markdown Parser.
    Bypasses Azure Document Intelligence and generates clean Markdown tables
    directly from Excel bytes. This output is ready for the BetaPipeline LLM.
    """
    
    @classmethod
    def from_bytes(cls, file_bytes: bytes, file_ext: str) -> List[Dict[str, str]]:
        """
        Parse Excel/CSV file bytes directly into a list of Markdown sections (one per sheet).
        Returns: [{"sheet_name": "Data", "content": "...markdown..."}, ...]
        """
        ext = file_ext.lower().replace(".", "")
        if ext == "csv":
            return cls._parse_csv(file_bytes)
        elif ext in ("xlsx", "xls"):
            return cls._parse_excel(file_bytes)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
            
    @classmethod
    def _parse_csv(cls, file_bytes: bytes) -> List[Dict[str, str]]:
        # Try to decode with different encodings
        content_str = None
        for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]:
            try:
                content_str = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if content_str is None:
            raise ValueError("Failed to decode CSV file with supported encodings")

        import csv
        reader = csv.reader(io.StringIO(content_str))
        rows = list(reader)
        
        # Limit to 1500 rows to protect LLM context windows and UI rendering
        if len(rows) > 1500:
            logger.warning(f"CSV has {len(rows)} rows. Truncating Markdown representation to 1500 rows.")
            rows = rows[:1500]
            
        md_content = cls._rows_to_markdown(rows, sheet_name="Data")
        return [{"sheet_name": "Data", "content": md_content}] if md_content else []

    @classmethod
    def _parse_excel(cls, file_bytes: bytes) -> List[Dict[str, str]]:
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="calamine")
        except ImportError:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
        except Exception as e:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
            
        markdown_sections = []
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            
            # Limit to 1500 rows per sheet to protect LLM context windows and UI rendering
            if len(df) > 1500:
                logger.warning(f"Sheet {sheet_name} has {len(df)} rows. Truncating Markdown representation to 1500 rows.")
                df = df.head(1500)
                
            rows = df.fillna("").astype(str).values.tolist()
            if not rows:
                continue
                
            md_table = cls._rows_to_markdown(rows, sheet_name)
            if md_table:
                markdown_sections.append({"sheet_name": sheet_name, "content": md_table})
                
        return markdown_sections

    @classmethod
    def _rows_to_markdown(cls, rows: List[List[str]], sheet_name: str) -> str:
        """
        Convert a 2D array of rows to a valid Markdown table string.
        Handles dynamic Excel structures (sparse rows, varying lengths).
        """
        if not rows:
            return ""
            
        # 1. Clean data: strip whitespace and resolve newlines
        cleaned_rows = []
        for row in rows:
             new_row = [cell.strip().replace("\n", " ") for cell in row]
             
             # Remove trailing empty cells from row (compacting)
             while new_row and not new_row[-1]:
                 new_row.pop()
                 
             if new_row:
                 cleaned_rows.append(new_row)

        if not cleaned_rows:
            return ""

        # 2. Determine MAXIMUM column width across ALL non-empty rows
        max_cols = max(len(row) for row in cleaned_rows)

        # 3. Prune Entirely Empty Columns
        empty_cols = set()
        for col_idx in range(max_cols):
            all_empty = True
            for row in cleaned_rows:
                if col_idx < len(row) and row[col_idx]:
                    all_empty = False
                    break
            if all_empty:
                empty_cols.add(col_idx)

        optimized_rows = []
        for row in cleaned_rows:
            # Pad the row to max_cols before pruning empty columns
            padded_row = row + [""] * (max_cols - len(row))
            filtered_row = [cell for idx, cell in enumerate(padded_row) if idx not in empty_cols]
            
            # REMOVED: Aggressive token saving.
            # We MUST preserve trailing empty cells to maintain a perfect 2D grid structure.
            # Otherwise, the LLM loses column alignment on sparse rows.
            
            # Check if row is entirely empty after pruning
            if any(cell.strip() for cell in filtered_row):
                optimized_rows.append(filtered_row)

        if not optimized_rows:
             return ""

        # Determine the True max columns after pruning and stripping
        max_final_cols = max(len(row) for row in optimized_rows)
        
        # 4. Build Markdown
        md_lines = [f"### Sheet: {sheet_name}"]
        
        # We don't force a user-row to be the header, as it might be sparse.
        # Create a generic header to establish the max grid width for the LLM.
        generic_header = ["C" + str(i+1) for i in range(max_final_cols)]
        md_lines.append("| " + " | ".join(generic_header) + " |")
        md_lines.append("|" + "|".join(["---"] * max_final_cols) + "|")
        
        # Build Body with Ragged Rows (saving massive tokens on sparse rows)
        for row in optimized_rows:
            md_lines.append("| " + " | ".join(row) + " |")
            
        return "\n".join(md_lines)
