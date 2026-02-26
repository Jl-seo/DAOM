import asyncio
import os
from openai import AsyncAzureOpenAI, AsyncOpenAI

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"
model = "claude-sonnet-4-5"

async def main():
    print("Testing standard AzureOpenAI client...")
    try:
        client1 = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-02-15-preview"
        )
        res = await client1.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print("client1 success!", res.choices[0].message.content)
    except Exception as e:
        print("client1 failed:", e)

    print("\nTesting AsyncOpenAI with /models/v1 base url...")
    try:
        client2 = AsyncOpenAI(
            base_url=f"{endpoint}/models/v1",
            api_key=api_key
        )
        res = await client2.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print("client2 success!", res.choices[0].message.content)
    except Exception as e:
        print("client2 failed:", e)

    print("\nTesting AsyncOpenAI with /models base url...")
    try:
        client3 = AsyncOpenAI(
            base_url=f"{endpoint}/models",
            api_key=api_key
        )
        res = await client3.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print("client3 success!", res.choices[0].message.content)
    except Exception as e:
        print("client3 failed:", e)

asyncio.run(main())
