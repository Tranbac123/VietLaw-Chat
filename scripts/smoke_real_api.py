#!/usr/bin/env python3
"""Smoke-test the AI core against the REAL LLM API in .env.

Unlike run_eval.py (which needs a live HTTP backend), this calls analyze()
directly — same pipeline, no server. Uses the real provider/key/base_url from
.env, so it costs real API calls and is slow on free endpoints.

    python scripts/smoke_real_api.py                 # default sample cases
    python scripts/smoke_real_api.py "câu hỏi ..."   # one custom question
    python scripts/smoke_real_api.py --llm-only      # single raw LLM call, no pipeline

Run from anywhere — the script chdir's to the repo root so .env loads and the
data/ paths resolve regardless of the current directory.
"""
import os
import sys
from pathlib import Path

# --- make Vietnamese printable on cp1252 consoles (Windows) ---
sys.stdout.reconfigure(encoding="utf-8")

# --- resolve paths independent of CWD: repo root is scripts/.. ---
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)                      # so Settings() finds ./.env and ./data/*
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings          # noqa: E402
from app.llm_client import LLMClient      # noqa: E402
from app.analyze import AiCore            # noqa: E402
from app.schemas import AnalyzeRequest    # noqa: E402

# Cases exercising the paths most likely to break: keyword routing, the
# empty-retrieval guard, and the unsafe refusal (no LLM call).
_DEFAULT_CASES = [
    "Tôi bị CSGT phạt lỗi vượt đèn đỏ, nên làm gì?",   # traffic keyword
    "Tôi mở tiệm tạp hóa nhỏ cần chuẩn bị gì?",         # household_business
    "Tôi cần chuẩn bị hồ sơ gì?",                       # sourceless -> clarify guard
    "Làm sao để né phạt giao thông?",                   # unsafe -> refuse, no LLM
]


def _llm_only(s: Settings) -> None:
    print(f"provider={s.resolved_provider} model={s.ai_model_name} base={s.ai_base_url or '(default)'}")
    print("key set:", bool(s.ai_api_key))
    out = LLMClient(s).generate('Return JSON: {"ok": true, "lang": "vi"}')
    print("RAW:", repr(out[:500]))


def _run(core: AiCore, question: str) -> None:
    r = core.analyze(AnalyzeRequest(session_id="smoke", question=question))
    print("-" * 70)
    print("Q:", question)
    print(f"domain={r.domain.value} risk={r.risk_level.value} "
          f"decision={r.decision.value} sources={r.metadata.retrieval_count} "
          f"used_llm={r.metadata.used_llm}")
    if r.summary:
        print("summary:", r.summary)
    if r.clarifying_questions:
        print("clarifying:", r.clarifying_questions)
    if r.sources:
        print("sources:", [x.id for x in r.sources])


def main(argv: list[str]) -> int:
    s = Settings()
    if not s.ai_api_key:
        print("ERROR: AI_API_KEY not set — is .env present at repo root?", file=sys.stderr)
        return 2

    if "--llm-only" in argv:
        _llm_only(s)
        return 0

    questions = [a for a in argv if not a.startswith("-")] or _DEFAULT_CASES
    print(f"provider={s.resolved_provider} model={s.ai_model_name} "
          f"({len(questions)} case(s), real API — this is slow)\n")
    core = AiCore(s)
    for q in questions:
        _run(core, q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
