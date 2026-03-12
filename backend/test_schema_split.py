import json

results = [
    {"guide_extracted": {"my_table": [{"col1": {"value": "row 1"}}]}},
    {"guide_extracted": {"my_table": [{"col1": {"value": "row 2"}}]}},
    {"guide_extracted": {"my_table": [{"col1": {"value": "row 3"}}]}}
]

merged_guide = {}
for res in results:
    for key, val in res.get("guide_extracted", {}).items():
        if isinstance(val, list):
            if key not in merged_guide:
                merged_guide[key] = []
            for row in val:
                if row not in merged_guide[key] and isinstance(row, dict):
                    merged_guide[key].append(row)
        else:
            if key not in merged_guide:
                merged_guide[key] = val

print("OUTPUT OF MERGED GUIDE:")
print(json.dumps(merged_guide, indent=2))
