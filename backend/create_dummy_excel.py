import pandas as pd

# Create dummy data matching SC102394-41.xlsx as seen in Mapper logs
# "The headers are: 'Trade', 'R.GP', 'RCT', 'POL', 'POD', 'DLY', 'SVC Mode', 'CUR', 'Unit', '2SD', 'Cargo Type', '4SD', 'Cargo Type', '4SH', 'Cargo Type', 'Effective Date', 'Expired Date', 'AMD'."

data = {
    'Trade': ['TRD1', 'TRD2', 'TRD3'],
    'R.GP': ['A', 'B', 'C'],
    'RCT': ['1', '2', '3'],
    'POL': ['PUSAN', 'PUSAN', 'PUSAN'],
    'POD': ['USWC', 'USEC', 'BOSTON'],
    'DLY': ['D1', 'D2', 'D3'],
    'SVC Mode': ['CY/CY', 'CY/CY', 'CY/CY'],
    'CUR': ['USD', 'USD', 'USD'],
    'Unit': ['BOX', 'BOX', 'BOX'],
    '2SD': ['GC', 'GC', 'GC'],
    'Cargo Type': ['FAK', 'FAK', 'FAK'],
    '4SD': ['GC', 'GC', 'GC'],
    'Cargo Type.1': ['FAK', 'FAK', 'FAK'],
    '4SH': ['GC', 'GC', 'GC'],
    'Cargo Type.2': ['FAK', 'FAK', 'FAK'],
    'Effective Date': ['2026-01-01', '2026-01-01', '2026-01-01'],
    'Expired Date': ['2026-12-31', '2026-12-31', '2026-12-31'],
    'AMD': ['0', '0', '0']
}

df = pd.DataFrame(data)

# Add some empty rows at the top to simulate the real file
df.index = df.index + 550

with pd.ExcelWriter('dummy_rates.xlsx', engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Rates', index=False, startrow=549)

print("Created dummy_rates.xlsx successfully.")
