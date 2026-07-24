# VIETLAW DEMO VERTICAL SLICE V1 — IMPLEMENTATION (V4 COMPLETE-MESSAGE ARCHITECTURE)

Implementer: Claude Code (Sonnet 5), continuing the V3 scripted architecture.
Date: 2026-07-24. Current architecture: **V4 scripted vertical slice with
complete-message scenario classification**.

This report describes ONLY the current V4 architecture. Earlier free-text /
general-grammar / prefix-matching descriptions are obsolete and superseded.
Authoritative closure of Codex findings lives in
`VIETLAW_DEMO_VERTICAL_SLICE_V1_REMEDIATION_V4.md`.

---

# 1. What this is

A **scripted** rental-deposit demo vertical slice, default-off behind a feature
flag. It is **not** a general legal chatbot, **not** a general Vietnamese
grammar, **not** full Phase A2, **not** persistence, **not** multi-episode
memory, and carries **no production/deployment readiness** claim. It is
**current-message-only**: no cross-turn state, no correction, no contradiction
resolution.

Baseline behavior is behaviorally unchanged when the flag is disabled (the
demo orchestrator is `None` and the runtime hook is skipped). `agent_runtime.py`
and `dependencies.py` were intentionally modified in earlier rounds (the flag
hook and the wiring seam) and are retroactively accepted; no protected file
outside the authorized task boundary changed. Those two files are unchanged in
V3.

---

# 2. Four supported scenario families

The demo owns a turn only for these; anything else is UNSUPPORTED
(`POLICY_DIRECT` or a baseline defer), with zero fact operations and zero
provider attempts:

- **A. GREETING_DIRECT** — a greeting/capability turn → direct social text, no LLM.
- **B. DEPOSIT_FACT_UPDATE** — a current USER paid-deposit statement with facts →
  deterministic acknowledgement, no LLM.
- **C. DEPOSIT_LEGAL_GUIDANCE** — paid-deposit facts + "tôi nên làm gì?" → one LLM
  enum-plan call (or safe fallback), backend-rendered guidance.
- **D. DEPOSIT_DRAFT_REQUEST** — paid-deposit + "viết giúp tôi..." → one LLM
  enum-plan call (or safe fallback), backend-rendered draft.

---

# 3. Processing order (runtime hook, flag-gated)

`AgentRuntime.analyze` → (validate/store/normalize/language/unsafe) → **demo
hook** → baseline pipeline. Inside `DemoOrchestrator.handle`:

1. **Safety defer FIRST** — baseline `unsafe/high_risk` flags, then the bounded
   demo-safety predicate `should_defer_demo_for_risk`, before any scenario
   classification / extraction / provider construction. On a match the demo
   returns `None` and the baseline pipeline owns the turn (zero provider).
2. **Scenario classification** — `classify_demo_scenario` on eligibility-
   normalized text; greeting/capability/source cues via the accepted social
   kernel.
3. **Route** — `route_demo` maps scenario → route. Only LEGAL_GENERATION and
   DOCUMENT_DRAFTING spend a provider call.
4. **Extraction** — only after an approved deposit scenario, from the approved
   anchored patterns.
5. **LLM enum plan** (C/D only) → backend deterministic rendering.

An unexpected exception in `handle` is contained at the runtime boundary (defer
to baseline, no HTTP 500, no leak); `CancelledError` propagates.

---

# 4. Complete-message scenario classification (V4)

`normalize_for_eligibility` (used only for safety and scenario matching, never
for anchors): NFC → lowercase → strip Vietnamese accents → replace separators
(hyphen, underscore, slash, backslash, brackets, parentheses, dot, punctuation)
with spaces → collapse whitespace. This normalizes obfuscations such as
`mã-tấu → ma tau` and `example[.]com → example com`.

**`DEMO_CLASSIFICATION_MODE=complete_message_allowlist`.** A deposit scenario
activates only if the **entire** normalized message `re.fullmatch`es one
owner-approved template — anchored at both message start and message end. There
is no start-only / `search`-based anchoring left in the classifier: a valid
paid-deposit prefix followed by **any** unrelated residual clause (e.g.
`Tôi đã đặt cọc 20 triệu. Tôi bị sa thải. Tôi nên làm gì?`) matches no template
and is `UNSUPPORTED` — the prior architecture extracted the valid prefix and
ignored the invalid suffix; V4 does not. Quoted, definitional, third-party
(`vợ tôi …`), future (`sẽ`), planned (`dự định`), required (`phải`), negated
(`chưa`), uncertain (`đoán`), and residual-bearing messages of any kind never
fullmatch a template and are `UNSUPPORTED`. Benign punctuation and whitespace
variation (newline, semicolon, colon, comma, dash, repeated spaces, case,
accent-folding) is absorbed by `normalize_for_eligibility` before matching, but
never turns an unrelated residual clause into an approved template.

---

# 5. Safety defer before scenario matching

`should_defer_demo_for_risk` matches bounded weapon / violence / retaliation /
self-help / police-criminal signals on the eligibility-normalized text, on word
boundaries (so `gay`/gậy never matches inside `ngay`/ngày). Separator-obfuscated
variants (`mã-tấu`, `trả_thù`, `công-an`, `triệu_tập`) normalize and match. It
produces no safety decision and never replaces baseline safety; overblocking is
accepted. It is not a production safety classifier.

---

# 6. Bounded extraction (only after scenario approval)

`extract_scenario_facts` runs only when `classify_demo_scenario` has already
returned one of the three approved deposit scenarios (i.e. only when the
**entire** message fullmatched a template). For an `UNSUPPORTED` message —
including a valid paid-deposit prefix followed by an unrelated residual clause
— extraction never runs: zero operations, zero trusted facts, no source
metadata attached. Facts are derived only from approved anchored patterns:

- `deposit_amount` — the first amount in the NFC original (the paid anchor
  guarantees the message opens with the actual paid amount); a document-stated
  or third-party amount never reaches extraction because such messages are
  UNSUPPORTED.
- `written_agreement_exists` (ABSENT), `payment_evidence_exists` (PRESENT,
  document-claimed), `property_handed_over` (ABSENT), `deposit_returned`
  (ABSENT) — from fixed approved fact clauses only, each anchored back to the NFC
  original. There is no general clause/polarity grammar.

Every `TextAnchor` is built via `create_validated_text_anchor` against the NFC
original, so `anchor.quote == nfc_original[anchor.start:anchor.end]`. Facts are
projected through the accepted A1 resolver (`resolve_fact_operation`); the LLM
never writes FactSlot state or selects an episode.

---

# 7. LLM returns an enum plan only — no model prose

The model's entire output surface is `DemoResponsePlan` (`extra="forbid"`, strict
enums): `plan_kind`, `summary_code`, `action_codes` (≤4), `tone`. **No** model-
generated summary prose, explanation prose, action prose, warnings, source
names, article numbers, URLs, facts, amounts, deadlines, or penalties are
possible — any arbitrary string field, extra field, or unknown enum fails
validation. An invalid or unavailable plan yields a deterministic default plan.
The request sends only bounded trusted facts (no raw history, no unrelated
issues).

**Conformance is enforced by Anthropic native Structured Outputs**
(`ANTHROPIC_OUTPUT_MODE=native_structured_outputs`), not by a prompt-only JSON
contract: every request declares `output_config.format.type = "json_schema"`
with a wire schema (`DEMO_RESPONSE_PLAN_JSON_SCHEMA`, hand-authored, with every
enum list built directly from the same Enum classes as `DemoResponsePlan`) that
is object-root, marks all four fields required, restricts every field to its
approved enum values, and sets `additionalProperties: false`.

**Two-layer `action_codes` cardinality contract (V2 remediation, Codex V1
finding H-1):** the raw wire schema intentionally **omits `maxItems`** —
Anthropic's Structured Outputs JSON Schema subset does not support it, and an
unsupported keyword risks the whole schema being rejected or silently ignored
by the provider. The maximum of **four** actions is enforced **only locally**,
by `DemoResponsePlan.action_codes`'s Pydantic `max_length=4` constraint. This
is a deliberate two-layer contract, not a gap: the wire schema constrains what
the provider can structurally emit (type/enum/required/additionalProperties);
local validation constrains cardinality before anything is rendered. An
oversized `action_codes` array is schema-invalid locally and falls back
deterministically after exactly one provider call, exactly like any other
local-validation failure — the provider can never directly control rendered
prose regardless of which layer rejects it. Enum values themselves are derived
from the shared enum classes; independent tests protect field names,
requiredness, types, local cardinality, and provider schema compatibility
separately (there is no single guarantee that the whole schema can never
drift — each property is independently tested).

**Exact response-block contract (V2 remediation, Codex V1 finding M-1):** the
structured plan is read **only** from `content[0].text`. The client requires,
in order: the decoded body is an object; `content` is a non-empty list;
`content[0]` is an object; `content[0]["type"] == "text"`; `content[0]["text"]`
is a non-empty string. Later content blocks are never inspected, searched, or
concatenated — an off-contract multi-block response (a leading non-text block,
or two text blocks) fails closed to `LLMErrorKind.PROVIDER_ERROR` rather than
being silently rescued or partially accepted; a valid first block is never
extended with a second block's text, and an invalid first block is never
rescued by a valid second block.

**Malformed top-level response (V2 remediation, Codex V1 finding M-2):** the
decoded JSON body is checked with `isinstance(data, dict)` immediately after
`response.json()`, before any `.get(...)` call — a top-level list, string,
null, or number fails closed to `LLMErrorKind.PROVIDER_ERROR` instead of
raising an unbounded `AttributeError`/`TypeError` out of the client.

**There is exactly one provider call per turn — no prompt-based JSON-repair
retry.** Every failure mode — invalid JSON, local schema-validation mismatch
(including an oversized `action_codes`), provider refusal
(`stop_reason="refusal"`), truncated output (`stop_reason="max_tokens"`),
malformed top-level body, off-contract content blocks, timeout, or
network/provider error — is classified into the same deterministic fallback
with a diagnostic `LLMErrorKind` (`REFUSAL`, `MAX_TOKENS`, `PROVIDER_ERROR`,
etc.). Refusal and truncated-output responses are classified by `stop_reason`
alone and their text is never parsed, even if a well-formed plan happens to be
present. The response text is still passed through the local
`DemoResponsePlan` Pydantic validator before use regardless of the wire-level
schema — the API constraint is defense at the source, not a replacement for
local validation.

Because no model prose reaches users, the former free-text guards (source-prose
/ certainty / fact-reversal scanners) are removed — release safety is now
structural, not scanner-based.

---

# 8. Backend deterministic rendering

All visible prose is backend-owned:

- **Guidance summary** — built from the trusted captured facts (amount, agreement
  absent, evidence present, handover not completed, deposit not returned); no
  certainty claim, no win prediction, no legal reference. It says the legal
  source is shown in the Nguồn section.
- **Actions** — `action_codes` mapped to fixed Vietnamese action texts (max 3,
  de-duplicated; a default set if empty).
- **Draft** — one fixed polite-firm refund message with the amount inserted only
  from the trusted `MoneyAmount`. No legal article/statute, no threat, no invented
  deadline or penalty.

The model cannot change the amount (backend uses the trusted captured value) and
cannot state the deposit was returned (backend renders that solely from the
trusted fact).

---

# 9. Source rendering (backend metadata only)

Approved Article 328 attribution appears only as an existing backend `SourceObject`
(`civil_deposit_001`), attached to legal-guidance responses. No deterministic
prose (guidance, draft, capability, source-lookup) hard-codes `Điều 328`, `Bộ
luật Dân sự`, a source ID, or a URL; capability/source-lookup text says the legal
source is shown in the Nguồn section.

---

# 10. Exact changed files (across the demo work)

**Demo source (new, untracked):** `app/contracts/demo_llm.py`,
`app/services/demo_deposit_extractor.py`, `app/services/demo_generation_router.py`,
`app/services/demo_llm_client.py`, `app/services/demo_llm_guards.py`,
`app/services/demo_llm_generation.py`.
**Demo tests (new, untracked):** `tests/unit/test_demo_deposit_extractor.py`,
`tests/unit/test_demo_generation_router.py`,
`tests/unit/test_demo_llm_generation.py`, `tests/test_demo_vertical_slice.py`.
**Modified existing (prior rounds, unchanged since V3):**
`app/runtime/agent_runtime.py` (flag hook + exception containment).
**Modified in V4:** `app/dependencies.py` (docstring-only wording correction,
no functional change); `app/services/demo_deposit_extractor.py` (complete-message
classifier, §4).
No frontend, `config.py`, API schema, baseline safety, generation/rendering, or
corpus change. The four accepted A1 files are byte-identical.

---

# 11. Recording script (single-message only)

- **A. Greeting:** `Xin chào` → direct, 0 provider attempts.
- **B. Fact update:** `Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng
  có sao kê chuyển khoản.` → amount 20,000,000, agreement ABSENT, evidence
  PRESENT/document-claimed, 0 provider attempts.
- **C. Legal guidance:** `Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao
  kê chuyển khoản, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi
  nên làm gì?` → one attempt or safe fallback; current-message facts only; no
  legal reference in prose; Article 328 shown via backend Source metadata.
- **D. Drafting:** `Tôi đã đặt cọc 20 triệu nhưng chủ nhà chưa trả lại tiền cọc.
  Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc.` → one attempt or drafting
  fallback; amount from trusted facts; no invented deadline/penalty/law/URL.

No correction, no contradiction resolution, no cross-turn memory, no high-risk
scenario.

---

# 12. Test and build results (authoritative, V4)

- Accepted A1: **81 passed**.
- Demo targeted: **167 passed** (extractor + router + generation + e2e; includes
  the V1 structured-output contract tests plus the V2 remediation tests: no
  `maxItems` on the wire, local five-action rejection, HTTP-400/malformed
  top-level-body/missing-or-empty-content/non-text-first-block/two-text-block
  cases, capitalization mutants, single-call guarantees, and no-text-leakage).
- Full backend: **1098 passed, 0 failed** (931 baseline + 167 demo).
- `compileall` of contracts/services/runtime: passed.
- Frontend build with pinned Node v20.19.4 (`npm run build`): passed.
- No real Anthropic call in the suite; no live credential stored.

`FRONTEND_BUILD=passed_with_node20`. No production/deployment readiness is
claimed until independent Codex re-verification.
