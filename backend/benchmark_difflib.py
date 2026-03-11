import time
from difflib import SequenceMatcher

# Mock 20000 OCR words
word_choices = [f"Sample text {i}" for i in range(20000)]

# Mock 100 extracted cells 
cells = [f"Sample text {i*20}" for i in range(100)]

start = time.time()
print("Starting pure python difflib fuzzy matching for 100 cells...")
for i, search_term in enumerate(cells):
    best_score = 0
    for word in word_choices:
        score = SequenceMatcher(None, search_term, word).ratio()
        if score > best_score:
            best_score = score
    if i % 10 == 0:
        print(f"Processed {i} cells in {time.time() - start:.2f} seconds")

end = time.time()
print(f"Total time for 100 cells x 20000 words: {end - start:.2f} seconds")
