import pandas as pd
import duckdb

# Create dummy Korean dataframe
df = pd.DataFrame({
    '환자 이름': ['홍길동', '김철수'],
    '방문 일자': ['2023-01-01', '2023-02-01']
})

print("1. Pandas DataFrame with Korean Columns:")
print(df)

# Connect to DuckDB
con = duckdb.connect(':memory:')

try:
    con.execute("CREATE TABLE raw_data AS SELECT * FROM df")
    print("\n2. DuckDB Table created from Pandas")
    
    schema_df = con.execute("DESCRIBE raw_data").df()
    print("\n3. DuckDB Schema (Korean Column Names):")
    print(schema_df[['column_name', 'column_type']])
    
    result = con.execute('SELECT "환자 이름" as patient_name FROM raw_data').df()
    print("\n4. DuckDB SELECT execution (Korean Alias):")
    print(result)
    print("\nSUCCESS!")
except Exception as e:
    print(f"\nERROR: {e}")
finally:
    con.close()
