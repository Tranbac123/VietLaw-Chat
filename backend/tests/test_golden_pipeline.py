"""In-process eval gate over the real golden + demo case files.

Runs AiCore.analyze() (stub LLM) across every case and checks the deterministic
guarantees: schema validity, enum/classification within acceptable lists, safety
notice, source presence, unsafe refusal, escalation. Content quality (must_include)
needs a live LLM and is covered by scripts/run_eval.py against a running backend.
"""
import json
from pathlib import Path

import pytest

from app.analyze import AiCore
from app.chat_store import ChatStore
from app.config import SAFETY_NOTICE, Settings
from app.patterns import PatternBank
from app.rag_retriever import Retriever, load_snippets
from app.schemas import AnalyzeRequest, Decision

_ROOT = Path(__file__).resolve().parents[2] / "data"
_STUB = ('{"summary":"Tóm tắt thận trọng.","clarifying_questions":["Bạn có giấy tờ liên quan không?"],'
         '"checklist":["Giấy tờ liên quan"],"next_steps":["Chuẩn bị hồ sơ và tham khảo luật sư nếu cần"],'
         '"used_source_ids":[]}')


class StubLLM:
    def generate(self, prompt):
        return _STUB


def _core(tmp_path):
    settings = Settings(_env_file=None, chat_db_path=str(tmp_path / "c.sqlite3"))
    return AiCore(
        settings,
        store=ChatStore(str(tmp_path / "c.sqlite3")),
        bank=PatternBank.load(str(_ROOT / "unsafe_patterns.json")),
        retriever=Retriever(load_snippets(str(_ROOT / "legal_snippets.json"))),
        llm=StubLLM(),
    )


def _load(name):
    d = json.load(open(_ROOT / name, encoding="utf-8"))
    return d if isinstance(d, list) else d.get("cases", d)


def _acc(turn, ek, ak):
    return turn.get(ak, [turn.get(ek)])


def _check_turn(resp, turn, cid):
    assert resp.contract_version == "v1"
    assert resp.chat_id and resp.user_message_id and resp.assistant_message_id
    assert resp.safety_notice == SAFETY_NOTICE
    assert resp.domain.value in _acc(turn, "expected_domain", "acceptable_domain")
    assert resp.risk_level.value in _acc(turn, "expected_risk", "acceptable_risk")
    assert resp.decision.value in _acc(turn, "expected_decision", "acceptable_decision")
    if resp.decision == Decision.refuse_unsafe_request:
        # A refusal may surface only safety/high-risk sources, never a harmful how-to.
        for s in resp.sources:
            assert s.source_type in ("safety_policy", "official_source", "procedure",
                                     "curated_note", "legal_snippet")


def _run_case(core, case):
    if "turns" in case:
        cid = None
        for turn in case["turns"]:
            req = AnalyzeRequest(question=turn["question"], session_id="eval", chat_id=cid)
            resp = core.analyze(req)
            cid = resp.chat_id
            _check_turn(resp, turn, cid)
        return
    resp = core.analyze(AnalyzeRequest(question=case["question"], session_id="eval"))
    _check_turn(resp, case, resp.chat_id)
    if case.get("requires_sources"):
        assert resp.sources, f"{case['id']} expected sources"
    if case.get("requires_escalation"):
        assert resp.decision in (Decision.recommend_professional_help, Decision.refuse_unsafe_request)


@pytest.mark.parametrize("case", _load("golden_cases.json"), ids=lambda c: c["id"])
def test_golden_cases(tmp_path, case):
    _run_case(_core(tmp_path), case)


@pytest.mark.parametrize("case", _load("demo_cases.json"), ids=lambda c: c["id"])
def test_demo_cases(tmp_path, case):
    _run_case(_core(tmp_path), case)
