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
    def from_bytes(cls, file_bytes: bytes, file_ext: str) -> str:
        """
        Parse Excel/CSV file bytes directly into a single Markdown string containing all tables.
        """
        ext = file_ext.lower().replace(".", "")
        if ext == "csv":
            return cls._parse_csv(file_bytes)
        elif ext in ("xlsx", "xls"):
            return cls._parse_excel(file_bytes)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
            
    @classmethod
    def _parse_csv(cls, file_bytes: bytes) -> str:
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
        
        return cls._rows_to_markdown(rows, sheet_name="Data")

    @classmethod
    def _parse_excel(cls, file_bytes: bytes) -> str:
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="calamine")
        except ImportError:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
        except Exception as e:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
            
        markdown_sections = []
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            rows = df.fillna("").astype(str).values.tolist()
            if not rows:
                continue
                
            md_table = cls._rows_to_markdown(rows, sheet_name)
            if md_table:
                markdown_sections.append(md_table)
                
        return "\n\n".join(markdown_sections)

    @classmethod
    def _rows_to_markdown(cls, rows: List[List[str]], sheet_name: str) -> str:
        """
        Convert a 2D array of rows to a valid Markdown table string.
        Automatically prunes entirely empty columns to save token space.
        """
        if not rows:
            return ""
            
        # 1. Prune Empty Columns
        col_count = max(len(row) for row in rows)
        empty_cols = set()
        for col_idx in range(col_count):
            all_empty = True
            for row in rows:
                if col_idx < len(row) and row[col_idx].strip():
                    all_empty = False
                    break
            if all_empty:
                empty_cols.add(col_idx)
                
        optimized_rows = []
        for row in rows:
            new_row = [cell.strip().replace("\n", " ") for col_idx, cell in enumerate(row) if col_idx not in empty_cols]
            
            # Remove trailing empty cells to compact the row
            while new_row and not new_row[-1]:
                new_row.pop()
                
            if new_row:
                optimized_rows.append(new_row)
                
        if not optimized_rows:
            return ""
            
        # 2. Build Markdown
        md_lines = [f"### Sheet: {sheet_name}"]
        
        # Assume first non-empty row is header conceptually for Markdown structure
        header_row = optimized_rows[0]
        md_lines.append("| " + " | ".join(header_row) + " |")
        
        # Build Separator
        separator = "| " + " | ".join(["---"] * len(header_row)) + " |"
        md_lines.append(separator)
        
        # Build Body
        for row in optimized_rows[1:]:
            # Pad row to match header length for valid markdown
            padded_row = row + [""] * (len(header_row) - len(row))
            # Truncate if row is longer than header
            padded_row = padded_row[:len(header_row)]
            md_lines.append("| " + " | ".join(padded_row) + " |")
            
        return "\n".join(md_lines)
