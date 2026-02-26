import asyncio
import httpx
from openai import AsyncOpenAI

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"
model = "claude-sonnet-4-5"

async def main():
    print("Testing HTTP directly to see exact error...")
    async with httpx.AsyncClient() as client:
        # Try Azure OpenAI route
        res1 = await client.post(
            f"{endpoint}/openai/deployments/{model}/chat/completions?api-version=2024-02-15-preview",
            headers={"api-key": api_key},
            json={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 10}
        )
        print("Azure Route Status:", res1.status_code)
        print("Azure Route Response:", res1.text)

        # Try Models route (MaaS)
        res2 = await client.post(
            f"{endpoint}/models/chat/completions?api-version=2024-05-01-preview",
            headers={"api-key": api_key},
            json={"model": model, "messages": [{"role": "user", "content": "hello"}], "max_tokens": 10}
        )
        print("Models Route Status:", res2.status_code)
        print("Models Route Response:", res2.text)

if __name__ == "__main__":
    asyncio.run(main())
