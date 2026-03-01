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
        if not rows:
            return []
            
        df = pd.DataFrame(rows)
        # Drop completely empty rows
        df = df.dropna(how='all')
        
        df.insert(0, 'row_id', range(0, len(df)))
        
        # Standardize column names (A, B, C...)
        clean_cols = ['row_id']
        for i in range(len(df.columns) - 1):
            name = ""
            n = i
            while n >= 0:
                name = chr(n % 26 + 65) + name
                n = n // 26 - 1
            clean_cols.append(name)
        df.columns = clean_cols
        
        if len(df) > 1500:
            logger.warning(f"CSV has {len(df)} rows. Truncating Markdown representation to 1500 rows.")
            df = df.head(1500)
            
        md_content = cls._df_to_markdown(df, sheet_name="Data")
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
        row_offset = 0
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            
            # Drop completely empty rows
            df = df.dropna(how='all')
            if df.empty:
                continue
                
            # Add row_id to match Pandas global tracking
            df.insert(0, 'row_id', range(row_offset, row_offset + len(df)))
            row_offset += len(df)
            
            # Standardize column names (A, B, C...)
            clean_cols = ['row_id']
            for i in range(len(df.columns) - 1):
                name = ""
                n = i
                while n >= 0:
                    name = chr(n % 26 + 65) + name
                    n = n // 26 - 1
                clean_cols.append(name)
            df.columns = clean_cols
            
            # Limit to 1500 rows per sheet to protect LLM context windows and UI rendering
            if len(df) > 1500:
                logger.warning(f"Sheet {sheet_name} has {len(df)} rows. Truncating Markdown representation to 1500 rows.")
                df = df.head(1500)
                
            md_table = cls._df_to_markdown(df, sheet_name)
            if md_table:
                markdown_sections.append({"sheet_name": sheet_name, "content": md_table})
                
        return markdown_sections

    @classmethod
    def _df_to_markdown(cls, df: pd.DataFrame, sheet_name: str) -> str:
        """
        Convert a standardized DataFrame (with row_id and A,B,C cols) to Markdown.
        Drops empty columns to save LLM tokens, but retains the original Excel column 
        letters (e.g., A, C, F) in the header to ensure flawless LLM coordinate mapping.
        """
        if df.empty:
            return ""
            
        md_lines = [f"### Sheet: {sheet_name}"]
        
        # 1. Drop entirely empty columns (excluding row_id) to save massive tokens
        data_cols = [c for c in df.columns if c != 'row_id']
        df_data = df[data_cols].replace('', pd.NA) # treat empty strings as NA for dropping
        df_data = df_data.dropna(axis=1, how='all')
        
        # Reconstruct the optimized column list
        optimized_cols = ['row_id'] + list(df_data.columns)
        
        md_lines.append("| " + " | ".join(optimized_cols) + " |")
        md_lines.append("|" + "|".join(["---"] * len(optimized_cols)) + "|")
        
        for _, row in df.iterrows():
            row_str = []
            for c in optimized_cols:
                val = str(row[c]).replace('\n', ' ').strip() if pd.notna(row[c]) else ""
                row_str.append(val)
            md_lines.append("| " + " | ".join(row_str) + " |")
            
        return "\n".join(md_lines)
