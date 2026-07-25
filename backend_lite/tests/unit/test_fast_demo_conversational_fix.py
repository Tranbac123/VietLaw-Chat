"""FAST DEMO V2 conversational-defect regressions.

Covers the three live defects observed against a running backend:
  1. capability phrasings falling through to the scope refusal;
  2. user-facing copy leaking implementation vocabulary ("Bản demo",
     "phản hồi dự phòng");
  3. a legal turn silently dropping to the deterministic fallback with no
     usable reason category.
"""

from __future__ import annotations

import pytest

from backend_lite.app.dependencies import _structured_output_supported
from backend_lite.app.services.fast_demo_routing import (
    CAPABILITY_TEXT,
    GREETING_TEXT,
    SCOPE_TEXT,
    FastDemoRoute,
    classify_route,
)


def route(text: str, *, active: bool = False) -> FastDemoRoute:
    return classify_route(text, has_active_matter=active)


# -- 1/2: capability phrasings, accented and accentless ---------------------

@pytest.mark.parametrize(
    "text",
    [
        # the exact phrase that regressed in the live conversation
        "bạn có thể giúp tôi việc gì?",
        "bạn giúp tôi được gì?",
        "bạn giúp được gì?",
        "bạn làm được gì?",
        "tôi có thể hỏi bạn gì?",
        "bạn hỗ trợ được gì?",
        # accentless
        "ban co the giup toi viec gi",
        "ban giup duoc gi",
        "ban giup toi duoc gi",
        "toi co the hoi ban gi",
        # punctuation / capitalisation / whitespace tolerance
        "BẠN CÓ THỂ GIÚP TÔI VIỆC GÌ?!",
        "   bạn   có thể   giúp tôi việc gì   ",
        "Bạn có thể hỗ trợ tôi việc gì ạ?",
    ],
)
def test_capability_phrases_route_to_capability(text: str) -> None:
    assert route(text) is FastDemoRoute.CAPABILITY


# -- 4: a mixed capability + legal message stays legal ----------------------

@pytest.mark.parametrize(
    "text",
    [
        "Bạn có thể giúp tôi việc gì với khoản cọc 20 triệu mà chủ nhà chưa trả?",
        "bạn giúp được gì cho vụ tiền cọc thuê nhà của tôi?",
    ],
)
def test_mixed_capability_and_legal_stays_legal(text: str) -> None:
    assert route(text) is FastDemoRoute.LEGAL_CONVERSATION


# -- 7: a typo must not defeat an explicit deposit cue ----------------------

@pytest.mark.parametrize(
    "text",
    [
        # "đẽ" is a typo for "đã"; "đặt cọc" is still explicit
        "tôi đẽ đặt cọc nhưng chủ không cho vào ở, tôi nên làm gì tiếp theo?",
        "toi de dat coc nhung chu khong cho vao o, toi nen lam gi tiep theo",
        "Tôi đã đặt cọc thuê nhà 20 triệu và có sao kê chuyển khoản.",
    ],
)
def test_deposit_cue_routes_legal_despite_typos(text: str) -> None:
    assert route(text) is FastDemoRoute.LEGAL_CONVERSATION


# -- 5/6: user-facing copy carries no implementation vocabulary -------------

_BANNED = [
    "bản demo",
    "phản hồi dự phòng",
    "provider",
    "fallback",
    "route",
    "scope",
    "structured output",
    "schema",
    "state",
    "json",
]


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("capability", CAPABILITY_TEXT),
        ("greeting", GREETING_TEXT),
        ("scope", SCOPE_TEXT),
    ],
)
def test_user_facing_copy_has_no_implementation_language(name: str, text: str) -> None:
    lowered = text.lower()
    leaked = [term for term in _BANNED if term in lowered]
    assert leaked == [], f"{name} copy leaks implementation vocabulary: {leaked}"


def test_capability_copy_describes_what_the_assistant_can_do() -> None:
    # It should read as an assistant offering help, not as a product disclaimer.
    assert "tiền cọc" in CAPABILITY_TEXT
    assert "Bản demo" not in CAPABILITY_TEXT


def test_fallback_copy_has_no_implementation_language() -> None:
    from backend_lite.app.services.fast_demo_orchestrator import _FALLBACK_SUMMARY

    lowered = _FALLBACK_SUMMARY.lower()
    assert "phản hồi dự phòng" not in lowered
    assert "provider" not in lowered
    # It must still reassure the user their facts were kept.
    assert "giữ lại" in _FALLBACK_SUMMARY


# -- 9: structured-output support detection (the provider root cause) -------

@pytest.mark.parametrize(
    "model",
    ["claude-opus-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
)
def test_structured_output_enabled_for_supporting_models(model: str, monkeypatch) -> None:
    monkeypatch.delenv("VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT", raising=False)
    assert _structured_output_supported(model) is True


@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "claude-opus-4-7", "claude-opus-4-6", None])
def test_structured_output_disabled_for_non_supporting_models(model, monkeypatch) -> None:
    # Sending output_config.format to these models is rejected by the API, which
    # is what silently dropped every legal turn to the fallback.
    monkeypatch.delenv("VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT", raising=False)
    assert _structured_output_supported(model) is False


def test_structured_output_override_forces_on_and_off(monkeypatch) -> None:
    monkeypatch.setenv("VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT", "1")
    assert _structured_output_supported("claude-sonnet-4-6") is True
    monkeypatch.setenv("VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT", "0")
    assert _structured_output_supported("claude-opus-5") is False
