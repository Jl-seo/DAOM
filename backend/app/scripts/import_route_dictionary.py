"""
Import carrier-port route mapping Excel into Cosmos DB reference_data container.
Parses 2 sheets into 3 dictionary categories: port, carrier, route.

Source: "전체 항로 매핑 및 선사별 세부항로 정리 (1).xlsx"
  - Sheet "항로 및 POD 매핑": 2139 rows (carrier-port mappings)
  - Sheet "HLMS_DATA": 535 rows (port master data with UN/LOCODE)

Usage:
    cd backend
    python3 -m app.scripts.import_route_dictionary --dry-run
    python3 -m app.scripts.import_route_dictionary
    python3 -m app.scripts.import_route_dictionary --model-id=abc123
"""
import sys
import asyncio
import logging
import hashlib
from datetime import datetime

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")

EXCEL_PATH = "/Users/seojeonglee/Downloads/전체 항로 매핑 및 선사별 세부항로 정리 (1).xlsx"
# __global__ means these entries are available for ANY model
TARGET_MODEL_ID = "__global__"


async def main():
    dry_run = "--dry-run" in sys.argv
    model_id = TARGET_MODEL_ID
    for arg in sys.argv[1:]:
        if arg.startswith("--model-id="):
            model_id = arg.split("=", 1)[1]

    if dry_run:
        logger.info("🔍 DRY RUN MODE\n")

    xf = pd.ExcelFile(EXCEL_PATH)
    logger.info(f"📂 File: {EXCEL_PATH}")
    logger.info(f"   Sheets: {xf.sheet_names}\n")

    # ──────────────────────────────────────────
    # Sheet 1: 항로 및 POD 매핑 (header=row0, skip cols 0-1)
    # ──────────────────────────────────────────
    df_route = pd.read_excel(xf, sheet_name="항로 및 POD 매핑", header=0)
    # Drop the first 2 unnamed number columns
    df_route = df_route.loc[:, ~df_route.columns.str.startswith("Unnamed")]
    logger.info(f"📋 Sheet '항로 및 POD 매핑': {len(df_route)} rows")
    logger.info(f"   Columns: {list(df_route.columns)}")

    # ──────────────────────────────────────────
    # Sheet 2: HLMS_DATA (port master)
    # ──────────────────────────────────────────
    df_hlms = pd.read_excel(xf, sheet_name="HLMS_DATA", header=0)
    logger.info(f"📋 Sheet 'HLMS_DATA': {len(df_hlms)} rows")
    logger.info(f"   Columns: {list(df_hlms.columns)[:8]}...")

    # ═══════════════════════════════════════════
    # Parse: PORT dictionary
    # ═══════════════════════════════════════════
    port_entries = {}

    # From 항로 및 POD 매핑
    for _, row in df_route.iterrows():
        locode = _s(row, "LOCODE_HLMS")
        if not locode:
            continue
        
        pod_col = _find_col(df_route.columns, ["POD/PVY NAME"])
        pod_name = _s(row, pod_col) if pod_col else ""
        locode_carrier = _s(row, "LOCODE_CARRIER")
        desc_carrier = _s(row, "DESCRIPTION_CARRIER")
        
        if locode not in port_entries:
            port_entries[locode] = {"code": locode, "label": pod_name or locode, "aliases": set()}
        
        e = port_entries[locode]
        e["aliases"].add(locode.lower())
        if pod_name:
            e["aliases"].add(pod_name.lower())
            if "," in pod_name:
                e["aliases"].add(pod_name.split(",")[0].strip().lower())
        if locode_carrier and locode_carrier != locode:
            e["aliases"].add(locode_carrier.lower())
        if desc_carrier:
            e["aliases"].add(desc_carrier.lower())
            if "," in desc_carrier:
                e["aliases"].add(desc_carrier.split(",")[0].strip().lower())

    # From HLMS_DATA (adds more ports + aliases)
    for _, row in df_hlms.iterrows():
        locode = _s(row, "Location Code")
        if not locode:
            continue
        loc_name = _s(row, "Location Name")
        loc_abrv = _s(row, "Location Abrv. Name")
        un_locode = _s(row, "UN/LOCODE")
        
        if locode not in port_entries:
            port_entries[locode] = {"code": locode, "label": loc_name or locode, "aliases": set()}
        
        e = port_entries[locode]
        e["aliases"].add(locode.lower())
        if loc_name:
            e["aliases"].add(loc_name.lower())
            if "," in loc_name:
                e["aliases"].add(loc_name.split(",")[0].strip().lower())
        if loc_abrv:
            e["aliases"].add(loc_abrv.lower())
        if un_locode and un_locode != locode:
            e["aliases"].add(un_locode.lower())

    # ═══════════════════════════════════════════
    # Parse: CARRIER dictionary
    # ═══════════════════════════════════════════
    carrier_entries = {}
    for _, row in df_route.iterrows():
        code = _s(row, "carrier code(HLMS)")
        if not code:
            continue
        name = _s(row, "carrier name(약어)")
        vendor_code = _s(row, "VENDOR CODE")
        vendor_name = _s(row, "VENDOR NAME")
        
        if code not in carrier_entries:
            carrier_entries[code] = {"code": code, "label": name or code, "aliases": set()}
        
        e = carrier_entries[code]
        e["aliases"].add(code.lower())
        if name:
            e["aliases"].add(name.lower())
        if vendor_code:
            e["aliases"].add(vendor_code.lower())
        if vendor_name:
            e["aliases"].add(vendor_name.lower())

    # ═══════════════════════════════════════════
    # Parse: ROUTE dictionary
    # ═══════════════════════════════════════════
    route_entries = {}
    route_col = _find_col(df_route.columns, ["LOCODE\nroute_KR", "LOCODE route_KR"])
    for _, row in df_route.iterrows():
        code = _s(row, route_col) if route_col else ""
        if not code:
            continue
        name = _s(row, "route_KR")
        
        if code not in route_entries:
            route_entries[code] = {"code": code, "label": name or code, "aliases": set()}
        
        e = route_entries[code]
        e["aliases"].add(code.lower())
        if name:
            e["aliases"].add(name.lower())

    # From HLMS_DATA: route mapping via "Perf. SEA Route" and KIFFA columns
    for _, row in df_hlms.iterrows():
        route_code = _s(row, "Perf. SEA Route")
        area = _s(row, "Area")
        kiffa_sea = _s(row, "KIFFA-SEA")
        
        if route_code and route_code not in route_entries:
            route_entries[route_code] = {"code": route_code, "label": kiffa_sea or area or route_code, "aliases": set()}
        
        if route_code:
            e = route_entries[route_code]
            e["aliases"].add(route_code.lower())
            if area:
                e["aliases"].add(area.lower())
            if kiffa_sea:
                e["aliases"].add(kiffa_sea.lower())

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Parsed Results:")
    logger.info(f"   🚢 port:    {len(port_entries)} unique codes")
    logger.info(f"   🏢 carrier: {len(carrier_entries)} unique codes")
    logger.info(f"   🗺️  route:   {len(route_entries)} unique codes")
    logger.info(f"   Model ID:  {model_id}")

    for cat_name, entries in [("port", port_entries), ("carrier", carrier_entries), ("route", route_entries)]:
        sample = list(entries.values())[:3]
        logger.info(f"\n   [{cat_name}] 샘플:")
        for s in sample:
            aliases_preview = ", ".join(sorted(s["aliases"])[:4])
            logger.info(f"     {s['code']:8s} → {s['label'][:30]:30s}  aliases=[{aliases_preview}]")

    if dry_run:
        logger.info(f"\n🔍 DRY RUN complete. Re-run without --dry-run to upload.")
        return

    # ═══════════════════════════════════════════
    # Upload to Cosmos DB
    # ═══════════════════════════════════════════
    from app.db.cosmos import init_cosmos, get_reference_data_container

    logger.info(f"\n⏳ Connecting to Cosmos DB...")
    await init_cosmos()
    container = get_reference_data_container()
    if not container:
        logger.error("❌ reference_data container not available!")
        return

    total = 0
    for cat_name, entries in [("port", port_entries), ("carrier", carrier_entries), ("route", route_entries)]:
        logger.info(f"\n📤 Uploading '{cat_name}' ({len(entries)} entries)...")
        ok = 0
        for code, entry in entries.items():
            doc_id = hashlib.md5(f"{model_id}_{cat_name}_{code}".encode()).hexdigest()
            doc = {
                "id": doc_id,
                "model_id": model_id,
                "category": cat_name,
                "standard_code": entry["code"],
                "standard_label": entry["label"],
                "aliases": [a for a in entry["aliases"] if _valid_alias(a)],
                "source": "ADMIN",
                "is_verified": True,
                "hit_count": 0,
                "extra": {},
                "created_at": datetime.utcnow().isoformat()
            }
            try:
                await container.upsert_item(body=doc)
                ok += 1
            except Exception as e:
                logger.error(f"   ❌ {code}: {e}")
        
        logger.info(f"   ✅ {ok}/{len(entries)} uploaded")
        total += ok

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Done! {total} entries → reference_data (model: {model_id})")


def _s(row, col_name) -> str:
    """Safe string getter for DataFrame row."""
    if not col_name:
        return ""
    val = row.get(col_name) if isinstance(row, dict) else row.get(col_name, None)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()

def _find_col(columns, candidates: list) -> str:
    """Find a column name that contains any of the candidate strings."""
    for col in columns:
        for c in candidates:
            if c in str(col):
                return col
    return ""

def _valid_alias(alias: str) -> bool:
    """Filter out garbage alias values."""
    if not alias or len(alias) < 2:
        return False
    if "?" in alias or "아닌지" in alias:
        return False
    return True


if __name__ == "__main__":
    asyncio.run(main())
