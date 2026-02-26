import asyncio
import httpx

endpoint = "https://jlseo4883-resource.services.ai.azure.com"
api_key = "5ut9nvyvQhz70UT7jiHw5jbfQxxnGV7xwgCXC6QUpMm9Q4w8zYE3JQQJ99BLACHYHv6XJ3w3AAAAACOG7lBd"
deployment_name = "claude-sonnet-4-5"

async def main():
    async with httpx.AsyncClient() as client:
        # According to Azure AI Studio documentation, MaaS Inference endpoints for Serverless usually accept:
        # /models/chat/completions (OpenAI compatible)
        # But wait, AnthropicFoundry hits /v1/messages... let's see what happens if we do that directly
        
        # Scenario 1: Azure AI Services model inference with OpenAI compat layer
        url1 = f"{endpoint}/models/chat/completions?api-version=2024-05-01-preview"
        print(f"Testing OpenAI Schema via Models Route: {url1}")
        res1 = await client.post(
            url1,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": deployment_name,
                "messages": [{"role": "user", "content": "Hello!"}],
                "max_tokens": 10
            }
        )
        print("Status:", res1.status_code)
        print("Response:", res1.text)
        print("-" * 50)

        # Scenario 2: What AnthropicFoundry SDK actually uses (Anthropic Schema)
        url2 = f"{endpoint}/v1/messages" # Or maybe without v1?
        # But wait, it might expect api-key in 'x-api-key' or just auth.
        # Let's try standard anthropic format with api-key header just in case.
        print(f"Testing Anthropic Schema via v1/messages: {url2}")
        res2 = await client.post(
            url2,
            headers={"api-key": api_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01"},
            json={
                "model": deployment_name,
                "messages": [{"role": "user", "content": "Hello!"}],
                "max_tokens": 10
            }
        )
        print("Status:", res2.status_code)
        print("Response:", res2.text)

if __name__ == "__main__":
    asyncio.run(main())
