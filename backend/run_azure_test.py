import sys
import os

sys.path.append(os.path.dirname(__file__))

def main():
    import uvloop
    import asyncio
    
    # We load relative to backend folder
    sys.path.append(os.getcwd())
    
    # Import from the original file I wrote
    from test_azure_excel import test_extraction
    asyncio.run(test_extraction())

if __name__ == "__main__":
    main()
