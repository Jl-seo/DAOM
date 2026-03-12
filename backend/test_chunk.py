import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

text = ""
for i in range(100):
    if i == 0:
        text += "| Name | Price |\n|---|---|\n"
    text += f"| Item {i} | ${i}.00 |\n"

chunks = BetaPipeline._chunk_with_headers(text, 100)
print(f"Total Chunks: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"--- Chunk {i} ---")
    print(c)
