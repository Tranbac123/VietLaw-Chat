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


def _demo_flag_enabled() -> bool:
    return (os.environ.get("VIETLAW_DEMO_VERTICAL_SLICE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


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
    )
    return AppContainer(settings, chat_store, snippet_store, unsafe_store, runtime)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container
