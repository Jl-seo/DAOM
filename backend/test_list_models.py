import asyncio
import httpx
from app.core.config import settings

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"

async def main():
    print("Testing HTTP to list models/deployments...")
    async with httpx.AsyncClient() as client:
        # Check standard OpenAI deployments route
        res1 = await client.get(
            f"{endpoint}/openai/deployments?api-version=2024-02-15-preview",
            headers={"api-key": api_key}
        )
        print("Azure Deployments JSON:", res1.text)

        # Check MaaS /models route
        res2 = await client.get(
            f"{endpoint}/models?api-version=2024-05-01-preview",
            headers={"api-key": api_key}
        )
        print("Models List JSON:", res2.text)

if __name__ == "__main__":
    asyncio.run(main())
