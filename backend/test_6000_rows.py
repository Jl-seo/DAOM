import pandas as pd
import json

# Create dummy 6000 row DF
df = pd.DataFrame({
    'POL': [f'Port_{i}' for i in range(6000)],
    'POD': [f'Dest_{i}' for i in range(6000)],
    'Rate': [100 + i for i in range(6000)]
})
df.to_excel('dummy_6000.xlsx', index=False, header=False)

# Build a mock environment for the python engine extract table logic
def extract_tables(filename):
    df = pd.read_excel(filename, header=None, engine='calamine')
    clean_cols = []
    for i in range(len(df.columns)):
        name = ""
        n = i
        while n >= 0:
            name = chr(n % 26 + 65) + name
            n = n // 26 - 1
        clean_cols.append(name)
    df.columns = clean_cols
    df.insert(0, '_sheet_name', 'Sheet1')
    df.insert(0, 'row_id', range(len(df)))
    
    col_map = {"POL": "A", "POD": "B", "Rate": "C"}
    h_id = -1
    
    extracted_table_rows = []
    data_rows = df[df["row_id"] > h_id]
    
    for _, row in data_rows.iterrows():
        row_is_empty = True
        row_data = {}
        for inner_key, excel_col in col_map.items():
            if excel_col in row and pd.notna(row[excel_col]):
                val = str(row[excel_col]).strip()
                if val:
                    row_is_empty = False
                    row_data[inner_key] = {"value": val}
        if not row_is_empty:
            extracted_table_rows.append(row_data)

    print(f"Extracted rows: {len(extracted_table_rows)}")

extract_tables('dummy_6000.xlsx')
