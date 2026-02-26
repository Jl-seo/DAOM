import asyncio
import os
from openai import AsyncAzureOpenAI

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"

models_to_test = ["gpt-4.1", "gpt-5.1", "gpt-5.2", "claude-sonnet-4-5"]

async def main():
    client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-15-preview"
    )

    for model in models_to_test:
        print(f"--- Testing {model} ---")
        try:
            res = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=10
            )
            print(f"SUCCESS: {model}")
        except Exception as e:
            print(f"FAILED: {model} - {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
