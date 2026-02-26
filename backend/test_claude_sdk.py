import asyncio
from anthropic import AsyncAnthropicFoundry

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"
deployment_name = "claude-sonnet-4-5"

async def main():
    client = AsyncAnthropicFoundry(
        api_key=api_key,
        endpoint=endpoint
    )
    print("Base URL:", client.base_url)
    
    try:
        res = await client.messages.create(
            model=deployment_name,
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print("SDK Success:", res.content[0].text)
    except Exception as e:
        print("SDK Error:", e)

asyncio.run(main())
