"""Optional model access.

The demo's default and fully supported path is ``LLM_PROVIDER=none``: every
agent produces deterministic, rule-derived output and the whole walkthrough
works offline. This module is the *enhancement* path (ADR-0005).

Three properties are enforced here rather than trusted to call sites:

* Redaction is applied and re-checked immediately before send.
* Any failure degrades to fixture mode instead of surfacing an error. An EOC
  tool that breaks when a vendor endpoint is slow is worse than one that says
  "model unavailable, here is the rule-based answer".
* The prompt is never persisted, only its SHA-256 — enough to prove which
  inputs produced an output without duplicating incident text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

from app.agents.redact import RedactionMap, assert_clean, redact
from app.config import get_settings

_TIMEOUT_SECONDS = 20.0

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
}


@dataclass(frozen=True)
class LlmResult:
    text: str
    model_id: str
    ok: bool
    error: str = ""


def prompt_hash(prompt: str) -> str:
    """SHA-256 of the exact prompt sent, for the audit trail."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def is_enabled() -> bool:
    return get_settings().llm_enabled


def model_id() -> str:
    settings = get_settings()
    if not settings.llm_enabled:
        return "deterministic-rules-v1"
    return settings.llm_model or _DEFAULT_MODELS.get(settings.llm_provider, "unknown")


async def complete(
    *,
    system: str,
    user: str,
    mapping: RedactionMap | None = None,
    max_tokens: int = 900,
) -> LlmResult:
    """Send a redacted prompt to the configured provider.

    Returns ``ok=False`` on any problem. Callers treat that as "use the
    deterministic path", so there is no error branch to forget.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        return LlmResult(text="", model_id="deterministic-rules-v1", ok=False, error="disabled")

    safe_user = redact(user, mapping)
    safe_system = redact(system, mapping)
    try:
        # Tripwire: if redaction missed something we do not send at all.
        assert_clean(safe_user)
        assert_clean(safe_system)
    except ValueError as exc:
        return LlmResult(text="", model_id=model_id(), ok=False, error=str(exc))

    try:
        if settings.llm_provider == "anthropic":
            return await _anthropic(safe_system, safe_user, max_tokens)
        if settings.llm_provider == "openai":
            return await _openai(safe_system, safe_user, max_tokens)
        return LlmResult(text="", model_id=model_id(), ok=False, error="unknown provider")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # Degrade, never raise: the caller falls back to fixture mode.
        return LlmResult(text="", model_id=model_id(), ok=False, error=f"{type(exc).__name__}")


async def _anthropic(system: str, user: str, max_tokens: int) -> LlmResult:
    settings = get_settings()
    model = settings.llm_model or _DEFAULT_MODELS["anthropic"]
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        response.raise_for_status()
        body = response.json()
        text = "".join(block.get("text", "") for block in body.get("content", []))
        return LlmResult(text=text.strip(), model_id=model, ok=bool(text.strip()))


async def _openai(system: str, user: str, max_tokens: int) -> LlmResult:
    settings = get_settings()
    model = settings.llm_model or _DEFAULT_MODELS["openai"]
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        body = response.json()
        text = body["choices"][0]["message"]["content"]
        return LlmResult(text=(text or "").strip(), model_id=model, ok=bool(text))
