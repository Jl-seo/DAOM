import asyncio
from app.core.config import settings
from azure.cosmos.aio import CosmosClient
import pprint

async def main():
    async with CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY) as client:
        database = client.get_database_client(settings.COSMOS_DATABASE)
        container = database.get_container_client('ExtractedData')
        
        # We look for P300 status items representing stuck extractions
        query = "SELECT TOP 10 c.id, c.status, c.file_url, c.error, c.logs, c._ts FROM c WHERE c.status = 'P300' ORDER BY c._ts DESC"
        items = []
        async for item in container.query_items(query=query):
            items.append(item)
            
        print(f"Found {len(items)} stuck jobs (P300):")
        for item in items:
            pprint.pprint(item)
            print("---")

asyncio.run(main())
