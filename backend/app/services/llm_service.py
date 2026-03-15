"""
LLM Service — Unified Multi-Model Abstraction Layer
=====================================================
Provides a single interface for calling LLMs regardless of the underlying provider.

Supported Providers:
- Azure OpenAI (GPT-4o, GPT-4.1, GPT-5.x, etc.) via `openai.AsyncAzureOpenAI`
- Anthropic (Claude) via Azure AI Foundry native `/anthropic/v1/messages` endpoint

The routing is automatic based on the model/deployment name:
- "gpt-*", "o1/o3/o4-*" → AsyncAzureOpenAI (supports Strict JSON Schema, Structured Outputs)
- "claude-*" → Anthropic Messages API on Azure AI Foundry
"""
import json
import logging
import re
from typing import Optional, List, Dict, Any

import httpx
from app.core.config import settings
from app.services.llm import get_openai_client, get_current_model

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Model Type Detection
# ──────────────────────────────────────────────

_ANTHROPIC_PREFIXES = ("claude",)

_NON_OPENAI_PREFIXES = (
    "claude",
    "meta",
    "llama",
    "mistral",
    "cohere",
    "command",
    "jamba",
    "phi",
    "deepseek",
    "grok",
    "kimi",
)

def is_openai_model(model_name: str) -> bool:
    """Returns True if the model should be routed to AsyncAzureOpenAI."""
    if not model_name:
        return True  # Default to OpenAI
    name_lower = model_name.lower().strip()
    # Explicit GPT/O-series check
    if name_lower.startswith("gpt") or name_lower.startswith("o1") or name_lower.startswith("o3") or name_lower.startswith("o4"):
        return True
    # Check against known non-OpenAI prefixes
    for prefix in _NON_OPENAI_PREFIXES:
        if name_lower.startswith(prefix):
            return False
    # Default: treat as OpenAI (safe fallback for custom deployment names)
    return True


def is_anthropic_model(model_name: str) -> bool:
    """Returns True if the model is Anthropic/Claude and needs the /anthropic/v1/messages endpoint."""
    if not model_name:
        return False
    name_lower = model_name.lower().strip()
    return any(name_lower.startswith(p) for p in _ANTHROPIC_PREFIXES)


def reset_inference_client():
    """Reset any cached state (called when model changes). Currently a no-op since we use httpx per-request."""
    pass


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

    if is_anthropic_model(model_name):
        return await _call_anthropic(messages, model_name, temperature, max_tokens)
    elif is_openai_model(model_name):
        return await _call_openai(messages, model_name, temperature, max_tokens, response_format, seed)
    else:
        # Other non-OpenAI models: try OpenAI SDK path first (some work via /openai/deployments)
        return await _call_openai(messages, model_name, temperature, max_tokens, response_format, seed)


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

    return _extract_openai_response(response)


async def _call_anthropic(
    messages: List[Dict[str, str]],
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """
    Route to Anthropic Claude via Azure AI Foundry native endpoint.
    
    Azure AI Foundry hosts Claude models at: {endpoint}/anthropic/v1/messages
    Auth: x-api-key header with the same API key used for Azure OpenAI.
    The model field should be the DEPLOYMENT NAME (e.g., "claude-sonnet-4-5").
    response_format is NOT supported — JSON extraction is done via prompt engineering.
    """
    endpoint = (settings.AZURE_OPENAI_ENDPOINT or settings.AZURE_AIPROJECT_ENDPOINT or "").rstrip("/")
    api_key = settings.AZURE_OPENAI_API_KEY

    if not endpoint or not api_key:
        raise ValueError("Azure AI endpoint and API key must be configured for Anthropic models")

    url = f"{endpoint}/anthropic/v1/messages"

    # Convert messages: Anthropic requires system to be separate from messages
    system_content = ""
    anthropic_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_content += content + "\n"
        else:
            anthropic_messages.append({"role": role, "content": content})

    # Ensure JSON output via system prompt (Anthropic doesn't support response_format)
    if system_content and "json" not in system_content.lower():
        system_content += "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no code fences, no explanation."

    payload: Dict[str, Any] = {
        "model": model_name,
        "max_tokens": max_tokens,
        "messages": anthropic_messages,
    }
    if temperature > 0:
        payload["temperature"] = temperature
    if system_content.strip():
        payload["system"] = system_content.strip()

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    logger.info(f"[LLM-Service] Anthropic route → model={model_name} at {url}")

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=120.0)

    if response.status_code != 200:
        error_body = response.text[:500]
        logger.error(f"[LLM-Service] Anthropic API error {response.status_code}: {error_body}")
        raise RuntimeError(f"Anthropic API error {response.status_code}: {error_body}")

    data = response.json()

    # Extract content from Anthropic's response format
    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block["text"]

    # Strip markdown code fences if Claude wraps JSON in them
    content = _strip_code_fences(content)

    finish_reason = data.get("stop_reason", "end_turn")
    usage = data.get("usage", {})

    return {
        "content": content,
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
        "finish_reason": finish_reason,
    }


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json...```) that Claude sometimes wraps around JSON."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1:]
        else:
            text = text[3:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _extract_openai_response(response) -> Dict[str, Any]:
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
