import time
from thefuzz import fuzz, process

# Mock 20000 OCR words
word_choices = {i: f"Sample text {i}" for i in range(20000)}

# Mock 1000 extracted cells 
cells = [f"Sample text {i*20}" for i in range(1000)]

start = time.time()
print("Starting fuzzy matching...")
for i, search_term in enumerate(cells):
    process.extractOne(search_term, word_choices, scorer=fuzz.ratio)
    if i % 100 == 0:
        print(f"Processed {i} cells in {time.time() - start:.2f} seconds")

end = time.time()
print(f"Total time for 1000 cells x 20000 words: {end - start:.2f} seconds")
