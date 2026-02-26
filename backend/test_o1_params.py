import asyncio
from openai import AsyncAzureOpenAI

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"
model = "gpt-5.1"

async def main():
    client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-15-preview"
    )

    try:
        # Testing what DAOM's code exactly sends: max_completion_tokens + temperature + response_format
        res = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hello please return json"}],
            max_completion_tokens=100,
            temperature=0, # DAOM has this
            response_format={"type": "json_object"} # DAOM has this too
        )
        print("SUCCESS:", res.choices[0].message.content)
    except Exception as e:
        print("FAILED:", type(e).__name__, e)

if __name__ == "__main__":
    asyncio.run(main())
