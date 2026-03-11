import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv(".env")
from app.db.cosmos import init_cosmos, get_models_container, close_cosmos

async def main():
    await init_cosmos()
    models_container = get_models_container()
    
    model_id = '99d08133-f8be-44f2-beb8-98a749e0a9a0'
    model_query = f"SELECT * FROM c WHERE c.id = '{model_id}'"
    model_items = [m async for m in models_container.query_items(query=model_query)]
    
    if model_items:
        model = model_items[0]
        print("Model Name:", model.get('name'))
        print("Comparison Settings:", json.dumps(model.get('comparison_settings'), ensure_ascii=False, indent=2))
    else:
        print("Model not found.")
        
    await close_cosmos()

if __name__ == "__main__":
    asyncio.run(main())
