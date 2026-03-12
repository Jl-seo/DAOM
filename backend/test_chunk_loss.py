import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

pipe = BetaPipeline(None)

# Create a mock 20 row table
mock_markdown = ""
mock_markdown += "## Document Title\n"
mock_markdown += "| Header A | Header B |\n"
mock_markdown += "|---|---|\n"
for i in range(1, 21):
    mock_markdown += f"| Row {i} Col A | Row {i} Col B |\n"

# Force it to chunk
# 20 rows * 30 chars = ~600 chars. Let's chunk at 200 chars.
chunks = pipe._chunk_with_headers(mock_markdown, 200)

for idx, chunk in enumerate(chunks):
    print(f"=== CHUNK {idx+1} ===")
    print(chunk)
    print("="*20)

