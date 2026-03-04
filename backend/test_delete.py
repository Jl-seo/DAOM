import asyncio
from app.services.dictionary_service import get_dictionary_service

async def main():
    try:
        service = get_dictionary_service()
        await service.delete_category("test_not_exist")
        print("Success")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
