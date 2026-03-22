import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(".env")

from app.db.cosmos import db, init_cosmos, get_container, EXTRACTIONS_CONTAINER

async def main():
    await init_cosmos()
    container = get_container(EXTRACTIONS_CONTAINER)
    
    query = "SELECT c.file_name, c.status, c.raw_extracted FROM c WHERE CONTAINS(c.file_name, '효성') ORDER BY c._ts DESC OFFSET 0 LIMIT 10"
    results = container.query_items(query=query)
    
    async for item in results:
        print(item.get("file_name"))

if __name__ == "__main__":
    asyncio.run(main())
