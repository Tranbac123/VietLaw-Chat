from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Request

from .config import Settings
from .guards.citation_guard import LiteCitationGuard
from .guards.safety_guard import LiteSafetyGuard
from .runtime.agent_runtime import AgentRuntime
from .services.chat_title import ChatTitleService
from .services.context_builder import SameChatContextBuilder
from .services.decision_policy import LiteDecisionPolicy
from .services.domain_classifier import LiteDomainClassifier
from .services.input_normalizer import InputNormalizer
from .services.language_detector import LiteLanguageDetector
from .services.lite_content_generator import LiteContentGenerator
from .services.rag_retriever import KeywordRagRetriever
from .services.response_builder import LiteResponseBuilder
from .services.risk_classifier import LiteRiskClassifier
from .services.unsafe_detector import PatternUnsafeDetector
from .stores.snippet_store import JsonSnippetStore
from .stores.sqlite_chat_store import SQLiteChatStore
from .stores.unsafe_pattern_store import JsonUnsafePatternStore


@dataclass
class AppContainer:
    settings: Settings
    chat_store: SQLiteChatStore
    snippet_store: JsonSnippetStore
    unsafe_store: JsonUnsafePatternStore
    runtime: AgentRuntime


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _demo_flag_enabled() -> bool:
    return _flag("VIETLAW_DEMO_VERTICAL_SLICE_ENABLED")


def fast_demo_enabled() -> bool:
    return _flag("VIETLAW_FAST_DEMO_V2_ENABLED")


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Claude models that support native Structured Outputs (`output_config.format`).
# Sending that parameter to a model outside this set is rejected by the API, which
# surfaces as an immediate 4xx and drops the turn to the deterministic fallback.
# Matched on prefix so dated snapshots of the same family are covered.
_STRUCTURED_OUTPUT_MODELS: tuple[str, ...] = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-sonnet-5",
    "claude-haiku-4-5",
)


def _structured_output_supported(model: str | None) -> bool:
    """Whether to send `output_config.format` for this model.

    ``VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT`` overrides the detection either way
    (``1``/``0``), so a newly-supported model can be opted in without a code change.
    When structured output is off, conformance is still enforced locally by the
    ``FastDemoPlan`` Pydantic validator -- the schema itself is never weakened.
    """

    override = (os.environ.get("VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT") or "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    name = (model or "").strip().lower()
    return any(name.startswith(prefix) for prefix in _STRUCTURED_OUTPUT_MODELS)


def _build_fast_demo_orchestrator(settings: Settings, snippet_store: JsonSnippetStore):
    """Construct the FAST DEMO V2 orchestrator only when its flag is enabled.

    Returns None otherwise, which keeps the flag-off path identical to the
    checkpoint: the state table is never created, the orchestrator is never
    called, and the runtime hook is skipped entirely.
    """

    if not fast_demo_enabled():
        return None
    try:
        from .services.demo_llm_client import AnthropicLLMClient, DemoLLMConfig
        from .services.fast_demo_orchestrator import FastDemoConfig, FastDemoOrchestrator
        from .services.fast_demo_source_pack import DEPOSIT_AUTHORITY_ID, FastDemoSourcePack
        from .stores.fast_demo_state_store import FastDemoStateStore

        pack = FastDemoSourcePack.from_snippets(snippet_store.active_snippets())
        if DEPOSIT_AUTHORITY_ID not in pack.available_ids:
            return None

        llm_config = DemoLLMConfig.from_env()
        fast_config = FastDemoConfig(
            enabled=llm_config.enabled,
            model=llm_config.model,
            api_key=llm_config.api_key,
            timeout_s=_float_env("VIETLAW_FAST_DEMO_TIMEOUT_S", 30.0),
            max_output_tokens=_int_env("VIETLAW_FAST_DEMO_MAX_TOKENS", 2048),
            temperature=0.0,
            use_structured_output=_structured_output_supported(llm_config.model),
        )
        store = FastDemoStateStore(settings.chat_db_path)
        store.ensure_schema()
        return FastDemoOrchestrator(
            store=store,
            source_pack=pack,
            llm_client=AnthropicLLMClient(llm_config),
            config=fast_config,
        )
    except Exception:  # noqa: BLE001 - fail closed to baseline, never crash startup
        return None


def _build_demo_orchestrator(snippet_store: JsonSnippetStore):
    """Construct the demo orchestrator only when the demo flag is enabled.

    Returns None otherwise, which keeps the runtime behaviorally compatible with
    the baseline when the demo flag is disabled. Importing the demo modules
    lazily avoids any import-time cost on the baseline path.
    """

    if not _demo_flag_enabled():
        return None
    from .services.demo_llm_client import AnthropicLLMClient, DemoLLMConfig
    from .services.demo_llm_generation import (
        ARTICLE_328_AUTHORITY_ID,
        EVIDENCE_CHECKLIST_ID,
        DemoOrchestrator,
    )

    source_objects = {}
    try:
        for snippet in snippet_store.active_snippets():
            if snippet.id in (ARTICLE_328_AUTHORITY_ID, EVIDENCE_CHECKLIST_ID):
                source_objects[snippet.id] = snippet.as_source()
    except Exception:  # noqa: BLE001 - demo must fail closed to baseline, never crash startup
        return None
    if ARTICLE_328_AUTHORITY_ID not in source_objects:
        return None
    config = DemoLLMConfig.from_env()
    return DemoOrchestrator(
        llm_client=AnthropicLLMClient(config),
        llm_config=config,
        source_objects=source_objects,
    )


def build_container(settings: Settings) -> AppContainer:
    chat_store = SQLiteChatStore(settings.chat_db_path)
    snippet_store = JsonSnippetStore(settings.legal_snippets_path)
    unsafe_store = JsonUnsafePatternStore(settings.unsafe_patterns_path)
    normalizer = InputNormalizer()
    demo_orchestrator = _build_demo_orchestrator(snippet_store)
    fast_demo_orchestrator = _build_fast_demo_orchestrator(settings, snippet_store)
    runtime = AgentRuntime(
        chat_store=chat_store,
        context_builder=SameChatContextBuilder(chat_store, normalizer, settings.context_message_limit),
        normalizer=normalizer,
        language_detector=LiteLanguageDetector(),
        unsafe_detector=PatternUnsafeDetector(unsafe_store, normalizer),
        domain_classifier=LiteDomainClassifier(),
        risk_classifier=LiteRiskClassifier(),
        decision_policy=LiteDecisionPolicy(),
        retriever=KeywordRagRetriever(snippet_store, normalizer, settings.rag_top_k),
        content_generator=LiteContentGenerator(),
        citation_guard=LiteCitationGuard(),
        safety_guard=LiteSafetyGuard(),
        response_builder=LiteResponseBuilder(),
        title_service=ChatTitleService(),
        demo_orchestrator=demo_orchestrator,
        fast_demo_orchestrator=fast_demo_orchestrator,
    )
    return AppContainer(settings, chat_store, snippet_store, unsafe_store, runtime)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container
