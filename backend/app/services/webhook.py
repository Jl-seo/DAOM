
import logging
import threading
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

def send_webhook_background(url: str, payload: Dict[str, Any]):
    """
    Send a webhook POST request in a background thread (fire-and-forget).
    Safe to call from synchronous code.
    """
    def _send():
        try:
            logger.info(f"[Webhook] Sending payload to {url}...")
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code >= 400:
                logger.error(f"[Webhook] Failed with status {response.status_code}: {response.text}")
            else:
                logger.info(f"[Webhook] Success! Status: {response.status_code}")
        except Exception as e:
            logger.error(f"[Webhook] Request failed: {e}")

    # Start independent thread
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
