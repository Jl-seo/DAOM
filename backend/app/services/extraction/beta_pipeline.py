import asyncio
import copy
import hashlib
import json
import logging
import re as re_module
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.schemas.model import ExtractionModel
from app.services.extraction.core import ExtractionPipeline, ExtractionResult, TokenUsage
from app.services.layout_parser import LayoutParser
from app.services.refiner import RefinerEngine
from app.services.llm import call_llm_single, get_current_model
from app.core.config import settings
from openai import AsyncAzureOpenAI

class AdaptiveSemaphore:
    """
    AIMD (Additive Increase Multiplicative Decrease) Semaphore
    Dynamically adjusts concurrency based on success/429 failures.
    """
    def __init__(self, initial_value: float, min_value: float = 2.0, max_value: float = 20.0):
        self._value = float(initial_value)
        self._min_value = float(min_value)
        self._max_value = float(max_value)
        self._active = 0
        self._cond = asyncio.Condition()

    async def acquire(self):
        async with self._cond:
            while self._active >= int(self._value):
                await self._cond.wait()
            self._active += 1

    async def release(self, is_429: bool = False):
        async with self._cond:
            self._active -= 1
            if is_429:
                # Multiplicative decrease on 429 (halve concurrency)
                self._value = max(self._min_value, self._value * 0.5)
                logger.warning(f"[AdaptiveSemaphore] 429 Hit. Scaling down concurrency to {int(self._value)}")
            else:
                # Additive increase on success
                self._value = min(self._max_value, self._value + 0.1)
            self._cond.notify(1)

class _AdaptiveContext:
    def __init__(self, sem: AdaptiveSemaphore):
        self.sem = sem
        self.is_429 = False

    async def __aenter__(self):
        await self.sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.sem.release(is_429=self.is_429)

logger = logging.getLogger(__name__)

# Shared constant for reference tag stripping across the pipeline
REF_TAG_PATTERN = r"\^[CWP][0-9A-Fa-f]+"

# Module-level cache for Designer work orders (per model hash)
_work_order_cache: Dict[str, dict] = {}

class BetaPipeline(ExtractionPipeline):
    """
    Two-Phase LLM Extraction Strategy (Designer → Engineer):
    1. LayoutParser: Structure-aware tagging (markdown tables + ^C/^W/^P)
    2. Designer LLM: Schema → Work Order (cacheable per model)
    3. Engineer LLM: Work Order + Tagged Text → JSON with ref tags
    4. Post-Processor: ref_map → exact bbox lookup + uncertainty preservation
    """
    
    def __init__(self, azure_client: AsyncAzureOpenAI):
        self.azure_client = azure_client
        self.semaphore = AdaptiveSemaphore(initial_value=5.0)

    # ==================================================================
    # Main Entry Point
    # ==================================================================

    async def execute(self, model: ExtractionModel, ocr_data: Dict[str, Any], focus_pages: Optional[List[int]] = None) -> ExtractionResult:
        """
        Designer → Engineer Pipeline:
        1. LayoutParser (tagged text + ref_map)
        2. Designer LLM (work order from schema — cached)
        3. Engineer LLM (extraction with ref tags)
        4. Post-Processor (ref → bbox + uncertainty)
        """
        start_time = datetime.utcnow()
        
        # --- 1. Layout Parsing (or Direct Markdown Bypass) ---
        if ocr_data.get("_is_direct_markdown"):
             logger.info("[BetaPipeline] Bypassing LayoutParser (Direct Markdown provided)")
             tagged_text = ocr_data.get("content", "")
             ref_map = {} # References not used for direct Excel parsing since no BBox exists
        else:
             parser = LayoutParser(ocr_data)
             tagged_text, ref_map = parser.parse(focus_pages=focus_pages)
        
        content_len = len(tagged_text)
        page_count = len(ocr_data.get("pages", []))
        logger.info(f"[BetaPipeline] Analysis: pages={page_count}, content_len={content_len} chars")

        # --- 2. Designer + Mapping Designer (PARALLEL) ---
        # Designer needs only the model schema (cached).
        # Analyst needs model + document skeleton (no dependency on work_order).
        # Run both concurrently to hide Analyst latency.
        skeleton_text = self._build_document_skeleton(tagged_text)
        work_order, analyst_result = await asyncio.gather(
            self._run_designer(model),
            self._run_analyst(model, skeleton_text)
        )
        
        # Inject mapping plan into work_order
        wo_target = work_order.get("work_order", work_order)
        if analyst_result:
            mapping_keys = ("dynamic_hints", "field_mappings", "inheritance_rules", "table_structure", "global_surcharge_rules")
            injected = []
            for key in mapping_keys:
                if key in analyst_result:
                    wo_target[key] = analyst_result[key]
                    injected.append(key)
            if injected:
                logger.info(f"[BetaPipeline] Mapping Designer injected: {', '.join(injected)}")
        
        # --- 2.5 Schema-First Table Fields Enforcement ---
        # Designer is a *hint provider*, Schema is the *source of truth*.
        # If model.fields defines table fields that the Designer omitted from
        # work_order.table_fields, we inject them here from the fallback builder.
        # This prevents silent drops when a Designer LLM decides to skip some fields.
        TABLE_FIELD_TYPES = ('list', 'table', 'array')
        existing_table_keys = {tf.get("key") for tf in wo_target.get("table_fields", [])}
        existing_common_keys = {cf.get("key") for cf in wo_target.get("common_fields", [])}
        
        injected_table_keys = []
        injected_common_keys = []
        for f in model.fields:
            if f.type in TABLE_FIELD_TYPES or bool(getattr(f, 'sub_fields', None)):
                if f.key not in existing_table_keys:
                    # Build a minimal table_field entry from model schema
                    entry = {
                        "key": f.key,
                        "instruction": f"Extract '{f.label}' from the document.",
                        "expected_format": f.type,
                        "columns": {},
                        "rules": ["Extract ALL rows."]
                    }
                    if f.description:
                        entry["instruction"] += f" Description: {f.description}"
                    for sf in (getattr(f, 'sub_fields', None) or []):
                        sf_key = sf.get("key") if isinstance(sf, dict) else getattr(sf, "key", None)
                        sf_label = (sf.get("label") if isinstance(sf, dict) else getattr(sf, "label", None)) or sf_key
                        if sf_key:
                            col_dict = {"instruction": f"Extract '{sf_label}'."}
                            sf_desc = sf.get("description") if isinstance(sf, dict) else getattr(sf, "description", None)
                            if sf_desc:
                                col_dict["instruction"] += f" Description: {sf_desc}"
                            entry["columns"][sf_key] = col_dict
                    wo_target.setdefault("table_fields", []).append(entry)
                    injected_table_keys.append(f.key)
            else:
                if f.key not in existing_common_keys and f.key not in existing_table_keys:
                    entry = {
                        "key": f.key,
                        "instruction": f"Extract '{f.label}' from the document.",
                        "expected_format": f.type,
                        "rules": []
                    }
                    if f.description:
                        entry["instruction"] += f" Description: {f.description}"
                    wo_target.setdefault("common_fields", []).append(entry)
                    injected_common_keys.append(f.key)
        
        if injected_table_keys or injected_common_keys:
            logger.info(f"[BetaPipeline] Schema-first enforcement: injected {len(injected_table_keys)} "
                        f"table fields ({', '.join(injected_table_keys)}), "
                        f"{len(injected_common_keys)} common fields ({', '.join(injected_common_keys)})")
        
        # --- 2.6 Schema Rule Injection (DETERMINISTIC — no LLM interpretation) ---
        # Directly inject include_when/exclude_when/group_row_behavior/field_inheritance
        # from model schema into work_order table_fields. Schema rules have absolute precedence.
        schema_rules_by_key = {}
        for f in model.fields:
            rules = {}
            if f.include_when:
                rules["include_when"] = f.include_when
            if f.exclude_when:
                rules["exclude_when"] = f.exclude_when
            if f.group_row_behavior:
                rules["group_row_behavior"] = f.group_row_behavior
            if f.field_inheritance:
                rules["field_inheritance"] = f.field_inheritance
            if rules:
                schema_rules_by_key[f.key] = rules
        
        if schema_rules_by_key:
            for tf in wo_target.get("table_fields", []):
                key = tf.get("key", "")
                if key in schema_rules_by_key:
                    tf.update(schema_rules_by_key[key])
            logger.info(f"[BetaPipeline] Schema rules injected for: {', '.join(schema_rules_by_key.keys())}")
        
        # Merge Analyst row_classification_rules ONLY for fields WITHOUT schema rules
        analyst_row_rules = analyst_result.get("row_classification_rules", []) if analyst_result else []
        if analyst_row_rules:
            for rule in analyst_row_rules:
                if not isinstance(rule, dict):
                    logger.warning(f"[BetaPipeline] Ignored malformed analyst rule (not a dict): {rule}")
                    continue
                table_key = rule.get("table_field", "")
                if table_key and table_key not in schema_rules_by_key:
                    for tf in wo_target.get("table_fields", []):
                        if tf.get("key") == table_key:
                            if rule.get("include_when") and not tf.get("include_when"):
                                tf["include_when"] = rule["include_when"]
                            if rule.get("exclude_when") and not tf.get("exclude_when"):
                                tf["exclude_when"] = rule["exclude_when"]
                    logger.info(f"[BetaPipeline] Analyst row_classification augmented: {table_key}")
        
        # --- 3. Parallel Extraction (Text + Table Division) ---
        is_excel = ocr_data.get("_is_direct_markdown", False)
        page_count = len(ocr_data.get("pages", []))
        
        # Adaptive Semaphore Initialization
        # Base concurrency on doc type & size
        if is_excel:
            initial_concurrency = 4.0
        else:
            initial_concurrency = max(5.0, min(15.0, 30.0 / max(1, page_count)))
            
        self.semaphore = AdaptiveSemaphore(initial_value=initial_concurrency, min_value=2.0, max_value=20.0)
        logger.info(f"[BetaPipeline] Dynamic Concurrency Initialized: {int(initial_concurrency)} (Excel: {is_excel}, Pages: {page_count})")
        
        # GPT-4.1 supports 128k context — use larger chunks to minimize LLM call count
        # 25K chars ≈ 6-8K tokens, well within limits while reducing chunk count by ~3x
        TEXT_CHUNK_SIZE = 150_000 if is_excel else 25_000
        SINGLE_SHOT_CHAR_LIMIT = 300_000 if is_excel else 50_000
        wo_inner = work_order.get("work_order", work_order)
        table_fields = wo_inner.get("table_fields", [])
        num_table_fields = len(table_fields)
        
        # Per-Table Schema Split: When 2+ table fields exist, extract each table independently
        # to prevent completion token exhaustion that causes only the first table to survive.
        # Single-table and no-table schemas use the original optimized unified path.
        text_work_order = work_order
        should_run_table_mapper = getattr(settings, 'ENABLE_TABLE_MAPPER', False)
        engineer_text_payload = tagged_text

        # --- 3b. Document Survey (Optional — Python facts + AI interpretation) ---
        survey_result = None
        survey_context = ""
        use_judge = model.beta_features.get("use_judge", False) if model.beta_features else False
        if use_judge:
            try:
                task_list = self._build_task_list(model)
                survey_result = await self._search_locations(task_list, tagged_text, model)
                if survey_result:
                    pf = survey_result.get("python_facts", {})
                    ai = survey_result.get("ai_interpretation", {})
                    ta = ai.get("table_analysis", {})
                    # Build context string for Engineer
                    survey_lines = [
                        "--- DOCUMENT SURVEY (PRE-EXTRACTION ANALYSIS) ---",
                        f"Document has {pf.get('total_table_rows', '?')} table rows, "
                        f"{pf.get('total_unique_entities', '?')} unique entities across "
                        f"{pf.get('num_tables', '?')} table(s).",
                    ]
                    # Add estimated output rows and destination list from AI
                    for fk, info in ta.items():
                        est = info.get("estimated_output_rows", "")
                        dests = info.get("all_destination_names", [])
                        skip = info.get("header_rows_to_skip", [])
                        excl = info.get("rows_to_exclude", [])
                        if est:
                            survey_lines.append(f"Expected output rows for '{fk}': ~{est}")
                        if dests:
                            survey_lines.append(f"ALL destinations to extract: {', '.join(dests[:40])}")
                        if skip:
                            survey_lines.append(f"Skip (group headers, not data): {skip}")
                        if excl:
                            survey_lines.append(f"Exclude (no rate data): {excl}")
                    # Fallback: use Python entities if AI didn't provide destinations
                    if not any(info.get("all_destination_names") for info in ta.values()):
                        ents = survey_result.get("all_entities", [])
                        if ents:
                            survey_lines.append(f"Detected entities (ensure none are missed): {', '.join(ents[:40])}")
                    survey_lines.append(
                        "CRITICAL: Do NOT truncate output. Extract ALL rows matching the above destinations."
                    )
                    survey_lines.append("--- END DOCUMENT SURVEY ---")
                    survey_context = "\n".join(survey_lines) + "\n\n"
                    logger.info(f"[BetaPipeline] Survey context: {len(survey_context)} chars")
            except Exception as e:
                logger.warning(f"[BetaPipeline] Survey failed (non-fatal): {e}")

        # Inject survey context into Engineer payload (prepend to document text)
        if survey_context:
            engineer_text_payload = survey_context + engineer_text_payload

        async def run_engineer_pipeline():
            # UNIFIED EXTRACTION FIRST (all tables together)
            # Per-Table Split is only used as fallback when output is truncated.
            # This dramatically reduces LLM call count for multi-table models:
            #   Before: 5 sub-orders × 13 chunks = 65 calls
            #   After:  1 unified × 4-5 chunks = 5 calls (with per-table fallback if truncated)
            current_len = len(engineer_text_payload)
            
            if current_len <= SINGLE_SHOT_CHAR_LIMIT:
                logger.info(f"[BetaPipeline] Route: Single-Shot Engineer ({num_table_fields} table fields, {current_len} chars)")
                output = await self._run_engineer(text_work_order, engineer_text_payload, model)
                
                # Fallback 1: Input too large
                if output.get("_truncated"):
                    logger.warning("[BetaPipeline] Single-Shot truncated! Falling back to Chunked Engineer.")
                    output = await self._run_engineer_chunked(text_work_order, engineer_text_payload, TEXT_CHUNK_SIZE, model)
            else:
                logger.info(f"[BetaPipeline] Route: Chunked Engineer ({num_table_fields} table fields, {current_len} chars)")
                output = await self._run_engineer_chunked(text_work_order, engineer_text_payload, TEXT_CHUNK_SIZE, model)
                
            # Fallback 2: Output truncated (completion tokens exhausted) → Per-Table Split
            # This is the ONLY path to per-table split now, ensuring it's used only when needed
            if output.get("_truncated") and num_table_fields >= 2:
                logger.warning(f"[BetaPipeline] Unified extraction truncated with {num_table_fields} tables. Falling back to Per-Table Schema Split.")
                output = await self._run_engineer_per_table(text_work_order, engineer_text_payload, TEXT_CHUNK_SIZE, model)
            
            return output
            
        async def run_table_mapper_pipeline():
            if not should_run_table_mapper:
                return {}
            try:
                from app.services.extraction.table_mapper import DirectTableMapper
                logger.info("[BetaPipeline] Route: DirectTableMapper (Parallel)")
                return await DirectTableMapper.extract_tables(wo_inner, tagged_text)
            except Exception as e:
                logger.error(f"[BetaPipeline] DirectTableMapper failed: {e}")
                return {}

        # Execute both pipelines concurrently
        engineer_output, table_output = await asyncio.gather(
            run_engineer_pipeline(),
            run_table_mapper_pipeline()
        )
        
        # Merge the fast deterministic table output into the LLM text output
        if table_output and engineer_output.get("guide_extracted"):
            engineer_output["guide_extracted"].update(table_output)
        elif table_output and not engineer_output.get("guide_extracted"):
            engineer_output["guide_extracted"] = table_output
        
        # --- 4. Post-Process (ref → bbox) ---
        final_guide = RefinerEngine.post_process_with_ref(
            engineer_output, ref_map
        )
        
        # --- 4a & 4b. Dictionary Auto-Normalization & Transform Rules ---
        # NOTE: Removed from BetaPipeline. These operations are now handled 
        # globally at the end of `ExtractionService.run_extraction_pipeline()` 
        # via the `rule_engine` module to ensure consistency across all extraction engines.

        
        # --- 4b. Judge LLM — Self-Audit (Optional) ---
        judge_result = None
        # use_judge already set above in Survey section
        if use_judge:
            try:
                processed_guide_pre = final_guide.get("guide_extracted", {})
                judge_result = await self._run_judge(
                    processed_guide_pre, tagged_text, model
                )
                # Apply confidence adjustments from Judge
                issues = judge_result.get("issues", [])
                if issues:
                    logger.warning(
                        f"[BetaPipeline] Judge flagged {len(issues)} issue(s): "
                        + ", ".join(i.get("field", "?") + "=" + i.get("type", "?") for i in issues[:5])
                    )
                    for issue in issues:
                        field_key = issue.get("field", "")
                        issue_type = issue.get("type", "")
                        if field_key and field_key in processed_guide_pre:
                            node = processed_guide_pre[field_key]
                            if isinstance(node, dict) and "confidence" in node:
                                orig_conf = node.get("confidence", 1.0)
                                if issue_type == "HALLUCINATION":
                                    node["confidence"] = 0.0
                                    node["_judge_flag"] = "HALLUCINATION"
                                elif issue_type == "SCOPE_ERROR":
                                    node["confidence"] = min(orig_conf, 0.3)
                                    node["_judge_flag"] = "SCOPE_ERROR"
                                elif issue_type == "VALUE_MISMATCH":
                                    node["confidence"] = min(orig_conf, 0.5)
                                    node["_judge_flag"] = "VALUE_MISMATCH"
                            # Handle INCOMPLETE (missing rows) — can't auto-fix, but flag for visibility
                            elif issue_type == "INCOMPLETE":
                                logger.warning(
                                    f"[BetaPipeline] Judge: INCOMPLETE — {field_key} "
                                    f"is missing rows: {issue.get('suggestion', '?')[:200]}"
                                )
                else:
                    logger.info("[BetaPipeline] Judge: All fields verified OK")

                # --- 4b-2. Field-Level Retry for flagged fields ---
                retryable = [
                    i for i in issues
                    if i.get("type") in ("HALLUCINATION", "SCOPE_ERROR", "VALUE_MISMATCH")
                ]
                if retryable and len(retryable) <= 10:
                    try:
                        retry_result = await self._retry_flagged_fields(
                            retryable, work_order, tagged_text, model
                        )
                        if retry_result:
                            for fk, fv in retry_result.items():
                                if fk.startswith("_"):
                                    continue
                                processed_guide_pre[fk] = fv
                                logger.info(f"[BetaPipeline] Retry replaced: {fk}")
                            judge_result["_retry_applied"] = list(retry_result.keys())
                    except Exception as re:
                        logger.warning(f"[BetaPipeline] Field retry failed (non-fatal): {re}")

            except Exception as e:
                logger.warning(f"[BetaPipeline] Judge failed (non-fatal): {e}")

            # --- 4b-3. Survey-based Gap Check (Python, no LLM) ---
            if survey_result:
                try:
                    survey_entities = set(
                        e.upper() for e in survey_result.get("all_entities", [])
                        if len(e) > 2 and not e[0].isdigit()
                    )
                    guide_pre = final_guide.get("guide_extracted", {})
                    for fk, fv in guide_pre.items():
                        actual_val = fv
                        if isinstance(fv, dict) and "value" in fv and isinstance(fv["value"], list):
                            actual_val = fv["value"]
                        if isinstance(actual_val, list) and len(actual_val) > 0:
                            extracted_vals = set()
                            for row in actual_val:
                                if isinstance(row, dict):
                                    for col in ["POD", "PORT", "port", "destination"]:
                                        pv = row.get(col, {})
                                        val = pv.get("value", "") if isinstance(pv, dict) else str(pv)
                                        if val:
                                            extracted_vals.add(val.upper())
                            missing = survey_entities - extracted_vals
                            # Filter to likely destination names (exclude headers like TRADE, COMMODITY)
                            skip_words = {"TRADE", "COMMODITY", "PORT", "VALIDITY", "OWS", "GFS", "GRI",
                                          "PSS", "REMARK", "20FT", "40FT", "CURRENCY", "FAK", "FALCON"}
                            missing = {m for m in missing if m not in skip_words}
                            if missing and len(missing) > 2:
                                logger.warning(
                                    f"[BetaPipeline] Survey Gap: {fk} has {len(actual_val)} rows "
                                    f"but {len(missing)} entities not found in extraction: "
                                    f"{', '.join(sorted(missing)[:15])}"
                                )
                                if judge_result is None:
                                    judge_result = {"issues": [], "verdict": "flagged"}
                                judge_result["_survey_gap"] = {
                                    "field": fk,
                                    "extracted_count": len(actual_val),
                                    "missing_count": len(missing),
                                    "missing_entities": sorted(missing)[:30],
                                }
                except Exception as e:
                    logger.warning(f"[BetaPipeline] Survey gap check failed: {e}")

        # --- 4c. Extract unmapped_critical_info → other_data ---
        other_data = []
        processed_guide = final_guide.get("guide_extracted", {})
        unmapped = processed_guide.pop("unmapped_critical_info", None)
        if unmapped:
            # Handle both single value and list of values
            unmapped_items = unmapped if isinstance(unmapped, list) else [unmapped]
            for item in unmapped_items:
                if isinstance(item, dict):
                    val = item.get("value")
                    if val and val is not None:
                        other_data.append({
                            "column": "unmapped_critical_info",
                            "value": val,
                            "confidence": item.get("confidence", 0.5),
                            "bbox": item.get("bbox")
                        })
                elif isinstance(item, str) and item:
                    other_data.append({
                        "column": "unmapped_critical_info",
                        "value": item,
                        "confidence": 0.5
                    })
        
        # --- 5. Build Result ---
        total_usage = engineer_output.get("_token_usage", {})
        
        final_result = ExtractionResult(
            guide_extracted=processed_guide,
            raw_content=ocr_data.get("content", ""),
            raw_tables=ocr_data.get("tables", []),
            token_usage=TokenUsage(**total_usage) if total_usage else TokenUsage(),
            work_order=work_order,
            other_data=other_data,
            beta_metadata={
                "parsed_content": tagged_text,
                "ref_map": ref_map,
                "pipeline_mode": "designer-engineer",
                "partial": engineer_output.get("_partial", False),
                "chunk_stats": engineer_output.get("_chunk_stats"),
                "judge_result": judge_result,
                "survey_result": {
                    "python_facts": survey_result.get("python_facts", {}) if survey_result else {},
                    "ai_interpretation": survey_result.get("ai_interpretation", {}) if survey_result else {},
                    "all_entities": survey_result.get("all_entities", []) if survey_result else [],
                    "elapsed_seconds": survey_result.get("_elapsed_seconds") if survey_result else None,
                } if survey_result else None,
            },
            model_name=model.name,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds()
        )
        
        return final_result

    # ==================================================================
    # Phase ①: Designer LLM (Work Order Generation — Cached)
    # ==================================================================

    async def _run_designer(self, model: ExtractionModel) -> dict:
        """
        Generate a work order from the model schema.
        Uses module-level cache keyed by hash(model.id + fields + rules + ref_data).
        Includes validation: if Designer output is malformed, builds fallback from schema.
        """
        global _work_order_cache
        
        cache_key = self._compute_cache_key(model)
        
        if cache_key in _work_order_cache:
            logger.info(f"[BetaPipeline] Designer: Cache HIT for model '{model.name}'")
            return copy.deepcopy(_work_order_cache[cache_key])
        
        logger.info(f"[BetaPipeline] Designer: Cache MISS — generating work order for '{model.name}'")
        
        system_prompt = RefinerEngine.construct_designer_prompt(model)
        user_prompt = "Generate the work order JSON. Output ONLY valid JSON, nothing else."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages)
        
        # Normalize: ensure { work_order: { ... } } structure
        if "work_order" in raw_result and isinstance(raw_result["work_order"], dict):
            work_order = raw_result
        elif isinstance(raw_result, dict) and "error" not in raw_result:
            work_order = {"work_order": raw_result}
        else:
            logger.warning(f"[BetaPipeline] Designer LLM returned error/empty, using fallback")
            work_order = self._build_fallback_work_order(model)
        
        # Validate: work_order must have common_fields or table_fields
        wo_inner = work_order.get("work_order", {})
        has_fields = wo_inner.get("common_fields") or wo_inner.get("table_fields")
        if not has_fields:
            logger.warning(f"[BetaPipeline] Designer output missing field definitions, using fallback")
            work_order = self._build_fallback_work_order(model)
        
        # Strip internal metadata before caching (prevents _token_usage leaking into Engineer prompt)
        work_order.pop("_token_usage", None)
        
        _work_order_cache[cache_key] = work_order
        logger.info(f"[BetaPipeline] Designer: Work order cached (key={cache_key[:16]}...)")
        
        return work_order

    # ==================================================================
    # Phase ③-b: Document Survey (Task List + Location Search)
    # ==================================================================

    @staticmethod
    def _build_task_list(model: ExtractionModel) -> list:
        """
        Step ①: Build a deterministic task list from the model schema.
        No LLM call — pure Python transformation.
        """
        tasks = []
        for f in model.fields:
            task = {
                "task_id": f"T_{f.key}",
                "field_key": f.key,
                "label": f.label,
                "type": "table_field" if f.type in ("table", "list") else "common_field",
                "description": f.description or f.label,
                "rules": f.rules or "",
            }
            if f.type in ("table", "list") and f.sub_fields:
                task["sub_field_keys"] = [
                    sf.get("key", sf.get("label", "")) for sf in f.sub_fields
                ]
            tasks.append(task)
        return tasks

    async def _search_locations(
        self, task_list: list, tagged_text: str, model: ExtractionModel
    ) -> dict:
        """
        Step ②: Hybrid Document Survey.
        - Python: deterministic facts (row counts, entities, table boundaries)
        - AI: semantic interpretation (header vs data, split/merge, field mapping)
        """
        import re
        import time as _time
        _t = _time.monotonic()

        if not tagged_text or len(tagged_text) < 50:
            logger.warning("[BetaPipeline] Survey: tagged_text too short, skipping")
            return {}

        # ─── Phase A: Python Deterministic Analysis ───────────────
        lines = tagged_text.split("\n")

        # A1. Extract all table rows (pipe-delimited)
        table_rows = []
        header_text_parts = []
        header_len = 0
        for line in lines:
            stripped = line.strip()
            is_table = stripped.startswith("|") and stripped.count("|") >= 3
            if is_table and "---" not in stripped:
                cells = [re.sub(r'\^[A-Z0-9]+', '', c).strip() for c in stripped.split("|")[1:-1]]
                table_rows.append(cells)
            elif not is_table and header_len < 1500:
                header_text_parts.append(stripped)
                header_len += len(stripped)

        # A2. Detect table boundaries (column count changes)
        tables_raw = []
        current_table = []
        prev_ncols = 0
        for row in table_rows:
            ncols = len(row)
            if ncols != prev_ncols and current_table:
                tables_raw.append(current_table)
                current_table = []
            current_table.append(row)
            prev_ncols = ncols
        if current_table:
            tables_raw.append(current_table)

        # A3. Extract entities from each table
        tables_info = []
        all_entities = set()
        for ti, table in enumerate(tables_raw):
            header = table[0] if table else []
            data_rows = table[1:] if len(table) > 1 else table
            entities = set()
            for row in data_rows:
                for cell in row[:5]:  # first 5 columns
                    cleaned = cell.strip()
                    if not cleaned:
                        continue
                    # Skip pure numbers, dates, currency patterns
                    if re.match(r'^[\d,.\-/~\s]+$', cleaned):
                        continue
                    if len(cleaned) <= 1:
                        continue
                    entities.add(cleaned)
            all_entities.update(entities)
            tables_info.append({
                "table_index": ti,
                "headers": header[:8],
                "total_rows": len(table),
                "data_rows": len(data_rows),
                "entities": sorted(entities)[:30],
                "entity_count": len(entities),
            })

        python_facts = {
            "total_table_rows": len(table_rows),
            "num_tables": len(tables_raw),
            "tables": tables_info,
            "total_unique_entities": len(all_entities),
            "header_text": "\n".join(header_text_parts[:15]),
        }

        logger.info(
            f"[BetaPipeline] Survey Python: {len(table_rows)} rows, "
            f"{len(tables_raw)} tables, {len(all_entities)} entities"
        )

        # ─── Phase B: AI Semantic Interpretation ──────────────────
        # Build compact fact sheet for AI
        fact_sheet = f"""PYTHON ANALYSIS RESULTS:
- Document has {len(table_rows)} table rows across {len(tables_raw)} table(s)
- {len(all_entities)} unique non-numeric entities found

DOCUMENT HEADER (non-table text):
{python_facts['header_text'][:800]}
"""
        for ti in tables_info:
            all_ents = ", ".join(ti["entities"])
            fact_sheet += f"\nTable {ti['table_index']+1}: {ti['data_rows']} data rows\n  Headers: {ti['headers'][:8]}\n  ALL entities: [{all_ents}]\n"

        # Task summary
        table_tasks = [t for t in task_list if t["type"] == "table_field"]
        common_tasks = [t for t in task_list if t["type"] == "common_field"]

        task_summary = "FIELDS TO EXTRACT:\n"
        for t in common_tasks:
            task_summary += f"  - {t['field_key']} ({t['label']}): single value\n"
        for t in table_tasks:
            sub = ", ".join(t.get("sub_field_keys", [])[:6])
            task_summary += f"  - {t['field_key']} ({t['label']}): TABLE [{sub}]\n"

        # Build field key mapping for table tasks
        table_field_keys = [t['field_key'] for t in table_tasks]
        common_field_keys = [t['field_key'] for t in common_tasks]

        system_prompt = f"""You are a document structure interpreter. Python already extracted these facts from the document.
Your job is to ADD MEANING — classify rows, find field values, estimate output counts.

{fact_sheet}
{task_summary}

RETURN JSON with EXACTLY these keys:
{{
  "field_mapping": {{
    // Use EXACTLY these field keys: {common_field_keys}
    // For each, find its value in the DOCUMENT HEADER text above
    "<field_key>": {{
      "found": true/false,
      "value_hint": "the actual value found in the document",
      "source": "header|table_column|footer|email_body"
    }}
  }},
  "table_analysis": {{
    // Use EXACTLY these field keys: {table_field_keys}
    // Map ALL Python tables to these extraction field(s)
    "<table_field_key>": {{
      "header_rows_to_skip": ["entity names that are GROUP HEADERS like 'OCEANIA', not actual data"],
      "rows_needing_split": ["entity names that have MULTIPLE date ranges and become multiple output rows"],
      "rows_to_exclude": ["entity names where rate values are '-' or empty"],
      "estimated_output_rows": <Python data_rows - skips - excludes + splits>,
      "all_destination_names": ["ALL port/city names that should appear as POD in the output"],
      "missing_risk_note": "structural observations about potential data loss"
    }}
  }},
  "document_type": "1-line description"
}}

RULES:
- Use Python's row counts as ground truth — do NOT re-count rows.
- For field_mapping: look at the DOCUMENT HEADER text to find single-value fields.
- For table_analysis: classify which entities are destinations vs headers vs excluded.
- all_destination_names must list EVERY actual port/city, not numbers or headers.
- Return ONLY valid JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Interpret the document structure now."},
        ]

        ai_result = await self.call_llm(messages, temperature=0.0)

        # Unwrap
        if "guide_extracted" in ai_result and "field_mapping" not in ai_result:
            ai_result = ai_result["guide_extracted"]

        elapsed = _time.monotonic() - _t
        logger.info(
            f"[BetaPipeline] Survey complete: {elapsed:.1f}s "
            f"(python={len(table_rows)} rows, ai={ai_result.get('document_type', '?')[:50]})"
        )

        return {
            "python_facts": python_facts,
            "ai_interpretation": ai_result,
            "all_entities": sorted(all_entities),
            "_elapsed_seconds": round(elapsed, 2),
        }

    # ==================================================================
    # Phase ④: Judge LLM (Self-Audit)
    # ==================================================================

    async def _run_judge(self, guide: dict, tagged_text: str, model: ExtractionModel) -> dict:
        """
        Post-extraction verification:
        1. Value accuracy — hallucination, scope errors, mismatches
        2. Completeness — missing table rows (INCOMPLETE detection)
        Returns {"issues": [...], "verdict": "pass"|"flagged"}.
        """
        import time as _time
        _t = _time.monotonic()

        # 1. Sample extraction results (avoid token explosion on large tables)
        sampled_guide = self._sample_for_judge(guide)
        guide_json = json.dumps(sampled_guide, ensure_ascii=False, indent=None)
        if len(guide_json) > 4000:
            guide_json = guide_json[:4000] + "...(truncated)"

        # 2. Build richer document context: head + mid + tail
        doc_len = len(tagged_text)
        doc_head = tagged_text[:2000] if doc_len > 0 else "(empty)"
        doc_mid = ""
        doc_tail = ""
        if doc_len > 5000:
            mid_start = doc_len // 2 - 500
            doc_mid = tagged_text[mid_start:mid_start + 1000]
        if doc_len > 2500:
            doc_tail = tagged_text[-1200:]

        # 3. Count table rows in document vs extraction for completeness check
        table_row_counts = {}
        for key, val in guide.items():
            if key.startswith("_"):
                continue
            actual_val = val
            if isinstance(val, dict) and "value" in val and isinstance(val["value"], list):
                actual_val = val["value"]
            if isinstance(actual_val, list):
                table_row_counts[key] = len(actual_val)

        # Count markdown table rows in source document
        doc_table_row_count = 0
        if tagged_text:
            doc_table_row_count = sum(
                1 for line in tagged_text.split("\n")
                if line.strip().startswith("|") and "---" not in line
                and line.strip().count("|") >= 3
            )

        completeness_context = ""
        if table_row_counts:
            completeness_context = "\n\nTABLE ROW COUNTS:\n"
            for tkey, tcount in table_row_counts.items():
                completeness_context += f"  - Extracted '{tkey}': {tcount} rows\n"
            if doc_table_row_count > 0:
                completeness_context += f"  - Source document markdown table rows: ~{doc_table_row_count}\n"
            completeness_context += (
                "  IMPORTANT: If the document appears to have significantly MORE data rows "
                "than what was extracted, flag as INCOMPLETE.\n"
            )

        # 4. Build Judge prompt
        field_list = ", ".join(
            f"{f.key}({f.label})" for f in model.fields
        )

        system_prompt = f"""You are an extraction QA auditor for a document data extraction system.
Your job is to verify BOTH the accuracy AND completeness of extracted data.

EXPECTED FIELDS: {field_list}

CHECK 1 — VALUE ACCURACY (per field):
1. HALLUCINATION — Value was invented (not found anywhere in the document)
2. SCOPE_ERROR — Value is from the wrong section/table
3. VALUE_MISMATCH — Value partially matches but has errors (wrong number, truncated)

CHECK 2 — COMPLETENESS (for table/list fields):
4. INCOMPLETE — The document contains MORE rows than were extracted.
   Look for port names, city names, item names in the source document that do NOT appear
   in the extraction result. If you find missing entries, report them.
   For INCOMPLETE issues, set "field" to the table field key, and in "suggestion"
   list the missing items you can see in the document.
{completeness_context}

RETURN JSON:
{{
  "issues": [
    {{"field": "field_key", "type": "HALLUCINATION|SCOPE_ERROR|VALUE_MISMATCH|INCOMPLETE", "reason": "brief explanation", "suggestion": "correct value, or comma-separated list of missing items"}}
  ],
  "verdict": "pass" or "flagged"
}}

RULES:
- Be CONSERVATIVE for value checks — only flag clear errors.
- Be AGGRESSIVE for completeness — if you see port/city names in the document that aren't extracted, flag INCOMPLETE.
- Minor formatting differences (e.g., "MSC" vs "M.S.C.") are OK for values.
- Return ONLY valid JSON."""

        user_prompt = f"""EXTRACTION RESULT:
{guide_json}

SOURCE DOCUMENT (head):
{doc_head}

SOURCE DOCUMENT (middle):
{doc_mid}

SOURCE DOCUMENT (tail):
{doc_tail}

Verify accuracy AND completeness now."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        result = await self.call_llm(messages, temperature=0.0)

        # Unwrap: call_llm auto-wraps flat dicts into {guide_extracted: {...}}
        if "guide_extracted" in result and "issues" not in result:
            result = result["guide_extracted"]

        # Parse and validate
        issues = result.get("issues", [])
        verdict = result.get("verdict", "unknown")

        # Accumulate Judge token usage into pipeline total
        judge_usage = result.get("_token_usage", {})

        elapsed = _time.monotonic() - _t
        logger.info(
            f"[BetaPipeline] Judge complete: verdict={verdict}, "
            f"issues={len(issues)}, elapsed={elapsed:.1f}s, "
            f"tokens={judge_usage.get('total_tokens', 0)}"
        )

        return {
            "issues": issues,
            "verdict": verdict,
            "_token_usage": judge_usage,
            "_elapsed_seconds": round(elapsed, 2),
            "_doc_table_rows": doc_table_row_count,
            "_extracted_table_rows": table_row_counts,
        }

    @staticmethod
    def _sample_for_judge(guide: dict, max_rows: int = 8) -> dict:
        """
        Sample extraction results for Judge input:
        - Common fields: keep as-is
        - Table fields: first 3 + last 2 + up to 3 random middle rows
        This prevents token explosion while giving the Judge enough signal.
        """
        import random
        sampled = {}
        for key, val in guide.items():
            if key.startswith("_"):
                continue
            if isinstance(val, list) and len(val) > max_rows:
                # Sample: first 3 + last 2 + random middle
                head = val[:3]
                tail = val[-2:]
                middle_pool = val[3:-2]
                mid_sample = random.sample(middle_pool, min(3, len(middle_pool)))
                sampled[key] = head + mid_sample + tail
                sampled[f"_{key}_total_rows"] = len(val)
            else:
                sampled[key] = val
        return sampled

    async def _retry_flagged_fields(
        self, issues: list, work_order: dict, tagged_text: str, model: ExtractionModel
    ) -> dict:
        """
        Phase ④-b: Re-extract fields flagged by Judge.
        Uses a stricter prompt: 'if not found, return null — do NOT guess.'
        Groups all flagged fields into a single LLM call to minimize cost.
        """
        import time as _time
        _t = _time.monotonic()

        flagged_keys = {i.get("field", "") for i in issues if i.get("field")}
        if not flagged_keys:
            return {}

        # Build focused field descriptions from model schema
        field_desc_parts = []
        for f in model.fields:
            if f.key in flagged_keys:
                issue = next((i for i in issues if i.get("field") == f.key), {})
                field_desc_parts.append(
                    f"- {f.key} ({f.label}): type={f.type}"
                    f"  PREVIOUS ERROR: {issue.get('type', '?')} — {issue.get('reason', '?')}"
                    f"  SUGGESTION: {issue.get('suggestion', 'Re-read document carefully')}"
                )

        if not field_desc_parts:
            return {}

        field_descriptions = "\n".join(field_desc_parts)

        # Use more document context for retry (head + tail)
        doc_context = tagged_text[:3000]
        if len(tagged_text) > 4000:
            doc_context += "\n...\n" + tagged_text[-1500:]

        system_prompt = f"""You are a document data re-extractor. A previous extraction attempt had errors.
You must CAREFULLY re-read the document and extract ONLY these flagged fields:

{field_descriptions}

STRICT RULES:
1. If the value is NOT clearly present in the document, return null. Do NOT guess.
2. If the value exists but in a different section, extract the CORRECT one based on context.
3. Return ONLY the re-extracted fields as JSON: {{"field_key": {{"value": ..., "confidence": 0.0-1.0}}}}
4. Do NOT include fields that were not flagged.
5. Return ONLY valid JSON."""

        user_prompt = f"""DOCUMENT:\n{doc_context}\n\nRe-extract the flagged fields now."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = await self.call_llm(messages, temperature=0.0)

        # Unwrap auto-wrapping
        if "guide_extracted" in result and not any(k in result for k in flagged_keys):
            result = result["guide_extracted"]

        # Filter to only flagged keys
        retry_output = {}
        for k in flagged_keys:
            if k in result:
                node = result[k]
                if isinstance(node, dict):
                    node["_retry"] = True
                retry_output[k] = node

        elapsed = _time.monotonic() - _t
        logger.info(
            f"[BetaPipeline] Field retry: {len(retry_output)}/{len(flagged_keys)} fields "
            f"re-extracted in {elapsed:.1f}s"
        )

        return retry_output

    def _build_document_skeleton(self, tagged_text: str) -> str:
        """
        Creates a 'skeleton' of the document for the Mapping Designer.
        Includes: first 3000 chars, section headers, table headers, document tail.
        """
        import re
        lines = tagged_text.splitlines()
        
        # 1. Document head (first 3000 chars)
        head = tagged_text[:3000]
        
        # 2. Section headers (Validity, Subject, etc.)
        section_headers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Match numbered sections, validity lines, subject lines, date ranges
            if (re.match(r'^\d+\.', stripped) or 
                re.search(r'(?i)(validity|effective|subject|amendment|surcharge|service)', stripped)):
                clean = re.sub(REF_TAG_PATTERN + r'\s*', '', stripped).strip()
                if clean and len(clean) < 200:
                    section_headers.append(f"L{i}: {clean}")
        
        # 3. Table headers (robust markdown detection)
        table_headers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped.startswith("|") and "-" in next_stripped:
                    if re.match(r"^\|[\s\-\:\|]+\|$", next_stripped):
                        clean_header = re.sub(REF_TAG_PATTERN, '', stripped).strip()
                        table_headers.append(f"L{i}: {clean_header}")
        
        # 4. Document tail (last 4000 chars for notes/footer/surcharges), stripped of ref tags
        tail = ""
        if len(tagged_text) > 5000:
            raw_tail = tagged_text[-4000:]
            tail = re.sub(REF_TAG_PATTERN, '', raw_tail).strip()
        else:
            # For short documents, we just take the whole tail so we don't miss anything
            # although the head probably covered it anyway.
            tail = ""
        
        # Assemble skeleton
        parts = [head]
        if section_headers:
            parts.append("\n--- SECTION HEADERS ---")
            parts.append("\n".join(section_headers[:15]))
        if table_headers:
            parts.append("\n--- TABLE HEADERS ---")
            parts.append("\n".join(table_headers[:10]))
        if tail:
            parts.append("\n--- DOCUMENT TAIL ---")
            parts.append(tail)
        
        return "\n".join(parts)

    async def _run_analyst(self, model: ExtractionModel, skeleton_text: str) -> dict:
        """
        Phase 1.5: Identify dynamic hints from the document skeleton.
        """
        logger.info(f"[BetaPipeline] Analyst: Analyzing document skeleton ({len(skeleton_text)} chars)")
        
        system_prompt = RefinerEngine.construct_analyst_prompt(model)
        user_prompt = f"DOCUMENT SKELETON:\n{skeleton_text}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            result = await self.call_llm(messages, response_format={"type": "json_object"})
            return result
        except Exception as e:
            logger.warning(f"[BetaPipeline] Analyst LLM failed, continuing without hints. Error: {e}")
            return {}

    @staticmethod
    def _build_engineer_schema(model: ExtractionModel, work_order: dict = None, is_beta_mode: bool = True) -> dict:
        """Create a Strict Structured Outputs JSON Schema from the model."""
        properties = {}
        required_keys = []
        is_strict = True
        
        allowed_keys = set()
        if work_order:
            wo_inner = work_order.get("work_order", work_order)
            for cf in wo_inner.get("common_fields", []):
                allowed_keys.add(cf.get("key"))
            for tf in wo_inner.get("table_fields", []):
                allowed_keys.add(tf.get("key"))
        
        for f in model.fields:
            if work_order and f.key not in allowed_keys:
                continue
                
            # If a field is explicitly marked as required by the user, add it to required_keys
            # Otherwise, for strict JSON schema compatibility, ALL keys defined in properties MUST be in the required list
            # We enforce all keys to be required in the schema, but allow their type to be ["object", "null"] so they can return null if not found
            required_keys.append(f.key) 
            
            if f.type in ["table", "list", "array"]:
                # If sub_fields are defined, make it strict
                if f.sub_fields:
                    sub_props = {}
                    sub_req = []
                    for sf in f.sub_fields:
                        if isinstance(sf, str):
                            sf_key = sf
                            sf_type = "string"
                        else:
                            sf_key = sf.get("key", "") if isinstance(sf, dict) else getattr(sf, "key", "")
                            sf_type = sf.get("type", "string") if isinstance(sf, dict) else getattr(sf, "type", "string")
                            
                        if sf_key:
                            if sf_type == "number":
                                sf_schema_type = ["number", "null"]
                            elif sf_type == "boolean":
                                sf_schema_type = ["boolean", "null"]
                            else:
                                # Default to string+null for string and unknown types
                                sf_schema_type = ["string", "null"]

                            if is_beta_mode:
                                sub_props[sf_key] = {
                                    "type": ["object", "null"],
                                    "properties": {
                                        "value": {"type": sf_schema_type},
                                        "ref": {"type": ["string", "null"]}
                                    },
                                    "required": ["value", "ref"],
                                    "additionalProperties": False
                                }
                            else:
                                sub_props[sf_key] = {
                                    "type": ["object", "null"],
                                    "properties": {
                                        "value": {"type": sf_schema_type},
                                        "confidence": {"type": ["number", "null"]},
                                        "page_number": {"type": ["integer", "null"]},
                                        "source_text": {"type": ["string", "null"]}
                                    },
                                    "required": ["value", "confidence", "page_number", "source_text"],
                                    "additionalProperties": False
                                }
                            sub_req.append(sf_key)
                    
                    properties[f.key] = {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": sub_props,
                            "required": sub_req,
                            "additionalProperties": False
                        }
                    }
                else:
                    is_strict = False
                    # Fallback if no sub_fields defined
                    properties[f.key] = {
                        "type": ["array", "null"],
                        "items": {"type": "object"}
                    }
            else:
                if f.type == "number":
                    f_schema_type = ["number", "null"]
                elif f.type == "boolean":
                    f_schema_type = ["boolean", "null"]
                else:
                    # Default to string+null for string and unknown types
                    f_schema_type = ["string", "null"]

                if is_beta_mode:
                    properties[f.key] = {
                        "type": ["object", "null"],
                        "properties": {
                            "value": {"type": f_schema_type},
                            "ref": {"type": ["string", "null"]}
                        },
                        "required": ["value", "ref"],
                        "additionalProperties": False
                    }
                else:
                    properties[f.key] = {
                        "type": ["object", "null"],
                        "properties": {
                            "value": {"type": f_schema_type},
                            "confidence": {"type": ["number", "null"]},
                            "page_number": {"type": ["integer", "null"]},
                            "source_text": {"type": ["string", "null"]}
                        },
                        "required": ["value", "confidence", "page_number", "source_text"],
                        "additionalProperties": False
                    }
                
        if not is_strict:
            return {"type": "json_object"}

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "extraction_result",
                "strict": is_strict,
                "schema": {
                    "type": "object",
                    "properties": {
                        "guide_extracted": {
                            "type": "object",
                            "properties": properties,
                            "required": required_keys,
                            "additionalProperties": False
                        },
                        "error": {"type": ["string", "null"]}
                    },
                    "required": ["guide_extracted", "error"] if is_strict else ["guide_extracted"],
                    "additionalProperties": not is_strict
                }
            }
        }

    @staticmethod
    def _build_fallback_work_order(model: ExtractionModel) -> dict:
        """Build a minimal work order directly from model schema when Designer fails."""
        TABLE_FIELD_TYPES = ('list', 'table', 'array')
        
        common_fields = []
        table_fields = []
        
        for f in model.fields:
            entry = {
                "key": f.key,
                "instruction": f"Extract '{f.label}' from the document.",
                "expected_format": f.type,
                "rules": []
            }
            if f.description:
                entry["instruction"] += f" Description: {f.description}"
            if f.type in TABLE_FIELD_TYPES or bool(getattr(f, 'sub_fields', None)):
                entry["columns"] = {}
                sub_fields = getattr(f, 'sub_fields', None) or []
                for sf in sub_fields:
                    if isinstance(sf, str):
                        sf_key = sf
                        sf_label = sf
                        col_dict = {"instruction": f"Extract '{sf_label}'."}
                    else:
                        sf_key = sf.get("key") if isinstance(sf, dict) else getattr(sf, "key", None)
                        if not sf_key:
                            continue
                        sf_label = (sf.get("label", sf_key) if isinstance(sf, dict) else getattr(sf, "label", sf_key)) or sf_key
                        col_dict = {"instruction": f"Extract '{sf_label}'."}
                        
                        desc = sf.get("description") if isinstance(sf, dict) else getattr(sf, "description", None)
                        if desc:
                            col_dict["instruction"] += f" Description: {desc}"
                            
                        rules = sf.get("rules") if isinstance(sf, dict) else getattr(sf, "rules", None)
                        if rules:
                            col_dict["rules"] = [rules]
                            
                    entry["columns"][sf_key] = col_dict
                entry["rules"].append("Extract ALL rows.")
                table_fields.append(entry)
            else:
                common_fields.append(entry)
        
        return {
            "work_order": {
                "document_type": getattr(model, 'description', None) or model.name,
                "extraction_mode": "table" if table_fields else "data",
                "common_fields": common_fields,
                "table_fields": table_fields,
                "integrity_rules": [
                    "Copy values exactly as written, UNLESS explicitly instructed to calculate, transform, or translate by the field rule.",
                    "Missing values must be null.",
                    "Extract in original language. Do NOT translate unless field rule says so."
                ]
            }
        }

    @staticmethod
    def _compute_cache_key(model: ExtractionModel) -> str:
        """Compute deterministic cache key from model schema."""
        fields_json = json.dumps(
            [{"key": f.key, "label": f.label, "description": f.description, 
              "rules": f.rules, "type": f.type, "sub_fields": getattr(f, 'sub_fields', None)} for f in model.fields],
            sort_keys=True, ensure_ascii=False
        )
        global_rules = model.global_rules or ""
        ref_data = json.dumps(model.reference_data or {}, sort_keys=True, ensure_ascii=False)
        
        raw = f"{model.id}|{fields_json}|{global_rules}|{ref_data}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ==================================================================
    # Phase ②: Engineer LLM (Value Extraction)
    # ==================================================================

    @staticmethod
    def _estimate_table_row_counts(tagged_text: str) -> str:
        """
        Count markdown table data rows in tagged text to generate a row count hint.
        Returns a hint string like:
          "TABLE ROW COUNTS: This document contains approximately 45 data rows across 2 tables."
        Production-safe: purely informational, never modifies extraction logic.
        """
        import re
        lines = tagged_text.split("\n")
        total_data_rows = 0
        
        for line in lines:
            stripped = line.strip()
            # It must look like a markdown row: starts and ends with |
            if stripped.startswith("|") and stripped.endswith("|"):
                # Ignore separators
                if re.match(r"^\|[\s\-\:\.\*]+\|$", stripped.replace(" ", "").replace("-", "")):
                    continue
                if "---" in stripped:
                    continue
                    
                # A valid row should have some columns
                if stripped.count("|") > 2:
                    total_data_rows += 1
                    
        if total_data_rows == 0:
            return ""
        
        return (
            f"\n\nTABLE ROW COUNTS (CRITICAL — DO NOT STOP EARLY):\n"
            f"This document contains approximately {total_data_rows} data rows. "
            f"You MUST extract ALL {total_data_rows} rows. "
            f"Do NOT stop after a few rows. Completeness is mandatory.\n"
        )

    async def _run_engineer(self, work_order: dict, tagged_text: str, model: ExtractionModel = None) -> dict:
        """
        Single-shot Engineer extraction.
        Returns raw LLM output dict with guide_extracted + _token_usage.
        """
        ref_data = (model.reference_data if model else None) or None
        system_prompt = RefinerEngine.construct_engineer_prompt(work_order, reference_data=ref_data)
        row_count_hint = self._estimate_table_row_counts(tagged_text)
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{tagged_text}\n{row_count_hint}\nExtract all fields. Return valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response_format = self._build_engineer_schema(model, work_order=work_order, is_beta_mode=True) if model else {"type": "json_object"}
        temp = model.temperature if model else None
        
        raw_result = await self.call_llm(messages, is_table_model=True, temperature=temp, response_format=response_format)
        return raw_result

    async def _run_engineer_chunked(self, work_order: dict, tagged_text: str, chunk_size: int, model: ExtractionModel = None) -> dict:
        """
        Chunked Engineer extraction with header preservation.
        Splits tagged text, injects table headers per chunk, merges results.
        """
        chunks = self._chunk_with_headers(tagged_text, chunk_size)
        logger.info(f"[BetaPipeline] Engineer Chunked: Created {len(chunks)} chunks")
        
        if not chunks:
            return {"guide_extracted": {}}
        
        ref_data = (model.reference_data if model else None) or None
        system_prompt = RefinerEngine.construct_engineer_prompt(work_order, reference_data=ref_data)
        
        # Build context preamble for subsequent chunks:
        # 1) First ~500 chars of the document (titles, headers, section context)
        # 2) Expected field keys from work order
        wo_inner = work_order.get("work_order", work_order)
        field_keys = []
        for cf in wo_inner.get("common_fields", []):
            field_keys.append(cf.get("key", ""))
        for tf in wo_inner.get("table_fields", []):
            field_keys.append(tf.get("key", ""))
        field_keys = [k for k in field_keys if k]
        
        # Build doc_context from the head of the document, but EXCLUDE table data rows
        # to prevent LLM from copying page-1 values into all subsequent chunks.
        # Only keep non-table text (company name, dates, invoice headers, etc.)
        doc_context_lines = []
        doc_context_len = 0
        for line in tagged_text.splitlines():
            stripped = line.strip()
            # Skip table rows (data lines starting with |)
            if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") > 2:
                continue
            # Skip table separator rows
            if stripped.startswith("|") and "---" in stripped:
                continue
            if doc_context_len + len(line) > 800:
                break
            doc_context_lines.append(line)
            doc_context_len += len(line) + 1
        doc_context = "\n".join(doc_context_lines).rstrip()
        
        # Extract section headers (e.g., "1. Validity: 12/1 ~ 12/7") for context preservation
        import re
        section_headers = []
        for line in tagged_text.splitlines():
            stripped = line.strip()
            # Match numbered sections, validity lines, or standalone date-like headers
            if re.match(r'^\d+\.', stripped) or any(k in stripped.lower() for k in ['validity', 'date', 'period', 'duration', 'route', 'port', 'service']):
                # Remove tag markers for cleaner context
                clean = re.sub(REF_TAG_PATTERN + r'\s*', '', stripped).strip()
                if clean and len(clean) < 200:
                    section_headers.append(clean)
        
        section_header_str = ""
        if section_headers:
            section_header_str = (
                "--- SECTION HEADERS (USE FOR DATE CONTEXT) ---\n"
                + "\n".join(section_headers[:10])
                + "\n--- END SECTION HEADERS ---\n\n"
                "CRITICAL: Match each table's rows to the nearest preceding section header for date/validity context.\n\n"
            )
            
        # Extract Global Surcharge Rules (Analyzed by Refiner)
        global_rules = wo_inner.get("global_surcharge_rules", [])
        global_rules_str = ""
        if global_rules:
            global_rules_str = (
                "--- 🚨 GLOBAL SURCHARGE RULES (APPLY TO EVERY ROW) ---\n"
                + "\n".join(f"- {rule}" for rule in global_rules) + "\n\n"
            )
        
        context_preamble = (
            f"{global_rules_str}"
            f"--- START PAST CONTEXT (FOR QUICK REFERENCE ONLY) ---\n"
            f"{doc_context}\n...\n"
            f"--- END PAST CONTEXT ---\n\n"
            f"{section_header_str}"
            f"CRITICAL WARNING: NEVER extract your primary list items or table rows from the PAST CONTEXT.\n"
            f"You MUST extract data rows ONLY from the ACTUAL CHUNK DATA below.\n"
            f"HOWEVER, if a field requires INHERITANCE (e.g., Start_Date, End_Date, Route, Currency from a Section Header), you MUST look at the PAST CONTEXT or SECTION HEADERS to find the inherited values that apply to the current chunk's rows.\n\n"
            f"EXPECTED FIELD KEYS: {', '.join(field_keys)}\n\n"
        )
        
        async def process_chunk(chunk_text: str, chunk_idx: int) -> dict:
            # First chunk has full context; subsequent chunks get preamble
            if chunk_idx > 0:
                prefix = context_preamble
            else:
                prefix = ""
            
            row_count_hint = self._estimate_table_row_counts(chunk_text)
            user_prompt = (
                f"{prefix}"
                f"--- START ACTUAL CHUNK DATA (Chunk {chunk_idx + 1}/{len(chunks)}) ---\n"
                f"{chunk_text}\n"
                f"--- END ACTUAL CHUNK DATA ---\n"
                f"{row_count_hint}\n"
                f"CRITICAL EXTRACTION RULES:\n"
                f"1. Read EACH ROW's actual cell values individually from the CHUNK DATA above.\n"
                f"2. DO NOT copy/repeat values from the first row or any other row.\n"
                f"3. Every row has DIFFERENT values for description, item_no, qty, unit_price, amount, etc.\n"
                f"4. If two rows appear identical, re-read the source text carefully — they are different.\n"
                f"Extract all fields from the ACTUAL CHUNK DATA only. Return valid JSON with guide_extracted wrapper."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            async with _AdaptiveContext(self.semaphore) as sem_ctx:
                try:
                    response_format = self._build_engineer_schema(model, work_order=work_order, is_beta_mode=True) if model else {"type": "json_object"}
                    temp = model.temperature if model else None
                    try:
                        result = await self.call_llm(messages, is_table_model=True, temperature=temp, response_format=response_format)
                    except Exception as llm_err:
                        error_str = str(llm_err).lower()
                        # Fallback to json_object if strict structured outputs are not supported by this model deployment
                        if "json_schema" in error_str or "response_format" in error_str or "unsupported" in error_str or "400" in error_str:
                            logger.warning(f"[BetaPipeline] Strict JSON Schema failed for Chunk {chunk_idx}, falling back to json_object. Error: {llm_err}")
                            result = await self.call_llm(messages, is_table_model=True, temperature=temp, response_format={"type": "json_object"})
                        else:
                            if "429" in error_str:
                                sem_ctx.is_429 = True
                            raise llm_err

                    if result.get("_had_429"):
                        sem_ctx.is_429 = True
                        
                    # Validate result structure
                    if not isinstance(result, dict):
                        logger.error(f"[BetaPipeline] Chunk {chunk_idx}: call_llm returned {type(result).__name__}, expected dict")
                        return {"guide_extracted": {}, "error": f"Unexpected LLM result type: {type(result).__name__}"}
                        
                    # Apply normalization to unwrap mistaken {value: [...]} and clean up
                    # We pass empty dicts for ocr_data and ref_map since this is just for structural cleanup
                    normalized_res = self._normalize_output(result, {}, {}, chunk_text)
                    
                    # _normalize_output returns an ExtractionResult object, we need to return a dict for _run_engineer_chunked
                    return {
                        "guide_extracted": normalized_res.guide_extracted,
                        "_token_usage": result.get("_token_usage", {}), # Preserve from raw result
                        "_had_429": result.get("_had_429")
                    }
                except Exception as e:
                    import traceback
                    logger.error(f"[BetaPipeline] Engineer Chunk {chunk_idx} CRASHED: {e}\n{traceback.format_exc()}")
                    return {"guide_extracted": {}, "error": str(e)}
        
        # Parallel execution
        tasks = [process_chunk(chunk, idx) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Instead of simple Python dict merge, format valid chunks for the Phase 3 Aggregator LLM
        valid_chunks: Dict[str, dict] = {}
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        any_truncated = False
        failed_chunks = []
        
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Chunk {idx} gather exception: {res}")
                failed_chunks.append(idx)
                continue
            
            if res.get("error"):
                logger.warning(f"[BetaPipeline] Chunk {idx} returned error: {res['error']}")
                failed_chunks.append(idx)
            
            if res.get("_truncated"):
                any_truncated = True
                
            # Accumulate token usage
            usage = res.get("_token_usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
            
            # Save valid extraction for Aggregator
            extracted_data = res.get("guide_extracted")
            if extracted_data and isinstance(extracted_data, dict):
                valid_chunks[f"chunk_{idx}"] = extracted_data

        if failed_chunks:
            logger.warning(f"[BetaPipeline] {len(failed_chunks)}/{len(results)} chunks FAILED: indices {failed_chunks}")
        
        # Build chunk health metadata for downstream visibility
        chunk_stats = {
            "total": len(results),
            "failed": len(failed_chunks),
            "succeeded": len(results) - len(failed_chunks),
        }
        is_partial = len(failed_chunks) > 0
        
        if not valid_chunks:
            logger.warning(f"[BetaPipeline] All {len(results)} chunks returned empty results. No data extracted.")
            return {"guide_extracted": {}, "_token_usage": total_usage, "_truncated": any_truncated, "_partial": True, "_chunk_stats": chunk_stats}

        # Always run the Aggregator to safely merge list fields via append.
        logger.info(f"[BetaPipeline] Aggregating {len(valid_chunks)} valid chunks (out of {len(results)} total).")

        agg_result = await self._run_aggregator(work_order, valid_chunks)
        
        # Accumulate Aggregator token usage
        agg_usage = agg_result.get("_token_usage", {})
        for k in total_usage:
            total_usage[k] += agg_usage.get(k, 0)

        return {
            "guide_extracted": agg_result.get("guide_extracted", {}),
            "_token_usage": total_usage,
            "_truncated": any_truncated,
            "_partial": is_partial,
            "_chunk_stats": chunk_stats,
            "logs": agg_result.get("logs", [])
        }

    async def _run_aggregator(self, work_order: dict, chunks_payload: Dict[str, dict]) -> dict:
        """
        Phase ③: Aggregator.
        Takes multiple chunked Engineer outputs and merges them using Python, keeping refs intact.
        Bypasses LLM aggregation completely to prevent massive table truncation due to completion token limits.
        """
        logger.info(f"[BetaPipeline] Aggregator: Deterministically merging {len(chunks_payload)} chunks in Python.")
        return self._run_aggregator_python_fallback(chunks_payload)

    def _run_aggregator_python_fallback(self, chunks_payload: Dict[str, dict]) -> dict:
        """
        Deterministic merge: append rows in chunk order, dedup, tag source.
        """
        merged_guide = {}
        seen_rows = {}  # field_key -> Set[row_hash]
        
        for chunk_id, guide_extracted in chunks_payload.items():
            # Extract chunk index from chunk_id (e.g. "chunk_2" -> 2)
            chunk_idx = int(chunk_id.split("_")[1]) if "_" in chunk_id else 0
            
            for key, val in guide_extracted.items():
                if isinstance(val, list):
                    # Table field — append rows with dedup, tag source chunk
                    if key not in merged_guide:
                        merged_guide[key] = []
                        seen_rows[key] = set()
                    
                    for row in val:
                        if not isinstance(row, dict):
                            continue
                        # Create hash WITHOUT _source_chunk for dedup
                        row_clean = {k: v for k, v in row.items() if not k.startswith("_source")}
                        row_hash = json.dumps(row_clean, sort_keys=True, ensure_ascii=False)
                        if row_hash not in seen_rows[key]:
                            seen_rows[key].add(row_hash)
                            row_copy = {**row, "_source_chunk": chunk_idx}
                            merged_guide[key].append(row_copy)
                else:
                    # Common field — first-non-null: keep first real value
                    if key not in merged_guide:
                        merged_guide[key] = val
                    elif isinstance(val, dict) and val.get("value") is not None:
                        existing = merged_guide[key]
                        if isinstance(existing, dict) and existing.get("value") is None:
                            merged_guide[key] = val
        
        total_rows = sum(len(v) for v in merged_guide.values() if isinstance(v, list))
        logger.info(f"[Aggregator] Merged {len(chunks_payload)} chunks → {len(merged_guide)} fields, {total_rows} total rows")
                            
        return {
            "guide_extracted": merged_guide,
            "_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "logs": [{"step": "Aggregator", "message": f"Python merge: {len(chunks_payload)} chunks, {total_rows} rows"}]
        }

    async def _run_engineer_per_table(self, work_order: dict, tagged_text: str, chunk_size: int, model: ExtractionModel = None) -> dict:
        """
        [Per-Table Schema Split]
        Splits the schema (work_order) so each table is extracted INDEPENDENTLY,
        preventing completion token exhaustion when multiple tables exist.
        Now used proactively when 2+ table fields exist (not just as fallback).
        """
        # Unwrap the work_order wrapper to access actual fields
        wo_inner = work_order.get("work_order", work_order)
        table_fields = wo_inner.get("table_fields", [])
        common_fields = wo_inner.get("common_fields", [])
        
        logger.info(f"[BetaPipeline] Per-Table Schema Split: {len(table_fields)} tables, {len(common_fields)} common fields.")
        
        if not table_fields:
            # If there are no tables but it still truncated, just return what we have (rare).
            return await self._run_engineer_chunked(work_order, tagged_text, chunk_size, model)
            
        merged_guide = {}
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        any_truncated = False
        any_partial = False
        total_chunks = 0
        failed_chunks = 0
        all_logs = []
        
        # We need to extract common fields once, and tables separately.
        # Create sub-work orders (properly wrapped in {"work_order": {...}} structure)
        sub_orders = []
        
        # 1. Common Fields Only (if any exist)
        if common_fields:
            sub_orders.append({"work_order": {
                **wo_inner,
                "table_fields": [],  # Exclude tables
                "extraction_mode": "data"
            }})
            
        # 2. Each Table Separately — with sibling table disambiguation context
        for t_field in table_fields:
            # Build sibling context: tell the LLM what OTHER tables exist
            # so it can distinguish which physical table in the document to extract
            sibling_descriptions = []
            for other_tf in table_fields:
                if other_tf.get("key") == t_field.get("key"):
                    continue
                other_key = other_tf.get("key", "unknown")
                other_instr = other_tf.get("instruction", "")
                other_cols = list(other_tf.get("columns", {}).keys())[:5]
                cols_str = ", ".join(other_cols) if other_cols else "N/A"
                sibling_descriptions.append(
                    f"  - {other_key}: {other_instr[:120]} (columns: {cols_str})"
                )
            
            # Inject disambiguation into integrity_rules
            sub_wo_inner = {
                **wo_inner,
                "common_fields": [],  # Exclude common
                "table_fields": [t_field],  # ONLY this table
                "extraction_mode": "table"
            }
            
            if sibling_descriptions:
                current_target_key = t_field.get("key", "unknown")
                current_target_instr = t_field.get("instruction", "")
                disambiguation_rule = (
                    f"MULTI-TABLE DISAMBIGUATION (CRITICAL): This document contains "
                    f"{len(table_fields)} different table types. You are extracting ONLY "
                    f"'{current_target_key}'. "
                    f"DO NOT extract rows that belong to these OTHER tables:\n"
                    + "\n".join(sibling_descriptions)
                    + f"\nONLY extract rows matching '{current_target_key}': {current_target_instr[:200]}"
                )
                existing_rules = list(sub_wo_inner.get("integrity_rules", []))
                existing_rules.insert(0, disambiguation_rule)
                sub_wo_inner["integrity_rules"] = existing_rules
                
                # Also inject as a dynamic hint for maximum visibility
                existing_hints = list(sub_wo_inner.get("dynamic_hints", []))
                existing_hints.insert(0, (
                    f"This document has {len(table_fields)} separate table sections. "
                    f"Each section has different data. You MUST find the section for "
                    f"'{current_target_key}' specifically. If no matching section exists, return an empty array."
                ))
                sub_wo_inner["dynamic_hints"] = existing_hints
            
            sub_orders.append({"work_order": sub_wo_inner})
            
        # Process each sub-order via gather for maximum parallelism
        async def process_sub_order(sub_wo):
            sub_inner = sub_wo.get("work_order", sub_wo)
            mode = sub_inner.get("extraction_mode", "unknown")
            table_key = sub_inner.get("table_fields", [{}])[0].get("key", "common") if sub_inner.get("table_fields") else "common"
            logger.info(f"[BetaPipeline] Schema Split: Extracting {mode} → {table_key}")
            return await self._run_engineer_chunked(sub_wo, tagged_text, chunk_size, model)
            
        tasks = [process_sub_order(wo) for wo in sub_orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Schema Split gather exception: {res}")
                continue
            
            if res.get("_truncated"):
                # If even a single table extraction truncates, we flag it (though we can't split further)
                any_truncated = True
            
            # Aggregate partial/chunk stats from sub-results
            if res.get("_partial"):
                any_partial = True
            sub_stats = res.get("_chunk_stats", {})
            total_chunks += sub_stats.get("total", 0)
            failed_chunks += sub_stats.get("failed", 0)
                
            # Accumulate token usage
            usage = res.get("_token_usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
                
            # Accumulate logs from chunked Engineer/Aggregator
            if "logs" in res:
                all_logs.extend(res["logs"])
                
            # Merge extracted data
            for key, val in res.get("guide_extracted", {}).items():
                 if isinstance(val, list):
                     if key not in merged_guide or not isinstance(merged_guide[key], list):
                         merged_guide[key] = []
                     merged_guide[key].extend(val)
                 elif val is not None:
                     # Common field — keep first non-null value
                     if key not in merged_guide or merged_guide.get(key) is None:
                         merged_guide[key] = val
        
        result = {
            "guide_extracted": merged_guide,
            "_token_usage": total_usage,
            "_truncated": any_truncated,
            "logs": all_logs
        }
        # Propagate aggregated partial/chunk stats
        if any_partial or failed_chunks > 0:
            result["_partial"] = True
            result["_chunk_stats"] = {"total": total_chunks, "failed": failed_chunks}
            logger.warning(f"[BetaPipeline] Per-Table Split: partial results — {failed_chunks}/{total_chunks} chunks failed across {len(sub_orders)} sub-orders")
        
        return result

    @staticmethod
    def _chunk_with_headers(tagged_text: str, chunk_size: int) -> List[str]:
        """
        Split tagged text into chunks with markdown table header preservation.
        When a chunk boundary falls inside a table, the header row + separator
        are injected at the start of each new chunk.
        ALSO: Injects the text paragraph immediately preceding the table to preserve context (e.g., Date, Category).
        """
        import re
        lines = tagged_text.split("\n")
        
        # Detect markdown table headers: | ... | followed by |---|
        table_headers: Dict[int, tuple] = {}  # line_idx -> (header_row, separator_row)
        table_contexts: Dict[int, str] = {}   # line_idx -> context_string
        
        current_context_buffer = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped.startswith("|") and "-" in next_stripped:
                    # Check if next_stripped is mostly a markdown divider e.g. |---|:---|
                    if re.match(r"^\|[\s\-\:\|]+\|$", next_stripped):
                        table_headers[i] = (line, lines[i + 1])
                        # Preserve last 3 non-empty lines before table as context
                        context_str = "\n".join([c for c in current_context_buffer if c.strip()][-3:])
                        table_contexts[i] = context_str
            
            if stripped and not stripped.startswith("|"):
                current_context_buffer.append(line)
            elif not stripped:
                current_context_buffer.append(line)
            # If inside a table (starts with |), we don't clear the context buffer.
            # We let it persist so if there are multiple tight tables, they might share context.
        
        chunks = []
        current_chunk: List[str] = []
        current_len = 0
        active_header: Optional[tuple] = None
        active_context: str = ""
        consecutive_non_table_lines = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Track table context
            if i in table_headers:
                active_header = table_headers[i]
                active_context = table_contexts.get(i, "")
                consecutive_non_table_lines = 0
            elif stripped.startswith("|"):
                consecutive_non_table_lines = 0
            elif stripped != "":
                # It's a non-empty line that doesn't start with |
                consecutive_non_table_lines += 1
                if consecutive_non_table_lines > 0:
                    active_header = None
                    active_context = ""
            else:
                # It's an empty line (\n inside a table). Give it some tolerance.
                consecutive_non_table_lines += 1
                if consecutive_non_table_lines > 2:
                    active_header = None
                    active_context = ""
            
            line_with_newline = line + "\n"
            line_len = len(line_with_newline)
            
            if current_len + line_len > chunk_size and current_chunk:
                # Flush current chunk
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
                
                # If inside a table, inject header and preceding context
                if active_header:
                    if active_context:
                        # Strip raw tags from context so it doesn't cause extraction hallucinations
                        clean_context = re.sub(REF_TAG_PATTERN, "", active_context)
                        context_block = f"--- TABLE CONTEXT (Inherited) ---\n{clean_context}\n---------------------------------\n"
                        current_chunk.append(context_block)
                        current_len += len(context_block)
                        
                    clean_header = re.sub(REF_TAG_PATTERN, "", active_header[0])
                    current_chunk.append(clean_header + "\n")  # header row
                    current_chunk.append(active_header[1] + "\n")  # separator
                    current_len += len(clean_header) + len(active_header[1]) + 2
            
            current_chunk.append(line_with_newline)
            current_len += line_len
        
        if current_chunk:
            chunks.append("".join(current_chunk))
        
        return chunks

    # ==================================================================
    # Legacy Methods (Backward Compatibility)
    # ==================================================================

    async def _extract_segment(self, model: ExtractionModel, text_segment: str, ocr_data: Dict, ref_map: Dict, mode: str) -> ExtractionResult:
        """[LEGACY] Helper to run a single LLM call for a text segment with specific mode."""
        system_prompt = RefinerEngine.construct_prompt(model, language="ko", mode=mode)
        user_prompt = f"DOCUMENT DATA (Tagged Layout Format):\n{text_segment}\n\nTASK: Extract fields based on system instructions.\nReturn valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_result = await self.call_llm(messages)
        return self._normalize_output(raw_result, ocr_data, ref_map, text_segment)

    def _merge_results(self, common: ExtractionResult, table: ExtractionResult) -> ExtractionResult:
        """[LEGACY] Merge Common and Table results into a single Dict."""
        merged = ExtractionResult()
        merged.guide_extracted.update(common.guide_extracted)
        merged.guide_extracted.update(table.guide_extracted)
        merged.token_usage.prompt_tokens = common.token_usage.prompt_tokens + table.token_usage.prompt_tokens
        merged.token_usage.completion_tokens = common.token_usage.completion_tokens + table.token_usage.completion_tokens
        merged.token_usage.total_tokens = common.token_usage.total_tokens + table.token_usage.total_tokens
        return merged

    async def _extract_table_chunked(self, model: ExtractionModel, tagged_text: str, ocr_data: Dict[str, Any], ref_map: Dict, chunk_size: int) -> ExtractionResult:
        """
        Stage 2 (Large Content): Extract TABLE data from chunks.
        Supports multi-sheet Excel files via `_excel_sheets` to prevent cross-sheet header contamination.
        """
        table_prompt = RefinerEngine.construct_prompt(model, language="ko", mode="table")
        
        # 1. Prepare Target Sheets / Texts
        target_sections = []
        if "_excel_sheets" in ocr_data and isinstance(ocr_data["_excel_sheets"], list):
            for sheet in ocr_data["_excel_sheets"]:
                target_sections.append({
                    "name": sheet.get("sheet_name", "Unknown Sheet"),
                    "content": sheet.get("content", "")
                })
        else:
            # Standard PDF/Image routing
            target_sections.append({
                "name": "Document",
                "content": tagged_text
            })

        # 2. Build Chunks Per Section
        all_chunk_tasks = []
        
        for section in target_sections:
            content = section["content"]
            if not content.strip():
                continue
                
            lines = content.split("\n")
            chunks = []
            current_chunk_lines = []
            current_chunk_len = 0
            
            for line in lines:
                line_len = len(line) + 1  # +1 for newline
                if current_chunk_len + line_len > chunk_size and current_chunk_lines:
                    chunks.append("\n".join(current_chunk_lines))
                    current_chunk_lines = []
                    current_chunk_len = 0
                
                current_chunk_lines.append(line)
                current_chunk_len += line_len
            
            if current_chunk_lines:
                chunks.append("\n".join(current_chunk_lines))
                
            # Header context STRICTLY isolated to this specific sheet/section
            header_context = content[:1500]
            
            response_format = self._build_engineer_schema(model) if model else {"type": "json_object"}
            temp = model.temperature if model else None
            
            # Create process task closure for this specific chunk
            for idx, chunk_text in enumerate(chunks):
                all_chunk_tasks.append(
                    self._process_table_chunk_task(
                        chunk_text, idx, header_context, section["name"], table_prompt, ocr_data, ref_map, response_format, temp
                    )
                )

        if not all_chunk_tasks:
            return ExtractionResult()
            
        logger.info(f"[BetaPipeline] Table Chunking: Created {len(all_chunk_tasks)} tasks across {len(target_sections)} sections")
        
        # 3. Parallel Execution
        results = await asyncio.gather(*all_chunk_tasks, return_exceptions=True)
        
        # 4. Merge Results (Field-aware Deduplication)
        merged_result = ExtractionResult()
        merged_guide = {} # Key -> List[Row]
        seen_rows = {}    # Key -> Set(row_hash)
        
        for res in results:
            if isinstance(res, Exception):
                continue
            
            # Token Usage
            merged_result.token_usage.prompt_tokens += res.token_usage.prompt_tokens
            merged_result.token_usage.completion_tokens += res.token_usage.completion_tokens
            merged_result.token_usage.total_tokens += res.token_usage.total_tokens
                        
            # Merge Lists
            if res.guide_extracted:
                for key, val in res.guide_extracted.items():
                    if isinstance(val, list):
                        if key not in merged_guide:
                            merged_guide[key] = []
                            seen_rows[key] = set()
                        
                        for row in val:
                            if not isinstance(row, dict): continue
                            
                            row_hash = json.dumps(row, sort_keys=True, ensure_ascii=False)
                            if row_hash not in seen_rows[key]:
                                seen_rows[key].add(row_hash)
                                merged_guide[key].append(row)

        merged_result.guide_extracted = self._normalize_column_keys(merged_guide)
        return merged_result

    async def _process_table_chunk_task(self, chunk_text: str, chunk_idx: int, header_context: str, section_name: str, table_prompt: str, ocr_data: Dict, ref_map: Dict, response_format: Dict = None, temperature: float = None) -> ExtractionResult:
        """Helper to process a single chunk safely."""
        final_chunk = chunk_text
        if chunk_idx > 0:
            final_chunk = f"--- [SHEET/SECTION HEADER: {section_name}] ---\n{header_context}\n... [Header Context End] ...\n{chunk_text}"
        
        user_prompt = (
            f"DOCUMENT DATA (Tagged Layout Format):\n{final_chunk}\n\n"
            f"TASK: Extract table rows from this section of the document.\n"
            f"Return valid JSON."
        )
        
        messages = [
            {"role": "system", "content": table_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        async with _AdaptiveContext(self.semaphore) as sem_ctx:
            try:
                raw_result = await self.call_llm(messages, is_table_model=True, temperature=temperature, response_format=response_format)
                if isinstance(raw_result, dict) and raw_result.get("_had_429"):
                    sem_ctx.is_429 = True
                return self._normalize_output(raw_result, ocr_data, ref_map, chunk_text)
            except Exception as e:
                if "429" in str(e):
                    sem_ctx.is_429 = True
                logger.error(f"[BetaPipeline] Table Chunk {chunk_idx} in {section_name} failed: {e}")
                res = ExtractionResult()
                res.error = str(e)
                return res

    def _normalize_column_keys(self, merged_guide: dict) -> dict:
        """
        Normalize column keys across chunks to prevent duplicates from
        case/format differences (e.g. 'Charge_Type' vs 'charge_type').
        Uses the first chunk's keys as canonical reference.
        """
        for field_key, rows in merged_guide.items():
            if not isinstance(rows, list) or not rows:
                continue
            
            # Use first row's keys as canonical
            canonical_keys = list(rows[0].keys())
            
            def _strip(s: str) -> str:
                return s.lower().replace("_", "").replace("-", "").replace(" ", "")
            
            canonical_map = {_strip(k): k for k in canonical_keys}
            
            normalized_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    normalized_rows.append(row)
                    continue
                new_row = {}
                for k, v in row.items():
                    norm_k = _strip(k)
                    new_row[canonical_map.get(norm_k, k)] = v
                normalized_rows.append(new_row)
            
            merged_guide[field_key] = normalized_rows
        
        return merged_guide



    async def _execute_chunked(self, model: ExtractionModel, ocr_data: Dict[str, Any], total_pages: int) -> ExtractionResult:
        # Chunking Config
        CHUNK_SIZE = 1
        OVERLAP = 0 # No overlap needed for single page chunks unless specifically requested for cross-page tables.
        # Actually, let's keep overlap logic but default to CHUNK_SIZE=1.
        # If CHUNK_SIZE=1 and OVERLAP=1, we get [1], [2], [3]... (no overlap)?
        # Wait, if step = 1-1 = 0, steps stop.
        # Let's use CHUNK_SIZE=1, OVERLAP=0 for safety first.
        # Or better: CHUNK_SIZE=1. Overlap logic is complex with size 1.
        # [SAFE OPTIMIZATION]
        # Chunk Size = 2 + Overlap = 1: Preserves table context across pages.
        # Semaphore = 5: High parallelism.
        CHUNK_SIZE = 2
        OVERLAP = 1 
        
        chunks = []
        # Create overlapping chunks: [1,2], [2,3], [3,4]...
        # Step = Chunk - Overlap = 2 - 1 = 1
        step = CHUNK_SIZE - OVERLAP
        if step < 1: step = 1
        
        for i in range(0, total_pages, step):
            # focus_pages is 1-based
            start_page = i + 1
            end_page = min(i + CHUNK_SIZE, total_pages)
            
            # Avoid single-page tail if possible, merge into previous?
            # Actually strict sliding window is fine.
            if start_page > total_pages: break
             
            chunk_pages = list(range(start_page, end_page + 1))
            
            # Deduplicate chunks (e.g. if last step creates subset)
            if chunks and set(chunk_pages).issubset(set(chunks[-1])):
                continue
                
            chunks.append(chunk_pages)

        logger.info(f"[BetaPipeline] Created {len(chunks)} chunks with overlap: {chunks}")
        
        # Parallel Execution with Semaphore
        tasks = []
        for chunk in chunks:
            tasks.append(self._process_chunk_safe(model, ocr_data, chunk))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge Results
        merged_result = ExtractionResult()
        merged_rows = []
        seen_keys = set() # For deduplication
        
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[BetaPipeline] Chunk failed: {res}")
                continue
            
            # Accumulate Tokens
            merged_result.token_usage.prompt_tokens += res.token_usage.prompt_tokens
            merged_result.token_usage.completion_tokens += res.token_usage.completion_tokens
            merged_result.token_usage.total_tokens += res.token_usage.total_tokens
            
            # Merge Rows (Deduplication Strategy needed)
            # Simple Strategy: If row content is identical, skip.
            # Robust Strategy: If Primary Key matches, skip.
            # For now: Append all, let frontend handle or use simple JSON hash.
            
            current_rows = res.table_rows or [] # Unified schema uses table_rows
            if not current_rows and res.guide_extracted:
                 # Flatten single object to list if it looks like a row
                 current_rows = [res.guide_extracted]
            
            for row in current_rows:
                row_hash = json.dumps(row, sort_keys=True)
                if row_hash not in seen_keys:
                    seen_keys.add(row_hash)
                    
                    # Patch Page Numbers
                    # (Simplified: trusting LayoutParser's relative mapping? No, we need absolute patching)
                    # For now, let's assume `_process_chunk_safe` returns patched rows?
                    # Or patch here?
                    # Let's rely on standard logic - pages might be re-indexed.
                    # We should implement patching in _process_chunk_safe ideally.
                    
                    merged_rows.append(row)
        
        merged_result.table_rows = merged_rows
        merged_result.is_table = True
        
        # Merge Metadata (Parsed Content for Debug View & RefMap)
        all_parsed_text = []
        all_ref_map = {}
        for res in results:
            if isinstance(res, Exception): continue
            if res.beta_metadata:
                text = res.beta_metadata.get("parsed_content", "")
                if text: all_parsed_text.append(text)
                ref_map = res.beta_metadata.get("ref_map", {})
                if ref_map: all_ref_map.update(ref_map)
        
        merged_result.beta_metadata = {
            "parsed_content": "\n... [Chunk Split] ...\n".join(all_parsed_text),
            "ref_map": all_ref_map
        }

        return merged_result

    async def _process_chunk_safe(self, model: ExtractionModel, ocr_data: Dict[str, Any], chunk_pages: List[int]) -> ExtractionResult:
        """Wrapper to use Semaphore and filter OCR"""
        async with _AdaptiveContext(self.semaphore) as sem_ctx:
            # Filter OCR
            chunk_ocr = self._filter_ocr_data(ocr_data, chunk_pages)
            
            # Execute Single Shot (LayoutParser inside sees 1..N pages)
            try:
                result = await self._execute_single_shot(model, chunk_ocr, focus_pages=None)
            except Exception as e:
                if "429" in str(e):
                    sem_ctx.is_429 = True
                # [ADAPTIVE CHUNKING ALERT]
                # If a chunk fails (esp. JSONDecodeError via Unterminated string == Token Limit),
                # and chunk size > 1, we must SPLIT THE CHUNK and retry.
                if len(chunk_pages) > 1:
                    logger.warning(f"[BetaPipeline] Chunk {chunk_pages} failed: {e}. Splitting into sub-chunks...")
                    mid = len(chunk_pages) // 2
                    left_pages = chunk_pages[:mid]
                    right_pages = chunk_pages[mid:]
                    
                    # Recursive call
                    left_res, right_res = await asyncio.gather(
                        self._process_chunk_safe(model, ocr_data, left_pages),
                        self._process_chunk_safe(model, ocr_data, right_pages)
                    )
                    
                    # Merge Results manually (simplified merge of two ExtractionResults)
                    merged = ExtractionResult()
                    merged.table_rows = left_res.table_rows + right_res.table_rows
                    merged.is_table = True
                    merged.token_usage.prompt_tokens = left_res.token_usage.prompt_tokens + right_res.token_usage.prompt_tokens
                    merged.token_usage.completion_tokens = left_res.token_usage.completion_tokens + right_res.token_usage.completion_tokens
                    merged.token_usage.total_tokens = left_res.token_usage.total_tokens + right_res.token_usage.total_tokens
                    # Guide extracted? Take first or merge? Usually guide is global.
                    # If both have it, take whichever has higher confidence or non-empty.
                    merged.guide_extracted = left_res.guide_extracted or right_res.guide_extracted
                    
                    # Metadata merge (complex but we just need parsed content for debug)
                    merged.beta_metadata = {
                        "parsed_content": (left_res.beta_metadata.get("parsed_content", "") if left_res.beta_metadata else "") + 
                                          "\n" + 
                                          (right_res.beta_metadata.get("parsed_content", "") if right_res.beta_metadata else ""),
                        # Naive merge of ref_map: simplest way is update
                        "ref_map": {**(left_res.beta_metadata.get("ref_map", {}) if left_res.beta_metadata else {}),
                                    **(right_res.beta_metadata.get("ref_map", {}) if right_res.beta_metadata else {})}
                    }
                    
                    return merged
                else:
                    # Single page failure: Cannot split further.
                    # This happens if 1 page > 16k tokens output or critical error.
                    logger.error(f"[BetaPipeline] Single-Page Chunk {chunk_pages} FAILED irrecoverably: {e}")
                    # Return error result object instead of crashing whole pipeline
                    err_res = ExtractionResult()
                    err_res.error = str(e)
                    return err_res

            # Patch Page Numbers
            # LayoutParser relative 1..N -> Absolute chunk_pages
            self._patch_page_numbers(result, chunk_pages)
            
            return result

    def _filter_ocr_data(self, ocr_data: Dict[str, Any], focus_pages: List[int]) -> Dict[str, Any]:
        """Specific filter for Beta Pipeline (same logic as service)"""
        if not focus_pages: return ocr_data.copy()
        
        filtered = {
            "content": "",
            "pages": [],
            "paragraphs": [],
            "tables": [],
            "styles": ocr_data.get("styles", [])
        }
        
        def is_on_focus_page(item):
            regions = item.get("bounding_regions") or item.get("boundingRegions") or []
            for region in regions:
                pn = region.get("page_number") or region.get("pageNumber")
                if pn in focus_pages: return True
            return False

        filtered["pages"] = [p for p in ocr_data.get("pages", []) 
                           if (p.get("page_number") or p.get("pageNumber")) in focus_pages]
        
        filtered["paragraphs"] = [p for p in ocr_data.get("paragraphs", []) if is_on_focus_page(p)]
        filtered["tables"] = [t for t in ocr_data.get("tables", []) if is_on_focus_page(t)]
        
        filtered["content"] = "\n".join([p.get("content", "") for p in filtered["paragraphs"]])
        return filtered

    def _patch_page_numbers(self, result: ExtractionResult, chunk_pages: List[int]):
        """
        Maps relative page numbers (1-based index in chunk) to absolute page numbers.
        Example: Chunk=[5,6], Result says Page 1 -> Mapped to Page 5.
        """
        def map_page(rel_page):
            if isinstance(rel_page, int) and 1 <= rel_page <= len(chunk_pages):
                return chunk_pages[rel_page - 1]
            return rel_page # Fallback

        # 1. Standard Fields
        for key, val in result.guide_extracted.items():
            if isinstance(val, dict) and "page_number" in val:
                val["page_number"] = map_page(val["page_number"])
                
        # 2. Table Rows
        for row in result.table_rows:
            # Row-level metadata
            if "_page" in row:
                row["_page"] = map_page(row["_page"])
                
            # Cell-level metadata (if any)
            for k, v in row.items():
                if isinstance(v, dict) and "page_number" in v:
                     v["page_number"] = map_page(v["page_number"])

        # 3. Ref Map (Metadata)
        if result.beta_metadata and "ref_map" in result.beta_metadata:
             for k, v in result.beta_metadata["ref_map"].items():
                 if "page_number" in v:
                     v["page_number"] = map_page(v["page_number"])

    def _normalize_output(self, raw_llm: Dict[str, Any], ocr_data: Dict, ref_map: Dict, tagged_text: str) -> ExtractionResult:
        """Convert LLM JSON to Standard ExtractionResult (Unified Dict Format)"""
        res = ExtractionResult()
        
        extracted = raw_llm.get("guide_extracted", {})
        
        # Legacy/Fallback: "rows" key -> wrap in _table_data or first list field if possible
        # [DEPRECATED] This path is no longer triggered with unified TABLE MODE prompt.
        # Kept for backward compatibility with any external callers.
        if "rows" in raw_llm:
            rows = raw_llm["rows"]
            if isinstance(rows, dict):
                # Convert dict-of-rows to list-of-rows
                try:
                    sorted_keys = sorted(rows.keys(), key=lambda x: int(x) if str(x).isdigit() else x)
                    rows = [rows[k] for k in sorted_keys]
                except:
                    rows = list(rows.values())
            
            # If guide_extracted is empty, put rows in a generic field
            # Ideally we should know the field name, but for now specific field key is better
            extracted["_legacy_rows"] = rows

        # Clean up {value: list} wrapper (LLM sometimes wraps table fields in text-field format)
        # Also clean up {value: val} for text fields if needed, but usually we keep confidence.
        # Strict schema requires:
        # - Text Field: {value: "...", confidence: 0.9}
        # - Table Field: [{...}, {...}] (List of Rows)
        
        cleaned_extracted = {}
        for k, v in extracted.items():
            # Recovery: If LLM hallucinated a JSON string instead of an actual array/object
            if isinstance(v, str):
                v_strip = v.strip()
                if (v_strip.startswith("[") and v_strip.endswith("]")) or (v_strip.startswith("{") and v_strip.endswith("}")):
                    try:
                        import json
                        parsed_v = json.loads(v_strip)
                        v = parsed_v
                    except:
                        pass
                        
            # Case 1: Already a list -> Keep it (Table Field)
            if isinstance(v, list):
                # But check if it's a list containing a single scalar object mistakenly generated by LLM
                if len(v) == 1 and isinstance(v[0], dict) and "value" in v[0] and "confidence" in v[0] and len(v[0].keys()) <= 5:
                    # Unwrap the mistakenly array-wrapped scalar
                    cleaned_extracted[k] = v[0]
                else:
                    cleaned_extracted[k] = v
                continue
                
            # Case 2: Dict wrapper
            if isinstance(v, dict):
                # Check if it wraps a list: {"value": [...]}
                if "value" in v and isinstance(v["value"], list):
                     list_val = v["value"]
                     # Unwrap mistakenly array-wrapped scalar inside 'value'
                     if len(list_val) == 1 and isinstance(list_val[0], dict) and "value" in list_val[0] and "confidence" in list_val[0] and len(list_val[0].keys()) <= 5:
                         cleaned_extracted[k] = list_val[0]
                     else:
                         cleaned_extracted[k] = list_val
                else:
                     # Text field -> Keep as is
                     cleaned_extracted[k] = v
            else:
                # Direct value -> Wrap for consistency? or Keep?
                # Service layer expects structure, but let's keep as is for legacy compat
                cleaned_extracted[k] = v
                
        res.guide_extracted = cleaned_extracted
        
        # Token Usage
        usage = raw_llm.get("_token_usage", {})
        res.token_usage = TokenUsage(**usage) if usage else TokenUsage()
        
        # Metadata
        res.beta_metadata = {
            "ref_map": ref_map,
            "parsed_content": tagged_text
        }
        
        return res

    async def call_llm(self, messages, is_table_model: bool = False, temperature: Optional[float] = None, response_format: Optional[Dict] = None):
        """Direct LLM Call with table-aware max_tokens, multi-model routing, and resilient exponential backoff"""
        import asyncio
        import random
        
        current_model_name = get_current_model()
        # Table models need more output tokens for many rows
        raw_max = settings.LLM_TABLE_MAX_TOKENS if is_table_model else settings.LLM_DEFAULT_MAX_TOKENS
        max_tokens = min(raw_max, 32768)  # GPT-4.1 supports up to 32K completion tokens
        
        temp = temperature if temperature is not None else settings.LLM_DEFAULT_TEMPERATURE
        resp_fmt = response_format if response_format is not None else {"type": "json_object"}
        
        # ── Multi-Model Routing ──
        # Non-OpenAI models (Claude, Llama, Mistral, etc.) use azure-ai-inference SDK
        from app.services.llm_service import is_openai_model
        if not is_openai_model(current_model_name):
            return await self._call_llm_inference(messages, current_model_name, temp, max_tokens, resp_fmt)
        
        # ── OpenAI Path (existing logic with retries) ──
        max_retries = 6
        base_delay = 2.0
        response = None
        had_429 = False
        
        for attempt in range(max_retries):
            try:
                response = await self.azure_client.chat.completions.create(
                    model=current_model_name,
                    messages=messages,
                    temperature=temp,
                    seed=42,
                    max_completion_tokens=max_tokens,
                    response_format=resp_fmt
                )
                break # Success
            except Exception as e:
                error_msg = str(e)
                error_lower = error_msg.lower()
                
                # Fallback: if strict JSON Schema is not supported, retry with json_object
                if resp_fmt.get("type") == "json_schema" and any(term in error_lower for term in ["json_schema", "response_format", "unsupported"]):
                    logger.warning(f"[BetaPipeline] Strict JSON Schema not supported, falling back to json_object: {error_msg[:100]}")
                    resp_fmt = {"type": "json_object"}
                    continue
                
                is_transient = any(term in error_lower for term in ["429", "rate limit", "timeout", "connection", "502", "503", "504"])
                
                if "429" in error_lower or "rate limit" in error_lower:
                    had_429 = True

                if not is_transient or attempt == max_retries - 1:
                    logger.error(f"[BetaPipeline] Azure API Fatal Error after {attempt+1} attempts: {error_msg}")
                    return {
                        "guide_extracted": {},
                        "error": f"LLM API Error: {error_msg}"
                    }
                
                delay = base_delay * (2 ** attempt) + random.uniform(0.1, 1.5)
                logger.warning(f"[BetaPipeline] Azure API Transient Error: {error_msg[:100]}... Retrying {attempt+1}/{max_retries} in {delay:.1f}s")
                await asyncio.sleep(delay)
        
        content = response.choices[0].message.content
        finish_reason = getattr(response.choices[0], "finish_reason", "stop")
        
        result = self._parse_llm_response(content, finish_reason, response.usage)
        result["_llm_model"] = current_model_name
        if had_429:
            result["_had_429"] = True
        return result

    async def _call_llm_inference(self, messages, model_name: str, temperature: float, max_tokens: int, response_format: Optional[Dict] = None):
        """
        Call non-OpenAI models (Claude, Llama, Mistral, etc.) via azure-ai-inference SDK.
        This is the routing path for Anthropic and other third-party models deployed on Azure AI Foundry.
        """
        import asyncio
        import random
        
        from app.services.llm_service import call_llm_unified
        
        max_retries = 6
        base_delay = 2.0
        had_429 = False
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[BetaPipeline] Inference route → model={model_name} (attempt {attempt+1})")
                result = await call_llm_unified(
                    messages=messages,
                    model_name=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
                
                content = result.get("content", "")
                finish_reason = result.get("finish_reason", "stop")
                usage = result.get("usage", {})
                
                # Build a mock usage object for _parse_llm_response compatibility
                class _MockUsage:
                    def __init__(self, d):
                        self.prompt_tokens = d.get("prompt_tokens", 0)
                        self.completion_tokens = d.get("completion_tokens", 0)
                        self.total_tokens = d.get("total_tokens", 0)
                
                parsed_res = self._parse_llm_response(content, finish_reason, _MockUsage(usage))
                parsed_res["_llm_model"] = model_name
                if had_429:
                    parsed_res["_had_429"] = True
                return parsed_res
                
            except Exception as e:
                error_msg = str(e)
                error_lower = error_msg.lower()
                is_transient = any(term in error_lower for term in ["429", "rate limit", "timeout", "connection", "502", "503", "504"])
                
                if "429" in error_lower or "rate limit" in error_lower:
                    had_429 = True
                
                if not is_transient or attempt == max_retries - 1:
                    logger.error(f"[BetaPipeline] Inference API Fatal Error after {attempt+1} attempts: {error_msg}")
                    return {
                        "guide_extracted": {},
                        "error": f"LLM Inference API Error: {error_msg}"
                    }
                
                delay = base_delay * (2 ** attempt) + random.uniform(0.1, 1.5)
                logger.warning(f"[BetaPipeline] Inference API Transient Error: {error_msg[:100]}... Retrying {attempt+1}/{max_retries} in {delay:.1f}s")
                await asyncio.sleep(delay)
        
        # Should not reach here
        return {"guide_extracted": {}, "error": "LLM Inference API: All retries exhausted"}

    def _parse_llm_response(self, content: str, finish_reason: str, usage) -> Dict:
        """Shared response parser for both OpenAI and Inference paths."""
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[BetaPipeline] JSON Decode Error: {e}. Content-Length: {len(content)}, finish_reason: {finish_reason}")
            result = {
                "guide_extracted": {}, 
                "error": f"LLM Output Malformed: {str(e)}", 
                "_raw_llm_content": content
            }
        
        # Normalize: LLM sometimes returns a list instead of dict
        if isinstance(result, list):
            logger.warning(f"[BetaPipeline] LLM returned list ({len(result)} items) instead of dict. Wrapping first item.")
            if result and isinstance(result[0], dict):
                result = {"guide_extracted": result[0]}
            else:
                result = {"guide_extracted": {}, "error": "LLM returned array instead of object"}
        elif not isinstance(result, dict):
            logger.warning(f"[BetaPipeline] LLM returned {type(result).__name__} instead of dict.")
            result = {
                "guide_extracted": {}, 
                "error": f"LLM returned {type(result).__name__} instead of object", 
                "_raw_llm_content": str(result)
            }
        
        # Ensure guide_extracted key exists and is a dictionary
        if isinstance(result, dict):
            if "guide_extracted" not in result:
                # LLM might return flat {field: value} without wrapper — wrap it
                if any(k not in ("_token_usage", "_truncated", "error", "_raw_llm_content") for k in result.keys()):
                    logger.info(f"[BetaPipeline] LLM returned flat dict without guide_extracted wrapper. Wrapping.")
                    result = {"guide_extracted": result}
                else:
                    result["guide_extracted"] = {}
            elif not isinstance(result["guide_extracted"], dict):
                logger.warning(f"[BetaPipeline] LLM returned non-dict for guide_extracted: {type(result['guide_extracted'])}. Wrapping it.")
                result["_raw_guide_extracted_string"] = str(result["guide_extracted"])
                result["guide_extracted"] = {}
        
        # Detect LLM output truncation
        if finish_reason == "length":
            logger.warning(f"[BetaPipeline] LLM output truncated (finish_reason='length'). Setting _truncated=True.")
            result["_truncated"] = True
        
        if usage:
             result["_token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        return result

