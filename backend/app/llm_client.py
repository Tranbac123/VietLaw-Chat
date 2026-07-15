"""LLM client — anthropic + OpenAI-compatible only.

One thin dispatch, no factory. `generate` retries once on transport failure then
raises LlmError (→503). The transport is injectable so tests never hit the network.
Providers force JSON where supported; the output_parser still validates regardless.
"""
from typing import Callable, Optional

from app.config import Settings
from app.errors import LlmError

Transport = Callable[[str], str]


class LLMClient:
    def __init__(self, settings: Settings, transport: Optional[Transport] = None):
        self.settings = settings
        self._transport = transport or self._build_transport(settings)

    def generate(self, prompt: str) -> str:
        attempts = self.settings.llm_max_retries + 1
        last: Exception | None = None
        for _ in range(attempts):
            try:
                return self._transport(prompt)
            except Exception as e:  # noqa: BLE001 - any transport failure is retryable
                last = e
        raise LlmError(f"LLM provider failed after {attempts} attempts: {last}") from last

    # ------------------------------------------------------------ transports

    def _build_transport(self, s: Settings) -> Transport:
        if s.resolved_provider == "openai":
            return self._openai_transport(s)
        return self._anthropic_transport(s)

    @staticmethod
    def _anthropic_transport(s: Settings) -> Transport:
        from anthropic import Anthropic

        client = Anthropic(api_key=s.ai_api_key, base_url=s.ai_base_url or None)

        def call(prompt: str) -> str:
            msg = client.messages.create(
                model=s.ai_model_name,
                max_tokens=1024,
                timeout=s.llm_timeout,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "{"},  # prefill forces JSON object
                ],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return "{" + text  # re-attach the prefilled opening brace

        return call

    @staticmethod
    def _openai_transport(s: Settings) -> Transport:
        from openai import OpenAI

        client = OpenAI(api_key=s.ai_api_key, base_url=s.ai_base_url or None,
                        timeout=s.llm_timeout, max_retries=0)

        def call(prompt: str) -> str:
            kwargs = dict(model=s.ai_model_name,
                          messages=[{"role": "user", "content": prompt}])
            try:
                resp = client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs)
            except Exception:
                # Some OpenAI-compatible servers reject response_format; retry plain.
                resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""

        return call
