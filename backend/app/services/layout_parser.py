import re
from typing import Dict, Any, List, Optional, Tuple
from rapidfuzz import fuzz, utils
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
        """Priority 1: Tag Table Cells"""
        for table in self.all_tables:
            fid = table["file_id"]
            offset_shift = table["file_content_offset"]

            for cell in table.get("cells", []):
                content = cell.get("content", "").strip()
                if not content: continue

                # Safety: Check Bounding Regions & Spans
                # Support both camelCase (raw Azure DI) and snake_case (doc_intel.py)
                regions = cell.get("boundingRegions") or cell.get("bounding_regions", [])
                spans = cell.get("spans", [])

                if not regions:
                    continue

                # Spans may be missing (doc_intel.py doesn't include them for cells)
                # Fall back to fuzzy offset estimation from content position
                if spans:
                    primary_span = spans[0]
                    local_offset = primary_span["offset"]
                    local_length = primary_span["length"]
                else:
                    # Without spans, try to find content in full_content
                    found_pos = self.full_content.find(content, offset_shift)
                    if found_pos == -1:
                        continue  # Can't locate in text
                    local_offset = found_pos - offset_shift
                    local_length = len(content)

                # Convert to Global Offset
                global_offset = offset_shift + local_offset

                # Get Global Page Number (support both pageNumber and page_number)
                local_page = regions[0].get("pageNumber") or regions[0].get("page_number")
                # Find global page match (inefficient but safe)
                global_page = self._find_global_page(fid, local_page)

                # Register
                self._register_tag(
                    text=content,
                    bbox=regions[0].get("polygon"),
                    global_page=global_page,
                    file_id=fid,
                    type_code="C",
                    offset=global_offset,
                    length=local_length,
                    priority=0 # Highest priority
                )

    def _pass_entities(self):
        """Priority 2: Tag NLP Entities in Unclaimed areas"""
        for page in self.global_pages:
            global_page_num = page["global_page_number"]
            fid = page["file_id"]
            offset_shift = page["file_content_offset"]

            words = page.get("words", [])

            for word in words:
                content = word.get("content", "")
                if not self._is_entity(content):
                    continue

                span = word.get("span", {})
                local_offset = span.get("offset", -1)
                length = span.get("length", 0)

                if local_offset == -1: continue

                global_offset = offset_shift + local_offset

                # Check collision with Table
                if self._is_region_claimed(global_offset, length):
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
        if not regions: return

        bbox = regions[0].get("polygon")

        # Get Global Page (support both pageNumber and page_number)
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

    def _reconstruct_text(self) -> str:
        """Flatten original text with inserted tags."""
        # Sort insertions:
        # Primary Key: Position (ascending)
        # Secondary Key: Priority (ascending) -> 0 (Table) before 1 (Entity)?
        # Actually if they serve different spans, position handles it.
        # Priority ensures deterministic order if collisions (unlikely due to mask).
        self.insertions.sort(key=lambda x: (x[0], x[1]))

        chunks = []
        last_pos = 0

        for pos, priority, tag_str in self.insertions:
            # Append text before tag
            chunks.append(self.full_content[last_pos:pos])
            # Append tag (with space for safety)
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


    def find_coordinate_by_text(self, target_text: str, page_limit: Optional[int] = None, file_id: Optional[str] = None) -> Optional[List[float]]:
        """
        Fallback: Fuzzy search in the document text using a 2-Pass Strategy with RapidFuzz.
        Pass 1: Strict - fuzz.ratio (>= 95) with symbols kept.
        Pass 2: Lenient - fuzz.partial_ratio after stripping symbols.
        
        Args:
            target_text: Text to search for.
            page_limit: Restrict search to specific Global Page Number.
            file_id: Restrict search to specific File ID (Critical for Multi-file context).
        """
        if not target_text or len(target_text) < 2:
            return None

        # Preprocess target using RapidFuzz utils (lowercase, strip, collapse whitespace)
        target_processed = utils.default_process(target_text)
        if not target_processed:
            return None

        # --- Internal Helper for Scanning RefMap ---
        def _scan_ref_map(normalized_target: str, is_strict: bool) -> Optional[List[float]]:
            best_score = 0.0
            best_bbox = None

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
                        return info["bbox"]  # Immediate return for exact match on correct page
                    if not best_bbox:
                        best_bbox = info["bbox"]
                    if not page_limit:
                        return info["bbox"]
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
                        return info["bbox"]

                    if score > best_score:
                        best_score = score
                        best_bbox = info["bbox"]

            return best_bbox

        # --- PASS 1: Strict (using fuzz.ratio) ---
        result_strict = _scan_ref_map(target_processed, is_strict=True)
        if result_strict:
            return result_strict

        # --- PASS 2: Lenient (using fuzz.partial_ratio, symbols stripped) ---
        target_norm_lenient = re.sub(r'[^a-zA-Z0-9ㄱ-ㅎㅏ-ㅣ가-힣]', '', target_text.lower())
        if not target_norm_lenient:
            return None

        return _scan_ref_map(target_norm_lenient, is_strict=False)
