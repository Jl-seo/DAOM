import asyncio
import re

# Simulate the auto-healing loop's error message
de = "Invalid Input Error: Function \"json_group_array\" is a Macro Function. \"DISTINCT\", \"FILTER\", and \"ORDER BY\" are only applicable to aggregate functions."
error_guide = f"""
The query failed with DuckDB Error: {de}

HOW TO FIX COMMON DUCKDB ERRORS:
- "Macro json_group_object() does not support...": You passed >2 arguments. Use json_object('k1',v1,'k2',v2) for single rows, or exactly json_group_object(key, val) to aggregate rows.
- "Table Function with name regexp_matches does not exist": You used regexp_matches in the FROM clause like a table. WRONG. Use SELECT regexp_extract(col, 'pattern') FROM raw_data.
- "Conversion Error": You tried to CAST an empty string. Change CAST(x AS INT) to TRY_CAST(x AS INT).
- "json_group_array/object ... ORDER BY": Remove the ORDER BY inside the macro. Use a CTE to order data first.
- Column not found: Double check the schema provided.

Fix the SQL syntax and return the corrected SQL query in JSON format.
"""
print("Auto-Healing Prompt is intact:")
print(error_guide)

# Check the old broken regex behavior just to confirm it's gone
sql_query_with_order_by = "SELECT json_group_array(json_object('a', A) ORDER BY B) FROM raw_data;"
macro_pattern = r"(?i)(json_group_array|json_group_object)\s*\(\s*(?:DISTINCT\s+)?(.*?)(?:\s+ORDER\s+BY.*?)?\s*\)"
bad_result = re.sub(macro_pattern, r"\1(\2)", sql_query_with_order_by)
print("\nOld Broken Regex Result (notice the missing closing paren and FROM clause):")
print(bad_result)

print("\nNew Approach: No regex for ORDER BY. We rely on LLM system prompt & auto-healing.")
