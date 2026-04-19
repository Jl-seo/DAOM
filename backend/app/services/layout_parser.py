import re
from typing import Dict, Any, List, Optional, Tuple
try:
    from rapidfuzz import fuzz, utils
except ImportError:
    fuzz = None
    utils = None

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class LayoutParser:
    """
    [Beta] Optimized Parser for Azure Document Intelligence.
    Implements 'Structure-Aware Tagging' to prevent duplicates and minimize tokens.
    
    Priority Strategy:
    1. Table Cells (^C) - Highest (Structure)
    2. Entities (^W)    - Medium (Semantics via NLP)
    3. Paragraphs (^P)  - Lowest (Context)
    """

    def __init__(self, inputs: Any, file_ids: Optional[List[str]] = None):
        """
        Initialize Parser with one or more Azure DI JSON outputs.
        
        Args:
            inputs: Single Dict (OCR result) or List[Dict] (Multiple OCR results)
            file_ids: Optional list of file IDs corresponding to inputs. 
                      If None, defaults to ["file_0", "file_1", ...].
        """
        # 0. Dependency Check
        if fuzz is None or utils is None:
            raise RuntimeError("Dependency 'rapidfuzz' is missing or failed to import. Service cannot run.")

        # 1. Normalize Input to List
        if isinstance(inputs, dict):
            self.ocr_list = [inputs]
        elif isinstance(inputs, list):
            self.ocr_list = inputs
        else:
            raise ValueError("Input must be Dict or List[Dict]")

        # 2. Assign File IDs
        if file_ids:
            if len(file_ids) != len(self.ocr_list):
                 raise ValueError(f"file_ids count ({len(file_ids)}) must match inputs ({len(self.ocr_list)})")
            self.file_ids = file_ids
        else:
            self.file_ids = [f"file_{i}" for i in range(len(self.ocr_list))]

        # 3. Merge Content & Build Page Map
        self.full_content = ""
        self.global_pages = [] # List of tuples: (file_id, local_page_obj)
        self.page_offset_map = {} # global_page_number -> (file_id, local_page_number)
        self.content_offsets = [] # (start_char, end_char, file_id)

        # Temporary accessors for iteration
        self.all_tables = []
        self.all_paragraphs = []

        current_global_page = 1
        current_char_offset = 0

        for idx, (ocr_data, fid) in enumerate(zip(self.ocr_list, self.file_ids)):
            # A. Content Merge (with None safety)
            file_content = ocr_data.get("content", "") or ""  # Handle None explicitly
            if idx > 0:
                # Add separator/newline to prevent word fusion
                separator = f"\n=== File: {fid} ===\n"
                self.full_content += separator
                current_char_offset += len(separator)

            file_start = current_char_offset
            self.full_content += file_content
            file_end = current_char_offset + len(file_content)
            self.content_offsets.append((file_start, file_end, fid))
            current_char_offset = file_end

            # B. Page Map
            local_pages = ocr_data.get("pages", [])
            for p in local_pages:
                # Store mapping
                self.page_offset_map[current_global_page] = (fid, p.get("page_number", 0))
                # Store flattened page object with global number injected (optional) or just refs
                p_copy = p.copy()
                p_copy["global_page_number"] = current_global_page
                p_copy["file_id"] = fid
                p_copy["file_content_offset"] = file_start # Shift for spans
                self.global_pages.append(p_copy)
                current_global_page += 1

            # C. Aggregate Tables/Paragraphs with File Context
            # We wrap them to store origin
            for t in ocr_data.get("tables", []):
                t_wrapper = t.copy()
                t_wrapper["file_id"] = fid
                t_wrapper["file_content_offset"] = file_start
                self.all_tables.append(t_wrapper)

            for p in ocr_data.get("paragraphs", []):
                p_wrapper = p.copy()
                p_wrapper["file_id"] = fid
                p_wrapper["file_content_offset"] = file_start
                self.all_paragraphs.append(p_wrapper)

        # Output artifacts
        self.ref_map: Dict[str, Any] = {}

        # Span State Management
        self.claimed_mask = bytearray(len(self.full_content))

        # List of (offset, priority, tag_string) to insert
        self.insertions: List[Tuple[int, int, str]] = []

        # Counters for Hex IDs
        self.counters = {
            "C": 1,
            "W": 1,
            "P": 1
        }

    def parse(self, focus_pages: Optional[List[int]] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Executes the 3-Pass Tagging Strategy.
        Notes: 'focus_pages' now refers to GLOBAL page numbers if provided.
        Returns: (tagged_text, ref_map) or (raw_content, {}) on error.
        """
        try:
            # Pass 1: Tables (^C)
            self._pass_tables()

            # Pass 2: Entities (^W)
            self._pass_entities()

            # Pass 3: Paragraphs (^P)
            self._pass_paragraphs()

            # Reconstruction
            return self._reconstruct_text(), self.ref_map
        except Exception as e:
            logger.warning(f"[LayoutParser] Parse failed, returning raw content: {e}")
            return self.full_content or "", {}

    def _mark_claimed(self, offset: int, length: int):
        """Mark a range as consumed in the global mask."""
        end = offset + length
        end = min(end, len(self.full_content))
        for i in range(offset, end):
            self.claimed_mask[i] = True

    def _is_region_claimed(self, offset: int, length: int) -> bool:
        """Check if any part of the region is already claimed."""
        end = offset + length
        end = min(end, len(self.full_content))
        return any(self.claimed_mask[offset:end])

    def _get_hex_id(self, prefix: str) -> str:
        val = self.counters[prefix]
        self.counters[prefix] += 1
        return f"{prefix}{format(val, 'X')}"

    def _register_tag(self, text: str, bbox: List[float], global_page: int, file_id: str, type_code: str, offset: int, length: int, priority: int = 10):
        """
        Register tag mapping and insertion point.
        Args:
            global_page: The sequential page number across all files.
            file_id: The ID of the source file.
            offset: Global text offset in merged content.
        """
        tag_id = self._get_hex_id(type_code) # e.g. "C1", "WA"
        tag_disp = f"^{tag_id}"

        # Get local page for user reference
        # (Already calculated, but can verify via page_offset_map if needed)

        # Ref Map
        self.ref_map[tag_id] = {
            "text": text,
            "bbox": bbox,
            "page_number": global_page, # For LLM context (it sees global pages)
            "file_id": file_id,         # For UI highlighting
            "type": type_code
        }

        # Insertion Point: End of the span
        insert_pos = offset + length
        self.insertions.append((insert_pos, priority, tag_disp))

        # Mark as claimed
        self._mark_claimed(offset, length)

    def _pass_tables(self):
        """Priority 1: Tag Table Cells as Markdown Tables with ^C tags.
        
        Reconstructs Azure DI table structure using row_index/column_index,
        then renders each table as a markdown table with ^C{id} tags in each cell.
        This preserves both: (1) row/column structure for LLM comprehension,
        and (2) tag-based bbox lookup via ref_map.
        """
        # Per-file cursor to track consumption for cells without spans (Excel/Office)
        file_cursors = {fid: 0 for fid in self.file_ids}

        # Initialize table replacement list: [(span_start, span_end, markdown_str)]
        if not hasattr(self, '_table_replacements'):
            self._table_replacements = []

        for table in self.all_tables:
            fid = table["file_id"]
            offset_shift = table["file_content_offset"]

            # --- Step 1: Collect all cells with their grid positions & tag IDs ---
            grid = {}  # (row_index, col_index) -> {"content": str, "tag_id": str}
            max_row = -1
            max_col = -1
            table_span_start = None
            table_span_end = None

            for cell in table.get("cells", []):
                content = cell.get("content", "").strip()
                row_idx = cell.get("rowIndex", cell.get("row_index", 0))
                col_idx = cell.get("columnIndex", cell.get("column_index", 0))
                row_span = cell.get("rowSpan", cell.get("row_span", 1))
                col_span = cell.get("columnSpan", cell.get("column_span", 1))

                max_row = max(max_row, row_idx + row_span - 1)
                max_col = max(max_col, col_idx + col_span - 1)

                # BBox & Page resolution
                regions = cell.get("boundingRegions") or cell.get("bounding_regions", [])
                spans = cell.get("spans", [])

                bbox = None
                global_page = self._find_global_page(fid, 1)

                if regions:
                    bbox = regions[0].get("polygon")
                    local_page = regions[0].get("pageNumber") or regions[0].get("page_number")
                    global_page = self._find_global_page(fid, local_page)

                # Resolve offset in full_content for claiming
                if not spans:
                    current_cursor = file_cursors.get(fid, 0)
                    search_start = offset_shift + current_cursor
                    found_pos = self.full_content.find(content, search_start) if content else -1

                    if found_pos == -1 and not content:
                        # Empty cell — no span to claim, just record in grid
                        for r in range(row_idx, row_idx + row_span):
                            for c in range(col_idx, col_idx + col_span):
                                if (r, c) not in grid:
                                    grid[(r, c)] = {"content": "", "tag_id": None}
                        continue
                    elif found_pos == -1:
                        # Can't locate — still register in grid without tag
                        for r in range(row_idx, row_idx + row_span):
                            for c in range(col_idx, col_idx + col_span):
                                if (r, c) not in grid:
                                    grid[(r, c)] = {"content": content, "tag_id": None}
                        continue

                    local_offset = found_pos - offset_shift
                    local_length = len(content)
                    file_cursors[fid] = local_offset + local_length
                else:
                    primary_span = spans[0]
                    local_offset = primary_span["offset"]
                    local_length = primary_span["length"]

                global_offset = offset_shift + local_offset

                # Track table span boundaries for replacement
                if table_span_start is None or global_offset < table_span_start:
                    table_span_start = global_offset
                cell_end = global_offset + local_length
                if table_span_end is None or cell_end > table_span_end:
                    table_span_end = cell_end

                # Register tag in ref_map (same as before — bbox tracking preserved)
                tag_id = self._get_hex_id("C")
                tag_disp = f"^{tag_id}"

                self.ref_map[tag_id] = {
                    "text": content,
                    "bbox": bbox,
                    "page_number": global_page,
                    "file_id": fid,
                    "type": "C"
                }

                # Mark as claimed
                self._mark_claimed(global_offset, local_length)

                # Store in grid (fill spanned cells, primary cell gets tag)
                # For merged cells (rowSpan > 1 or colSpan > 1), propagate
                # content to ALL spanned positions so the LLM sees the value
                # in every row/column of the span. This prevents extraction
                # misses for fields like validity dates in vertically merged cells.
                is_merged = (row_span > 1 or col_span > 1)
                if is_merged:
                    logger.info(
                        f"[LayoutParser] Merged cell detected: ({row_idx},{col_idx}) "
                        f"span=({row_span}x{col_span}) content='{content[:60]}'"
                    )
                for r in range(row_idx, row_idx + row_span):
                    for c in range(col_idx, col_idx + col_span):
                        if (r, c) not in grid:
                            if r == row_idx and c == col_idx:
                                grid[(r, c)] = {"content": content, "tag_id": tag_disp}
                            elif is_merged and content:
                                # Spanned cell — propagate content with marker
                                # so LLM can see the inherited value per-row
                                grid[(r, c)] = {"content": content, "tag_id": None}
                            else:
                                grid[(r, c)] = {"content": "", "tag_id": None}

            # --- Step 1.5: Carry-Forward for undetected merged cells ---
            # Scenario B: Azure DI reports merged cells as separate empty cells
            # with rowSpan=1. Detect this pattern and carry forward values from
            # the cell above when a cell is empty and the above cell has content.
            #
            # Domain rule (shipping-rate tables):
            #  - Values written in a specific row's cell (e.g. a surcharge
            #    "WRS $40/teu" in the Abu Dhabi row) apply ONLY to that port.
            #  - Values that span a whole block (Validity, POL, Currency,
            #    Region, Trade) merge vertically and should be inherited
            #    across all rows of the block.
            # These two cases produce the same "lots of empty cells" shape,
            # so empty_ratio alone can't distinguish them. We therefore
            # restrict carry-forward to a WHITELIST of column headers that
            # semantically represent block-level attributes. Surcharge,
            # remark, amount, and port-unique columns are never propagated.
            STRUCTURAL_HEADER_KEYWORDS = (
                "validity", "valid", "pol", "pod", "por", "pvy",
                "currency", "ccy", "region", "trade", "area",
                "service", "lane", "route", "origin", "destination",
                "commodity", "rate_type",
                "유효기간", "항로", "지역", "구간", "출발", "도착", "통화",
            )

            def _is_structural_column(col_idx: int) -> bool:
                header = grid.get((0, col_idx), {}).get("content", "").strip().lower()
                if not header:
                    return False
                return any(kw in header for kw in STRUCTURAL_HEADER_KEYWORDS)

            if max_row > 1 and max_col >= 0:
                data_row_count = max_row  # rows 1..max_row are data rows
                for c in range(max_col + 1):
                    # Gate 1: column header must be "structural" (block-level
                    # attribute). Per-row values like WRS/Surcharge/Remark
                    # are never carried forward.
                    if not _is_structural_column(c):
                        continue

                    # First pass: count empty data cells in this column
                    empty_count = 0
                    non_empty_count = 0
                    for r in range(1, max_row + 1):
                        cell_content = grid.get((r, c), {}).get("content", "").strip()
                        if cell_content:
                            non_empty_count += 1
                        else:
                            empty_count += 1

                    # Only carry-forward if column has merge-like pattern:
                    # Some non-empty values + significant empty gaps
                    if non_empty_count == 0 or empty_count == 0:
                        continue
                    empty_ratio = empty_count / data_row_count
                    if empty_ratio < 0.3:
                        continue  # Not enough empty cells to indicate merges
                    
                    # Second pass: carry forward
                    carried = 0
                    for r in range(1, max_row + 1):
                        above = grid.get((r - 1, c), {})
                        current = grid.get((r, c), {})
                        above_content = above.get("content", "").strip()
                        current_content = current.get("content", "").strip()
                        
                        if not current_content and above_content:
                            grid[(r, c)] = {"content": above_content, "tag_id": None}
                            carried += 1
                    
                    if carried > 0:
                        sample_val = grid.get((1, c), {}).get("content", "")[:40]
                        logger.info(
                            f"[LayoutParser] Carry-forward applied: col={c}, "
                            f"{carried}/{data_row_count} cells inherited "
                            f"(empty_ratio={empty_ratio:.0%}, sample='{sample_val}')"
                        )

            # --- Step 2: Build Markdown Table from grid ---
            if max_row < 0 or max_col < 0:
                continue

            md_rows = []
            for r in range(max_row + 1):
                cells_str = []
                for c in range(max_col + 1):
                    cell_info = grid.get((r, c), {"content": "", "tag_id": None})
                    cell_text = cell_info["content"].replace("|", "\\|").replace("\n", " ")
                    tag = cell_info["tag_id"]
                    if tag and cell_text:
                        cells_str.append(f" {cell_text} {tag} ")
                    elif tag:
                        cells_str.append(f" {tag} ")
                    else:
                        cells_str.append(f" {cell_text} ")
                md_rows.append("|" + "|".join(cells_str) + "|")

                # Add separator after header row (row 0)
                if r == 0:
                    sep = "|" + "|".join(["---"] * (max_col + 1)) + "|"
                    md_rows.append(sep)

            markdown_table = "\n" + "\n".join(md_rows) + "\n"


            # --- Step 3: Register table replacement ---
            if table_span_start is not None and table_span_end is not None:
                self._table_replacements.append((table_span_start, table_span_end, markdown_table))
                logger.info(
                    f"[LayoutParser] Table registered: span=[{table_span_start}, {table_span_end}], "
                    f"grid={max_row+1}x{max_col+1}, "
                    f"md_first_row={md_rows[0][:80] if md_rows else '(empty)'}"
                )
            else:
                # Table with no locatable spans — append as insertion at best guess
                # Use first paragraph after table or end of content
                insert_at = offset_shift
                self._table_replacements.append((insert_at, insert_at, markdown_table))
                logger.warning(f"[LayoutParser] Table with no spans, inserted at offset {insert_at}")

    def _pass_entities(self):
        """Priority 2: Tag NLP Entities in Unclaimed areas"""
        # Per-page cursor for span-less fallback (Excel/Office files)
        page_cursors: Dict[int, int] = {}

        for page in self.global_pages:
            global_page_num = page["global_page_number"]
            fid = page["file_id"]
            offset_shift = page["file_content_offset"]

            words = page.get("words", [])
            cursor_key = global_page_num
            if cursor_key not in page_cursors:
                page_cursors[cursor_key] = 0

            for word in words:
                content = word.get("content", "")
                if not content or not self._is_entity(content):
                    continue

                span = word.get("span", {})
                local_offset = span.get("offset", -1)
                length = span.get("length", 0)

                # Fallback for Excel/Office: span is missing
                if local_offset == -1:
                    search_start = offset_shift + page_cursors[cursor_key]
                    found_pos = self.full_content.find(content, search_start)
                    if found_pos == -1:
                        continue
                    local_offset = found_pos - offset_shift
                    length = len(content)
                    page_cursors[cursor_key] = local_offset + length

                global_offset = offset_shift + local_offset

                # Check collision with Table
                if self._is_region_claimed(global_offset, length):
                    # Advance cursor past this word even if claimed
                    page_cursors[cursor_key] = max(page_cursors[cursor_key], local_offset + length)
                    continue

                # Register Entity
                self._register_tag(
                    text=content,
                    bbox=word.get("boundingBox", word.get("polygon")),
                    global_page=global_page_num,
                    file_id=fid,
                    type_code="W",
                    offset=global_offset,
                    length=length,
                    priority=1
                )

    def _pass_paragraphs(self):
        """Priority 3: Tag Remaining Paragraphs (Gaps)"""
        for para in self.all_paragraphs:
            content = para.get("content", "").strip()
            if not content: continue

            fid = para["file_id"]
            offset_shift = para["file_content_offset"]

            # Paragraphs spans
            spans = para.get("spans", [])
            if not spans:
                # Without spans, try to locate content in full text
                found_pos = self.full_content.find(content, offset_shift)
                if found_pos == -1:
                    continue
                local_offset = found_pos - offset_shift
                local_length = len(content)
            else:
                primary_span = spans[0]
                local_offset = primary_span["offset"]
                local_length = primary_span["length"]

            global_offset = offset_shift + local_offset

            # Gap Scanning in Global Mask
            current_gap_start = -1
            para_end = global_offset + local_length

            for i in range(global_offset, min(para_end, len(self.full_content))):
                is_claimed = self.claimed_mask[i]

                if not is_claimed:
                    if current_gap_start == -1:
                        current_gap_start = i
                else:
                    if current_gap_start != -1:
                        # Gap ended, register gap
                        self._register_gap(current_gap_start, i, para, fid, offset_shift)
                        current_gap_start = -1

            # Final gap
            if current_gap_start != -1:
                self._register_gap(current_gap_start, para_end, para, fid, offset_shift)

        # --- Excel/Office Fallback ---
        # When paragraphs are empty (common with Excel), scan full_content
        # for unclaimed text regions and register them as ^P tags.
        if not self.all_paragraphs:
            self._pass_content_gaps()

    def _pass_content_gaps(self):
        """Fallback: Scan full_content for unclaimed text when paragraphs are empty."""
        content_len = len(self.full_content)
        if content_len == 0:
            return

        # Walk through content, find unclaimed regions by newline boundaries
        lines = self.full_content.split("\n")
        current_offset = 0

        for line in lines:
            line_len = len(line)
            if line_len < 2 or not line.strip():
                current_offset += line_len + 1  # +1 for \n
                continue

            # Check if this line region has unclaimed characters
            line_start = current_offset
            line_end = current_offset + line_len

            # Find unclaimed gaps within this line
            gap_start = -1
            for i in range(line_start, min(line_end, content_len)):
                if not self.claimed_mask[i]:
                    if gap_start == -1:
                        gap_start = i
                else:
                    if gap_start != -1:
                        self._register_content_gap(gap_start, i)
                        gap_start = -1

            if gap_start != -1:
                self._register_content_gap(gap_start, line_end)

            current_offset += line_len + 1  # +1 for \n

    def _register_content_gap(self, start: int, end: int):
        """Register an unclaimed text region as a ^P tag (content-based fallback)."""
        length = end - start
        if length < 3:
            return

        text_segment = self.full_content[start:end].strip()
        if not text_segment or len(text_segment) < 2:
            return

        # Determine file_id and page from content_offsets
        file_id = self.file_ids[0] if self.file_ids else "file_0"
        global_page = 1

        for (f_start, f_end, fid) in self.content_offsets:
            if f_start <= start < f_end:
                file_id = fid
                # Find the closest page
                global_page = self._find_global_page(fid, 1)
                break

        self._register_tag(
            text=text_segment,
            bbox=None,  # No bbox available for content-based gaps
            global_page=global_page,
            file_id=file_id,
            type_code="P",
            offset=start,
            length=length,
            priority=2
        )

    def _register_gap(self, start: int, end: int, parent_para: Dict, file_id: str, offset_shift: int):
        """Register a 'Gap' paragraph (unclaimed text within a paragraph)."""
        length = end - start
        if length < 3: return # Skip junk

        text_segment = self.full_content[start:end].strip()
        # Token Diet: Skip if empty or just punctuation/whitespace
        if not text_segment or len(text_segment) < 2:
            return

        # BBox Safety (support both camelCase and snake_case)
        regions = parent_para.get("boundingRegions") or parent_para.get("bounding_regions", [])
        if not regions:
             # Fallback for Excel/Digital: Use dummy bbox or None if strict
             # Azure Layout model for Office files often omits polygons.
             # We should register it anyway to capture text, even if highlighting fails.
             bbox = None
             global_page = self._find_global_page(file_id, 1) # Default page 1
        else:
             bbox = regions[0].get("polygon")
             local_page = regions[0].get("pageNumber") or regions[0].get("page_number")
             global_page = self._find_global_page(file_id, local_page)

        self._register_tag(
            text=text_segment,
            bbox=bbox,
            global_page=global_page,
            file_id=file_id,
            type_code="P",
            offset=start,
            length=length,
            priority=2 # Lowest priority
        )

    def _find_global_page(self, file_id: str, local_page: int) -> int:
        """Helper to lookup global page number from file_id and local page."""
        # Check page map (reverse lookup or store better structure)
        # Optimized: Pre-calculate in __init__ or scan global_pages list
        for p in self.global_pages:
            if p["file_id"] == file_id and p.get("page_number") == local_page:
                return p["global_page_number"]
        return 1 # Fallback

    def _extract_unclaimed_text(self, start: int, end: int) -> str:
        """Extract non-cell text fragments from within a table replacement span.
        
        When Azure DI treats a form (key-value metadata + data table) as a single
        table object, the replacement span [start, end) covers metadata text that
        is NOT part of any cell. This method recovers those fragments using the
        claimed_mask to distinguish cell text from metadata text.
        
        Returns recovered text fragments joined by newlines, or empty string.
        """
        fragments = []
        current_fragment = []
        content_len = len(self.full_content)
        
        for i in range(start, min(end, content_len)):
            if not self.claimed_mask[i]:
                current_fragment.append(self.full_content[i])
            else:
                if current_fragment:
                    text = "".join(current_fragment).strip()
                    if text and len(text) >= 2:  # Skip whitespace-only fragments
                        fragments.append(text)
                    current_fragment = []
        
        # Final fragment
        if current_fragment:
            text = "".join(current_fragment).strip()
            if text and len(text) >= 2:
                fragments.append(text)
        
        return "\n".join(fragments)

    def _reconstruct_text(self) -> str:
        """Flatten original text with inserted tags and markdown table replacements."""
        # Sort table replacements by start position (non-overlapping assumed)
        table_repls = sorted(getattr(self, '_table_replacements', []), key=lambda x: x[0])

        # Diagnostic: log all table replacements and detect overlaps
        if table_repls:
            logger.info(f"[LayoutParser] _reconstruct_text: {len(table_repls)} table replacement(s)")
            for i, (s, e, _md) in enumerate(table_repls):
                overlap = "OVERLAP" if i > 0 and s < table_repls[i-1][1] else "ok"
                logger.info(f"  Table {i}: span=[{s}, {e}] len={e-s} {overlap}")

        # Filter out insertions that fall within table replacement zones
        # (table cells already have tags embedded in the markdown)
        table_zones = [(s, e) for s, e, _ in table_repls]

        def in_table_zone(pos):
            for s, e in table_zones:
                if s <= pos <= e:
                    return True
            return False

        # Sort non-table insertions (^W, ^P tags)
        filtered_insertions = [
            (pos, pri, tag) for pos, pri, tag in self.insertions
            if not in_table_zone(pos)
        ]
        filtered_insertions.sort(key=lambda x: (x[0], x[1]))

        # Merge both streams: table replacements + tag insertions
        # Build output by walking through the content in order
        chunks = []
        last_pos = 0
        
        # Create unified event list
        events = []
        for s, e, md in table_repls:
            events.append((s, 'table', (s, e, md)))
        for pos, pri, tag in filtered_insertions:
            events.append((pos, 'tag', (pos, pri, tag)))
        events.sort(key=lambda x: (x[0], 0 if x[1] == 'table' else 1))

        for _, etype, data in events:
            if etype == 'table':
                s, e, md = data
                if s < last_pos:
                    # Overlapping table span — still emit its markdown to avoid
                    # losing form metadata tables that overlap with data tables.
                    # Azure DI invoice forms often produce two overlapping tables:
                    # a key-value form table and a data table sharing the same area.
                    unclaimed = self._extract_unclaimed_text(max(s, last_pos), e)
                    if unclaimed.strip():
                        chunks.append(unclaimed + "\n")
                    chunks.append(md)
                    last_pos = max(last_pos, e)
                    continue
                # Append text before table
                chunks.append(self.full_content[last_pos:s])
                # Preserve non-cell text trapped inside the table span.
                # Azure DI form tables can span metadata (Invoice No, Date, etc.)
                # that is NOT part of the cell grid — recover it here.
                unclaimed = self._extract_unclaimed_text(s, e)
                if unclaimed.strip():
                    chunks.append(unclaimed + "\n")
                # Append markdown table (replaces original cell text from s to e)
                chunks.append(md)
                last_pos = e
            else:
                pos, pri, tag_str = data
                if pos < last_pos:
                    continue  # Inside a replaced table zone
                # Append text before tag
                chunks.append(self.full_content[last_pos:pos])
                chunks.append(f" {tag_str}")
                last_pos = pos

        # Append remaining
        chunks.append(self.full_content[last_pos:])

        return "".join(chunks)

    def _is_entity(self, text: str) -> bool:
        """
        Determine if a word should be tagged as an Entity (^W).
        Entities include: numbers, currency, uppercase abbreviations, and Korean proper nouns.
        """
        # Numbers or alphanumeric codes (e.g., "PO-2024-001", "12345")
        if re.search(r'[\d]', text): return True

        # Uppercase abbreviations (e.g., "USD", "POL")
        if text.isupper() and len(text) > 2: return True

        # Currency symbols
        if any(s in text for s in ["$", "€", "£", "₩"]): return True

        # Korean words (proper nouns, place names like 인천항, 부산항)
        # Tag if word contains Hangul and is a reasonable length (2+ chars)
        if len(text) >= 2 and re.search(r'[가-힣]+', text): return True

        return False


    def find_coordinate_by_text(self, target_text: str, page_limit: Optional[int] = None, file_id: Optional[str] = None) -> Optional[Tuple[List[float], int]]:
        """
        Fallback: Fuzzy search in the document text using a 2-Pass Strategy with RapidFuzz.
        Returns: (bbox, page_number) or None
        """
        if not target_text or len(target_text) < 2:
            return None

        # Preprocess target using RapidFuzz utils (lowercase, strip, collapse whitespace)
        target_processed = utils.default_process(target_text)
        if not target_processed:
            return None

        # --- Internal Helper for Scanning RefMap ---
        def _scan_ref_map(normalized_target: str, is_strict: bool) -> Optional[Tuple[List[float], int]]:
            best_score = 0.0
            best_result = None # (bbox, page)

            for idx, info in self.ref_map.items():
                ref_page = info.get("page_number")
                ref_file = info.get("file_id")
                raw_ref_text = info["text"]

                # Filter Scope
                if page_limit and ref_page != page_limit: continue
                if file_id and ref_file != file_id: continue

                # Normalize Reference based on pass type
                if is_strict:
                    # Pass 1: Use default_process (lowercase, strip)
                    ref_norm = utils.default_process(raw_ref_text)
                else:
                    # Pass 2: Strip all non-alphanumeric except Hangul
                    ref_norm = re.sub(r'[^a-zA-Z0-9ㄱ-ㅎㅏ-ㅣ가-힣]', '', raw_ref_text.lower())

                if not ref_norm:
                    continue

                # 1. Exact Match Check (fast path)
                if normalized_target == ref_norm:
                    if page_limit and ref_page == page_limit:
                        return (info["bbox"], ref_page)
                    if not best_result:
                        best_result = (info["bbox"], ref_page)
                    if not page_limit:
                        return (info["bbox"], ref_page)
                    continue

                # 2. Fuzzy Match using RapidFuzz
                if is_strict:
                    # Pass 1: Full string ratio (requires high similarity)
                    score = fuzz.ratio(normalized_target, ref_norm)
                    threshold = settings.FUZZY_MATCH_THRESHOLD_STRICT
                else:
                    # Pass 2: Partial ratio (finds best substring match)
                    score = fuzz.partial_ratio(normalized_target, ref_norm)
                    threshold = settings.FUZZY_MATCH_THRESHOLD_LENIENT

                # Boost score for page match
                if page_limit and ref_page == page_limit:
                    score = min(100, score + 5)

                if score >= threshold:
                    # Very high score - return immediately
                    if score >= 98:
                        return (info["bbox"], ref_page)

                    if score > best_score:
                        best_score = score
                        best_result = (info["bbox"], ref_page)

            return best_result

        # --- PASS 1: Strict (using fuzz.ratio) ---
        result_strict = _scan_ref_map(target_processed, is_strict=True)
        if result_strict:
            return result_strict

        # --- PASS 2: Lenient (using fuzz.partial_ratio, symbols stripped) ---
        target_norm_lenient = re.sub(r'[^a-zA-Z0-9ㄱ-ㅎㅏ-ㅣ가-힣]', '', target_text.lower())
        if not target_norm_lenient:
            return None

        return _scan_ref_map(target_norm_lenient, is_strict=False)
