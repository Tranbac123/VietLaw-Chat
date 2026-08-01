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
from .storage_readiness import ProductionStorageError, validate_persistent_storage
from .stores.snippet_store import JsonSnippetStore
from .stores.sqlite_chat_store import SQLiteChatStore
from .stores.unsafe_pattern_store import JsonUnsafePatternStore


#: Deployment Correction Round 2 (MEDIUM-01): the frozen Public Beta V0 /
#: Traffic Safe Subset V1 inventory this deployment must ship exactly --
#: never derived at runtime from the pack itself, so a mutated/truncated/
#: expanded pack cannot silently redefine what "correct" means. Reading
#: `data/traffic_rules.json`'s enabled rows is how this was determined, not
#: a change to any rule, selector, or citation.
EXPECTED_TOTAL_TRAFFIC_ROWS = 15
EXPECTED_ENABLED_TRAFFIC_RULES = 3
EXPECTED_DISABLED_TRAFFIC_RULES = 12
EXPECTED_ENABLED_TRAFFIC_RULE_IDS: frozenset[str] = frozenset(
    {
        "traffic_red_light__motorcycle__safe_v1",
        "traffic_red_light__car__safe_v1",
        "traffic_no_helmet__motorcycle__driver_safe_v1",
    }
)


@dataclass(frozen=True)
class TrafficPackHealthStatus:
    """Deployment Correction Round 1 (MEDIUM-01): whether the curated
    traffic vertical is REQUIRED (the feature flag is on) and, if so,
    whether it actually LOADED -- distinct facts the pre-correction code
    conflated into a single `None` orchestrator for both "flag off" and
    "flag on but construction silently failed." `/api/health` must fail
    (503) only for the second case; the first is a normal, intentional
    configuration (see `routes_health.py`).

    Deployment Correction Round 2 (MEDIUM-01): `loaded=True` alone no
    longer proves the pack is the FROZEN inventory this deployment must
    ship -- a pack that parses cleanly but has been mutated (wrong enabled
    count, an unexpected enabled ID, a wrong total/disabled row count) is
    a genuinely different independent finding from "failed to load", and
    must fail health just as loudly. `exact_inventory_valid` is that
    additional gate; `total_rule_count`/`enabled_rule_count`/
    `disabled_rule_count`/`enabled_rule_ids` are the bounded structured
    facts it is computed from."""

    required: bool
    loaded: bool
    enabled_rule_count: int | None = None
    total_rule_count: int | None = None
    disabled_rule_count: int | None = None
    enabled_rule_ids: frozenset[str] | None = None
    exact_inventory_valid: bool = False


@dataclass
class AppContainer:
    settings: Settings
    chat_store: SQLiteChatStore
    snippet_store: JsonSnippetStore
    unsafe_store: JsonUnsafePatternStore
    runtime: AgentRuntime
    traffic_pack_status: TrafficPackHealthStatus


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _demo_flag_enabled() -> bool:
    return _flag("VIETLAW_DEMO_VERTICAL_SLICE_ENABLED")


def fast_demo_enabled() -> bool:
    return _flag("VIETLAW_FAST_DEMO_V2_ENABLED")


def traffic_pack_enabled() -> bool:
    """Public Beta V0: curated static data only, same risk class as the
    existing deposit pack -- on by default, but still an explicit opt-out
    switch for ops (`VIETLAW_TRAFFIC_PACK_ENABLED=0`)."""

    raw = (os.environ.get("VIETLAW_TRAFFIC_PACK_ENABLED") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def official_legal_search_enabled() -> bool:
    """Public Beta V0: off by default. A live network call is a materially
    different risk than curated static data, so this vertical requires an
    explicit opt-in, unlike `traffic_pack_enabled`."""

    return _flag("VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED")


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


def _build_legal_fallback_orchestrator(
    settings: Settings,
) -> tuple[object | None, TrafficPackHealthStatus]:
    """Construct the Public Beta V0 legal-fallback orchestrator.

    Requires only the traffic pack to build successfully -- unlike FAST DEMO
    V2, this vertical has no hard dependency on a live LLM (its curated and
    general-guidance paths are fully deterministic, and its official-search
    path is itself optional, gated by `official_legal_search_enabled()`).
    Fails closed to `None` (never crashes startup), exactly like every other
    optional hook in this module.

    Also returns a `TrafficPackHealthStatus` (Deployment Correction Round 1,
    MEDIUM-01) distinguishing "flag off, orchestrator intentionally absent"
    from "flag on, but the pack failed to load/construct" -- the
    pre-correction code returned bare `None` for both, leaving
    `/api/health` unable to tell an intentional configuration apart from a
    broken one.
    """

    if not traffic_pack_enabled():
        return None, TrafficPackHealthStatus(required=False, loaded=False)
    try:
        from pathlib import Path

        from .services.legal_fallback_orchestrator import LegalFallbackOrchestrator
        from .services.traffic_source_pack import TrafficSourcePack
        from .stores.legal_fallback_state_store import LegalFallbackStateStore

        traffic_pack_path = Path(settings.legal_snippets_path).parent / "traffic_rules.json"
        traffic_pack = TrafficSourcePack.from_file(traffic_pack_path)

        search_service = None
        search_enabled = official_legal_search_enabled()
        if search_enabled:
            # No concrete search-provider integration is wired in this task
            # (see the architecture report §7, "Known limitations") -- the
            # flag exists so a future task can inject a real
            # `OfficialLegalSearchService` here without touching the
            # orchestrator or any of its callers.
            search_service = None

        store = LegalFallbackStateStore(settings.chat_db_path)
        store.ensure_schema()
        orchestrator = LegalFallbackOrchestrator(
            store=store,
            traffic_pack=traffic_pack,
            search_service=search_service,
            official_search_enabled=search_enabled and search_service is not None,
        )
        enabled_rule_ids = traffic_pack.enabled_rule_ids
        enabled_rule_count = len(enabled_rule_ids)
        total_rule_count = traffic_pack.total_rule_count
        disabled_rule_count = traffic_pack.disabled_rule_count
        exact_inventory_valid = (
            total_rule_count == EXPECTED_TOTAL_TRAFFIC_ROWS
            and enabled_rule_count == EXPECTED_ENABLED_TRAFFIC_RULES
            and disabled_rule_count == EXPECTED_DISABLED_TRAFFIC_RULES
            and enabled_rule_ids == EXPECTED_ENABLED_TRAFFIC_RULE_IDS
        )
        return orchestrator, TrafficPackHealthStatus(
            required=True,
            loaded=True,
            enabled_rule_count=enabled_rule_count,
            total_rule_count=total_rule_count,
            disabled_rule_count=disabled_rule_count,
            enabled_rule_ids=enabled_rule_ids,
            exact_inventory_valid=exact_inventory_valid,
        )
    except Exception:  # noqa: BLE001 - fail closed to baseline, never crash startup
        return None, TrafficPackHealthStatus(required=True, loaded=False)


def _build_request_receipts(settings: Settings):
    """Session-scoped exactly-once receipts.

    Always wired: idempotency must not depend on a demo feature flag, and a
    request without ``client_request_id`` still takes the legacy path. A store
    that cannot create its table degrades to ``None`` rather than blocking
    startup.
    """

    from .stores.fast_demo_request_receipts import (
        FastDemoRequestReceiptStore,
        RequestReceiptStoreError,
    )

    store = FastDemoRequestReceiptStore(settings.chat_db_path)
    try:
        store.ensure_schema()
    except RequestReceiptStoreError:  # noqa: BLE001 - degrade, never crash startup
        return None
    return store


def build_container(settings: Settings) -> AppContainer:
    storage_status = validate_persistent_storage(
        app_env=settings.app_env, db_path=settings.chat_db_path
    )
    if not storage_status.ready:
        raise ProductionStorageError(storage_status.reason)

    chat_store = SQLiteChatStore(settings.chat_db_path)
    snippet_store = JsonSnippetStore(settings.legal_snippets_path)
    unsafe_store = JsonUnsafePatternStore(settings.unsafe_patterns_path)
    normalizer = InputNormalizer()
    demo_orchestrator = _build_demo_orchestrator(snippet_store)
    fast_demo_orchestrator = _build_fast_demo_orchestrator(settings, snippet_store)
    legal_fallback_orchestrator, traffic_pack_status = _build_legal_fallback_orchestrator(settings)
    request_receipts = _build_request_receipts(settings)
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
        legal_fallback_orchestrator=legal_fallback_orchestrator,
        request_receipts=request_receipts,
    )
    return AppContainer(
        settings, chat_store, snippet_store, unsafe_store, runtime, traffic_pack_status
    )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container
