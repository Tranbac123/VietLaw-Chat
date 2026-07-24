# VIETLAW DEMO — ANTHROPIC STRUCTURED OUTPUT CONTRACT V1

Engineer: Claude Code (Sonnet 5).
Date: 2026-07-24.

Narrow contract-conformance change on top of the accepted V4 scripted
architecture. No scenario expansion, no classification/extraction/rendering
change, no fact/source change, no frontend change, no persistence, no deploy.

> **Superseded in part by
> `VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V2.md`.** Codex V1 verification
> found the raw wire schema's `"maxItems": 4` on `action_codes` (§5 below) is
> not a supported Anthropic Structured Outputs keyword (H-1); that keyword has
> been **removed** from the wire schema. The four-action cap is now enforced
> **only locally** by `DemoResponsePlan`'s Pydantic `max_length=4` — a
> deliberate two-layer contract, not a gap. Codex V1 also found the response
> parser searched/concatenated later content blocks instead of reading only
> `content[0].text` (M-1), and that a malformed non-dict top-level response
> body was not explicitly rejected before `.get(...)` calls (M-2); both are
> now fixed in `demo_llm_client.py`. See V2 for the corrected schema, request/
> response handling, full test list, and current test totals (167 demo / 1098
> full backend). The architecture, request shape, repair-policy removal, and
> single-provider-call guarantee described below remain otherwise accurate.

---

# 1. Verdict

**VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V1_READY_FOR_CODEX**

The Anthropic request now declares native Structured Outputs
(`output_config.format.type = "json_schema"`) with a wire schema equivalent to
`DemoResponsePlan` — object root, all four fields required, string-enum-only,
`action_codes` bounded to 4 approved values, `additionalProperties: false`.
Prompt-only JSON is no longer the conformance mechanism; the prompt-based
JSON-repair retry is removed entirely — exactly one provider call per turn,
with every failure mode (invalid JSON, local schema mismatch, refusal,
truncation, network/provider error) classified straight into the existing
deterministic fallback. The local `DemoResponsePlan` Pydantic validator remains
the final authority regardless of the wire-level constraint. All V4 behavior
(scenario classification, extraction, backend-only rendering, trusted
amount/facts, source metadata, safety-defer-first ordering) is unchanged and
re-verified. All local tests pass; no live request was made in this task.

---

# 2. Repository identity

- Root: `/Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat`
- Branch: `main` (expected) · HEAD: `612770ed86b853814b4f96a73848e157cfe02dce` (expected).
- Nothing staged before or after; the six accumulated-WIP tracked files were
  not touched this round; the four accepted A1 files and the ten
  protected-WIP files remain SHA-256 byte-identical (14/14 OK).

---

# 3. Read-only contract audit (performed before any edit)

**Request payload (before):**
```json
{"model": "...", "max_tokens": N, "system": "...", "messages": [{"role": "user", "content": "..."}]}
```
No structural-output field of any kind — conformance relied entirely on
prompt text plus after-the-fact local validation.

**Primary prompt (before):** a Vietnamese system-prompt instruction telling the
model to return only the four-field JSON object and never free text/amounts/
articles/sources/URLs, plus a user-prompt body containing the JSON-dumped
`LLMPlanRequest` and a human-readable inline schema-hint string
(`_plan_schema_hint()`).

**Repair prompt (before):** identical to the primary, prefixed with "Phản hồi
trước không phải JSON hợp lệ..." — fired only when the first parse's
`GuardOutcome.reason_code == "demo.plan.invalid_json.v1"` (i.e. `json.loads`
itself failed), never for schema-shape failures.

**`DemoResponsePlan` fields (unchanged, already correct):** `plan_kind:
PlanKind`, `summary_code: SummaryCode`, `action_codes: list[ActionCode]`
(default `[]`, `max_length=4`), `tone: Tone`.

**Enum values (unchanged):** `PlanKind` = {legal_guidance, draft_request};
`SummaryCode` = {deposit_not_returned, deposit_no_written_agreement,
deposit_handover_not_completed}; `ActionCode` = {preserve_payment_evidence,
send_written_refund_request, request_written_response, seek_professional_help};
`Tone` = {neutral, polite_firm}.

**Required-fields / additionalProperties policy (before):** enforced only
locally, after the fact, via `StrictDemoModel`'s `extra="forbid"` — never
communicated to the model as an API-level decoding constraint.
`action_codes` was locally optional (`default_factory=list`); the owner's
wire-schema requirement ("all required") is a distinct, additive constraint
applied only to the request sent to Anthropic (see §4/§5), not a change to
local leniency.

**Parser path (unchanged):** `demo_llm_guards.parse_demo_plan(raw)` →
`json.loads` (→ `invalid_json` on failure) → `isinstance(data, dict)` → `
DemoResponsePlan.model_validate(data)` (→ `schema_invalid` on any extra field,
wrong type, or unknown enum value).

**Why the live repair response could be schema-invalid, established by static
analysis alone (no live request needed for this diagnosis):** the original
contract asked the model, in natural language, to emit a specific JSON shape,
with zero API-level enforcement. A model can trivially satisfy "return valid
JSON" while still drifting from the *exact* schema in ways that pass JSON
syntax but fail strict `extra="forbid"` + enum-only validation — an added
explanatory field, a near-miss enum string, a differently-named key, or an
extra wrapper. This is exactly the observed live signature in
`LIVE_SMOKE_V3.md` (repair response valid JSON, `llm_error_kind=schema_invalid`
after repair). The repair prompt only re-asks for "valid JSON" — it does not
re-communicate the strict schema any more forcefully than the original prompt
— so a schema-shape failure (as opposed to a syntax failure) has no reason to
resolve on retry. Anthropic's native Structured Outputs constrains the model's
decoding directly against the supplied JSON Schema (enum + additionalProperties
included), which is precisely the enforcement layer prompt text cannot provide.

---

# 4. Exact changed files

**Modified (all within the allowed boundary):**
- `backend_lite/app/contracts/demo_llm.py` — added `LLMErrorKind.REFUSAL` and
  `LLMErrorKind.MAX_TOKENS`; added `DEMO_RESPONSE_PLAN_JSON_SCHEMA` (hand-
  authored wire schema, built directly from the `PlanKind`/`SummaryCode`/
  `ActionCode`/`Tone` enum classes so it cannot drift from `DemoResponsePlan`).
- `backend_lite/app/services/demo_llm_client.py` — added module-level
  `STRUCTURED_OUTPUT_CONFIG`; included it as `output_config` in the request
  payload; added `stop_reason` classification (`"refusal"` →
  `LLMErrorKind.REFUSAL`, `"max_tokens"` → `LLMErrorKind.MAX_TOKENS`) before
  any text extraction is attempted.
- `backend_lite/app/services/demo_llm_generation.py` — removed the
  prompt-based JSON-repair retry entirely from `request_plan`; exactly one
  attempt per turn now, in all cases; simplified `_user_prompt` (dropped the
  now-redundant `repair` parameter and inline schema-hint text, since the
  schema is enforced at the API level, not by prompt text); updated module and
  section docstrings.
- `backend_lite/tests/unit/test_demo_llm_generation.py` — replaced the two
  tests that asserted the old 2-attempt repair behavior; added the full V1
  structured-output test block (schema shape, wire payload, refusal,
  max_tokens, network error, no-second-call-on-schema-error, enum-only
  containment).
- `backend_lite/tests/test_demo_vertical_slice.py` — updated two tests'
  fixtures/comments to single-response reality (no repair) and added explicit
  `fake.calls == 1` assertions.
- `VIETLAW_DEMO_VERTICAL_SLICE_V1_IMPLEMENTATION.md` — §7 rewritten to
  describe native Structured Outputs and the no-repair single-call model;
  test totals updated to 147/1078.

**Created:** `VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V1.md`.

**Not modified:** `demo_deposit_extractor.py`, `demo_generation_router.py`,
`agent_runtime.py`, `dependencies.py`, A1 files, baseline safety, API schemas,
frontend, corpus. No new source file was required beyond the allowed list; no
`STRUCTURED_OUTPUT_SCOPE_AMENDMENT_REQUIRED` condition was hit.

---

# 5. Structured Output schema

`DEMO_RESPONSE_PLAN_JSON_SCHEMA` (in `contracts/demo_llm.py`):

```json
{
  "type": "object",
  "properties": {
    "plan_kind": {"type": "string", "enum": ["legal_guidance", "draft_request"]},
    "summary_code": {"type": "string", "enum": ["deposit_not_returned", "deposit_no_written_agreement", "deposit_handover_not_completed"]},
    "action_codes": {
      "type": "array",
      "items": {"type": "string", "enum": ["preserve_payment_evidence", "send_written_refund_request", "request_written_response", "seek_professional_help"]},
      "maxItems": 4
    },
    "tone": {"type": "string", "enum": ["neutral", "polite_firm"]}
  },
  "required": ["plan_kind", "summary_code", "action_codes", "tone"],
  "additionalProperties": false
}
```

Object root ✔; all four fields required ✔ (including `action_codes`, which
the model must always emit, even as `[]` — a wire-level requirement distinct
from the local Pydantic model's lenient default, which exists only for
convenient local/test construction); string enums only ✔; `action_codes`
restricted to the four approved values with a 4-item cap ✔;
`additionalProperties: false` ✔; no amount/fact/source/URL/article/deadline/
penalty/metadata field exists anywhere in the schema ✔ (verified by an
explicit disjointness test). Enum values are lowercase snake_case,
unambiguous, and identical to the existing `DemoResponsePlan` values — the
schema is generated directly from the Enum classes, so it is structurally
impossible for it to diverge from the Pydantic model without a test failure.
The Pydantic model remains the final local validator; the wire schema is
defense at the source, not a replacement.

---

# 6. Anthropic request

`AnthropicLLMClient.complete()` now sends:

```json
{
  "model": "<config.model>",
  "max_tokens": <max_tokens>,
  "system": "<system prompt>",
  "messages": [{"role": "user", "content": "<user prompt>"}],
  "output_config": {"format": {"type": "json_schema", "schema": <DEMO_RESPONSE_PLAN_JSON_SCHEMA>}}
}
```

No API key, header, or raw payload is printed or logged anywhere in the
implementation or tests — verified by a mocked-transport test that inspects
the captured payload/headers in-memory only and asserts no `api_key`/`api-key`
substring appears in the serialized body. Preserved unchanged: timeout
handling (`httpx.TimeoutException` → `LLMErrorKind.TIMEOUT`), exception
containment in the orchestration layer, `CancelledError` propagation (it is a
`BaseException` and is never caught), attempt accounting, no full raw chat
history in the request (`LLMPlanRequest` is unchanged), no model fact writes,
no model episode selection.

---

# 7. Repair policy

Prompt-based JSON repair is removed for the structured-output path. Failures
are now classified purely by actual API/local outcome:

| Condition | Result |
|---|---|
| Valid structured output, passes local `DemoResponsePlan` validation | `LLM_ACCEPTED` |
| `stop_reason == "refusal"` | `LLMErrorKind.REFUSAL` → deterministic fallback |
| `stop_reason == "max_tokens"` | `LLMErrorKind.MAX_TOKENS` → deterministic fallback |
| `httpx` timeout / network error / non-200 status | `TIMEOUT` / `NETWORK` / `PROVIDER_ERROR` → deterministic fallback |
| Response text fails `json.loads` | `INVALID_JSON` → deterministic fallback (no repair) |
| Response text is valid JSON but fails `DemoResponsePlan.model_validate` | `SCHEMA_INVALID` → deterministic fallback (no repair) |
| Unexpected exception in the client | `PROVIDER_ERROR` → deterministic fallback |

No second network call is made for any of these — verified directly by a
mocked-transport test counting real HTTP calls (`test_schema_invalid_response_
makes_no_second_network_call`). No second provider was introduced; this task
did not touch `demo_generation_router.py`, `demo_deposit_extractor.py`, or any
routing/extraction/rendering logic.

---

# 8. Local test method

No live call was made. New offline coverage (all against the required list):

| # | Requirement | Test |
|---|---|---|
| 1 | request includes `output_config.format.type=json_schema` | `test_client_request_includes_structured_output_config` |
| 2 | schema matches `DemoResponsePlan` | `test_structured_output_schema_matches_enums` |
| 3 | `additionalProperties=false` | `test_structured_output_schema_is_object_root_all_required_no_extra` |
| 4 | all four fields required | `test_structured_output_schema_is_object_root_all_required_no_extra` |
| 5 | enum sets are correct | `test_structured_output_schema_matches_enums`, `test_structured_output_schema_bounds_action_codes_list` |
| 6 | valid structured response parses | `test_client_valid_structured_response_parses_end_to_end` |
| 7 | extra field rejected locally | `test_demo_response_plan_cannot_carry_arbitrary_text_or_amount` (+ pre-existing `test_arbitrary_string_field_rejected`) |
| 8 | unknown enum rejected locally | pre-existing `test_unknown_enum_rejected` |
| 9 | refusal safely falls back | `test_client_refusal_stop_reason_raises_refusal_kind`, `test_orchestrator_refusal_falls_back_cleanly` |
| 10 | max_tokens safely falls back | `test_client_max_tokens_stop_reason_raises_max_tokens_kind`, `test_orchestrator_max_tokens_falls_back_cleanly` |
| 11 | provider/network error safely falls back | `test_client_httpx_network_error_raises_network_kind`, `test_orchestrator_network_error_falls_back_cleanly` (+ pre-existing timeout test) |
| 12 | no repair network request for schema errors | `test_schema_invalid_response_makes_no_second_network_call`, `test_invalid_json_no_repair_no_third_attempt` |
| 13 | model text never reaches `AnalyzeResponse` | structural (enum-only contract) + e2e `test_model_prose_never_reaches_user` |
| 14 | trusted amount/facts backend-owned | `test_backend_render_uses_trusted_amount_not_model`, e2e `test_model_cannot_change_trusted_amount` |
| 15 | source metadata backend-owned | e2e `test_scenario_c_legal_guidance_...` (unchanged, re-verified) |

All existing A1, demo, and full-backend regressions were run.

---

# 9. Targeted test results

| File | Result |
|---|---|
| `test_demo_deposit_extractor.py` | 63 passed |
| `test_demo_generation_router.py` | 20 passed |
| `test_demo_llm_generation.py` | 29 passed |
| `test_demo_vertical_slice.py` (e2e) | 35 passed |
| **Demo total** | **147 passed, 0 failed** |

---

# 10. A1 regression

`pytest test_legal_fact_contracts.py test_fact_conflict_resolver.py -q` →
**81 passed, 0 failed**. Accepted A1 files byte-identical (SHA-256).

---

# 11. Full backend regression

`pytest backend_lite/tests -q` → **1078 passed, 0 failed** (931 baseline + 147
demo). `compileall` of contracts/services/runtime → passed. `git diff --check`
→ clean.

---

# 12. Frontend build

`export PATH="$HOME/.nvm/versions/node/v20.19.4/bin:$PATH"; cd frontend; npm run
build` → succeeds (`node v20.19.4`, `✓ built`). No frontend file was modified;
unaffected by this change.

---

# 13. Preserved V4 behavior (re-verified, not changed)

Scenario classification (`classify_demo_scenario`, full-message allowlist),
bounded extraction (`extract_scenario_facts`), safety-defer-before-scenario-
matching (`should_defer_demo_for_risk`), backend deterministic rendering
(`render_guidance_summary`/`render_draft`/`render_actions`), trusted-fact-only
amount, backend-only source metadata (`civil_deposit_001`), and the four
scenario families are all unchanged — none of their source files were touched
in this task, and their full test suites (extractor 63, router 20, e2e 35) all
still pass.

---

# 14. Known limitations and residual risk

- **The exact wire shape of Anthropic's `output_config` request field has not
  been live-verified in this task** (explicitly out of scope — "no live
  test"). The implementation follows the literal specification given
  (`output_config.format.type = "json_schema"` with a `schema` key) as
  precisely as stated; it does not add unverified extra keys (e.g. a `name` or
  `strict` field sometimes seen in other providers' structured-output
  conventions) since their necessity for Anthropic's API could not be
  confirmed without a live call. If the live API expects a different exact
  shape, the next live smoke test will surface this as an HTTP-level or
  parse-level failure, observable without exposing any raw payload or secret,
  and the request-construction code is isolated to one small, clearly
  identified location (`demo_llm_client.py`'s `STRUCTURED_OUTPUT_CONFIG` and
  its use in `complete()`) for a fast follow-up fix if needed.
  `MODEL_CAN_CHANGE_TRUSTED_AMOUNT` and all other structural-safety properties
  are unaffected either way, since they do not depend on the exact wire shape
  being accepted — an unaccepted/ignored `output_config` field would at worst
  degrade back toward prompt-only behavior for one field, not weaken any
  safety property (the local `DemoResponsePlan` validator, backend-only
  rendering, and trusted-fact sourcing all remain fully in force regardless).
- No live request was made or attempted in this task, per instruction.

---

# 15. Final verdict

**VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V1_READY_FOR_CODEX**

```
STRUCTURED_OUTPUT_MODE=native_structured_outputs
PROMPT_ONLY_JSON_CONTRACT=no
OUTPUT_CONFIG_PRESENT=yes
SCHEMA_OBJECT_ROOT=yes
SCHEMA_ALL_FIELDS_REQUIRED=yes
SCHEMA_ENUM_ONLY=yes
SCHEMA_ADDITIONAL_PROPERTIES_FALSE=yes
SCHEMA_ACTION_CODES_BOUNDED=yes
SCHEMA_NO_FORBIDDEN_FIELDS=yes

REPAIR_PATH_REMOVED=yes
MAX_PROVIDER_CALLS_PER_TURN=1
REFUSAL_CLASSIFIED=yes
MAX_TOKENS_CLASSIFIED=yes
NETWORK_ERROR_CLASSIFIED=yes
LOCAL_VALIDATION_PRESERVED=yes

BACKEND_RENDERING_ONLY=yes
TRUSTED_AMOUNT_PRESERVED=yes
TRUSTED_FACTS_PRESERVED=yes
SOURCE_METADATA_BACKEND_OWNED=yes
V4_BEHAVIOR_PRESERVED=yes

A1_TESTS_PASSED=81
TARGETED_TESTS_PASSED=147
FULL_BACKEND_TESTS_PASSED=1078
FRONTEND_BUILD=passed_with_node20

LIVE_REQUEST_MADE=no
FILES_OUTSIDE_BOUNDARY_CHANGED=0
TRACKED_FILES_STAGED=0
COMMIT_CREATED=no
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
REPORT_AT_PROJECT_ROOT=yes
```
