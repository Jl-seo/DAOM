import asyncio
from app.core.config import settings
from azure.cosmos.aio import CosmosClient
import pprint

async def main():
    async with CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY) as client:
        database = client.get_database_client(settings.COSMOS_DATABASE)
        container = database.get_container_client('ExtractedData')
        
        # We query for logs referencing the stuck job ID directly
        job_id = "93126cff-6d42-450c-99d6-033579da92c6"
        query = "SELECT c.id, c.status, c.logs, c._ts FROM c WHERE c.type = 'extraction_log' AND c.job_id = @job_id"
        parameters = [{"name": "@job_id", "value": job_id}]
        
        items = []
        async for item in container.query_items(query=query, parameters=parameters):
            items.append(item)
            
        print(f"Found {len(items)} logs for job {job_id}:")
        for item in items:
            print(f"ID: {item.get('id')} - Status: {item.get('status')} - TS: {item.get('_ts')}")
            for log_entry in item.get('logs', []):
                print(f"  - [{log_entry.get('timestamp')}] {log_entry.get('step')}")
                if log_entry.get('details'):
                    print(f"    Details: {log_entry.get('details')}")
            print("---")

asyncio.run(main())
