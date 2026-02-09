
import asyncio
import logging
from app.services.chunked_extraction import merge_chunk_results, ChunkResult
from app.schemas.model import FieldDefinition

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_normalization():
    logger.info("--- Testing Schema Normalization Logic ---")

    # 1. Define Schema (Standard Keys)
    fields = [
        FieldDefinition(key="charge_type", label="Charge Type", type="string"),
        FieldDefinition(key="base_rate_20", label="Base Rate 20'", type="string"),
        FieldDefinition(key="pol_code", label="POL Code", type="string"),
        FieldDefinition(key="line_items", label="Items", type="table") # Table container
    ]

    # 2. Mock Chunk Results (Fragmented/Dirty Keys)
    # Simulator of LLM returning:
    # - "Charge_Type" instead of "charge_type"
    # - "20gp" instead of "base_rate_20" (Wait, my logic handles underscore/case, NOT aliases yet)
    # Let's test what IS implemented: Case & Underscore removal.
    
    # Note: My current implementation only handles:
    # 1. lower().strip()
    # 2. lower().replace("_", "")
    
    # So "Charge_Type" -> "charge_type" (WORKING)
    # "POL Code" -> "polcode" -> matches "pol_code".replace("_", "")?
    # "pol_code" -> "polcode". 
    # If schema key is "pol_code", schema_map["polcode"] = "pol_code".
    # So "POL Code" -> lower/strip "pol code" != "polcode". No match.
    # "POL_CODE" -> "pol_code" (MATCH)
    
    chunk_data = {
        "rows": [
            {
                "Charge_Type": "OFR",       # Should match 'charge_type'
                "chargeType": "OFR_Dup",    # Should match 'charge_type'
                "Base_Rate_20": "100",      # Should match 'base_rate_20'? No, key is base_rate_20.
                                            # "base_rate_20" strip/_ -> "baserate20"
                                            # "Base_Rate_20" strip/_ -> "baserate20" -> MATCH!
                "Unknown_Field": "Discard"  # Should be preserved but not normalized?
            }
        ],
        "_pages": [1]
    }

    result = ChunkResult(chunk_index=0, success=True, extracted_data=chunk_data)

    # 3. Execution
    merged, errors = merge_chunk_results([result], fields)

    # 4. Verification
    logger.info(f"Merged Result Keys: {merged.keys()}")
    
    if "line_items" in merged:
        rows = merged["line_items"]["value"]
        first_row = rows[0]
        logger.info(f"Normalized Row: {first_row}")

        # Assertions
        assert "charge_type" in first_row, "Failed to normalize Charge_Type"
        assert first_row["charge_type"] == "OFR_Dup", "Should take last value or merge?" 
        # Logic: overwrites. Last one wins in the loop of keys.
        
        assert "base_rate_20" in first_row, "Failed to normalize Base_Rate_20"
        assert "Unknown_Field" in first_row, "Should preserve unknown fields"
        
        logger.info("✅ Normalization Test Passed!")
    else:
        logger.error("❌ Failed to merge rows into 'line_items'")

if __name__ == "__main__":
    test_normalization()
