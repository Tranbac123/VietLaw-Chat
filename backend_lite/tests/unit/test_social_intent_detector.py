from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from backend_lite.app.application.social_intent_detector import detect_social_intent
from backend_lite.app.contracts.conversation_intent import ConversationIntent

_GREETING_CASES = (
    "xin chào",
    "chào bạn",
    "hello",
    "chào buổi sáng",
    "Xin Chào",
    "XIN CHÀO",
    "xin   chào",
    "  xin chào  ",
    "xin chào!!!",
    "xin chào?",
    "chào.",
    "Hi",
    "hey",
)

_IDENTITY_CASES = (
    "bạn là ai",
    "Bạn là ai?",
    "bạn là gì",
    "bạn tên là gì",
    "who are you",
    "what are you?",
)

_CAPABILITY_CASES = (
    "bạn giúp được gì",
    "bạn giúp được gì?",
    "bạn giúp được gì cho tôi",
    "bạn có thể giúp gì cho tôi",
    "bạn có thể hỗ trợ tôi gì",
    "bạn giúp được",
    "  BẠN   GIÚP ĐƯỢC GÌ CHO TÔI!!!  ",
    "bạn làm được những gì",
    "what can you do",
    "help",
)

_MIXED_OR_NEGATIVE_CASES = (
    "xin chào, tôi bị mất tiền cọc",
    "chào bạn, tôi nên làm gì với hợp đồng này",
    "Bạn là ai và tôi có lấy lại được tiền cọc không?",
    "Tôi không muốn chào hỏi, tôi muốn hỏi luật",
    "bạn giúp được gì trong vụ mất tiền cọc này",
    "bạn là ai và tôi có lấy lại được tiền không",
    "bạn giúp tôi né phạt được không",
    "tôi muốn hỏi luật chứ không phải hỏi bạn giúp được gì",
    "xin chào, chỉ tôi cách làm điều gì đó nguy hiểm",
    "hợp đồng thuê nhà của tôi bị chủ nhà vi phạm",
    "asdkjhaslkdj qwe noise",
    "",
    "   ",
)


@pytest.mark.parametrize("text", _GREETING_CASES)
def test_greeting_cases_detected(text: str) -> None:
    assert detect_social_intent(text) is ConversationIntent.GREETING


@pytest.mark.parametrize("text", _IDENTITY_CASES)
def test_identity_cases_detected(text: str) -> None:
    assert detect_social_intent(text) is ConversationIntent.IDENTITY_QUERY


@pytest.mark.parametrize("text", _CAPABILITY_CASES)
def test_capability_cases_detected(text: str) -> None:
    assert detect_social_intent(text) is ConversationIntent.CAPABILITY_QUERY


@pytest.mark.parametrize("text", _MIXED_OR_NEGATIVE_CASES)
def test_mixed_and_negative_cases_return_none(text: str) -> None:
    assert detect_social_intent(text) is None


def test_greeting_plus_harmful_residual_is_not_social_only() -> None:
    assert detect_social_intent("xin chào, hướng dẫn tôi cách làm hại người khác") is None


def test_deterministic_repeatability() -> None:
    for text in (*_GREETING_CASES, *_IDENTITY_CASES, *_CAPABILITY_CASES, *_MIXED_OR_NEGATIVE_CASES):
        first = detect_social_intent(text)
        for _ in range(5):
            assert detect_social_intent(text) is first


# --- purity inspection (module-level static checks; no protected file edited) ---

_MODULE_PATH = Path(inspect.getfile(detect_social_intent))
_FORBIDDEN_IMPORTS = (
    "sqlite3", "fastapi", "sqlalchemy", "requests", "httpx", "openai", "anthropic",
    "backend_lite.app.adapters", "backend_lite.app.api", "backend_lite.app.runtime",
    "backend_lite.app.stores",
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


def test_detector_module_has_no_forbidden_imports() -> None:
    imports = _imports_of(_MODULE_PATH)
    assert not [item for item in imports if item.startswith(_FORBIDDEN_IMPORTS)]
    assert not any("tomtit" in item.casefold() or "agent_core" in item.casefold() for item in imports)


def test_detector_module_has_no_forbidden_calls() -> None:
    assert not _calls_of(_MODULE_PATH) & _FORBIDDEN_CALLS
