import asyncio
from app.services.extraction.beta_pipeline import BetaPipeline

# Mock the text of a 10-page PDF
dummy_page = "This is a paragraph of text. " * 500  # ~14000 chars per page
tagged_text = "\n".join([f"=== PAGE {i} ===\n{dummy_page}" for i in range(1, 11)])

print(f"Total Text Length: {len(tagged_text)}")

# Test chunking logic 
chunk_size = 25000
chunks = BetaPipeline._chunk_with_headers(tagged_text, chunk_size)

print(f"Number of chunks generated: {len(chunks)}")
total_chunk_content = sum(len(c) for c in chunks)
print(f"Total Content in Chunks: {total_chunk_content}")
if total_chunk_content < len(tagged_text):
    print("WARNING: Data was lost during chunking!")
else:
    print("Chunking seems to preserve all text length.")
