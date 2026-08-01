"""VietLaw Public Beta V0: the `IS_LEGAL_OR_RIGHTS_RELATED?` gate (task §3).

This is what prevents ordinary non-legal follow-ups ("tôi nên làm gì?",
"cảm ơn") from ever reaching the curated-traffic/official-search/general-
guidance vertical -- see the regression this module's own overly-generic
"toi nen lam gi" phrase caused during implementation (fixed by removing it).
"""

from __future__ import annotations

import pytest

from backend_lite.app.services.legal_intent_classifier import is_legal_or_rights_related


@pytest.mark.parametrize(
    "message",
    [
        "Tôi bị phạt vi phạm giao thông thì phải làm sao?",
        "Tôi có quyền khiếu nại quyết định này không?",
        "Công ty giữ lương của tôi, tôi có quyền khởi kiện không?",
        "Tôi muốn hỏi luật sư về hợp đồng lao động của mình.",
    ],
)
def test_legal_phrase_is_recognized(message: str) -> None:
    assert is_legal_or_rights_related(message, traffic_topic_detected=False) is True


@pytest.mark.parametrize(
    "message",
    [
        "tôi nên làm gì?",
        "cảm ơn nhé",
        "hôm nay thời tiết thế nào?",
        "cho tôi công thức nấu ăn phở bò",
        "kết quả bóng đá tối qua thế nào?",
        "giá vàng hôm nay bao nhiêu?",
    ],
)
def test_ordinary_non_legal_message_is_not_promoted(message: str) -> None:
    assert is_legal_or_rights_related(message, traffic_topic_detected=False) is False


def test_non_legal_override_wins_even_with_an_incidental_legal_looking_word() -> None:
    # "luật chơi" ("the rules of the game") must never trigger the legal
    # fallback just because it contains the substring "luật".
    assert is_legal_or_rights_related("Luật chơi của trò này là gì?", traffic_topic_detected=False) is False


def test_traffic_topic_detected_is_always_legal_intent_even_without_a_phrase_match() -> None:
    # A positive traffic-classifier signal is legal-intent by definition,
    # even for a message with no legal-phrase wording of its own.
    assert is_legal_or_rights_related("Xe máy.", traffic_topic_detected=True) is True


def test_empty_message_is_never_legal_intent() -> None:
    assert is_legal_or_rights_related("", traffic_topic_detected=False) is False
    assert is_legal_or_rights_related("   ", traffic_topic_detected=False) is False
