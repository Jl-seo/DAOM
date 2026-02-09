"""
Standalone simulation of TIER 3 merge logic.
No project imports needed. Reproduces _normalize_output + merge exactly.
"""
import json

# ─── Simulate ExtractionResult ───
class FakeResult:
    def __init__(self):
        self.table_rows = []
        self.guide_extracted = {}
        self.is_table = False
        self.error = None

# ─── Exact copy of _normalize_output (beta_pipeline.py L468-524) ───
def normalize_output(raw_llm: dict) -> FakeResult:
    res = FakeResult()
    
    extracted = raw_llm.get("guide_extracted", {})
    res.guide_extracted = extracted
    
    if "rows" in raw_llm:
        rows = raw_llm["rows"]
        if isinstance(rows, dict):
            try:
                sorted_keys = sorted(rows.keys(), key=lambda x: int(x) if str(x).isdigit() else x)
                rows = [rows[k] for k in sorted_keys]
            except:
                rows = list(rows.values())
        res.table_rows = rows
        res.is_table = True
    else:
        found_table = False
        for k, v in extracted.items():
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                res.table_rows = v
                res.is_table = True
                found_table = True
                break
        
        if not found_table and extracted:
            pass
    
    return res

# ─── Exact copy of merge logic (beta_pipeline.py L195-235) ───
def merge_results(results: list) -> FakeResult:
    merged_result = FakeResult()
    merged_rows = []
    seen_keys = set()
    
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"  ❌ Chunk {i}: EXCEPTION: {res}")
            continue
        
        current_rows = res.table_rows or []
        if not current_rows and res.guide_extracted:
            current_rows = [res.guide_extracted]
            print(f"  ⚠️  Chunk {i}: table_rows EMPTY → wrapped guide_extracted as 1 row. Keys: {list(res.guide_extracted.keys()) if isinstance(res.guide_extracted, dict) else 'N/A'}")
        
        before = len(merged_rows)
        for row in current_rows:
            row_hash = json.dumps(row, sort_keys=True, ensure_ascii=False)
            if row_hash not in seen_keys:
                seen_keys.add(row_hash)
                merged_rows.append(row)
        after = len(merged_rows)
        
        print(f"  📦 Chunk {i}: table_rows={len(res.table_rows or [])} | is_table={res.is_table} | added= {after - before} new rows")
    
    merged_result.table_rows = merged_rows
    merged_result.is_table = bool(merged_rows)
    
    if not merged_rows:
        for res in results:
            if isinstance(res, Exception): continue
            if res.guide_extracted:
                merged_result.guide_extracted = res.guide_extracted
                merged_result.is_table = False
                break
    
    return merged_result

# ─── Then simulate _validate_and_format (extraction_service.py L254-275) ───
def validate_and_format(extraction_result: FakeResult) -> dict:
    """Simulate what extraction_service does after pipeline returns"""
    result_dict = {
        "guide_extracted": extraction_result.guide_extracted,
    }
    
    if extraction_result.is_table:
        result_dict["_is_table"] = True
        result_dict["_table_rows"] = extraction_result.table_rows
    
    # Now simulate _validate_and_format TABLE MODE path (L258-275)
    table_rows = result_dict.get("_table_rows", [])
    is_single_row = len(table_rows) == 1
    
    if result_dict.get("_is_table") and not is_single_row:
        return {"guide_extracted": table_rows, "_is_table": True}
    elif is_single_row and table_rows:
        return {"guide_extracted": table_rows[0]}
    else:
        return {"guide_extracted": result_dict.get("guide_extracted", {})}


# ════════════════════════════════════════════════════════
# TEST SCENARIOS
# ════════════════════════════════════════════════════════

print("=" * 70)
print("TEST 1: Normal — 8 chunks each return 4 rows → expect 32 merged")
print("=" * 70)
llm_responses = []
for c in range(8):
    rows = [{"Route": f"R{c}_{r}", "POL": "KRPUS", "POD": f"P{r}"} for r in range(4)]
    llm_responses.append({"guide_extracted": {"Rate_Explosion_List": rows}})
results = [normalize_output(r) for r in llm_responses]
merged = merge_results(results)
final = validate_and_format(merged)
print(f"\n  ✅ merged.table_rows = {len(merged.table_rows)}")
print(f"  ✅ final guide_extracted type = {type(final['guide_extracted']).__name__}, len = {len(final['guide_extracted'])}")

print("\n" + "=" * 70)
print("TEST 2: Only chunk 0 returns rows, chunks 1-7 return empty guide_extracted")
print("=" * 70)
results_2 = []
for c in range(8):
    if c == 0:
        resp = {"guide_extracted": {"Rate_Explosion_List": [
            {"Route": "NEU", "POL": "KRPUS", "POD": "DEHAM"},
            {"Route": "NEU", "POL": "KRPUS", "POD": "NLRTM"},
        ]}}
    else:
        resp = {"guide_extracted": {}}  # Empty!
results_2 = [normalize_output(r) for r in [
    {"guide_extracted": {"Rate_Explosion_List": [
        {"Route": "NEU", "POL": "KRPUS", "POD": "DEHAM"},
        {"Route": "NEU", "POL": "KRPUS", "POD": "NLRTM"},
    ]}},
    {"guide_extracted": {}},
    {"guide_extracted": {}},
    {"guide_extracted": {}},
]]
merged_2 = merge_results(results_2)
final_2 = validate_and_format(merged_2)
print(f"\n  ⚠️  merged rows = {len(merged_2.table_rows)}")
print(f"  → Only chunk 0 data survives!")

print("\n" + "=" * 70)
print("TEST 3: Chunks return rows but as DIFFERENT field keys")
print("=" * 70)
results_3 = [normalize_output(r) for r in [
    {"guide_extracted": {"Rate_Explosion_List": [{"Route": "NEU", "POD": "DEHAM"}]}},
    {"guide_extracted": {"rate_explosion_list": [{"Route": "MED", "POD": "EGDAM"}]}},
    {"guide_extracted": {"운임리스트": [{"Route": "NEU", "POD": "BEANR"}]}},
]]
merged_3 = merge_results(results_3)
print(f"\n  📊 merged rows = {len(merged_3.table_rows)} (all found because _normalize finds first list-of-dicts regardless of key name)")

print("\n" + "=" * 70)
print("TEST 4: LLM returns guide_extracted with NO list (just text fields)")
print("=" * 70)
results_4 = [normalize_output(r) for r in [
    {"guide_extracted": {"Rate_Explosion_List": [
        {"Route": "NEU", "POD": "DEHAM"},
    ]}},
    {"guide_extracted": {"summary": {"value": "some text", "confidence": 0.9}}},  # Not a list!
    {"guide_extracted": {"summary": {"value": "other text", "confidence": 0.8}}},  # Not a list!
]]
merged_4 = merge_results(results_4)
final_4 = validate_and_format(merged_4)
print(f"\n  📊 merged rows = {len(merged_4.table_rows)}")
print(f"  ⚠️  Chunks 1,2 had no list-of-dicts → guide_extracted dict wrapped as row!")
print(f"  → final guide_extracted = {json.dumps(final_4['guide_extracted'], ensure_ascii=False, indent=2)[:200]}...")

print("\n" + "=" * 70)
print("TEST 5: What header_context prepending does to chunk output")
print("=" * 70)
# Chunk 0: gets raw data for rows 1-4
# Chunk 1: gets header_context (rows 1-2 text) + rows 5-8 data
# LLM might extract rows 1-2 AGAIN from header_context!
results_5 = [normalize_output(r) for r in [
    {"guide_extracted": {"Rate_Explosion_List": [
        {"Route": "NEU", "POL": "KRPUS", "POD": "DEHAM", "Rate_20FT": 1985},
        {"Route": "NEU", "POL": "KRPUS", "POD": "NLRTM", "Rate_20FT": 1760},
        {"Route": "NEU", "POL": "KRPUS", "POD": "BEANR", "Rate_20FT": 1610},
    ]}},
    # Chunk 1: LLM sees header context (rows 1-2 text) + chunk 1 rows
    # LLM returns rows from BOTH header AND chunk → duplicates
    {"guide_extracted": {"Rate_Explosion_List": [
        {"Route": "NEU", "POL": "KRPUS", "POD": "DEHAM", "Rate_20FT": 1985},  # DUP from header!
        {"Route": "NEU", "POL": "KRPUS", "POD": "NLRTM", "Rate_20FT": 1760},  # DUP from header!
        {"Route": "MED", "POL": "KRPUS", "POD": "EGDAM", "Rate_20FT": 1510},  # NEW
        {"Route": "MED", "POL": "KRPUS", "POD": "ITGOA", "Rate_20FT": 1700},  # NEW
    ]}},
]]
merged_5 = merge_results(results_5)
print(f"\n  📊 merged rows = {len(merged_5.table_rows)} (dedup removed header duplicates)")
print(f"  Rows:")
for r in merged_5.table_rows:
    print(f"    {r}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
FINDING: The merge logic ITSELF is correct. 
The problem is upstream: if subsequent chunks' LLM calls return EMPTY OR 
MALFORMED guide_extracted (no list-of-dicts), then _normalize_output 
sets table_rows=[] and merge only gets chunk 0's rows.

ROOT CAUSE CANDIDATES:
1. LLM returns empty {} for chunks 1-N (because header_context + chunk 
   text confuses the LLM about what to extract)
2. LLM throws exceptions on chunks 1-N (rate limiting, timeout)
3. LLM returns data in a format _normalize_output doesn't recognize
""")
