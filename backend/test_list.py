import asyncio
from app.services.dictionary_service import get_dictionary_service

async def main():
    service = get_dictionary_service()
    categories = await service.list_categories()
    print("Categories:", categories)

if __name__ == "__main__":
    asyncio.run(main())
