import sys, os, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.extraction.beta_pipeline import BetaPipeline

# Mock 26 column text
headers = "| " + " | ".join([f"Col{i}" for i in range(26)]) + " |\n"
sep = "|---" * 26 + "|\n"
text = headers + sep
for i in range(50):
    text += "| " + " | ".join([f"Val{i}_{c}" for c in range(26)]) + " |\n"

chunks = BetaPipeline._chunk_with_headers(text, 4000)
print(f"Total Chunks: {len(chunks)}")
for i, c in enumerate(chunks[:2]):
    print(f"--- Chunk {i} ---")
    print(c[:200] + "...\n")
