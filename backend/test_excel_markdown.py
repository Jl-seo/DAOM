import sys
import os

# Setup path so we can import the module
from app.services.extraction.excel_parser import ExcelParser

# Mock some sparse data
rows = [
    ["POL", "POD", "20DC", "40DC", "Remark"],
    ["KRPUS", "CNPVG", "100", "", ""],
    ["KRPUS", "USLAX", "200", "400", "Express"],
    ["KRPUS", "JPTYO", "", "", ""],
    ["", "", "", "", ""]
]

md = ExcelParser._rows_to_markdown(rows, "TestSheet")
print("=== GENERATED MARKDOWN ===")
print(md)

# Verify alignment
lines = md.split('\n')
header = lines[1] # | C1 | C2 | C3 | C4 | C5 |
col_count = header.count('|') - 1

print(f"\nExpected {col_count} columns per row.")
for idx, line in enumerate(lines[3:]):
    if line.strip():
        actual_cols = line.count('|') - 1
        if actual_cols != col_count:
            print(f"❌ MISMATCH on row {idx+1}: expected {col_count}, got {actual_cols} -> {line}")
            sys.exit(1)

print("✅ ALL ROWS PERFECTLY ALIGNED!")
