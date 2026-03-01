import pandas as pd
excel_data = pd.read_excel("dummy_6000.xlsx", sheet_name=None, header=None, engine="calamine")
for sheet, df in excel_data.items():
    print(f"Sheet: {sheet}, Rows: {len(df)}")
