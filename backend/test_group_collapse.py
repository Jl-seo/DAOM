import json
import pandas as pd

# Mock model fields
class MockField:
    def __init__(self, key, type):
        self.key = key
        self.type = type

class MockModel:
    def __init__(self, fields):
        self.fields = fields

model = MockModel([
    MockField('procurement', 'text'),
    MockField('rate_basis', 'text'),
    MockField('sc_number', 'text'),
    MockField('shipping_rates_extracted', 'table')
])

# Mock multiple rows returned by DuckDB
json_results = [
    {
        "procurement": "FK",
        "rate_basis": "ETD",
        "sc_number": "Amend",
        "shipping_rates_extracted": '[{"POL": "BUSAN", "POD": "LA"}]'
    },
    {
        "procurement": "FK",
        "rate_basis": "ETD",
        "sc_number": "Amend",
        "shipping_rates_extracted": '[{"POL": "GWANGYANG", "POD": "NY"}]'
    },
    {
        "procurement": None,
        "rate_basis": "",
        "sc_number": "Amend2",
        "shipping_rates_extracted": None
    }
]

table_keys = {f.key for f in model.fields if f.type == 'table'}

collapsed_result = {}
for row in json_results:
    for k, v in row.items():
        if pd.isna(v) or v is None:
            continue
            
        # Handle Table Fields
        if k in table_keys:
            if k not in collapsed_result:
                collapsed_result[k] = []
            
            if isinstance(v, str):
                try:
                    parsed_v = json.loads(v)
                    if isinstance(parsed_v, list):
                        collapsed_result[k].extend(parsed_v)
                    else:
                        collapsed_result[k].append(parsed_v)
                except json.JSONDecodeError:
                    collapsed_result[k].append({"value": v})
            elif isinstance(v, list):
                collapsed_result[k].extend(v)
            else:
                collapsed_result[k].append(v)
        
        # Handle Text Fields
        else:
            if k not in collapsed_result or collapsed_result[k] == "" or collapsed_result[k] is None:
                if v:
                    collapsed_result[k] = v

for f in model.fields:
    if f.key not in collapsed_result:
        collapsed_result[f.key] = [] if f.type == 'table' else ""

print(json.dumps(collapsed_result, indent=2))
