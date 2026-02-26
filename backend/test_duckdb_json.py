import duckdb
import pandas as pd
import json

df = pd.DataFrame({
    'category': ['A', 'A', 'B', 'B', 'A'],
    'value': [10, 20, 30, 40, 50]
})

con = duckdb.connect(':memory:')
con.execute("CREATE TABLE raw_data AS SELECT * FROM df")

queries = [
    # Basic json_group_array - SHOULD WORK
    "SELECT category, json_group_array(value) as values FROM raw_data GROUP BY category",
    
    # Nested json_object inside json_group_array - SHOULD WORK
    "SELECT category, json_group_array(json_object('val', value)) as items FROM raw_data GROUP BY category",
    
    # What the LLM likely did: trying to FILTER or order inside the macro
    "SELECT category, json_group_array(value ORDER BY value DESC) as values FROM raw_data GROUP BY category",
    
    # Workaround using CTE
    """
    WITH ordered AS (SELECT category, value FROM raw_data ORDER BY value DESC)
    SELECT category, json_group_array(value) as values FROM ordered GROUP BY category
    """
]

print("Testing DuckDB json_group_array behavior:\n")
for idx, q in enumerate(queries):
    print(f"--- Query {idx+1} ---")
    print(q.strip())
    try:
        res = con.execute(q).df()
        print("✅ SUCCESS")
        print(res)
    except Exception as e:
        print(f"❌ ERROR: {e}")
    print("\n")
    
con.close()
