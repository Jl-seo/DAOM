import re

queries = [
    "SELECT category, json_group_array(value ORDER BY value DESC) as v FROM raw",
    "SELECT json_group_array(DISTINCT value ORDER BY date) FROM raw",
    "SELECT json_group_object(k, v ORDER BY k) FROM raw",
    "SELECT a, b FROM table"
]

def auto_fix_sql(sql):
    fixed = sql
    
    # Fix json_group_array(X ORDER BY Y) -> json_group_array(X)
    # This strips DISTINCT and ORDER BY from within json_group_array and json_group_object
    pattern = r"(json_group_array|json_group_object)\s*\(\s*(?:DISTINCT\s+)?(.*?)(?:\s+ORDER\s+BY.*?)?\s*\)"
    
    fixed = re.sub(pattern, r"\1(\2)", fixed, flags=re.IGNORECASE)
    
    return fixed

for q in queries:
    print("ORIGINAL:", q)
    print("FIXED:   ", auto_fix_sql(q))
    print("-")
