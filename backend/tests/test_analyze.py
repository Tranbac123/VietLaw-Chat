"""End-to-end analyze() — error matrix."""
import json
from pathlib import Path

import pytest

from app.analyze import AiCore
from app.chat_store import ChatStore
from app.config import Settings
from app.errors import ChatNotFound, InvalidRequest, LlmError
from app.patterns import PatternBank
from app.rag_retriever import Retriever, load_snippets
from app.schemas import AnalyzeRequest, Decision, Domain, RiskLevel

_ROOT = Path(__file__).resolve().parents[2] / "data"


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def generate(self, prompt):
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def _core(tmp_path, llm_text='{"summary":"Tóm tắt vụ việc.","clarifying_questions":["Bạn có hợp đồng không?"],"checklist":["Hợp đồng"],"next_steps":["Chuẩn bị giấy tờ"],"used_source_ids":[]}'):
    settings = Settings(_env_file=None, chat_db_path=str(tmp_path / "c.sqlite3"))
    if isinstance(llm_text, Exception):
        # Real client wraps transport failures into LlmError after retry.
        from app.llm_client import LLMClient

        def boom(_prompt):
            raise llm_text
        llm = LLMClient(settings, transport=boom)
    else:
        llm = FakeLLM(llm_text)
    return AiCore(
        settings,
        store=ChatStore(str(tmp_path / "c.sqlite3")),
        bank=PatternBank.load(str(_ROOT / "unsafe_patterns.json")),
        retriever=Retriever(load_snippets(str(_ROOT / "legal_snippets.json"))),
        llm=llm,
    )


def _req(q, **kw):
    return AnalyzeRequest(question=q, session_id=kw.pop("session_id", "s1"), **kw)


# ---- demo 1: civil deposit ----

def test_demo_deposit(tmp_path):
    r = _core(tmp_path).analyze(_req("Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?"))
    assert r.domain == Domain.civil_dispute
    assert r.risk_level == RiskLevel.medium
    assert r.decision == Decision.ask_clarifying_questions
    assert r.chat_id and r.user_message_id and r.assistant_message_id
    assert r.sources  # source panel populated
    assert r.safety_notice
    assert r.metadata.used_llm is True


# ---- demo 5: follow-up in same chat ----

def test_followup_same_chat_keeps_domain_and_history(tmp_path):
    core = _core(tmp_path)
    first = core.analyze(_req("Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?"))
    second = core.analyze(_req("Vậy tôi cần chuẩn bị giấy tờ gì?", chat_id=first.chat_id))
    assert second.chat_id == first.chat_id
    assert second.domain == Domain.civil_dispute
    assert second.metadata.used_current_chat_history is True
    assert second.sources  # retrieved via same-chat context


# ---- demo 4: unsafe evasion ----

def test_unsafe_evasion_refused(tmp_path):
    r = _core(tmp_path).analyze(_req("Làm sao để né phạt giao thông?"))
    assert r.domain == Domain.high_risk
    assert r.risk_level == RiskLevel.high
    assert r.decision == Decision.refuse_unsafe_request
    # Refusal may surface safety/high-risk sources, never a harmful how-to.
    for s in r.sources:
        assert s.source_type in ("safety_policy", "official_source", "procedure", "curated_note")
    assert r.metadata.unsafe_intent_detected is True
    assert r.metadata.detected_topic == "traffic"
    assert "legal_evasion" in r.metadata.safety_flags
    assert "traffic_evasion" in r.metadata.safety_flags
    assert r.metadata.used_llm is False


# ---- unsupported language + non-legal ----

def test_unsupported_language(tmp_path):
    r = _core(tmp_path).analyze(_req("What documents do I need to sell food online?", language="en"))
    assert r.decision == Decision.unsupported
    assert r.domain == Domain.unknown
    assert r.metadata.used_llm is False


def test_non_legal_unsupported(tmp_path):
    r = _core(tmp_path).analyze(_req("Viết cho tôi bài thơ tình."))
    assert r.decision == Decision.unsupported


# ---- empty retrieval must not yield ungrounded guidance ----

def test_sourceless_guidance_downgrades_to_clarify(tmp_path):
    # Pure procedural question: routes administrative/answer_with_guidance but no
    # snippet token overlaps → empty retrieval. Must ask to clarify, not fabricate.
    r = _core(tmp_path).analyze(_req("Tôi cần chuẩn bị hồ sơ gì?"))
    assert r.metadata.retrieval_count == 0
    assert r.decision == Decision.ask_clarifying_questions


# ---- fallback + error classification ----

def test_llm_parse_failure_falls_back_200(tmp_path):
    r = _core(tmp_path, llm_text="totally not json").analyze(
        _req("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả."))
    assert r.metadata.llm_parse_error is True
    assert r.clarifying_questions  # cautious fallback content
    assert r.decision == Decision.ask_clarifying_questions


def test_llm_unreachable_raises_llm_error(tmp_path):
    core = _core(tmp_path, llm_text=TimeoutError("down"))
    with pytest.raises(LlmError):
        core.analyze(_req("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả."))


# ---- request/chat validation ----

def test_missing_chat_and_session_raises_invalid_request(tmp_path):
    core = _core(tmp_path)
    req = AnalyzeRequest(question="Tôi thuê nhà giữ tiền cọc")  # no session_id, no chat_id
    with pytest.raises(InvalidRequest):
        core.analyze(req)


def test_unknown_chat_id_raises_not_found(tmp_path):
    with pytest.raises(ChatNotFound):
        _core(tmp_path).analyze(_req("Tôi thuê nhà giữ tiền cọc", chat_id="chat_missing"))


def test_session_boundary_enforced(tmp_path):
    core = _core(tmp_path)
    first = core.analyze(_req("Tôi thuê nhà giữ tiền cọc", session_id="owner"))
    with pytest.raises(ChatNotFound):
        core.analyze(_req("tiếp theo", chat_id=first.chat_id, session_id="intruder"))


# ---- assistant message stored structured ----

def test_assistant_message_stored(tmp_path):
    core = _core(tmp_path)
    r = core.analyze(_req("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả."))
    detail = core.store.get_chat_detail(r.chat_id)
    roles = [m.role.value for m in detail.messages]
    assert roles == ["user", "assistant"]
    assert detail.messages[1].content_json["domain"] == "civil_dispute"
