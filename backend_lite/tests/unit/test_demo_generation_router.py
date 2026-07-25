from __future__ import annotations

import pytest

from backend_lite.app.contracts.demo_llm import DemoRoute, DemoScenario, LLM_ROUTES
from backend_lite.app.services.demo_generation_router import route_demo, should_defer_demo_for_risk


@pytest.mark.parametrize(
    "text",
    [
        "Chủ nhà đang giữ dao và đe dọa tôi vì tiền cọc.",
        "Chủ nhà cầm mã-tấu vì tiền cọc. Tôi nên làm gì?",
        "Tôi muốn trả_thù chủ nhà vì tiền cọc.",
        "công-an mời tôi vì tiền cọc.",
        "Tôi bị triệu_tập vì tiền cọc.",
        "Chủ nhà dọa giết tôi vì khoản cọc.",
        "Tôi đang bị hành hung vì tranh chấp tiền cọc.",
        "Tôi sợ mình sẽ bị bắt vì vụ tiền cọc này.",
        "Tôi muốn tự xử chủ nhà vì họ không trả tiền cọc.",
        "Chủ nhà tạt axit vì tiền cọc.",
    ],
)
def test_risk_signals_defer(text: str):
    assert should_defer_demo_for_risk(text) is True


@pytest.mark.parametrize(
    "text",
    ["Tôi đã đặt cọc 20 triệu hôm nay.", "Xin chào", "Tôi có sao kê chuyển khoản tiền cọc."],
)
def test_ordinary_text_not_deferred(text: str):
    assert should_defer_demo_for_risk(text) is False


def test_greeting_route():
    r = route_demo("xin chào", "xin chao", DemoScenario.UNSUPPORTED)
    assert r.route is DemoRoute.SOCIAL_DIRECT and r.llm_required is False


def test_capability_route():
    r = route_demo("bạn có thể làm gì cho tôi?", "ban co the lam gi cho toi", DemoScenario.UNSUPPORTED)
    assert r.route is DemoRoute.CAPABILITY_DIRECT and r.llm_required is False


def test_source_lookup_route():
    r = route_demo("bạn vừa dùng nguồn nào?", "ban vua dung nguon nao", DemoScenario.UNSUPPORTED)
    assert r.route is DemoRoute.SOURCE_LOOKUP_DIRECT and r.llm_required is False


def test_fact_update_route_no_llm():
    r = route_demo("...", "...", DemoScenario.DEPOSIT_FACT_UPDATE)
    assert r.route is DemoRoute.FACT_UPDATE_DIRECT and r.llm_required is False


def test_legal_guidance_route_llm():
    r = route_demo("...", "...", DemoScenario.DEPOSIT_LEGAL_GUIDANCE)
    assert r.route is DemoRoute.LEGAL_GENERATION and r.llm_required is True
    assert r.route in LLM_ROUTES


def test_drafting_route_llm():
    r = route_demo("...", "...", DemoScenario.DEPOSIT_DRAFT_REQUEST)
    assert r.route is DemoRoute.DOCUMENT_DRAFTING and r.llm_required is True


def test_unsupported_route_policy_no_llm():
    r = route_demo("tôi muốn kiện", "toi muon kien", DemoScenario.UNSUPPORTED)
    assert r.route is DemoRoute.POLICY_DIRECT and r.llm_required is False
