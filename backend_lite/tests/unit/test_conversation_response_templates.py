from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from backend_lite.app.application.response_templates import render_social_response

_FORBIDDEN_BRANDING = ("tomtit", "TomTit", "TOMTIT")
_FORBIDDEN_OVERCLAIM = (
    "thay thế luật sư",
    "thay cho luật sư",
    "mọi lĩnh vực pháp luật",
    "tất cả các lĩnh vực pháp luật",
    "đã nộp",
    "đã liên hệ",
    "đã xác minh",
    "đã gửi",
)


def test_greeting_response_exact_text() -> None:
    assert render_social_response("greeting") == "Chào bạn, hôm nay tôi có thể hỗ trợ gì cho bạn?"


def test_identity_response_mentions_vietlaw_chat() -> None:
    text = render_social_response("identity")
    assert "VietLaw-Chat" in text


def test_identity_response_does_not_claim_replacing_a_lawyer() -> None:
    text = render_social_response("identity").casefold()
    assert "không thay thế luật sư" in text
    assert "thay thế luật sư" in text  # present only inside the negated clause above


def test_capability_response_only_claims_supported_features() -> None:
    text = render_social_response("capability")
    low = text.casefold()
    assert "checklist" in low
    assert "bước tiếp theo" in low
    for forbidden in _FORBIDDEN_OVERCLAIM:
        if forbidden == "mọi lĩnh vực pháp luật":
            assert "không hỗ trợ mọi lĩnh vực pháp luật" in low
            continue
        assert forbidden.casefold() not in low


@pytest.mark.parametrize("template_id", ["greeting", "identity", "capability"])
def test_no_tomtit_branding(template_id: str) -> None:
    text = render_social_response(template_id)
    for banned in _FORBIDDEN_BRANDING:
        assert banned not in text


@pytest.mark.parametrize("template_id", ["greeting", "identity", "capability"])
def test_no_urls(template_id: str) -> None:
    text = render_social_response(template_id)
    assert "http://" not in text
    assert "https://" not in text
    assert "www." not in text


@pytest.mark.parametrize("template_id", ["greeting", "identity", "capability"])
def test_no_long_generic_legal_checklist_markers(template_id: str) -> None:
    """Social templates must not contain the legal-pipeline checklist/next-step markers."""
    text = render_social_response(template_id)
    assert "Câu hỏi làm rõ" not in text
    assert "Nguồn tham khảo" not in text
    assert "\n-" not in text  # no bulleted checklist rendered directly in social text


@pytest.mark.parametrize("template_id", ["greeting", "identity", "capability"])
def test_no_claim_of_replacing_a_lawyer(template_id: str) -> None:
    text = render_social_response(template_id).casefold()
    assert "tôi là luật sư" not in text
    assert "thay thế hoàn toàn luật sư" not in text


def test_unknown_template_id_fails_loudly() -> None:
    with pytest.raises(ValueError):
        render_social_response("not_a_real_template")


def test_deterministic_repeatability() -> None:
    for template_id in ("greeting", "identity", "capability"):
        first = render_social_response(template_id)
        for _ in range(5):
            assert render_social_response(template_id) == first


# --- purity inspection (module-level static checks; no protected file edited) ---

_MODULE_PATH = Path(inspect.getfile(render_social_response))
_FORBIDDEN_IMPORTS = (
    "sqlite3", "fastapi", "sqlalchemy", "requests", "httpx", "openai", "anthropic",
    "backend_lite.app.adapters", "backend_lite.app.api", "backend_lite.app.runtime",
    "backend_lite.app.stores", "os", "sys",
)
_FORBIDDEN_CALLS = {"open", "now", "utcnow", "time", "monotonic", "random", "uuid4", "getenv"}


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


def test_templates_module_has_no_forbidden_imports() -> None:
    imports = _imports_of(_MODULE_PATH)
    assert not [item for item in imports if item.startswith(_FORBIDDEN_IMPORTS)]
    assert not any("tomtit" in item.casefold() or "agent_core" in item.casefold() for item in imports)


def test_templates_module_has_no_forbidden_calls() -> None:
    assert not _calls_of(_MODULE_PATH) & _FORBIDDEN_CALLS
