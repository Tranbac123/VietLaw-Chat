from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from backend_lite.app.application.conversation_router import route
from backend_lite.app.contracts.conversation_intent import ConversationIntent
from backend_lite.app.contracts.conversation_route import ConversationRoute, RouteResult


def test_greeting_routes_to_direct_response_with_greeting_template() -> None:
    result = route(ConversationIntent.GREETING)
    assert result.route is ConversationRoute.DIRECT_RESPONSE
    assert result.template_id == "greeting"
    assert result.intent is ConversationIntent.GREETING


def test_identity_query_routes_to_direct_response_with_identity_template() -> None:
    result = route(ConversationIntent.IDENTITY_QUERY)
    assert result.route is ConversationRoute.DIRECT_RESPONSE
    assert result.template_id == "identity"


def test_capability_query_routes_to_direct_response_with_capability_template() -> None:
    result = route(ConversationIntent.CAPABILITY_QUERY)
    assert result.route is ConversationRoute.DIRECT_RESPONSE
    assert result.template_id == "capability"


def test_unknown_routes_to_runtime_fallback_with_no_template() -> None:
    result = route(ConversationIntent.UNKNOWN)
    assert result.route is ConversationRoute.RUNTIME_FALLBACK
    assert result.template_id is None


def test_none_routes_to_runtime_fallback_with_no_template() -> None:
    result = route(None)
    assert result.route is ConversationRoute.RUNTIME_FALLBACK
    assert result.template_id is None
    assert result.intent is ConversationIntent.UNKNOWN


@pytest.mark.parametrize(
    "intent",
    [ConversationIntent.GREETING, ConversationIntent.IDENTITY_QUERY, ConversationIntent.CAPABILITY_QUERY],
)
def test_direct_response_route_results_carry_no_response_text(intent: ConversationIntent) -> None:
    result = route(intent)
    assert not hasattr(result, "response_text")
    field_names = {f.name for f in dataclasses.fields(result)}
    assert "response_text" not in field_names


def test_route_results_have_stable_reason_codes() -> None:
    assert route(ConversationIntent.GREETING).reason_code == "conversation.route.greeting.v1"
    assert route(ConversationIntent.IDENTITY_QUERY).reason_code == "conversation.route.identity.v1"
    assert route(ConversationIntent.CAPABILITY_QUERY).reason_code == "conversation.route.capability.v1"
    assert route(ConversationIntent.UNKNOWN).reason_code == "conversation.route.unknown.v1"


def test_route_result_is_frozen_and_immutable() -> None:
    result = route(ConversationIntent.GREETING)
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.route = ConversationRoute.RUNTIME_FALLBACK  # type: ignore[misc]


def test_deterministic_repeatability() -> None:
    for intent in (
        ConversationIntent.GREETING,
        ConversationIntent.IDENTITY_QUERY,
        ConversationIntent.CAPABILITY_QUERY,
        ConversationIntent.UNKNOWN,
        None,
    ):
        first = route(intent)
        for _ in range(5):
            assert route(intent) == first


def test_route_result_type() -> None:
    assert isinstance(route(ConversationIntent.GREETING), RouteResult)


# --- purity inspection (module-level static checks; no protected file edited) ---

_MODULE_PATH = Path(inspect.getfile(route))
_FORBIDDEN_IMPORTS = (
    "sqlite3", "fastapi", "sqlalchemy", "requests", "httpx", "openai", "anthropic",
    "backend_lite.app.adapters", "backend_lite.app.api", "backend_lite.app.runtime",
    "backend_lite.app.stores", "backend_lite.app.application.response_templates",
)
_FORBIDDEN_CALLS = {"open", "now", "utcnow", "time", "monotonic", "random", "uuid4"}


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _calls_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            calls.add(function.id if isinstance(function, ast.Name) else getattr(function, "attr", ""))
    return calls


def test_router_module_has_no_forbidden_imports() -> None:
    imports = _imports_of(_MODULE_PATH)
    assert not [item for item in imports if item.startswith(_FORBIDDEN_IMPORTS)]
    assert not any("tomtit" in item.casefold() or "agent_core" in item.casefold() for item in imports)


def test_router_module_has_no_forbidden_calls() -> None:
    assert not _calls_of(_MODULE_PATH) & _FORBIDDEN_CALLS


def test_router_does_not_call_response_templates() -> None:
    """Router must not own or generate response text (Phase A report, section 21)."""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "render_social_response" not in source
    assert "response_templates" not in source
