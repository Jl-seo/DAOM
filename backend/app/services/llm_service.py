"""
LLM Service — Unified Multi-Model Abstraction Layer
=====================================================
Provides a single interface for calling LLMs regardless of the underlying provider.

Supported Providers:
- Azure OpenAI (GPT-4o, GPT-4.1, etc.) via `openai.AsyncAzureOpenAI`
- Azure AI Inference (Claude, Llama, Mistral, etc.) via `azure.ai.inference.aio.ChatCompletionsClient`

The routing is automatic based on the model/deployment name:
- "gpt-*" → AsyncAzureOpenAI (supports Strict JSON Schema, Structured Outputs)
- "claude-*", "meta-*", "mistral-*", etc. → ChatCompletionsClient (json_object mode only)
"""
import json
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncAzureOpenAI
from app.core.config import settings
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Model Type Detection
# ──────────────────────────────────────────────

# Prefixes that indicate non-OpenAI models deployed on Azure AI Foundry
_NON_OPENAI_PREFIXES = (
    "claude",
    "meta",
    "llama",
    "mistral",
    "cohere",
    "command",
    "jamba",
    "phi",
)

def is_openai_model(model_name: str) -> bool:
    """Returns True if the model should be routed to AsyncAzureOpenAI."""
    if not model_name:
        return True  # Default to OpenAI
    name_lower = model_name.lower().strip()
    # Explicit GPT check
    if name_lower.startswith("gpt") or name_lower.startswith("o1") or name_lower.startswith("o3") or name_lower.startswith("o4"):
        return True
    # Check against known non-OpenAI prefixes
    for prefix in _NON_OPENAI_PREFIXES:
        if name_lower.startswith(prefix):
            return False
    # Default: treat as OpenAI (safe fallback for custom deployment names)
    return True


# ──────────────────────────────────────────────
# Azure AI Inference Client (Singleton)
# ──────────────────────────────────────────────

_inference_client = None

def get_inference_client():
    """
    Singleton Azure AI Inference ChatCompletionsClient.
    Uses AzureKeyCredential with the same API key as OpenAI for simplicity.
    """
    global _inference_client
    if _inference_client is not None:
        return _inference_client

    try:
        from azure.ai.inference.aio import ChatCompletionsClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError:
        logger.error("[LLM-Service] azure-ai-inference is not installed. Run: pip install azure-ai-inference")
        raise ImportError("azure-ai-inference package is required for non-OpenAI models. Install with: pip install azure-ai-inference")

    endpoint = settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT
    endpoint = endpoint.rstrip('/')
    api_key = settings.AZURE_OPENAI_API_KEY

    if not endpoint or not api_key:
        raise ValueError("Azure AI endpoint and API key must be configured for Inference Client")

    logger.info(f"[LLM-Service] Creating Inference Client — Endpoint: {endpoint}")

    _inference_client = ChatCompletionsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )
    return _inference_client


def reset_inference_client():
    """Reset the inference client singleton (called when model changes)."""
    global _inference_client
    if _inference_client is not None:
        # Schedule close in background — don't block
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_inference_client.close())
            else:
                loop.run_until_complete(_inference_client.close())
        except Exception:
            pass
    _inference_client = None


# ──────────────────────────────────────────────
# Unified LLM Call
# ──────────────────────────────────────────────

async def call_llm_unified(
    messages: List[Dict[str, str]],
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    response_format: Optional[Dict] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Unified LLM call that routes to the correct provider based on model name.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model_name: Deployment name. If None, uses current global model.
        temperature: Sampling temperature.
        max_tokens: Max completion tokens.
        response_format: {"type": "json_object"} or {"type": "json_schema", ...}
        seed: Optional seed for reproducibility.

    Returns:
        Raw response dict with:
        - "content": str (response text)
        - "usage": {"prompt_tokens", "completion_tokens", "total_tokens"}
        - "finish_reason": str
    """
    if model_name is None:
        model_name = get_current_model()

    if is_openai_model(model_name):
        return await _call_openai(messages, model_name, temperature, max_tokens, response_format, seed)
    else:
        return await _call_inference(messages, model_name, temperature, max_tokens, response_format)


async def _call_openai(
    messages: List[Dict[str, str]],
    model_name: str,
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict],
    seed: Optional[int],
) -> Dict[str, Any]:
    """Route to AsyncAzureOpenAI (GPT models)."""
    client = get_openai_client()

    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }

    if response_format:
        kwargs["response_format"] = response_format
    if seed is not None:
        kwargs["seed"] = seed

    logger.info(f"[LLM-Service] OpenAI route → model={model_name}")

    try:
        response = await client.chat.completions.create(**kwargs)
    except Exception as e:
        error_str = str(e).lower()
        # Fallback: if strict JSON Schema is not supported, retry with json_object
        if response_format and response_format.get("type") == "json_schema":
            if any(term in error_str for term in ["json_schema", "response_format", "unsupported", "400"]):
                logger.warning(f"[LLM-Service] Strict JSON Schema failed, falling back to json_object: {e}")
                kwargs["response_format"] = {"type": "json_object"}
                response = await client.chat.completions.create(**kwargs)
            else:
                raise
        else:
            raise

    return _extract_response(response)


async def _call_inference(
    messages: List[Dict[str, str]],
    model_name: str,
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict],
) -> Dict[str, Any]:
    """Route to Azure AI Inference ChatCompletionsClient (Claude, Llama, etc.)."""
    client = get_inference_client()

    # Convert standard message dicts to azure-ai-inference message objects
    from azure.ai.inference.models import (
        SystemMessage,
        UserMessage,
        AssistantMessage,
    )

    converted_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            converted_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            converted_messages.append(AssistantMessage(content=content))
        else:
            converted_messages.append(UserMessage(content=content))

    kwargs = {
        "messages": converted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "model": model_name,
    }

    # Azure AI Inference supports response_format for some models
    # but NOT strict json_schema — always use json_object or omit
    if response_format:
        # Force to json_object for non-OpenAI models (strict schema not supported)
        kwargs["response_format"] = {"type": "json_object"}

    logger.info(f"[LLM-Service] Inference route → model={model_name}")

    response = await client.complete(**kwargs)

    # Extract response in unified format
    content = response.choices[0].message.content if response.choices else ""
    finish_reason = response.choices[0].finish_reason if response.choices else "stop"

    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return {
        "content": content,
        "usage": usage,
        "finish_reason": str(finish_reason),
    }


def _extract_response(response) -> Dict[str, Any]:
    """Extract unified response dict from AsyncAzureOpenAI response."""
    content = response.choices[0].message.content if response.choices else ""
    finish_reason = getattr(response.choices[0], "finish_reason", "stop") if response.choices else "stop"

    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return {
        "content": content,
        "usage": usage,
        "finish_reason": str(finish_reason),
    }


# ──────────────────────────────────────────────
# Legacy Compatibility: AzureOpenAIService class
# Used by vibe_dictionary.py
# ──────────────────────────────────────────────

class AzureOpenAIService:
    """
    Simple wrapper for backward compatibility with existing code
    that imports AzureOpenAIService (e.g., vibe_dictionary.py).
    """

    def __init__(self, deployment_name: str = "gpt-4o"):
        self.deployment_name = deployment_name

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        """Simple chat completion that returns the content string."""
        result = await call_llm_unified(
            messages=messages,
            model_name=self.deployment_name,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format or {"type": "json_object"},
        )
        return result.get("content", "")
