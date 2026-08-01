"""MODE_2D (+ correction rounds 1-2): article-level legal citations, bounded
to civil_deposit_001.

Trust boundary under test: article/clause numbers, document identity and the
citation URL can only ever originate from curated `data/legal_snippets.json`
data and backend-only deterministic resolution
(`fast_demo_source_pack.resolve_deposit_applicable_clause`/
`attach_deposit_citation_metadata`) -- never from the model's own text.
`FastDemoPlan` structurally cannot carry any of these fields (`extra=
"forbid"`, no such field declared), so this is enforced by schema shape, not
by post-hoc parsing of generated prose. Zero live provider calls throughout.

Round 1 correction (M-01): `applicable_clause=2` now requires
`receiving_party_nonperformance_status == "confirmed"`, a narrowly-bounded
fact. Merely `property_handover_status`/`deposit_returned_status` being
`"absent"` no longer selects Khoản 2 -- that was the M-01 finding.

Round 1 correction (M-02): the build-time gate enforces exact identity
(document title / article number / article title / clause list) for the one
bounded snippet, and rejects article-level authoring on any other snippet
outright rather than silently discarding it.

Round 2 correction (M-01): independent review found the round-1 resolver
still trusted the MODEL-selected evidence span (`span.original_quote`)
rather than the full current message, so a selectively-quoted embedded
substring from a hypothetical/negated/quoted full message could still
resolve `confirmed`. `infer_receiving_party_nonperformance_from_message` now
takes the full current message as its only authoritative input; the model
may still propose the slot, but its evidence quote is diagnostic-only. Four
outcomes: "confirmed", "not_confirmed", the explicit string "unknown"
(persisted, clearing any stale "confirmed"), and `None` (no_update, only
when the message does not discuss the topic at all).

Round 2 correction (M-02): `require_positive_int_list` no longer coerces via
`int(str(item))` -- every `clause_numbers` item must already be a genuine
Python `int` as produced by the (now type-aware) frontmatter parser.
`resolve_deposit_applicable_clause` fails closed (`None`) for both an
omitted and an empty `clause_numbers` argument, not only a non-matching one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend_lite.app.config import Settings
from backend_lite.app.contracts.fast_demo import FastDemoFacts, FastDemoPlan
from backend_lite.app.main import create_app
from backend_lite.app.schemas.content import SourceObject
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_fact_validation import (
    infer_receiving_party_nonperformance_from_message as infer_nonperformance,
)
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import (
    DEPOSIT_AUTHORITY_ID,
    FastDemoSourcePack,
    attach_deposit_citation_metadata,
    resolve_deposit_applicable_clause,
)
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]
SNIPPETS_PATH = REPO_ROOT / "data" / "legal_snippets.json"
SNIPPETS_MD_ROOT = REPO_ROOT / "data" / "snippets_md"

PRIMARY_URL = "https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm"
DOCUMENT_NUMBER = "91/2015/QH13"

import scripts.build_snippets as build_snippets  # noqa: E402  (repo root on sys.path via that module)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=SNIPPETS_PATH,
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _plan(**overrides) -> str:
    payload = {
        "response_kind": "legal",
        "response_mode": "guidance",
        "summary": "Đã ghi nhận thông tin của bạn.",
        "analysis": None,
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "draft": None,
        "known_facts_summary": [],
        "uncertainty_notice": None,
        "fact_updates": [],
        "selected_source_ids": ["civil_deposit_001"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _build(tmp_path: Path, responses: list[str]):
    settings = _settings(tmp_path)
    app = create_app(settings)
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    store = FastDemoStateStore(settings.chat_db_path)
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(
            enabled=True, model="claude-test-model", api_key="test-key",
            timeout_s=30.0, max_output_tokens=2048, temperature=0.0,
        ),
    )
    return app, fake, store


def _ask(client: TestClient, question: str, *, chat_id: str | None = None, session: str = "s1"):
    payload = {"session_id": session, "question": question}
    if chat_id:
        payload["chat_id"] = chat_id
    return client.post("/api/analyze", json=payload)


def _nonperformance_update(evidence: str) -> dict:
    """A model PROPOSAL for the slot. Per M-01 round 2, this evidence_quote
    is diagnostic-only -- the persisted value is always derived from the
    full current message, never from this quote."""

    return {
        "operation": "set",
        "slot": "receiving_party_nonperformance_status",
        "value": None,
        "evidence_quote": evidence,
    }


def _base_source(clause_numbers: list[int] | None = None) -> SourceObject:
    return SourceObject(
        id=DEPOSIT_AUTHORITY_ID,
        title="Đặt cọc để bảo đảm giao kết hoặc thực hiện hợp đồng",
        source_name="Bộ luật Dân sự 2015 - Điều 328",
        url=PRIMARY_URL,
        snippet="Đặt cọc là việc...",
        source_type="official_source",
        last_checked="2026-07-30",
        document_title="Bộ luật Dân sự 2015",
        document_number=DOCUMENT_NUMBER,
        article_number="328",
        article_title="Đặt cọc",
        clause_numbers=clause_numbers if clause_numbers is not None else [1, 2],
    )


# ---------------------------------------------------------------------------
# Curated data carries the exact verified metadata
# ---------------------------------------------------------------------------

def test_civil_deposit_001_carries_dieu_328_metadata() -> None:
    snippets = json.loads(SNIPPETS_PATH.read_text(encoding="utf-8"))
    entry = next(s for s in snippets if s["id"] == DEPOSIT_AUTHORITY_ID)

    assert entry["document_title"] == "Bộ luật Dân sự 2015"
    assert entry["document_number"] == DOCUMENT_NUMBER
    assert entry["article_number"] == "328"
    assert entry["article_title"] == "Đặt cọc"
    assert entry["clause_numbers"] == [1, 2]
    assert entry["source_url"] == PRIMARY_URL


def test_document_number_is_exactly_91_2015_qh13() -> None:
    snippets = json.loads(SNIPPETS_PATH.read_text(encoding="utf-8"))
    entry = next(s for s in snippets if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert entry["document_number"] == "91/2015/QH13"
    assert entry["document_number"] != "92/2015/QH13"


# ---------------------------------------------------------------------------
# Round 2, tests 1-4: positive cases -- explicit, current, correctly
# attributed evidence confirms.
# ---------------------------------------------------------------------------

def test_01_explicit_landlord_refusal_confirms() -> None:
    """The nonperformance FACT may still be confirmed (round 4-6 inference is
    unchanged), but per the MVP safety decision it has zero authority over
    the structured clause citation: applicable_clause is always None."""

    assert infer_nonperformance("Chủ nhà từ chối giao nhà.") == "confirmed"
    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts, [1, 2]) is None


def test_02_explicit_cancellation_confirms() -> None:
    assert infer_nonperformance("Chủ nhà hủy thỏa thuận thuê nhà.") == "confirmed"


def test_03_stated_future_non_performance_confirms() -> None:
    assert infer_nonperformance("Chủ nhà nói chắc chắn sẽ không thực hiện hợp đồng.") == "confirmed"


def test_04_passed_deadline_plus_continuing_nonperformance_confirms() -> None:
    assert infer_nonperformance("Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.") == "confirmed"
    assert infer_nonperformance(
        "Bên nhận cọc thông báo sẽ không tiếp tục giao kết hợp đồng."
    ) == "confirmed"


# ---------------------------------------------------------------------------
# Round 2, tests 5-8: actor negatives -- the wrong actor performing the
# action must never confirm.
# ---------------------------------------------------------------------------

def test_05_user_refusal_does_not_confirm() -> None:
    assert infer_nonperformance("Tôi từ chối tiếp tục thuê nhà.") != "confirmed"


def test_06_user_cancellation_does_not_confirm() -> None:
    assert infer_nonperformance("Tôi là người hủy giao dịch.") != "confirmed"


def test_07_previous_tenant_refusal_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà nói người thuê trước từ chối thực hiện hợp đồng.") != "confirmed"


def test_08_unrelated_party_refusal_with_explicit_actor_correction_does_not_confirm() -> None:
    assert infer_nonperformance("Không phải chủ nhà hủy giao dịch; chính tôi hủy.") != "confirmed"


# ---------------------------------------------------------------------------
# Round 2, tests 9-23: context negatives -- negation, hypothetical, generic
# legal text, unverified quotation, hearsay, historical-superseded,
# contradictory, uncertain, temporary/not-yet-due, bare non-handover/return.
# ---------------------------------------------------------------------------

def test_09_negated_refusal_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà không từ chối giao nhà.") != "confirmed"


def test_10_negated_cancellation_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà không hủy giao dịch.") != "confirmed"


def test_11_hypothetical_refusal_does_not_confirm() -> None:
    assert infer_nonperformance("Nếu chủ nhà từ chối giao nhà thì tôi phải làm gì?") != "confirmed"


def test_12_hypothetical_cancellation_does_not_confirm() -> None:
    assert infer_nonperformance("Giả sử chủ nhà hủy hợp đồng thì sao?") != "confirmed"
    assert infer_nonperformance("Trường hợp bên nhận cọc từ chối thì xử lý thế nào?") != "confirmed"


def test_13_generic_legal_text_does_not_confirm() -> None:
    assert infer_nonperformance(
        "Luật quy định trường hợp bên nhận cọc từ chối thực hiện hợp đồng."
    ) != "confirmed"


def test_14_article_clause_discussion_does_not_confirm() -> None:
    assert infer_nonperformance("Khoản 2 Điều 328 nói về trường hợp bên nhận cọc từ chối.") != "confirmed"


def test_15_quoted_unverified_refusal_does_not_confirm() -> None:
    assert infer_nonperformance(
        'Tin nhắn ghi: "chủ nhà từ chối giao nhà" nhưng tôi chưa xác minh.'
    ) != "confirmed"


def test_16_hearsay_does_not_confirm() -> None:
    assert infer_nonperformance("Tôi nghe nói chủ nhà sẽ hủy hợp đồng.") != "confirmed"
    assert infer_nonperformance("Có người bảo chủ nhà không giao nhà nữa.") != "confirmed"


def test_17_historical_but_superseded_does_not_confirm() -> None:
    assert infer_nonperformance(
        "Trước đây chủ nhà từng từ chối giao nhà, nhưng hiện đã đồng ý giao đúng hạn."
    ) != "confirmed"
    assert infer_nonperformance(
        "Chủ nhà từng hủy giao dịch nhưng sau đó hai bên đã tiếp tục hợp đồng."
    ) != "confirmed"


def test_18_contradictory_same_message_does_not_confirm() -> None:
    assert infer_nonperformance(
        "Chủ nhà từ chối giao nhà, nhưng thật ra chủ nhà không từ chối."
    ) != "confirmed"


def test_19_uncertain_cancellation_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà hủy giao dịch hay không thì tôi chưa biết.") != "confirmed"


def test_20_temporary_delay_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà chỉ xin chậm vài ngày.") != "confirmed"


def test_21_future_due_date_does_not_confirm() -> None:
    assert infer_nonperformance("Tuần sau mới đến hạn giao nhà.") == "not_confirmed"
    assert infer_nonperformance("Hôm nay chưa đến hạn trả cọc.") == "not_confirmed"
    facts = FastDemoFacts(receiving_party_nonperformance_status="not_confirmed")
    assert resolve_deposit_applicable_clause(facts, [1, 2]) is None


def test_22_bare_non_handover_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà chưa giao nhà.") != "confirmed"


def test_23_bare_non_return_of_deposit_does_not_confirm() -> None:
    assert infer_nonperformance("Chủ nhà chưa trả cọc.") != "confirmed"


def test_unrelated_message_does_not_discuss_the_topic_at_all() -> None:
    """The `None` (no_update) outcome is reserved for messages that do not
    discuss receiving-party refusal/nonperformance at all."""

    assert infer_nonperformance("Tôi nên chuẩn bị giấy tờ gì?") is None


def test_legacy_facts_alone_no_longer_select_khoan_2() -> None:
    """The M-01 finding itself: property_handover_status/deposit_returned_status
    being 'absent' must never, by themselves, select clause 2."""

    facts = FastDemoFacts(property_handover_status="absent", deposit_returned_status="absent")
    assert resolve_deposit_applicable_clause(facts, [1, 2]) is None


# ---------------------------------------------------------------------------
# Round 3 (M-01 re-opened): exact Codex adversarial matrix failures --
# generic example/educational context, a lawyer's quoted/reported question,
# and a historical cancellation followed by continuation of the agreement
# without the word "đã". Each is checked end to end: direct inference,
# persisted state, resolved clause, and the rendered source's article-only
# citation.
# ---------------------------------------------------------------------------

ROUND_3_MUST_NOT_CONFIRM_MESSAGES = [
    "Tôi đang đọc một ví dụ về chủ nhà từ chối giao nhà.",
    'Luật sư hỏi tôi: "Chủ nhà có từ chối giao nhà không?"',
    "Chủ nhà từng hủy giao dịch nhưng sau đó hai bên tiếp tục hợp đồng.",
    "Trong ví dụ, chủ nhà hủy thỏa thuận.",
    "Bài viết đưa ví dụ bên nhận cọc từ chối.",
    "Người tư vấn hỏi tôi chủ nhà có từ chối hay không.",
    'Luật sư hỏi: "Chủ nhà hủy hợp đồng à?"',
    "Chủ nhà từng từ chối nhưng sau đó vẫn tiếp tục hợp đồng.",
    "Trước đây chủ nhà hủy nhưng hiện hai bên tiếp tục thuê.",
    "Hôm qua chủ nhà nói không giao nhưng hôm nay đồng ý giao.",
]

# The three exact Codex-required failures. Unlike two of the variants above
# ("Bài viết đưa ví dụ..." carries no deposit/follow-up routing cue at all;
# "...hủy hợp đồng à?" trips the PRE-EXISTING, unrelated destroying-evidence
# safety pattern "hủy ... hợp đồng" in `fast_demo_routing.py`, which this
# task is explicitly forbidden from touching), all three of these route to
# `legal_conversation` cleanly, so they are exercised end to end in addition
# to direct inference.
ROUND_3_EXACT_CODEX_FAILURES = ROUND_3_MUST_NOT_CONFIRM_MESSAGES[:3]


@pytest.mark.parametrize("message", ROUND_3_MUST_NOT_CONFIRM_MESSAGES)
def test_round_3_exact_codex_matrix_direct_inference_not_confirmed(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_3_EXACT_CODEX_FAILURES)
def test_round_3_exact_codex_matrix_end_to_end(tmp_path: Path, message: str) -> None:
    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed", f"persisted status confirmed for: {message!r}"

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None, f"applicable_clause set for: {message!r}"
    # Frontend source data represents only Điều 328, never a Khoản.
    assert source["article_number"] == "328"


def test_round_3_generic_example_context_writes_unknown_not_no_update(tmp_path: Path) -> None:
    """An example discussing refusal is related but non-factual: it must
    write 'unknown' (clearing any stale confirmed), not silently no-update."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"

        _ask(client, "Tôi đang đọc một ví dụ về chủ nhà từ chối giao nhà.", chat_id=chat_id)

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "unknown"


def test_round_3_sentence_scoping_does_not_borrow_actor_across_sentences() -> None:
    """Step 2: an action in one sentence must not attach to an actor/negator
    from a different sentence. 'chính tôi hủy' in the second clause must not
    confirm just because 'chủ nhà' appeared in the first."""

    assert infer_nonperformance("Không phải chủ nhà hủy giao dịch; chính tôi hủy.") != "confirmed"


# ---------------------------------------------------------------------------
# Round 4 (M-01A + M-01B): bounded clause analysis.
#
# M-01A -- global non-factual framing classes: educational/example/document
# description, and reported or quoted questions. Round 3's marker sets were
# too narrow ("tài liệu"/"mô tả" uncovered; the attributed-asker allowlist
# omitted "bạn tôi"; the question-form allowlist omitted "đúng không").
#
# M-01B -- actor attribution is now CLAUSE-scoped, not sentence-scoped: a
# broker's cancellation in a later comma-conjunction clause must never
# borrow the landlord named in an earlier one.
# ---------------------------------------------------------------------------

ROUND_4_EDUCATIONAL_OR_REPORTED_QUESTION = [
    "Tài liệu mô tả chủ nhà từ chối bàn giao.",
    'Bạn tôi hỏi: "Chủ nhà sẽ không giao nhà đúng không?"',
    "Trong tài liệu có ví dụ chủ nhà hủy hợp đồng.",
    "Người tư vấn hỏi chủ nhà có từ chối hay không.",
    "Bài viết mô tả bên nhận cọc từ chối thực hiện hợp đồng.",
]

ROUND_4_BROKER_CLAUSE_ATTRIBUTION = [
    "Chủ nhà đồng ý, nhưng bên môi giới hủy thỏa thuận.",
    "Chủ nhà đồng ý, tuy nhiên bên môi giới hủy thỏa thuận.",
    "Chủ nhà đồng ý, sau đó bên môi giới hủy thỏa thuận.",
    "Chủ nhà đồng ý, hiện bên môi giới hủy thỏa thuận.",
    "Chủ nhà đồng ý, bây giờ bên môi giới hủy thỏa thuận.",
    # Bare comma, no conjunction: not a clause boundary (splitting every
    # comma would destroy actor/action phrases), so this one is caught by
    # the wrong-actor allowlist instead. Both mechanisms are required.
    "Chủ nhà đồng ý, bên môi giới hủy thỏa thuận.",
]

ROUND_4_MUST_NOT_CONFIRM = (
    ROUND_4_EDUCATIONAL_OR_REPORTED_QUESTION + ROUND_4_BROKER_CLAUSE_ATTRIBUTION
)

# Two required negatives never reach `legal_conversation` on a single turn,
# for reasons entirely outside this task's scope (routing must not change):
#   - "Trong tài liệu có ví dụ chủ nhà hủy hợp đồng." trips the PRE-EXISTING
#     destroying-evidence safety pattern ("hủy ... hợp đồng") -> route=unsafe;
#   - "Bài viết mô tả bên nhận cọc từ chối thực hiện hợp đồng." carries no
#     deposit/follow-up routing cue -> route=scope_or_unsupported.
# Both render no source at all, so they cannot leak Khoản 2 either way; they
# are verified by direct inference only.
ROUND_4_MUST_NOT_CONFIRM_E2E = [
    m
    for m in ROUND_4_MUST_NOT_CONFIRM
    if m
    not in {
        "Trong tài liệu có ví dụ chủ nhà hủy hợp đồng.",
        "Bài viết mô tả bên nhận cọc từ chối thực hiện hợp đồng.",
    }
]

ROUND_4_MUST_CONFIRM = [
    "Chủ nhà từ chối giao nhà.",
    "Chủ nhà hủy thỏa thuận thuê nhà.",
    "Chủ nhà nói chắc chắn sẽ không giao nhà.",
    "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng.",
    "Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.",
]


@pytest.mark.parametrize("message", ROUND_4_MUST_NOT_CONFIRM)
def test_round_4_required_negative_direct_inference(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_4_MUST_NOT_CONFIRM_E2E)
def test_round_4_required_negative_end_to_end(tmp_path: Path, message: str) -> None:
    """Persisted state, resolved clause, and the rendered citation must all
    stay at article level: PERSISTED_STATUS_NOT_CONFIRMED / APPLICABLE_CLAUSE
    None / KHOAN_2_RENDERED no / ARTICLE_328_PRESERVED yes."""

    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed", f"persisted confirmed for: {message!r}"

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None, f"clause resolved for: {message!r}"
    assert source["article_number"] == "328"


@pytest.mark.parametrize("message", ROUND_4_MUST_CONFIRM)
def test_round_4_required_positive_direct_inference(message: str) -> None:
    """The positive allowlist must not have been narrowed by the new guards."""

    assert infer_nonperformance(message) == "confirmed"


def test_round_4_bare_unattributed_question_does_not_confirm() -> None:
    """Clause-local question framing (`có ... không`) blocks a positive
    reading even with no reporting verb and no attributed asker -- this was
    an unreported false positive before round 4."""

    assert infer_nonperformance("Chủ nhà có từ chối giao nhà không?") != "confirmed"


def test_round_4_owner_scenario_stays_at_article_level(tmp_path: Path) -> None:
    """The owner's own demo sentence must remain legally safe: a bare
    non-handover/non-return with no refusal or matured-deadline evidence is
    `unknown`, and the citation stays at Điều 328 -- never forced to Khoản 2."""

    message = (
        "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà "
        "và cũng chưa trả lại tiền."
    )
    assert infer_nonperformance(message) == "unknown"

    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà không giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "unknown"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None
    assert source["article_number"] == "328"


def _confirmed_then(tmp_path: Path, follow_up: str) -> str:
    """Establish `confirmed` on turn 1, send ``follow_up`` on turn 2, and
    return the directly-inspected persisted status after turn 2."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
        _ask(client, follow_up, chat_id=chat_id)
    return store.load(chat_id).state.facts.receiving_party_nonperformance_status


def test_round_4_state_confirmed_then_educational_description_clears(tmp_path: Path) -> None:
    assert _confirmed_then(tmp_path, "Tài liệu mô tả chủ nhà từ chối bàn giao.") == "unknown"


def test_round_4_state_confirmed_then_reported_question_clears(tmp_path: Path) -> None:
    assert (
        _confirmed_then(tmp_path, 'Bạn tôi hỏi: "Chủ nhà sẽ không giao nhà đúng không?"')
        == "unknown"
    )


def test_round_4_state_confirmed_then_broker_cancellation_clears(tmp_path: Path) -> None:
    assert _confirmed_then(
        tmp_path, "Chủ nhà đồng ý, nhưng bên môi giới hủy thỏa thuận."
    ) in {"unknown", "not_confirmed"}


def test_round_4_state_confirmed_then_unrelated_question_preserves(tmp_path: Path) -> None:
    """Only a genuinely unrelated message may preserve the prior FACT state.
    Per the MVP safety decision, applicable_clause is None regardless."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        second = _ask(client, "Tôi nên chuẩn bị giấy tờ gì?", chat_id=chat_id).json()

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
    source = next(s for s in second["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


# ---------------------------------------------------------------------------
# Round 5 (M-01B): POSITIVE actor binding.
#
# Round 4 authorized an action by finding a receiving-party actor somewhere
# earlier in the clause and rejecting only actors named in a denylist. That
# is unsound in two ways, both independently reproduced by the round-4
# review: an unlisted third party ("người quen", "bạn bè", "ai đó") borrowed
# the landlord, and the matured-deadline branch bypassed the actor check
# entirely. Round 5 inverts the invariant -- an action confirms only when an
# EXPLICIT receiving-party actor is bound to it as the nearest preceding
# subject -- so every unlisted or unrecognized subject fails closed by
# construction rather than by enumeration.
# ---------------------------------------------------------------------------

ROUND_5_THIRD_PARTY_ACTION = [
    "Chủ nhà đồng ý, người quen hủy thỏa thuận.",
    "Chủ nhà đồng ý, bạn bè hủy thỏa thuận.",
    "Chủ nhà đồng ý, ai đó hủy thỏa thuận.",
    "Chủ nhà đồng ý, hàng xóm hủy thỏa thuận.",
    "Chủ nhà đồng ý, người đại diện hủy thỏa thuận.",
    "Chủ nhà đồng ý, một người khác hủy thỏa thuận.",
]

ROUND_5_MATURED_WRONG_ACTOR = [
    "Chủ nhà đồng ý, bên môi giới đã quá hạn nhưng vẫn chưa giao nhà.",
    "Chủ nhà đồng ý, tôi đã quá hạn nhưng vẫn chưa giao nhà.",
    "Chủ nhà đồng ý, người thuê trước đã quá hạn nhưng vẫn chưa giao nhà.",
    "Chủ nhà đồng ý, luật sư đã quá hạn nhưng vẫn chưa giao nhà.",
    "Chủ nhà đồng ý, người quen đã quá hạn nhưng vẫn chưa giao nhà.",
]

ROUND_5_MUST_NOT_CONFIRM = ROUND_5_THIRD_PARTY_ACTION + ROUND_5_MATURED_WRONG_ACTOR

ROUND_5_MUST_CONFIRM = [
    "Chủ nhà từ chối giao nhà.",
    "Chủ nhà hủy thỏa thuận thuê nhà.",
    # Direct inference must confirm; this one is known not to reach
    # `legal_conversation` (routing deferred to MODE_2E), so it is a
    # direct-only control.
    "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng.",
    "Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.",
    "Theo thỏa thuận đã quá hạn, bên cho thuê vẫn chưa bàn giao nhà.",
]

# Reported/competing-actor statements. Bounded policy: unless the message
# asserts the receiving party's conduct directly, binding fails closed.
# `Chủ nhà nói người quen ...` binds the third party (nearest subject);
# `Người quen nói chủ nhà ...` binds the landlord but is blocked as hearsay
# by the speech-verb guard.
ROUND_5_COMPETING_ACTORS = [
    "Chủ nhà nói người quen đã hủy thỏa thuận.",
    "Chủ nhà thông báo bên môi giới sẽ không giao nhà.",
    "Người quen nói chủ nhà đã hủy thỏa thuận.",
    "Bên môi giới nói chủ nhà từ chối giao nhà.",
    "Tôi nói rằng chủ nhà không thực hiện hợp đồng.",
]

# Constructions the round-4 independent review recorded as SUPPORTED. The
# binding rewrite must not narrow them: in each, the nearest subject before
# the action genuinely IS the receiving party, even though a third party is
# named earlier in the message.
ROUND_5_SUPPORTED_CONSTRUCTIONS = [
    "Tôi vẫn muốn thuê, nhưng chủ nhà từ chối giao nhà.",
    "Bên môi giới vẫn hỗ trợ, nhưng chủ nhà hủy thỏa thuận thuê nhà.",
    "Chủ nhà, là bên nhận cọc, từ chối thực hiện hợp đồng.",
    "Bên môi giới hỗ trợ, nhưng chủ nhà hủy thỏa thuận.",
]


@pytest.mark.parametrize("message", ROUND_5_MUST_NOT_CONFIRM)
def test_round_5_wrong_actor_direct_inference(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_5_MUST_NOT_CONFIRM)
def test_round_5_wrong_actor_end_to_end(tmp_path: Path, message: str) -> None:
    """DIRECT_RESULT_NOT_CONFIRMED / PERSISTED_STATUS_NOT_CONFIRMED /
    APPLICABLE_CLAUSE None / KHOAN_2_RENDERED no, for every third-party
    action and every matured-deadline wrong-actor form."""

    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed", f"persisted confirmed for: {message!r}"

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None, f"clause resolved for: {message!r}"
    assert source["article_number"] == "328"


@pytest.mark.parametrize("message", ROUND_5_MUST_CONFIRM)
def test_round_5_positive_controls_direct_inference(message: str) -> None:
    """Positive actor binding must not have narrowed the supported set."""

    assert infer_nonperformance(message) == "confirmed"


@pytest.mark.parametrize("message", ROUND_5_SUPPORTED_CONSTRUCTIONS)
def test_round_5_supported_constructions_still_confirm(message: str) -> None:
    """A third party named EARLIER in the clause must not block a landlord
    who is genuinely the nearest subject of the action."""

    assert infer_nonperformance(message) == "confirmed"


@pytest.mark.parametrize("message", ROUND_5_COMPETING_ACTORS)
def test_round_5_competing_actor_statements_fail_closed(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


def test_round_5_matured_deadline_binds_actor_to_still_unmet_action() -> None:
    """The matured branch must use the SAME binding as refusal/cancellation,
    not an independent weaker co-occurrence path: identical deadline and
    still-unmet cues flip on the bound actor alone."""

    assert (
        infer_nonperformance("Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.")
        == "confirmed"
    )
    assert (
        infer_nonperformance(
            "Chủ nhà đồng ý, bên môi giới đã quá hạn nhưng vẫn chưa giao nhà."
        )
        != "confirmed"
    )


def test_round_5_unknown_actor_fails_closed() -> None:
    """An action with no explicit actor bound to it is `unknown`, never the
    receiving party -- the invariant that makes an exhaustive third-party
    denylist unnecessary."""

    assert infer_nonperformance("Đã hủy thỏa thuận rồi.") != "confirmed"
    assert infer_nonperformance("Đã quá hạn nhưng vẫn chưa giao nhà.") != "confirmed"


def test_round_5_state_confirmed_then_third_party_cancellation_clears(tmp_path: Path) -> None:
    assert _confirmed_then(tmp_path, "Chủ nhà đồng ý, người quen hủy thỏa thuận.") in {
        "unknown",
        "not_confirmed",
    }


def test_round_5_state_confirmed_then_third_party_matured_clears(tmp_path: Path) -> None:
    assert _confirmed_then(
        tmp_path, "Chủ nhà đồng ý, bên môi giới đã quá hạn nhưng vẫn chưa giao nhà."
    ) in {"unknown", "not_confirmed"}


def test_round_5_state_third_party_then_landlord_refusal_confirms(tmp_path: Path) -> None:
    """not_confirmed/unknown -> explicit landlord refusal -> confirmed FACT.
    Per the MVP safety decision, applicable_clause stays None regardless."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà đồng ý, người quen hủy thỏa thuận.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status != "confirmed"

        second = _ask(client, "Chủ nhà từ chối giao nhà.", chat_id=chat_id).json()

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
    source = next(s for s in second["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


# ---------------------------------------------------------------------------
# Round 6 (M-01B): CONSERVATIVE POSITIVE EVENT GRAMMAR.
#
# Round 5 tried to recognize arbitrary Vietnamese actors and bind the
# nearest one. Independent verification broke it three ways: subjects the
# generic detector never matched (`đại diện công ty`, `cán bộ quản lý`) were
# invisible and borrowed an earlier landlord; larger nouns merely CONTAINING
# a trusted phrase (`hiệp hội chủ nhà`) were read as the trusted subject;
# and `Theo người quen, chủ nhà ...` still confirmed.
#
# Round 6 stops identifying actors altogether. A positive event must match
# one of a small set of affirmative templates anchored so a trusted subject
# heads its own assertion segment. The tests below are therefore
# METAMORPHIC: they assert the invariant over arbitrary unseen subjects and
# prefixes, not over an enumerated list.
# ---------------------------------------------------------------------------

ROUND_6_REQUIRED_FAILURES = [
    "Chủ nhà đồng ý, đại diện công ty hủy giao dịch.",
    "Chủ nhà đồng ý, cán bộ quản lý hủy hợp đồng.",
    "Hiệp hội chủ nhà hủy thỏa thuận.",
    "Câu lạc bộ chủ nhà từ chối giao nhà.",
    "Theo người quen, chủ nhà đã hủy thỏa thuận.",
    "Theo hàng xóm, chủ nhà từ chối giao nhà.",
]

# "Chủ nhà đồng ý, cán bộ quản lý hủy hợp đồng." trips the PRE-EXISTING
# destroying-evidence safety pattern ("hủy ... hợp đồng") in
# `fast_demo_routing.py` -> route=unsafe, so it renders no source at all and
# cannot leak Khoản 2 by any path. Routing is out of scope for this task, so
# it is verified by direct inference only.
ROUND_6_REQUIRED_FAILURES_E2E = [
    m for m in ROUND_6_REQUIRED_FAILURES if m != "Chủ nhà đồng ý, cán bộ quản lý hủy hợp đồng."
]

ROUND_6_REQUIRED_POSITIVES = [
    "Chủ nhà từ chối giao nhà.",
    "Chủ nhà hủy thỏa thuận thuê nhà.",
    "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng.",
    "Bên cho thuê nói chắc chắn sẽ không bàn giao nhà.",
    "Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.",
    "Theo thỏa thuận đã quá hạn, bên cho thuê vẫn chưa bàn giao nhà.",
]

ROUND_6_ATTRIBUTION_FAILURES = [
    "Theo người quen, chủ nhà đã hủy thỏa thuận.",
    "Theo hàng xóm, chủ nhà từ chối giao nhà.",
    "Theo đại diện công ty, bên cho thuê không thực hiện hợp đồng.",
    "Người quen nói chủ nhà đã hủy thỏa thuận.",
    "Bên môi giới cho biết chủ nhà từ chối giao nhà.",
]

ROUND_6_SUBJECT_BORROWING_FAILURES = [
    "Chủ nhà đồng ý, đại diện công ty hủy giao dịch.",
    "Chủ nhà đồng ý, cán bộ quản lý hủy hợp đồng.",
    "Chủ nhà đồng ý, nhân viên công ty từ chối bàn giao.",
    "Chủ nhà đồng ý, tổ chức khác không thực hiện hợp đồng.",
    "Chủ nhà đồng ý, người được ủy quyền hủy thỏa thuận.",
]

ROUND_6_MATURED_FAILURES = [
    "Hiệp hội chủ nhà đã quá hạn nhưng vẫn chưa giao nhà.",
    "Chủ nhà đồng ý, đại diện công ty đã quá hạn nhưng chưa giao nhà.",
    "Đã quá hạn nhưng chưa rõ ai phải giao nhà.",
    "Theo người quen, chủ nhà đã quá hạn nhưng chưa giao nhà.",
]

# Metamorphic corpora. None of these subjects/prefixes appears anywhere in
# the implementation -- that is the point.
ROUND_6_ARBITRARY_UNTRUSTED_SUBJECTS = [
    "đại diện công ty",
    "cán bộ quản lý",
    "tổ chức X",
    "nhân viên Y",
    "người A",
    "bên thứ ba",
    "đơn vị quản lý",
    "hội đồng ABC",
    "ông Nguyễn Văn A",
    "văn phòng luật XYZ",
]

ROUND_6_ARBITRARY_LARGER_NOUN_PREFIXES = [
    "Hiệp hội",
    "Câu lạc bộ",
    "Nhóm",
    "Đại diện",
    "Tổ chức của",
    "Liên minh",
    "Văn phòng",
]

ROUND_6_ARBITRARY_REPORTING_SUBJECTS = [
    "người quen",
    "hàng xóm",
    "đại diện công ty",
    "một người bạn",
    "ông A",
    "bên thứ ba",
    "đơn vị quản lý",
]


@pytest.mark.parametrize("message", ROUND_6_REQUIRED_FAILURES)
def test_round_6_required_failures_direct_inference(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_6_REQUIRED_FAILURES_E2E)
def test_round_6_required_failures_end_to_end(tmp_path: Path, message: str) -> None:
    """PERSISTED_STATUS_NOT_CONFIRMED / APPLICABLE_CLAUSE None /
    KHOAN_2_RENDERED no / ARTICLE_328_PRESERVED yes."""

    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed", f"persisted confirmed for: {message!r}"

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None, f"clause resolved for: {message!r}"
    assert source["article_number"] == "328"


@pytest.mark.parametrize("message", ROUND_6_REQUIRED_POSITIVES)
def test_round_6_required_positives_direct_inference(message: str) -> None:
    """The grammar must still admit every supported affirmative structure."""

    assert infer_nonperformance(message) == "confirmed"


@pytest.mark.parametrize("message", ROUND_6_ATTRIBUTION_FAILURES)
def test_round_6_attributed_statements_fail_closed(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_6_SUBJECT_BORROWING_FAILURES)
def test_round_6_subject_borrowing_fails_closed(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("message", ROUND_6_MATURED_FAILURES)
def test_round_6_matured_deadline_grammar_fails_closed(message: str) -> None:
    assert infer_nonperformance(message) != "confirmed"


@pytest.mark.parametrize("subject", ROUND_6_ARBITRARY_UNTRUSTED_SUBJECTS)
def test_round_6_metamorphic_arbitrary_subject_never_borrows(subject: str) -> None:
    """INVARIANT: `Chủ nhà đồng ý, <any subject> hủy thỏa thuận.` never
    confirms -- for subjects the implementation has never seen. The grammar
    does not classify the subject at all; it simply is not a trusted subject
    at the head of its segment."""

    assert infer_nonperformance(f"Chủ nhà đồng ý, {subject} hủy thỏa thuận.") != "confirmed"


@pytest.mark.parametrize("prefix", ROUND_6_ARBITRARY_LARGER_NOUN_PREFIXES)
def test_round_6_metamorphic_larger_noun_never_trusted(prefix: str) -> None:
    """INVARIANT: a larger noun merely CONTAINING a trusted phrase is never
    trusted, for arbitrary prefixes."""

    assert infer_nonperformance(f"{prefix} chủ nhà hủy thỏa thuận.") != "confirmed"


@pytest.mark.parametrize("reporter", ROUND_6_ARBITRARY_REPORTING_SUBJECTS)
def test_round_6_metamorphic_attribution_never_confirms(reporter: str) -> None:
    """INVARIANT: the attribution MARKER makes the statement
    non-authoritative, whoever the reporting subject is."""

    assert infer_nonperformance(f"Theo {reporter}, chủ nhà hủy thỏa thuận.") != "confirmed"


def test_round_6_trusted_subject_must_head_its_own_segment() -> None:
    """The same words confirm or fail purely on whether the trusted subject
    heads the assertion segment."""

    assert infer_nonperformance("Chủ nhà hủy thỏa thuận.") == "confirmed"
    assert infer_nonperformance("Hiệp hội chủ nhà hủy thỏa thuận.") != "confirmed"
    assert infer_nonperformance("Bên cho thuê căn nhà này hủy thỏa thuận.") != "confirmed"


def test_round_6_trusted_appositive_is_transparent() -> None:
    """A bounded appositive that merely restates the trusted subject must not
    break the segment (round-4-verified supported construction)."""

    assert (
        infer_nonperformance("Chủ nhà, là bên nhận cọc, từ chối thực hiện hợp đồng.")
        == "confirmed"
    )


def test_round_6_state_confirmed_then_unseen_subject_clears(tmp_path: Path) -> None:
    assert _confirmed_then(tmp_path, "Chủ nhà đồng ý, đại diện công ty hủy giao dịch.") in {
        "unknown",
        "not_confirmed",
    }


def test_round_6_state_confirmed_then_attributed_report_clears(tmp_path: Path) -> None:
    assert _confirmed_then(tmp_path, "Theo người quen, chủ nhà đã hủy thỏa thuận.") in {
        "unknown",
        "not_confirmed",
    }


# ---------------------------------------------------------------------------
# MVP SAFETY CONVERGENCE: automatic Khoản 2 selection is disabled.
#
# Correction rounds 1 through 6 progressively narrowed the conditions under
# which free-form language could select Khoản 2 Điều 328, and independent
# verification kept finding narrow adversarial inputs that still confirmed
# unsafely. The product decision for this MVP is to stop deriving a
# structured legal consequence from free-form language altogether:
# `resolve_deposit_applicable_clause` now unconditionally returns `None`.
# The nonperformance FACT may still be computed and persisted (round 4-6
# inference is unchanged and untouched by this task), but it has zero
# authority over the structured citation.
# ---------------------------------------------------------------------------

MVP_INVARIANT_MESSAGES = [
    "Chủ nhà từ chối giao nhà.",
    "Chủ nhà hủy thỏa thuận thuê nhà.",
    "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng.",
    "Đã quá hạn bàn giao nhưng chủ nhà vẫn chưa giao nhà.",
    "Theo thỏa thuận đã quá hạn, bên cho thuê vẫn chưa bàn giao nhà.",
    "Chủ nhà thông báo sẽ không trả lời.",
    "Theo hợp đồng, chủ nhà hủy thỏa thuận.",
    "Thẻ của tôi đã quá hạn, chủ nhà chưa giao nhà.",
]

# "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng." does not reach
# `legal_conversation` in a single turn (the known, pre-existing MODE_2E
# routing gap -- routing is out of scope for this task) and so renders no
# source at all; it cannot be checked end to end for that reason, not
# because of anything this task changed. It is still covered by the
# resolver-level invariant test below, which does not depend on routing.
MVP_INVARIANT_MESSAGES_E2E = [
    m for m in MVP_INVARIANT_MESSAGES
    if m != "Bên nhận cọc thông báo sẽ không thực hiện hợp đồng."
]


@pytest.mark.parametrize("message", MVP_INVARIANT_MESSAGES_E2E)
def test_mvp_automatic_clause_2_disabled_for_every_representative_message(
    tmp_path: Path, message: str
) -> None:
    """No representative refusal/cancellation/matured-deadline message may
    ever select Khoản 2 in this MVP, regardless of what the nonperformance
    fact resolves to."""

    plan = _plan(fact_updates=[_nonperformance_update(message)])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None, f"clause resolved for: {message!r}"
    assert source["article_number"] == "328"
    assert source["document_number"] == DOCUMENT_NUMBER
    assert source["url"] == PRIMARY_URL


@pytest.mark.parametrize("status", ["unknown", "not_confirmed", "confirmed"])
@pytest.mark.parametrize(
    "clause_numbers",
    [None, [], [1], [2], [1, 2], [2, 3]],
    ids=["none", "empty", "one", "two_only", "one_two", "two_three"],
)
def test_mvp_resolver_returns_none_for_every_fact_state_and_clause_list(
    status: str, clause_numbers: list[int] | None
) -> None:
    """Complete 3x6 matrix (LOW-01): every fact state combined with every
    clause-list shape -- including [2] and [2, 3], which a curated snippet
    could in principle carry even though civil_deposit_001 itself does not
    -- must return None. The resolver is unconditional; it does not inspect
    either argument."""

    facts = FastDemoFacts(receiving_party_nonperformance_status=status)
    assert resolve_deposit_applicable_clause(facts, clause_numbers) is None


def test_mvp_stale_confirmed_fact_cannot_select_clause_2(tmp_path: Path) -> None:
    """A pre-existing `confirmed` fact from an earlier turn must not cause
    applicable_clause=2 on a later, unrelated turn."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
        second = _ask(client, "Chủ nhà nói gì về tình trạng nhà?", chat_id=chat_id).json()

    source = next(s for s in second["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


def test_mvp_newly_confirmed_fact_cannot_select_clause_2(tmp_path: Path) -> None:
    """A fact that becomes `confirmed` on THIS turn must not cause
    applicable_clause=2 either."""

    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà hủy thỏa thuận")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Chủ nhà hủy thỏa thuận thuê nhà.").json()
        chat_id = body["chat_id"]

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


def test_mvp_owner_scenario_matches_required_citation_fields(tmp_path: Path) -> None:
    message = (
        "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà "
        "và cũng chưa trả lại tiền."
    )
    plan = _plan(
        fact_updates=[
            {"operation": "set", "slot": "deposit_amount", "value": 20000000,
             "evidence_quote": "20 triệu"},
            _nonperformance_update("chủ nhà không giao nhà"),
        ],
    )
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, message).json()
        chat_id = body["chat_id"]

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None
    assert source["article_number"] == "328"
    assert source["document_number"] == DOCUMENT_NUMBER
    assert source["url"] == PRIMARY_URL
    facts = store.load(chat_id).state.facts
    assert facts.deposit_amount.value == 20000000
    # No unconditional double-deposit conclusion anywhere in the note.
    assert "gấp đôi" not in (source["relevance_note"] or "")
    assert "chắc chắn được" not in (source["relevance_note"] or "")


# ---------------------------------------------------------------------------
# Round 2, tests 24-26: selective-quote attack. The FULL current message is
# hypothetical/negated/unverified-quoted, but the model proposes ONLY the
# embedded positive substring as its evidence_quote. The persisted value and
# the resolved clause must both be defeated by the full-message trust
# boundary regardless of what the model selected.
# ---------------------------------------------------------------------------

def test_24_selective_quote_attack_hypothetical_defeated(tmp_path: Path) -> None:
    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Nếu chủ nhà từ chối giao nhà thì tôi phải làm gì?").json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


def test_25_selective_quote_attack_negated_defeated(tmp_path: Path) -> None:
    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Chủ nhà không từ chối giao nhà.").json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


def test_26_selective_quote_attack_unverified_quote_defeated(tmp_path: Path) -> None:
    plan = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(
            client,
            'Tin nhắn ghi: "chủ nhà từ chối giao nhà" nhưng tôi chưa xác minh.',
        ).json()
        chat_id = body["chat_id"]

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


# ---------------------------------------------------------------------------
# Round 2, tests 27-32: state transitions. Persisted state is inspected
# directly via the store, not only via response rendering.
# ---------------------------------------------------------------------------

def test_27_confirmed_to_not_yet_due_clears_to_not_confirmed(tmp_path: Path) -> None:
    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("tuần sau mới đến hạn")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"

        _ask(client, "Chủ nhà nói tuần sau mới đến hạn giao nhà.", chat_id=chat_id)

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "not_confirmed"


def test_28_confirmed_to_hypothetical_clears_to_unknown(tmp_path: Path) -> None:
    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"

        _ask(client, "Nếu chủ nhà từ chối giao nhà thì tôi phải làm gì?", chat_id=chat_id)

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "unknown"


def test_29_confirmed_to_contradictory_clears_from_confirmed(tmp_path: Path) -> None:
    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà nhưng chưa đến hạn giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"

        _ask(
            client,
            "Chủ nhà từ chối giao nhà nhưng chưa đến hạn giao nhà.",
            chat_id=chat_id,
        )

    persisted = store.load(chat_id).state.facts.receiving_party_nonperformance_status
    assert persisted != "confirmed"


def test_30_not_confirmed_to_explicit_refusal_becomes_confirmed(tmp_path: Path) -> None:
    plan1 = _plan(fact_updates=[_nonperformance_update("tuần sau mới đến hạn")])
    plan2 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà nói tuần sau mới đến hạn giao nhà.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "not_confirmed"

        _ask(client, "Chủ nhà từ chối giao nhà.", chat_id=chat_id)

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"


def test_31_confirmed_survives_a_genuinely_unrelated_message(tmp_path: Path) -> None:
    """Only an unrelated message may preserve the previous FACT state
    unchanged. Per the MVP safety decision, applicable_clause stays None."""

    plan1 = _plan(fact_updates=[_nonperformance_update("chủ nhà từ chối giao nhà")])
    plan2 = _plan(fact_updates=[])
    app, fake, store = _build(tmp_path, [plan1, plan2])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà từ chối giao nhà cho tôi.").json()
        chat_id = first["chat_id"]
        assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"

        second = _ask(client, "Tôi nên chuẩn bị giấy tờ gì?", chat_id=chat_id).json()

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
    source = next(s for s in second["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None


def test_32_end_to_end_confirmed_refusal_never_selects_khoan_2(tmp_path: Path) -> None:
    """MVP safety decision: even an explicit, confirmed refusal renders
    Điều 328 only -- applicable_clause is always None, regardless of the
    persisted nonperformance fact (formerly `..._resolves_clause_2`)."""

    plan = _plan(
        fact_updates=[
            {"operation": "set", "slot": "deposit_amount", "value": 20000000,
             "evidence_quote": "20 triệu"},
            _nonperformance_update("chủ nhà từ chối giao nhà"),
        ],
    )
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(
            client,
            "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà từ chối giao nhà.",
        ).json()
        chat_id = body["chat_id"]

    assert store.load(chat_id).state.facts.receiving_party_nonperformance_status == "confirmed"
    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None
    assert source["article_number"] == "328"
    assert source["document_number"] == DOCUMENT_NUMBER
    assert source["url"] == PRIMARY_URL
    assert fake.calls == 1


def test_unresolved_facts_render_dieu_328_without_khoan(tmp_path: Path) -> None:
    plan = _plan()
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà chưa giao nhà.").json()

    source = next(s for s in body["sources"] if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert source["applicable_clause"] is None
    assert source["article_number"] == "328"


# ---------------------------------------------------------------------------
# Runtime clause-membership invariant (unchanged from round 1)
# ---------------------------------------------------------------------------

def test_applicable_clause_must_belong_to_curated_clause_numbers() -> None:
    """MVP safety decision: the resolver returns None for every fact state
    and every curated clause list, including a fully curated [1, 2] with a
    confirmed nonperformance fact. The runtime membership invariant in
    attach_deposit_citation_metadata is retained as defense in depth even
    though it is currently never exercised."""

    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts, [1]) is None
    assert resolve_deposit_applicable_clause(facts, [1, 2]) is None

    source_missing_clause_2 = _base_source(clause_numbers=[1])
    result = attach_deposit_citation_metadata(source_missing_clause_2, facts)
    assert result.applicable_clause is None


# ---------------------------------------------------------------------------
# Round 2, tests 33-42: build/resolver strict typing and fail-closed
# ---------------------------------------------------------------------------

def test_33_quoted_numeric_clause_strings_fail_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", 'clause_numbers: ["1", "2"]')
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_34_float_clause_values_fail_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", "clause_numbers: [1.0, 2]")
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_35_boolean_clause_values_fail_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", "clause_numbers: [true, 2]")
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_36_zero_padded_quoted_clause_strings_fail_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", 'clause_numbers: ["01", "02"]')
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


# ---------------------------------------------------------------------------
# Round 3 (M-02B): the SHARED inline-list parser must stay string-only for
# every field other than clause_numbers. Round 2 accidentally made
# `split_inline_list` globally type-aware, which changed unrelated fields'
# (e.g. tags) acceptance of unquoted booleans/numbers.
# ---------------------------------------------------------------------------

def test_shared_parser_unquoted_booleans_stay_strings() -> None:
    assert build_snippets.split_inline_list("[true, false]") == ["true", "false"]


def test_shared_parser_unquoted_integers_stay_strings() -> None:
    assert build_snippets.split_inline_list("[123, 456]") == ["123", "456"]


def test_shared_parser_unquoted_decimals_stay_strings() -> None:
    assert build_snippets.split_inline_list("[1.5, 2.0]") == ["1.5", "2.0"]


def test_shared_parser_bare_words_stay_strings() -> None:
    assert build_snippets.split_inline_list("[alpha, beta]") == ["alpha", "beta"]


def test_shared_parser_quoted_embedded_comma_unaffected() -> None:
    assert build_snippets.split_inline_list('["alpha,beta", gamma]') == ["alpha,beta", "gamma"]


def test_tags_field_with_unquoted_booleans_and_numbers_still_builds(tmp_path: Path) -> None:
    """A non-clause_numbers field authoring unquoted true/false/numbers must
    build exactly as it did before round 2's global-typing regression."""

    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(
        root,
        'tags: ["dat_coc", "tien_coc", "hop_dong", "chu_nha_giu_coc", "thue_nha", "dan_su", "tranh_chap_tien"]',
        "tags: [true, false, 123, 1.5, alpha]",
    )
    snippets = build_snippets.build(root, tmp_path / "out.json")
    entry = next(s for s in snippets if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert entry["tags"] == ["true", "false", "123", "1.5", "alpha"]
    assert all(isinstance(t, str) for t in entry["tags"])


def test_clause_numbers_strict_parser_rejects_single_quoted_strings(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", "clause_numbers: ['1', '2']")
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_clause_numbers_strict_parser_rejects_false(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", "clause_numbers: [false, 2]")
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_clause_numbers_strict_parser_rejects_mixed_int_and_string(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", 'clause_numbers: [1, "2"]')
    with pytest.raises(build_snippets.SnippetBuildError, match="non-integer item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


# ---------------------------------------------------------------------------
# Trailing/leading/doubled-comma correction (M-03): the strict clause_numbers
# grammar accepts only `[1, 2]` -- any empty segment from a stray comma is a
# hard build error, never silently discarded. The shared list parser's own
# comma-drops-empty-item behavior is untouched, proven directly and via a
# full build on an unrelated `tags` field.
# ---------------------------------------------------------------------------

def test_clause_numbers_strict_parser_rejects_trailing_comma() -> None:
    with pytest.raises(ValueError, match="empty item"):
        build_snippets.parse_clause_numbers_strict("[1, 2,]")


def test_clause_numbers_strict_parser_rejects_leading_comma() -> None:
    with pytest.raises(ValueError, match="empty item"):
        build_snippets.parse_clause_numbers_strict("[,1, 2]")


def test_clause_numbers_strict_parser_rejects_double_comma() -> None:
    with pytest.raises(ValueError, match="empty item"):
        build_snippets.parse_clause_numbers_strict("[1,,2]")


def test_clause_numbers_strict_parser_rejects_whitespace_only_token() -> None:
    with pytest.raises(ValueError, match="empty item"):
        build_snippets.parse_clause_numbers_strict("[1, ,2]")


def test_clause_numbers_strict_parser_accepts_exact_valid_form() -> None:
    assert build_snippets.parse_clause_numbers_strict("[1, 2]") == [1, 2]


def test_trailing_comma_fails_the_build_with_no_partial_output(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", "clause_numbers: [1, 2,]")
    with pytest.raises(build_snippets.SnippetBuildError, match="empty item"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_shared_tags_parser_trailing_comma_behavior_unchanged() -> None:
    """The shared parser's pre-existing stray-comma tolerance for unrelated
    fields (tags, risk_notes, ...) must not change: it silently drops the
    empty segment rather than rejecting it, exactly as before M-03."""

    assert build_snippets.split_inline_list("[alpha, beta,]") == ["alpha", "beta"]
    assert build_snippets.split_inline_list("[,alpha, beta]") == ["alpha", "beta"]


def test_37_omitted_clause_list_returns_none() -> None:
    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts) is None
    assert resolve_deposit_applicable_clause(facts, None) is None


def test_38_empty_clause_list_returns_none() -> None:
    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts, []) is None


def test_39_single_clause_without_2_returns_none() -> None:
    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts, [1]) is None


def test_40_confirmed_plus_curated_two_still_returns_none() -> None:
    """MVP safety decision (formerly `..._returns_2`): a fully curated
    clause list plus a confirmed nonperformance fact no longer selects
    clause 2 -- automatic clause selection is disabled unconditionally."""

    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    assert resolve_deposit_applicable_clause(facts, [1, 2]) is None


def test_41_runtime_attachment_still_rejects_uncurated_clause() -> None:
    facts = FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    source_missing_clause_2 = _base_source(clause_numbers=[1])
    result = attach_deposit_citation_metadata(source_missing_clause_2, facts)
    assert result.applicable_clause is None


def test_42_valid_corpus_rebuild_remains_byte_identical(tmp_path: Path) -> None:
    before = SNIPPETS_PATH.read_text(encoding="utf-8")
    out = tmp_path / "rebuilt.json"
    build_snippets.build(SNIPPETS_MD_ROOT, out)
    after = out.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# 5/6/7 (schema trust boundary, unchanged from round 0, reconfirmed)
# ---------------------------------------------------------------------------

def test_model_cannot_declare_an_article_or_clause_field_at_all() -> None:
    payload = {
        "response_kind": "legal", "response_mode": "guidance", "summary": "x",
        "analysis": None, "clarifying_questions": [], "checklist": [],
        "next_steps": [], "draft": None, "known_facts_summary": [],
        "uncertainty_notice": None, "fact_updates": [],
        "selected_source_ids": ["civil_deposit_001"],
        "article_number": "999",
        "applicable_clause": 5,
    }
    with pytest.raises(ValidationError):
        FastDemoPlan.model_validate(payload)


def test_model_cannot_inject_a_citation_url_or_document_identity() -> None:
    payload = {
        "response_kind": "legal", "response_mode": "guidance", "summary": "x",
        "analysis": None, "clarifying_questions": [], "checklist": [],
        "next_steps": [], "draft": None, "known_facts_summary": [],
        "uncertainty_notice": None, "fact_updates": [],
        "selected_source_ids": ["civil_deposit_001"],
        "source_url": "https://evil.example/fake-law",
        "document_title": "Luật bịa đặt",
    }
    with pytest.raises(ValidationError):
        FastDemoPlan.model_validate(payload)


def test_unknown_source_id_is_dropped_not_rendered(tmp_path: Path) -> None:
    plan = _plan(selected_source_ids=["civil_deposit_001", "invented_article_999"])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà chưa giao nhà.").json()

    ids = [s["id"] for s in body["sources"]]
    assert ids == [DEPOSIT_AUTHORITY_ID]
    assert "invented_article_999" not in ids


# ---------------------------------------------------------------------------
# No duplicate, source-less stays empty, unrelated sources unaffected
# ---------------------------------------------------------------------------

def test_selecting_the_same_id_twice_does_not_duplicate_the_source(tmp_path: Path) -> None:
    plan = _plan(selected_source_ids=["civil_deposit_001", "civil_deposit_001"])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà chưa giao nhà.").json()

    ids = [s["id"] for s in body["sources"]]
    assert ids == [DEPOSIT_AUTHORITY_ID]


def test_sourceless_response_has_no_sources_and_no_invented_citation(tmp_path: Path) -> None:
    plan = _plan(selected_source_ids=[])
    app, fake, store = _build(tmp_path, [plan])
    with TestClient(app) as client:
        body = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà chưa giao nhà.").json()

    assert body["sources"] == []


def test_unrelated_snippets_carry_no_article_level_metadata() -> None:
    snippets = json.loads(SNIPPETS_PATH.read_text(encoding="utf-8"))
    for entry in snippets:
        if entry["id"] == DEPOSIT_AUTHORITY_ID:
            continue
        assert entry.get("article_number") is None
        assert entry.get("document_title") is None
        assert not entry.get("clause_numbers")


def test_relevance_note_is_single_general_conditional_article_level_note() -> None:
    """MVP safety decision: since applicable_clause is always None, there is
    exactly one relevance note -- general, conditional, article-level only
    -- regardless of the nonperformance fact (formerly two distinct
    confirmed/unresolved variants)."""

    confirmed = attach_deposit_citation_metadata(
        _base_source(), FastDemoFacts(receiving_party_nonperformance_status="confirmed")
    )
    unresolved = attach_deposit_citation_metadata(_base_source(), FastDemoFacts())

    assert confirmed.applicable_clause is None
    assert unresolved.applicable_clause is None
    assert confirmed.relevance_note is not None
    # Same note regardless of the fact state -- the MVP decision does not
    # vary the citation's structured or textual content by inferred facts.
    assert confirmed.relevance_note == unresolved.relevance_note

    note = confirmed.relevance_note
    # Never an unconditional entitlement, guaranteed recovery, a claim that
    # Khoản 2 applies, or a specific compensation amount.
    assert "40" not in note
    assert "gấp đôi" not in note
    assert "chắc chắn được" not in note
    assert "khoản 2" not in note.lower()
    # Must explain what Điều 328 concerns and condition any further
    # consequence on verified facts / the agreement.
    assert "đặt cọc" in note
    assert "phụ thuộc" in note


# ---------------------------------------------------------------------------
# M-02: exact build-time legal identity gate (round 1, reconfirmed)
# ---------------------------------------------------------------------------

def _copy_snippets_md(tmp_path: Path) -> Path:
    import shutil

    dest = tmp_path / "snippets_md"
    shutil.copytree(SNIPPETS_MD_ROOT, dest)
    return dest


def _replace_in_deposit_md(root: Path, old: str, new: str) -> None:
    target = root / "civil_dispute" / "001_civil_deposit_001.md"
    text = target.read_text(encoding="utf-8").replace(old, new)
    assert text != target.read_text(encoding="utf-8"), "replacement had no effect"
    target.write_text(text, encoding="utf-8")


def test_wrong_article_number_fails_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, 'article_number: "328"', 'article_number: "999"')
    with pytest.raises(build_snippets.SnippetBuildError, match="article_number must be exactly"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_wrong_article_title_fails_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, 'article_title: "Đặt cọc"', 'article_title: "Bịa đặt"')
    with pytest.raises(build_snippets.SnippetBuildError, match="article_title must be exactly"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_wrong_document_title_fails_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, 'document_title: "Bộ luật Dân sự 2015"', 'document_title: "Luật bịa đặt"')
    with pytest.raises(build_snippets.SnippetBuildError, match="document_title must be exactly"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize(
    "bad_clauses,expected_match",
    [
        ("[1]", "clause_numbers must be exactly"),
        ("[2]", "clause_numbers must be exactly"),
        ("[1, 3]", "clause_numbers must be exactly"),
        ("[1, 1, 2]", "duplicate clause numbers"),
        ("[2, 1]", "sorted ascending"),
    ],
)
def test_malformed_clause_list_fails_the_build(tmp_path: Path, bad_clauses: str, expected_match: str) -> None:
    root = _copy_snippets_md(tmp_path)
    _replace_in_deposit_md(root, "clause_numbers: [1, 2]", f"clause_numbers: {bad_clauses}")
    with pytest.raises(build_snippets.SnippetBuildError, match=expected_match):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_article_metadata_on_unexpected_snippet_fails_the_build(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    target = root / "traffic" / "007_traffic_law_001.md"
    text = target.read_text(encoding="utf-8")
    text = text.replace("source_type: official_source", 'article_number: "211194"\nsource_type: official_source')
    target.write_text(text, encoding="utf-8")

    with pytest.raises(build_snippets.SnippetBuildError, match="not on the approved article-citation allowlist"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_real_authoring_data_passes_the_exact_identity_gate() -> None:
    output = Path("/tmp") / "mode2d_correction_probe_out.json"
    snippets = build_snippets.build(SNIPPETS_MD_ROOT, output)
    entry = next(s for s in snippets if s["id"] == DEPOSIT_AUTHORITY_ID)
    assert entry["article_number"] == "328"
    assert entry["clause_numbers"] == [1, 2]
    output.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Frontend-adjacent regression: generic-source and source-less behavior
# unaffected by this correction.
# ---------------------------------------------------------------------------

def test_generic_source_display_unaffected_by_the_correction(tmp_path: Path) -> None:
    # civil_contract_002 (CONTRACT_EFFECT_ID) is displayable (official_source)
    # and carries no article-level metadata in this task -- an unrelated
    # bounded Civil Code source whose generic display must stay unaffected.
    # It is selected by the pack once rental_contract_status == "present" in
    # loaded.state, so a prior turn establishes that fact first.
    setup_plan = _plan(
        selected_source_ids=["civil_deposit_001"],
        fact_updates=[
            {"operation": "affirm", "slot": "rental_contract_status",
             "value": None, "evidence_quote": "có hợp đồng thuê nhà"},
        ],
    )
    follow_up_plan = _plan(selected_source_ids=["civil_deposit_001", "civil_contract_002"])
    app, fake, store = _build(tmp_path, [setup_plan, follow_up_plan])
    with TestClient(app) as client:
        first = _ask(client, "Chủ nhà chưa trả cọc, tôi có hợp đồng thuê nhà.").json()
        chat_id = first["chat_id"]
        body = _ask(client, "Chủ nhà vẫn chưa trả cọc.", chat_id=chat_id).json()

    contract = next((s for s in body["sources"] if s["id"] == "civil_contract_002"), None)
    assert contract is not None
    assert contract.get("article_number") is None
    assert contract.get("document_title") is None
