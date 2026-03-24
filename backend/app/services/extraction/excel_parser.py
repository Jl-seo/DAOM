import io
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import re

logger = logging.getLogger(__name__)

class ExcelParser:
    """
    Direct Excel/CSV to Markdown Parser & Structural Normalizer.
    Bypasses Azure Document Intelligence and generates clean Markdown tables
    directly from Excel bytes or cleanly transforms complex pivots.
    """
    
    @classmethod
    def normalize_bytes(cls, file_bytes: bytes, ext: str) -> bytes:
        """
        Reads an Excel/CSV file into memory. If any sheet holds a horizontal cross-tab
        matrix (e.g., PODs arranged horizontally with repeating equipment patterns), 
        it intelligently 'half-unpivots' it into a flat vertical table. 
        Returns the modified workbook as new XLSX bytes compatible with downstream.
        """
        try:
            if ext.lower() == 'csv':
                content_str = None
                for encoding in ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]:
                    try:
                        content_str = file_bytes.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if not content_str: return file_bytes
                import csv
                reader = csv.reader(io.StringIO(content_str))
                df = pd.DataFrame(list(reader))
                excel_data = {"Data": df}
            else:
                fc_io = io.BytesIO(file_bytes)
                try:
                    excel_data = pd.read_excel(fc_io, sheet_name=None, header=None, engine="calamine")
                except ImportError:
                    fc_io.seek(0)
                    excel_data = pd.read_excel(fc_io, sheet_name=None, header=None, engine="openpyxl")
        except Exception as e:
            logger.debug(f"Failed to load Excel for normalization: {e}")
            return file_bytes
            
        needs_rewrite = False
        processed_sheets = {}
        
        for sheet_name, df in excel_data.items():
            if df.empty:
                processed_sheets[sheet_name] = df
                continue
                
            unpivoted_df = cls._try_half_unpivot_matrix(df)
            if len(unpivoted_df.columns) != len(df.columns) or len(unpivoted_df) != len(df):
                logger.info(f"Sheet '{sheet_name}' was UNPIVOTED by Parser! Original: {df.shape}, New: {unpivoted_df.shape}")
                needs_rewrite = True
                unpivoted_df.loc[-1] = unpivoted_df.columns
                unpivoted_df.index = unpivoted_df.index + 1
                unpivoted_df = unpivoted_df.sort_index()
                unpivoted_df.columns = range(len(unpivoted_df.columns))
                processed_sheets[sheet_name] = unpivoted_df
            else:
                processed_sheets[sheet_name] = df
                
        if not needs_rewrite:
            return file_bytes
            
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name, df in processed_sheets.items():
                df.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False, header=False)
                
        logger.info("[ExcelParser] Excel structurally normalized (Virtual Workbook Created).")
        return output.getvalue()
        
    @classmethod
    def _try_half_unpivot_matrix(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detects if a DataFrame is a horizontal cross-tab where the bottom-most 
        header contains repeating equipment sizes, and flattens it properly.
        """
        equip_pattern = re.compile(r"^\s*(20|40|45|hc|hcd|hq|dc|rf|ot)[\'\s]*$", re.IGNORECASE)
        
        header_bottom_idx = -1
        for i in range(min(20, len(df))):
            row = df.iloc[i].fillna("").astype(str).tolist()
            equip_matches = [x for x in row if equip_pattern.match(x)]
            if len(equip_matches) >= 6:
                counts = pd.Series(equip_matches).value_counts()
                if any(c > 1 for c in counts):
                    header_bottom_idx = i
                    break
                    
        if header_bottom_idx == -1: return df
        
        header_top_idx = max(0, header_bottom_idx - 2)
        header_block = df.iloc[header_top_idx : header_bottom_idx + 1].copy()
        for i in range(len(header_block) - 1):
            header_block.iloc[i] = header_block.iloc[i].replace(r'^\s*$', pd.NA, regex=True).ffill()
            
        bottom_row = df.iloc[header_bottom_idx].fillna("").astype(str).tolist()
        
        idx_cols, val_cols = [], []
        for c in range(len(df.columns)):
            val = bottom_row[c].strip()
            if equip_pattern.match(val):
                val_cols.append(df.columns[c])
            else:
                idx_cols.append(df.columns[c])
                
        upper_cols = []
        for c in range(len(df.columns)):
            col_parts = []
            for r in range(header_top_idx, header_bottom_idx):
                val = str(header_block.loc[r, df.columns[c]]).strip()
                if val and val.lower() != 'nan':
                    col_parts.append(val)
            upper_cols.append(" | ".join(col_parts))
            
        idx_names = [bottom_row[df.columns.get_loc(ic)] or f"IDX_{ic}" for ic in idx_cols]
        data_df = df.iloc[header_bottom_idx + 1:].copy()
        
        flattened_rows = []
        pod_groups = {}
        for vc in val_cols:
            pod_info = upper_cols[df.columns.get_loc(vc)]
            if pod_info not in pod_groups:
                pod_groups[pod_info] = {}
            equipment = bottom_row[df.columns.get_loc(vc)]
            pod_groups[pod_info][equipment] = vc
            
        for _, row in data_df.iterrows():
            base_dict = {}
            for ic, name in zip(idx_cols, idx_names):
                base_dict[name] = row[ic]
                
            for pod_info, equip_dict in pod_groups.items():
                has_val = False
                equip_vals = {}
                for eq, vc in equip_dict.items():
                    val = str(row[vc]).strip()
                    if val and val.lower() not in ('nan', 'none'):
                        has_val = True
                    equip_vals[eq] = val
                    
                if has_val:
                    new_row = base_dict.copy()
                    new_row['CROSS_TAB_DEST_INFO'] = pod_info
                    new_row.update(equip_vals)
                    flattened_rows.append(new_row)
                    
        return pd.DataFrame(flattened_rows)

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
