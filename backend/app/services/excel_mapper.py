"""
Excel Mapper Module
Converts Excel/CSV files to Azure Document Intelligence compatible JSON format.
This allows Excel files to be processed through the same LLM extraction pipeline
without calling Azure OCR services.

Beta Feature: use_virtual_excel_ocr

OPTIMIZATION (2026-02-07):
- Virtual page splitting: Large sheets split into ~250 row pages for LLM chunking
- Empty column pruning: Fully-empty columns removed to reduce token waste
- Header repetition: Column headers repeated on each virtual page for LLM context
- Empty cell skip: Only non-empty cells included in words/content
"""
import io
import logging
from typing import Dict, Any, List, Tuple, Set
import aiohttp

logger = logging.getLogger(__name__)

# Virtual canvas dimensions
VIRTUAL_WIDTH = 1000
CELL_HEIGHT = 50  # Height per row

# --- CHUNKING OPTIMIZATION ---
# Large single-sheet Excel files must be split into virtual "pages"
# so that beta_chunking.split_ocr_into_chunks can distribute work
# across parallel LLM calls. Without this, 5000 rows = 1 page = 1 chunk.
ROWS_PER_VIRTUAL_PAGE = 250  # ~250 rows per virtual page ≈ 15K chars


class ExcelMapper:
    """Maps Excel/CSV data to Azure Document Intelligence JSON format."""

    @classmethod
    async def from_url(cls, file_url: str) -> Dict[str, Any]:
        """
        Download file from URL and convert to Doc Intel format.
        """
        try:
            # Download file
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status != 200:
                        raise ValueError(f"Failed to download file: {response.status}")
                    file_bytes = await response.read()

            # Determine file type from URL (strip SAS query params)
            ext = file_url.rsplit(".", 1)[-1].lower().split("?")[0]

            if ext == "csv":
                return cls._parse_csv(file_bytes)
            elif ext in ("xlsx", "xls"):
                return cls._parse_excel(file_bytes)
            else:
                raise ValueError(f"Unsupported file extension: {ext}")

        except Exception as e:
            logger.error(f"[ExcelMapper] Error processing file: {e}")
            raise e

    @classmethod
    def from_bytes(cls, file_bytes: bytes, file_type: str = "xlsx") -> Dict[str, Any]:
        """
        Convert file bytes to Doc Intel format.
        """
        if file_type == "csv":
            return cls._parse_csv(file_bytes)
        else:
            return cls._parse_excel(file_bytes)

    @classmethod
    def _optimize_rows(cls, rows: List[List[str]]) -> Tuple[List[List[str]], Set[int]]:
        """
        Optimize rows by removing fully-empty columns to reduce LLM token waste.

        Example: A 50-column Excel where 30 columns are empty → 20 columns after pruning.
        This can reduce token usage by ~60% for sparse spreadsheets.

        Returns (optimized_rows, removed_col_indices).
        """
        if not rows:
            return rows, set()

        col_count = max(len(row) for row in rows)

        # Find columns that are completely empty
        empty_cols: Set[int] = set()
        for col_idx in range(col_count):
            all_empty = True
            for row in rows:
                if col_idx < len(row) and row[col_idx].strip():
                    all_empty = False
                    break
            if all_empty:
                empty_cols.add(col_idx)

        if not empty_cols:
            return rows, set()

        # Remove empty columns from all rows
        optimized = []
        for row in rows:
            new_row = [
                cell for col_idx, cell in enumerate(row)
                if col_idx not in empty_cols
            ]
            optimized.append(new_row)

        logger.info(
            f"[ExcelMapper] Pruned {len(empty_cols)} empty columns "
            f"({col_count} → {col_count - len(empty_cols)} cols)"
        )
        return optimized, empty_cols

    @classmethod
    def _parse_csv(cls, file_bytes: bytes) -> Dict[str, Any]:
        """
        Parse CSV file to Doc Intel format.
        """
        import csv

        # Try to decode with different encodings
        content_str = None
        for encoding in ["utf-8", "cp949", "euc-kr", "latin-1"]:
            try:
                content_str = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if content_str is None:
            raise ValueError("Failed to decode CSV file with supported encodings")

        # Parse CSV
        reader = csv.reader(io.StringIO(content_str))
        rows = list(reader)

        if not rows:
            return cls._empty_result()

        # OPTIMIZATION: Remove empty columns
        rows, _ = cls._optimize_rows(rows)

        result = cls._rows_to_doc_intel(rows, sheet_name="Sheet1", page_number=1)
        result["_layout_parser_bypass"] = True
        return result

    @classmethod
    def _parse_excel(cls, file_bytes: bytes) -> Dict[str, Any]:
        """
        Parse Excel file to Doc Intel format.
        Prioritizes 'calamine' engine for performance (Rust-based),
        falling back to 'openpyxl' if not available.

        OPTIMIZATION: Splits large sheets into virtual pages of
        ROWS_PER_VIRTUAL_PAGE rows each, enabling parallel LLM chunking.
        Each virtual page includes the header row for LLM context.
        """
        import pandas as pd

        # 1. Try Calamine (Fastest)
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="calamine")
            logger.info("[ExcelMapper] Using 'calamine' engine for high-performance Excel reading.")
        except ImportError:
            logger.warning("[ExcelMapper] 'python-calamine' not found. Falling back to openpyxl (slower).")
            try:
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
            except ImportError:
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
        except Exception as e:
            logger.warning(f"[ExcelMapper] Calamine failed ({e}). Falling back to openpyxl.")
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")

        all_pages = []
        all_tables = []
        all_content_parts = []
        global_page_number = 0

        for sheet_idx, sheet_name in enumerate(excel_file.sheet_names):
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            rows = df.fillna("").astype(str).values.tolist()

            if not rows:
                continue

            # OPTIMIZATION: Remove fully-empty columns to reduce token waste
            rows, _ = cls._optimize_rows(rows)

            if not rows or not rows[0]:
                continue

            # --- VIRTUAL PAGE SPLITTING ---
            # Split large sheets into virtual pages for chunking support.
            # Header row (row 0) is repeated on each virtual page for LLM context.
            header_row = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []

            if len(data_rows) <= ROWS_PER_VIRTUAL_PAGE:
                # Small sheet — single page (no splitting needed)
                global_page_number += 1
                result = cls._rows_to_doc_intel(rows, sheet_name, global_page_number)
                all_pages.extend(result["pages"])
                all_tables.extend(result["tables"])
                all_content_parts.append(result["content"])
            else:
                # Large sheet — split into virtual pages
                num_virtual_pages = (len(data_rows) + ROWS_PER_VIRTUAL_PAGE - 1) // ROWS_PER_VIRTUAL_PAGE
                logger.info(
                    f"[ExcelMapper] Sheet '{sheet_name}': {len(rows)} rows → "
                    f"{num_virtual_pages} virtual pages "
                    f"({ROWS_PER_VIRTUAL_PAGE} rows/page)"
                )

                for vp_idx in range(num_virtual_pages):
                    start = vp_idx * ROWS_PER_VIRTUAL_PAGE
                    end = min(start + ROWS_PER_VIRTUAL_PAGE, len(data_rows))
                    page_data_rows = data_rows[start:end]

                    # Prepend header row for LLM context on every virtual page
                    virtual_rows = [header_row] + page_data_rows

                    global_page_number += 1
                    result = cls._rows_to_doc_intel(
                        virtual_rows, sheet_name, global_page_number
                    )
                    all_pages.extend(result["pages"])
                    all_tables.extend(result["tables"])
                    all_content_parts.append(result["content"])

        total_chars = sum(len(c) for c in all_content_parts)
        logger.info(
            f"[ExcelMapper] Final: {len(all_pages)} pages, "
            f"{len(all_tables)} tables, ~{total_chars:,} chars"
        )

        return {
            "content": "\n\n".join(all_content_parts),
            "pages": all_pages,
            "tables": all_tables,
            "paragraphs": [],
            "key_value_pairs": [],
            "documents": [],
            "_layout_parser_bypass": True
        }

    @classmethod
    def _rows_to_doc_intel(cls, rows: List[List[str]], sheet_name: str, page_number: int) -> Dict[str, Any]:
        """
        Convert a 2D array of rows to Doc Intel format.
        OPTIMIZATION: Skips empty cells in content/words to reduce token waste.
        """
        if not rows:
            return cls._empty_result()

        row_count = len(rows)
        col_count = max(len(row) for row in rows) if rows else 0

        if col_count == 0:
            return cls._empty_result()

        # Virtual dimensions
        page_width = VIRTUAL_WIDTH
        page_height = row_count * CELL_HEIGHT
        cell_width = page_width / col_count

        # Build content string — OPTIMIZATION: skip consecutive empty cells
        content_lines = []
        for row in rows:
            # Only include non-empty cells with their column context
            non_empty_parts = []
            for cell in row:
                non_empty_parts.append(cell.strip() if cell.strip() else "")
            # Remove trailing empty cells
            while non_empty_parts and not non_empty_parts[-1]:
                non_empty_parts.pop()
            content_lines.append("\t".join(non_empty_parts))
        content = "\n".join(content_lines)

        # Build words (each non-empty cell as a word)
        words = []
        lines = []

        for row_idx, row in enumerate(rows):
            line_content_parts = []
            for col_idx, cell_value in enumerate(row):
                if not cell_value.strip():
                    continue

                # Calculate virtual polygon
                x1 = col_idx * cell_width
                y1 = row_idx * CELL_HEIGHT
                x2 = (col_idx + 1) * cell_width
                y2 = (row_idx + 1) * CELL_HEIGHT

                polygon = [x1, y1, x2, y1, x2, y2, x1, y2]

                words.append({
                    "content": cell_value,
                    "polygon": polygon,
                    "confidence": 1.0
                })

                line_content_parts.append(cell_value)

            if line_content_parts:
                line_y1 = row_idx * CELL_HEIGHT
                line_y2 = (row_idx + 1) * CELL_HEIGHT
                lines.append({
                    "content": "\t".join(line_content_parts),
                    "polygon": [0, line_y1, page_width, line_y1, page_width, line_y2, 0, line_y2]
                })

        # Build table cells — OPTIMIZATION: skip empty cells
        cells = []
        for row_idx, row in enumerate(rows):
            for col_idx, cell_value in enumerate(row):
                if not cell_value.strip():
                    continue  # Skip empty cells entirely

                x1 = col_idx * cell_width
                y1 = row_idx * CELL_HEIGHT
                x2 = (col_idx + 1) * cell_width
                y2 = (row_idx + 1) * CELL_HEIGHT

                polygon = [x1, y1, x2, y1, x2, y2, x1, y2]

                cells.append({
                    "row_index": row_idx,
                    "column_index": col_idx,
                    "content": cell_value,
                    "kind": "columnHeader" if row_idx == 0 else "content",
                    "bounding_regions": [{
                        "page_number": page_number,
                        "polygon": polygon
                    }]
                })

        # Build page object
        page = {
            "page_number": page_number,
            "width": page_width,
            "height": page_height,
            "unit": "pixel",
            "words": words,
            "lines": lines,
            "selection_marks": []
        }

        # Build table object
        table = {
            "row_count": row_count,
            "column_count": col_count,
            "cells": cells,
            "bounding_regions": [{
                "page_number": page_number,
                "polygon": [0, 0, page_width, 0, page_width, page_height, 0, page_height]
            }]
        }

        return {
            "content": content,
            "pages": [page],
            "tables": [table],
            "paragraphs": [],
            "key_value_pairs": [],
            "documents": []
        }

    @classmethod
    def _empty_result(cls) -> Dict[str, Any]:
        """
        Return empty Doc Intel format.
        """
        return {
            "content": "",
            "pages": [],
            "tables": [],
            "paragraphs": [],
            "key_value_pairs": [],
            "documents": []
        }
