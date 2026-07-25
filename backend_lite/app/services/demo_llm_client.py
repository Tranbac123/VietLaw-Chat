"""DEMO single-provider LLM client (Anthropic) with an injectable fake.

Exactly one provider, exactly one HTTP call per ``complete`` -- no retry loop,
no prompt-based JSON-repair call (the demo uses Anthropic native Structured
Outputs; see ``ANTHROPIC_OUTPUT_MODE=native_structured_outputs`` in the owner
decision). The request declares ``output_config.format.type = "json_schema"``
with a wire schema equivalent to :class:`DemoResponsePlan`
(``DEMO_RESPONSE_PLAN_JSON_SCHEMA``), so conformance is enforced by the
provider's own decoding constraint, not by prompt text. The response text is
still passed through the local ``DemoResponsePlan`` Pydantic validator before
use -- the API-level schema is defense at the source, not a replacement for
local validation. No provider response is logged verbatim. The API key is read
from the environment and never logged. Tests inject :class:`FakeLLMClient`; no
live credential is required for the automated suite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..contracts.demo_llm import DEMO_RESPONSE_PLAN_JSON_SCHEMA, LLMErrorKind
from ..env_loader import load_local_env

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 1024

# Anthropic native Structured Outputs request block. Declared once at module
# scope so every request uses byte-identical structured-output configuration.
STRUCTURED_OUTPUT_CONFIG: dict = {
    "format": {
        "type": "json_schema",
        "schema": DEMO_RESPONSE_PLAN_JSON_SCHEMA,
    }
}


class LLMClientError(RuntimeError):
    def __init__(self, kind: LLMErrorKind, detail: str = "") -> None:
        super().__init__(kind.value)
        self.kind = kind
        # detail is bounded and must never carry raw provider/user content.
        self.detail = detail[:120]


@dataclass(frozen=True)
class DemoLLMConfig:
    enabled: bool
    provider: str
    model: str | None
    timeout_s: float
    api_key: str | None
    max_tokens: int = _DEFAULT_MAX_TOKENS

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "DemoLLMConfig":
        if env is None:
            load_local_env()
        source = env if env is not None else os.environ
        return cls(
            enabled=_flag(source.get("VIETLAW_LLM_ENABLED")),
            provider=(source.get("VIETLAW_LLM_PROVIDER") or "anthropic").strip().lower(),
            model=(source.get("VIETLAW_LLM_MODEL") or "").strip() or None,
            timeout_s=_float(source.get("VIETLAW_LLM_TIMEOUT_S"), 15.0),
            api_key=(source.get("ANTHROPIC_API_KEY") or "").strip() or None,
        )

    def readiness_error(self) -> LLMErrorKind | None:
        """Return the fail-closed reason the LLM cannot run, or None if usable."""

        if not self.enabled:
            return LLMErrorKind.DISABLED
        if self.provider != "anthropic":
            return LLMErrorKind.PROVIDER_ERROR
        if not self.api_key:
            return LLMErrorKind.MISSING_API_KEY
        if not self.model:
            return LLMErrorKind.MISSING_MODEL
        return None


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float(value: str | None, default: float) -> float:
    try:
        parsed = float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class LLMClientProtocol(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        timeout_s: float,
        json_schema: dict | None = None,
        temperature: float | None = None,
        use_structured_output: bool = True,
    ) -> str:
        """Return the raw model text for one prompt, or raise LLMClientError.

        ``json_schema``/``temperature`` are FAST DEMO V2 additions and optional:
        omitting them reproduces the original demo request exactly.
        """
        ...


class AnthropicLLMClient:
    """Direct Anthropic Messages API client over the existing httpx dependency."""

    def __init__(self, config: DemoLLMConfig) -> None:
        self._config = config

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        timeout_s: float,
        json_schema: dict | None = None,
        temperature: float | None = None,
        use_structured_output: bool = True,
    ) -> str:
        readiness = self._config.readiness_error()
        if readiness is not None:
            raise LLMClientError(readiness, "provider not ready")
        # json_schema/temperature are FAST DEMO V2 additions. When omitted the
        # payload is byte-identical to the original demo request.
        payload = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        # Native structured outputs are not available on every Claude model. When
        # unsupported, omit output_config entirely rather than sending a parameter
        # the model rejects; the caller still validates the returned JSON locally.
        if use_structured_output:
            payload["output_config"] = (
                {"format": {"type": "json_schema", "schema": json_schema}}
                if json_schema is not None
                else STRUCTURED_OUTPUT_CONFIG
            )
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {
            "x-api-key": self._config.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(_ANTHROPIC_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMClientError(LLMErrorKind.TIMEOUT, "provider timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMClientError(LLMErrorKind.NETWORK, "provider network error") from exc

        if response.status_code != 200:
            # Do not log or surface the raw body (may echo user data).
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, f"status {response.status_code}")
        try:
            data = response.json()
        except (ValueError, AttributeError) as exc:
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "unreadable provider body") from exc

        # Malformed top-level response (Codex V1 finding M-2): a non-object body
        # (list/string/null/number/...) fails closed here, before any `.get(...)`
        # call is attempted -- a top-level `.get` on a non-dict would otherwise
        # raise an unbounded AttributeError.
        if not isinstance(data, dict):
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "malformed top-level response")

        # Structured-output-specific stop reasons are classified before any text
        # extraction is attempted, so a refusal or truncated response never falls
        # through to a (partial/empty) text-parsing path. Refusal/truncated text
        # is never parsed -- classification alone is bounded and sufficient.
        stop_reason = data.get("stop_reason")
        if stop_reason == "refusal":
            raise LLMClientError(LLMErrorKind.REFUSAL, "provider declined to produce structured output")
        if stop_reason == "max_tokens":
            raise LLMClientError(LLMErrorKind.MAX_TOKENS, "provider output truncated at max_tokens")

        # Exact response-block contract (Codex V1 finding M-1): the structured
        # plan is read ONLY from content[0].text. Later blocks are never
        # inspected, searched, or concatenated -- an off-contract multi-block
        # response (e.g. a leading "thinking" block, or two "text" blocks) fails
        # closed rather than being silently rescued or partially accepted.
        content = data.get("content")
        if not isinstance(content, list) or not content:
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "missing or empty content")
        first_block = content[0]
        if not isinstance(first_block, dict):
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "malformed first content block")
        if first_block.get("type") != "text":
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "first content block is not text")
        text = first_block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "empty provider text")
        return text


class FakeLLMClient:
    """Deterministic test double. Returns canned text or raises a configured error."""

    def __init__(self, *, responses: list[str] | None = None, error: LLMErrorKind | None = None) -> None:
        self._responses = list(responses or [])
        self._error = error
        self.calls = 0
        self.last_system: str | None = None
        self.last_user: str | None = None
        self.last_json_schema: dict | None = None
        self.last_temperature: float | None = None
        self.last_use_structured_output: bool | None = None

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        timeout_s: float,
        json_schema: dict | None = None,
        temperature: float | None = None,
        use_structured_output: bool = True,
    ) -> str:
        self.calls += 1
        self.last_use_structured_output = use_structured_output
        self.last_system = system
        self.last_user = user
        self.last_json_schema = json_schema
        self.last_temperature = temperature
        if self._error is not None:
            raise LLMClientError(self._error, "fake error")
        if not self._responses:
            raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "fake exhausted")
        return self._responses.pop(0)


__all__ = [
    "AnthropicLLMClient",
    "DemoLLMConfig",
    "FakeLLMClient",
    "LLMClientError",
    "LLMClientProtocol",
]
