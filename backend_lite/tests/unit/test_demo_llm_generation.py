from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend_lite.app.contracts.demo_llm import (
    DEMO_RESPONSE_PLAN_JSON_SCHEMA,
    ActionCode,
    DemoResponsePlan,
    GenerationOutcomeKind,
    LLMErrorKind,
    LLMPlanRequest,
    PlanKind,
    SummaryCode,
    Tone,
    TrustedFactView,
)
from backend_lite.app.services.demo_llm_client import (
    STRUCTURED_OUTPUT_CONFIG,
    AnthropicLLMClient,
    DemoLLMConfig,
    FakeLLMClient,
    LLMClientError,
)
from backend_lite.app.services.demo_llm_generation import PROMPT_VERSION, request_plan
from backend_lite.app.services.demo_llm_guards import default_plan, parse_demo_plan


def _config(**ov) -> DemoLLMConfig:
    base = dict(enabled=True, provider="anthropic", model="claude-x", timeout_s=15.0, api_key="k")
    base.update(ov)
    return DemoLLMConfig(**base)


def _request(mode="legal_generation") -> LLMPlanRequest:
    return LLMPlanRequest(
        request_id="r", generation_mode=mode,
        trusted_facts=[TrustedFactView(slot="deposit_returned", status="absent")],
        prompt_version=PROMPT_VERSION,
    )


def _valid_plan_json(**ov) -> str:
    payload = {"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
               "action_codes": ["send_written_refund_request"], "tone": "neutral"}
    payload.update(ov)
    return json.dumps(payload)


def _run(coro):
    return asyncio.run(coro)


# --- plan parsing (structural safety) ---------------------------------------

def test_valid_enum_plan_accepted():
    plan, outcome = parse_demo_plan(_valid_plan_json())
    assert plan is not None and outcome.ok
    assert plan.plan_kind is PlanKind.LEGAL_GUIDANCE


def test_arbitrary_string_field_rejected():
    plan, outcome = parse_demo_plan(json.dumps({"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
                                                 "action_codes": [], "tone": "neutral", "summary": "free text prose"}))
    assert plan is None  # extra field forbidden


def test_unknown_enum_rejected():
    plan, _ = parse_demo_plan(_valid_plan_json(summary_code="made_up_code"))
    assert plan is None


def test_prose_instead_of_json_rejected():
    plan, outcome = parse_demo_plan("Theo Điều 999 bạn thắng.")
    assert plan is None and outcome.reason_code == "demo.plan.invalid_json.v1"


def test_default_plan_is_valid():
    assert isinstance(default_plan("legal_generation"), DemoResponsePlan)
    assert default_plan("document_drafting").plan_kind is PlanKind.DRAFT_REQUEST


# --- provider accounting + fallback -----------------------------------------

def test_valid_plan_one_attempt():
    client = FakeLLMClient(responses=[_valid_plan_json()])
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.LLM_ACCEPTED
    assert result.attempts == 1


def test_invalid_json_falls_back_with_exactly_one_attempt_no_repair():
    # V1 structured-output contract: no prompt-based JSON-repair call exists.
    # A single invalid-JSON response goes straight to the deterministic
    # fallback; the second queued response is never consumed.
    client = FakeLLMClient(responses=["nope", _valid_plan_json()])
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.attempts == 1
    assert client.calls == 1
    assert result.error_kind is LLMErrorKind.INVALID_JSON


def test_invalid_json_no_repair_no_third_attempt():
    client = FakeLLMClient(responses=["nope", "still nope"])
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert client.calls == 1  # no repair call made
    assert isinstance(result.plan, DemoResponsePlan)  # default plan used


def test_schema_invalid_uses_default_plan():
    client = FakeLLMClient(responses=[json.dumps({"plan_kind": "legal_guidance"})])
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.error_kind is LLMErrorKind.SCHEMA_INVALID
    assert client.calls == 1


def test_timeout_one_attempt_default_plan():
    client = FakeLLMClient(error=LLMErrorKind.TIMEOUT)
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.attempts == 1
    assert result.error_kind is LLMErrorKind.TIMEOUT


def test_disabled_no_attempt_default_plan():
    client = FakeLLMClient(responses=[_valid_plan_json()])
    result = _run(request_plan(_request(), client, _config(enabled=False)))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert client.calls == 0


class _RaisingClient:
    def __init__(self):
        self.calls = 0

    async def complete(self, *, system, user, max_tokens, timeout_s):
        self.calls += 1
        raise RuntimeError("boom secret")


def test_unexpected_exception_contained():
    result = _run(request_plan(_request(), _RaisingClient(), _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.attempts == 1
    assert isinstance(result.plan, DemoResponsePlan)


def test_cancellation_propagates():
    class _Cancelling:
        async def complete(self, *, system, user, max_tokens, timeout_s):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        _run(request_plan(_request(), _Cancelling(), _config()))


# --- backend rendering: model cannot alter trusted facts --------------------

def test_backend_render_uses_trusted_amount_not_model():
    from backend_lite.app.contracts.legal_facts import FactSlot, FactValue, FactStatus, Claimant, MoneyAmount
    from backend_lite.app.services.demo_llm_generation import AppliedFacts, render_guidance_summary, render_draft

    applied = AppliedFacts(slots={
        "deposit_amount": FactSlot[FactValue](status=FactStatus.PRESENT, claimant=Claimant.USER,
                                              value=MoneyAmount(amount_vnd=20_000_000, as_written="20 triệu")),
        "deposit_returned": FactSlot[FactValue](status=FactStatus.ABSENT, claimant=Claimant.USER),
    })
    # A model plan cannot carry an amount; the backend always renders 20 triệu.
    assert "20 triệu" in render_guidance_summary(applied)
    assert "50 triệu" not in render_guidance_summary(applied)
    assert "20 triệu" in render_draft(applied)
    # No legal-reference text in backend prose.
    for text in (render_guidance_summary(applied), render_draft(applied)):
        assert "Điều" not in text and "Bộ luật" not in text


def test_backend_render_reflects_not_returned_only_from_facts():
    from backend_lite.app.contracts.legal_facts import FactSlot, FactValue, FactStatus, Claimant
    from backend_lite.app.services.demo_llm_generation import AppliedFacts, render_guidance_summary

    applied = AppliedFacts(slots={
        "deposit_returned": FactSlot[FactValue](status=FactStatus.ABSENT, claimant=Claimant.USER),
    })
    summary = render_guidance_summary(applied)
    assert "chưa hoàn trả" in summary  # backend states not-returned from the trusted fact


# =============================================================================
# V1 STRUCTURED OUTPUT CONTRACT -- schema shape, wire config, provider outcomes
# =============================================================================

# --- (1)-(5): the wire JSON Schema is object-root, all-required, enum-only,
# additionalProperties=false, and action_codes is constrained to approved values.

def test_structured_output_schema_is_object_root_all_required_no_extra():
    schema = DEMO_RESPONSE_PLAN_JSON_SCHEMA
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"plan_kind", "summary_code", "action_codes", "tone"}
    assert set(schema["properties"]) == {"plan_kind", "summary_code", "action_codes", "tone"}


def test_structured_output_schema_matches_enums():
    # Derived-from-the-enum guarantee: this test would fail the moment the
    # schema constant and the Enum classes ever drifted apart.
    schema = DEMO_RESPONSE_PLAN_JSON_SCHEMA
    assert set(schema["properties"]["plan_kind"]["enum"]) == {m.value for m in PlanKind}
    assert set(schema["properties"]["summary_code"]["enum"]) == {m.value for m in SummaryCode}
    assert set(schema["properties"]["action_codes"]["items"]["enum"]) == {m.value for m in ActionCode}
    assert set(schema["properties"]["tone"]["enum"]) == {m.value for m in Tone}
    for field in ("plan_kind", "summary_code", "tone"):
        assert schema["properties"][field]["type"] == "string"
    assert schema["properties"]["action_codes"]["type"] == "array"


def test_structured_output_schema_has_no_max_items():
    # Codex V1 finding H-1: Anthropic Structured Outputs does not support
    # `maxItems`; the wire schema must not declare it. The four-action cap is
    # enforced ONLY locally (see test_local_action_codes_rejects_five_actions).
    assert "maxItems" not in DEMO_RESPONSE_PLAN_JSON_SCHEMA["properties"]["action_codes"]


def test_local_action_codes_rejects_five_actions():
    five = [ActionCode.PRESERVE_PAYMENT_EVIDENCE, ActionCode.SEND_WRITTEN_REFUND_REQUEST,
            ActionCode.REQUEST_WRITTEN_RESPONSE, ActionCode.SEEK_PROFESSIONAL_HELP,
            ActionCode.PRESERVE_PAYMENT_EVIDENCE]
    with pytest.raises(Exception):
        DemoResponsePlan.model_validate({
            "plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
            "action_codes": [a.value for a in five], "tone": "neutral",
        })
    # Four is still accepted locally.
    four = five[:4]
    plan = DemoResponsePlan.model_validate({
        "plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
        "action_codes": [a.value for a in four], "tone": "neutral",
    })
    assert len(plan.action_codes) == 4


def test_structured_output_schema_has_no_free_text_or_forbidden_fields():
    # No amount, fact, source, URL, article, deadline, or penalty field exists
    # anywhere in the wire schema -- only the four enum-only fields.
    forbidden = {"amount", "amount_vnd", "fact", "facts", "source", "source_id",
                 "url", "article", "deadline", "penalty", "summary", "text", "metadata"}
    assert forbidden.isdisjoint(DEMO_RESPONSE_PLAN_JSON_SCHEMA["properties"])


# --- (1): the Anthropic client's request payload includes output_config -----

def _fake_response(json_body: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_body, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def _anthropic_config() -> DemoLLMConfig:
    return DemoLLMConfig(enabled=True, provider="anthropic", model="claude-x", timeout_s=15.0, api_key="test-key")


def test_client_request_includes_structured_output_config():
    captured: dict = {}

    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _fake_response({"stop_reason": "end_turn", "content": [{"type": "text", "text": _valid_plan_json()}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))

    assert text == _valid_plan_json()
    assert captured["json"]["output_config"]["format"]["type"] == "json_schema"
    assert captured["json"]["output_config"]["format"]["schema"] == DEMO_RESPONSE_PLAN_JSON_SCHEMA
    assert captured["json"]["output_config"] is STRUCTURED_OUTPUT_CONFIG
    # API key present in the header dict object (never printed/logged), never in the body.
    assert "x-api-key" in captured["headers"]
    assert "api_key" not in captured["json"] and "api-key" not in json.dumps(captured["json"])


# --- (6): a valid structured response parses --------------------------------

def test_client_valid_structured_response_parses_end_to_end():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({"stop_reason": "end_turn", "content": [{"type": "text", "text": _valid_plan_json()}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    plan, outcome = parse_demo_plan(text)
    assert outcome.ok and plan is not None and plan.plan_kind is PlanKind.LEGAL_GUIDANCE


# --- (9): refusal stop reason safely falls back -----------------------------

def test_client_refusal_stop_reason_raises_refusal_kind():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({"stop_reason": "refusal", "content": []})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert exc_info.value.kind is LLMErrorKind.REFUSAL


def test_orchestrator_refusal_falls_back_cleanly():
    client = FakeLLMClient(error=LLMErrorKind.REFUSAL)
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.error_kind is LLMErrorKind.REFUSAL
    assert result.attempts == 1
    assert isinstance(result.plan, DemoResponsePlan)


# --- (10): max_tokens / incomplete output safely falls back -----------------

def test_client_max_tokens_stop_reason_raises_max_tokens_kind():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({"stop_reason": "max_tokens", "content": [{"type": "text", "text": '{"plan_kind":'}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert exc_info.value.kind is LLMErrorKind.MAX_TOKENS


def test_orchestrator_max_tokens_falls_back_cleanly():
    client = FakeLLMClient(error=LLMErrorKind.MAX_TOKENS)
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.error_kind is LLMErrorKind.MAX_TOKENS
    assert result.attempts == 1


# --- (11): provider/network error safely falls back (NETWORK, distinct from TIMEOUT) --

def test_client_httpx_network_error_raises_network_kind():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        raise httpx.ConnectError("connection refused")

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert exc_info.value.kind is LLMErrorKind.NETWORK


def test_orchestrator_network_error_falls_back_cleanly():
    client = FakeLLMClient(error=LLMErrorKind.NETWORK)
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.error_kind is LLMErrorKind.NETWORK
    assert result.attempts == 1


# --- (12): no repair network request is made for structured-output schema errors --

def test_schema_invalid_response_makes_no_second_network_call():
    call_count = {"n": 0}

    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        call_count["n"] += 1
        return _fake_response({"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"plan_kind": "legal_guidance"}'}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    plan, outcome = parse_demo_plan(text)
    assert plan is None  # missing required fields -> schema-invalid
    assert call_count["n"] == 1  # exactly one HTTP call was made; no repair


# --- (13)-(15): model text/facts/sources never reach AnalyzeResponse; covered
# structurally by DemoResponsePlan (enum-only, extra="forbid") and by
# test_backend_render_uses_trusted_amount_not_model /
# test_backend_render_reflects_not_returned_only_from_facts above, plus the
# end-to-end assertions in test_demo_vertical_slice.py.

def test_demo_response_plan_cannot_carry_arbitrary_text_or_amount():
    with pytest.raises(Exception):
        DemoResponsePlan.model_validate({
            "plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
            "action_codes": [], "tone": "neutral", "amount": "50 triệu",
        })
    with pytest.raises(Exception):
        DemoResponsePlan.model_validate({
            "plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
            "action_codes": [], "tone": "neutral", "summary": "free text prose",
        })


# =============================================================================
# V2 REMEDIATION -- HTTP status, top-level malformed body, exact content[0].text
# contract, no-concatenation, capitalization mutants, single-call guarantees.
# =============================================================================

def _client_error(status_code=None, body=None, raises=None):
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        if raises is not None:
            raise raises
        return _fake_response(body, status_code=status_code or 200)

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    return exc_info.value


# --- (4) HTTP 400 -> bounded provider error ----------------------------------

def test_http_400_raises_bounded_provider_error():
    err = _client_error(status_code=400, body={"error": "bad request"})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR
    assert "bad request" not in err.detail


# --- (5)-(7) malformed top-level bodies fail closed before any .get(...) ----

def test_top_level_list_raises_bounded_provider_error():
    err = _client_error(body=[])
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_top_level_string_raises_bounded_provider_error():
    err = _client_error(body="not an object")
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_top_level_null_raises_bounded_provider_error():
    err = _client_error(body=None)
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_top_level_number_raises_bounded_provider_error():
    err = _client_error(body=42)
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


# --- (8)-(9) missing / empty content -----------------------------------------

def test_missing_content_raises_bounded_provider_error():
    err = _client_error(body={"stop_reason": "end_turn"})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_empty_content_raises_bounded_provider_error():
    err = _client_error(body={"stop_reason": "end_turn", "content": []})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


# --- (10)-(11) content[0].text exact contract; later blocks never rescue ----

def test_non_text_first_block_rejected_even_with_valid_second_block():
    err = _client_error(body={
        "stop_reason": "end_turn",
        "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": _valid_plan_json()}],
    })
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_two_text_blocks_are_not_concatenated():
    # content[0].text alone is a valid, complete plan; content[1] must be
    # ignored entirely (never appended, never inspected).
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": _valid_plan_json()}, {"type": "text", "text": "IGNORED_TRAILING_TEXT"}],
        })

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert text == _valid_plan_json()
    assert "IGNORED_TRAILING_TEXT" not in text


def test_two_text_blocks_first_invalid_is_not_rescued_by_second():
    # content[0].text alone is invalid; content[1] (a valid plan) must never
    # rescue it -- the client fails closed rather than searching further.
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "not json"}, {"type": "text", "text": _valid_plan_json()}],
        })

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    # The client returns content[0].text verbatim; it is the caller's parser
    # (parse_demo_plan) that then correctly rejects it as invalid JSON.
    assert text == "not json"
    plan, outcome = parse_demo_plan(text)
    assert plan is None


# --- (12)-(13) empty / malformed first block ---------------------------------

def test_empty_first_text_raises_bounded_provider_error():
    err = _client_error(body={"stop_reason": "end_turn", "content": [{"type": "text", "text": ""}]})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_malformed_first_block_not_a_dict_raises_bounded_provider_error():
    err = _client_error(body={"stop_reason": "end_turn", "content": ["not-a-dict"]})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


def test_first_block_missing_text_field_raises_bounded_provider_error():
    err = _client_error(body={"stop_reason": "end_turn", "content": [{"type": "text"}]})
    assert err.kind is LLMErrorKind.PROVIDER_ERROR


# --- (14)-(15) refusal / max_tokens never parse text, even if present -------

def test_refusal_does_not_parse_text_even_if_valid_plan_present():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({"stop_reason": "refusal", "content": [{"type": "text", "text": _valid_plan_json()}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert exc_info.value.kind is LLMErrorKind.REFUSAL


def test_max_tokens_does_not_parse_partial_text():
    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        return _fake_response({"stop_reason": "max_tokens", "content": [{"type": "text", "text": '{"plan_kind": "leg'}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(LLMClientError) as exc_info:
            _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    assert exc_info.value.kind is LLMErrorKind.MAX_TOKENS


# --- (16) capitalization mutants fail local validation ----------------------

def test_capitalization_mutants_fail_local_validation():
    for mutant in (
        {"plan_kind": "Legal_Guidance", "summary_code": "deposit_not_returned", "action_codes": [], "tone": "neutral"},
        {"plan_kind": "legal_guidance", "summary_code": "DEPOSIT_NOT_RETURNED", "action_codes": [], "tone": "neutral"},
        {"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned", "action_codes": [], "tone": "Neutral"},
        {"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned", "action_codes": ["Send_Written_Refund_Request"], "tone": "neutral"},
    ):
        with pytest.raises(Exception):
            DemoResponsePlan.model_validate(mutant)


# --- (17) invalid JSON uses exactly one HTTP call ----------------------------

def test_invalid_json_response_makes_exactly_one_network_call():
    call_count = {"n": 0}

    async def fake_post(self, url, *, json, headers, **kw):  # noqa: ANN001
        call_count["n"] += 1
        return _fake_response({"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json at all"}]})

    client = AnthropicLLMClient(_anthropic_config())
    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        text = _run(client.complete(system="sys", user="usr", max_tokens=256, timeout_s=15.0))
    plan, outcome = parse_demo_plan(text)
    assert plan is None and outcome.reason_code == "demo.plan.invalid_json.v1"
    assert call_count["n"] == 1


# --- (19) oversized action_codes falls back after exactly one call ---------

def test_oversized_action_codes_uses_exactly_one_call_and_falls_back():
    oversized = json.dumps({
        "plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
        "action_codes": ["preserve_payment_evidence", "send_written_refund_request",
                          "request_written_response", "seek_professional_help",
                          "preserve_payment_evidence"],
        "tone": "neutral",
    })
    client = FakeLLMClient(responses=[oversized])
    result = _run(request_plan(_request(), client, _config()))
    assert result.outcome is GenerationOutcomeKind.DETERMINISTIC_FALLBACK
    assert result.error_kind is LLMErrorKind.SCHEMA_INVALID
    assert client.calls == 1
    assert isinstance(result.plan, DemoResponsePlan)


# --- (20) no provider text leakage -------------------------------------------

def test_no_provider_text_leakage_in_bounded_error():
    secret = "SECRET_PROVIDER_TEXT_MARKER"
    err = _client_error(body={"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": secret}]})
    assert secret not in err.detail
    assert secret not in str(err)
