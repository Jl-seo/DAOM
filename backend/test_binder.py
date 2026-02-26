import pandas as pd
import duckdb
import re

# Simulate problematic columns from user screenshot
df = pd.DataFrame({
    'Service Contract No.:': ['123', '456'],
    '환자 이름!!': ['홍길동', '김철수'],
    ' A (B) c ': [1, 2]
})

clean_cols = []
for col in df.columns:
    c = str(col).strip()
    c = re.sub(r'[^a-zA-Z0-9가-힣_]', '_', c)
    c = re.sub(r'_+', '_', c)
    c = c.strip('_')
    if not c: c = f"col_{len(clean_cols)}"
    clean_cols.append(c)

df.columns = clean_cols
print("Cleaned Columns:", list(df.columns))

con = duckdb.connect(':memory:')
con.execute("CREATE TABLE raw_data AS SELECT * FROM df")
print("DuckDB Schema:")
print(con.execute("DESCRIBE raw_data").df()[['column_name']])
con.close()
