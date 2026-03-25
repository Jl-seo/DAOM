
import asyncio
import logging
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def send_webhook_async(url: str, payload: Dict[str, Any]):
    """
    Send a webhook POST request asynchronously (fire-and-forget).
    Uses httpx for async HTTP, compatible with FastAPI's event loop.
    """
    try:
        logger.info(f"[Webhook] Sending payload to {url}...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.error(f"[Webhook] Failed with status {response.status_code}: {response.text}")
            else:
                logger.info(f"[Webhook] Success! Status: {response.status_code}")
    except Exception as e:
        logger.error(f"[Webhook] Request failed: {e}")


def send_webhook_background(url: str, payload: Dict[str, Any]):
    """
    Schedule a webhook POST as a fire-and-forget asyncio task.
    Safe to call from both sync and async contexts within a running event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_webhook_async(url, payload))
    except RuntimeError:
        # No running event loop (e.g. called from non-async context) — fallback to thread
        import threading
        import requests as sync_requests

        def _send():
            try:
                response = sync_requests.post(url, json=payload, timeout=10)
                if response.status_code >= 400:
                    logger.error(f"[Webhook] Failed with status {response.status_code}: {response.text}")
                else:
                    logger.info(f"[Webhook] Success! Status: {response.status_code}")
            except Exception as e:
                logger.error(f"[Webhook] Request failed: {e}")

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()
