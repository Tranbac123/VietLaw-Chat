# VIETLAW DEMO — ANTHROPIC STRUCTURED OUTPUT CONTRACT REMEDIATION V2

Engineer: Claude Code (Sonnet 5).
Date: 2026-07-24.

Narrow remediation of three Codex-V1 findings (HIGH H-1, MEDIUM M-1, MEDIUM
M-2) on top of the accepted V1 structured-output contract and V4 scripted
architecture. No architecture change, no demo expansion, no scenario/
extraction/router/rendering/facts/sources/runtime/dependencies/API-schema/
frontend/A1/safety/corpus change, no live Anthropic call, no deploy, no
stage/commit/push.

---

# 1. Verdict

**VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V2_READY_FOR_CODEX**

`"maxItems": 4` is removed from the raw wire schema (H-1) — Anthropic's
Structured Outputs JSON Schema subset does not support it, and the four-action
cap is now enforced only by the local `DemoResponsePlan` Pydantic
`max_length=4` constraint. The Anthropic client now reads the structured plan
exclusively from `content[0].text` (M-1) — a non-text or malformed first block
fails closed regardless of what a later block contains, and two text blocks
are never concatenated. The decoded top-level response body is validated as a
`dict` immediately after `response.json()`, before any `.get(...)` call (M-2)
— a list/string/null/number top-level body fails closed to a bounded
`LLMClientError(PROVIDER_ERROR)` instead of risking an unbounded
`AttributeError`/`TypeError`. Exactly one provider call per turn is preserved;
no repair path was reintroduced. All required regressions and 20 new targeted
tests pass; no live request was made.

---

# 2. Repository identity

- Root: `/Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat`
- Branch: `main` · HEAD unchanged (no commit created this task).
- Nothing staged before or after. `git diff --check` clean. The tracked-file
  diff (`git diff --name-only`) is unchanged from before this task — it is the
  pre-existing accumulated WIP from prior sessions, none of which this task
  touched. All files this task modified/created remain untracked, as before.

---

# 3. Exact changed files

**Modified:**
- `backend_lite/app/contracts/demo_llm.py` — removed `"maxItems": 4` from
  `DEMO_RESPONSE_PLAN_JSON_SCHEMA["properties"]["action_codes"]`; expanded the
  adjacent doc-comment to state the two-layer cardinality contract explicitly
  (wire schema constrains type/enum/required/additionalProperties only; local
  Pydantic `max_length=4` is the sole cardinality enforcement).
- `backend_lite/app/services/demo_llm_client.py` — added an explicit
  `isinstance(data, dict)` guard immediately after `response.json()`, before
  any `data.get(...)` call; replaced the old "collect all text blocks and join
  them" logic with an exact `content[0].text` contract: `content` must be a
  non-empty list, `content[0]` must be a dict, `content[0]["type"]` must equal
  `"text"`, and `content[0]["text"]` must be a non-empty string — anything
  else raises `LLMClientError(PROVIDER_ERROR)` with a bounded, generic detail
  string (never the raw block/body). Updated the module docstring accordingly.
- `backend_lite/tests/unit/test_demo_llm_generation.py` — replaced
  `test_structured_output_schema_bounds_action_codes_list` (asserted
  `maxItems == 4`) with `test_structured_output_schema_has_no_max_items`
  (asserts the key is absent) and added
  `test_local_action_codes_rejects_five_actions`; added 20 new tests for the
  §7 requirement list (HTTP 400, malformed top-level bodies ×4, missing/empty
  content, non-text-first-block, two-text-block non-concatenation ×2,
  empty/malformed first block ×3, refusal/max_tokens non-parsing ×2,
  capitalization mutants, single-call guarantees ×2, no-text-leakage).
- `VIETLAW_DEMO_VERTICAL_SLICE_V1_IMPLEMENTATION.md` — §7 rewritten to
  describe the two-layer `action_codes` cardinality contract, the exact
  `content[0].text` response-block contract, and the malformed-top-level-body
  guard; test totals updated to 167/1098.
- `VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V1.md` — added a superseded-in-part
  notice at the top pointing to this V2 report for the H-1/M-1/M-2 fixes.

**Created:** `VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V2.md` (this file).

**Not modified:** `test_demo_vertical_slice.py` was not required — no e2e
fixture depended on `maxItems`, response-block shape, or top-level-body shape
(those are exercised only at the client/generation unit level); scenario
classifier, extractor, router, generation/rendering behavior, facts, sources,
runtime, dependencies, API schemas, frontend, A1, safety, corpus were not
touched. No `STRUCTURED_OUTPUT_V2_SCOPE_AMENDMENT_REQUIRED` condition was hit.

---

# 4. H-1 — unsupported raw wire constraint removed

**Before:** `DEMO_RESPONSE_PLAN_JSON_SCHEMA["properties"]["action_codes"]`
declared `"maxItems": 4`, a JSON Schema keyword not supported by Anthropic's
Structured Outputs subset — risking outright schema rejection or the
constraint being silently ignored by the provider.

**After:**
```json
"action_codes": {
  "type": "array",
  "items": {"type": "string", "enum": ["preserve_payment_evidence", "send_written_refund_request", "request_written_response", "seek_professional_help"]}
}
```
No replacement unsupported keyword was added. `type=array`, enum-restricted
`items`, wire-level `required`, and `additionalProperties: false` are all
preserved unchanged. The four-action cap is enforced exclusively by
`DemoResponsePlan.action_codes: list[ActionCode] = Field(default_factory=list,
max_length=4)` — unchanged from V1. An oversized `action_codes` array (5+
items) is therefore structurally acceptable to the provider but fails local
`DemoResponsePlan` validation as `SCHEMA_INVALID`, which — like every other
local-validation failure — falls back deterministically after exactly one
provider call. The provider can never control rendered prose regardless of
which layer (wire or local) rejects an oversized plan.

Proven by: `test_structured_output_schema_has_no_max_items` (absence of the
key), `test_local_action_codes_rejects_five_actions` (five rejected, four
accepted), `test_oversized_action_codes_uses_exactly_one_call_and_falls_back`
(end-to-end: `FakeLLMClient` returns a 5-action plan, `request_plan` reports
`DETERMINISTIC_FALLBACK` + `SCHEMA_INVALID` + exactly one call).

---

# 5. M-1 — exact `content[0].text` response-block contract

**Before:** the client collected every block with `type == "text"` from
`content` and joined them (`"".join(texts)`) — meaning a valid `content[0]`
could be silently extended by a stray second text block, and a non-text
`content[0]` (e.g. `"thinking"`) was simply skipped rather than rejected,
letting a later block rescue an off-contract first block.

**After**, in `AnthropicLLMClient.complete`, following the `stop_reason`
check:
```python
content = data.get("content")
if not isinstance(content, list) or not content:
    raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "missing or empty content")
first_block = content[0]
if not isinstance(first_block, dict):
    raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "malformed first content block")
if first_block.get("type") != "text":
    raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "first content block is not text")
text = first_block.get("text")
if not isinstance(text, str) or not text.strip():
    raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "empty provider text")
return text
```
Only `content[0]["text"]` is ever returned, verbatim (no strip/transform on
the returned value — validation checks non-emptiness via `.strip()` without
mutating what is returned). No later block is ever inspected, searched, or
concatenated. A non-text or malformed `content[0]` fails closed even when
`content[1]` holds a perfectly valid plan; an invalid `content[0].text` is
never rescued by a valid `content[1].text` — the caller's JSON/schema
validation on the returned (invalid) text still runs and correctly rejects it,
but no second-block fallback occurs inside the client.

Proven by: `test_non_text_first_block_rejected_even_with_valid_second_block`,
`test_two_text_blocks_are_not_concatenated`,
`test_two_text_blocks_first_invalid_is_not_rescued_by_second`,
`test_empty_first_text_raises_bounded_provider_error`,
`test_malformed_first_block_not_a_dict_raises_bounded_provider_error`,
`test_first_block_missing_text_field_raises_bounded_provider_error`,
`test_missing_content_raises_bounded_provider_error`,
`test_empty_content_raises_bounded_provider_error`,
`test_refusal_does_not_parse_text_even_if_valid_plan_present`,
`test_max_tokens_does_not_parse_partial_text`.

---

# 6. M-2 — malformed top-level response fails closed

**Before:** after `response.json()` succeeded (i.e. valid JSON syntax), the
code called `data.get("stop_reason")` directly — if the decoded JSON was a
list, string, `null`, or number rather than an object, this `.get(...)` call
would raise an unbounded `AttributeError` (or, for a string, silently succeed
calling `.get` — Python strings have no `.get`, so it would raise) out of the
client, uncontained.

**After**, immediately following the `response.json()` try/except and before
any other access:
```python
if not isinstance(data, dict):
    raise LLMClientError(LLMErrorKind.PROVIDER_ERROR, "malformed top-level response")
```
All four required malformed cases (`[]`, `"text"`, `null`, and — beyond the
required set — a bare number `42`) now produce a bounded
`LLMClientError(PROVIDER_ERROR)`, use the deterministic fallback, make exactly
one provider call, and expose no raw exception or provider body (`err.detail`
is a fixed short string, never the malformed payload).

Proven by: `test_top_level_list_raises_bounded_provider_error`,
`test_top_level_string_raises_bounded_provider_error`,
`test_top_level_null_raises_bounded_provider_error`,
`test_top_level_number_raises_bounded_provider_error`,
`test_http_400_raises_bounded_provider_error`,
`test_no_provider_text_leakage_in_bounded_error`.

---

# 7. Stop-reason handling (unchanged, re-verified)

`refusal` → `LLMErrorKind.REFUSAL`; `max_tokens` → `LLMErrorKind.MAX_TOKENS`;
any other value (including `end_turn`) falls through to the content-block
contract in §5. No retries were added anywhere in this task; refusal/
truncated text is never parsed even when a syntactically valid plan is
present in `content[0].text` (re-verified by
`test_refusal_does_not_parse_text_even_if_valid_plan_present` and
`test_max_tokens_does_not_parse_partial_text`, both constructed with a
well-formed/partial plan string in the first block to prove the stop-reason
check short-circuits before any text is read).

---

# 8. Required tests (§7 of the task) — mapped

| # | Requirement | Test |
|---|---|---|
| 1 | wire schema has no maxItems | `test_structured_output_schema_has_no_max_items` |
| 2 | local model rejects five action codes | `test_local_action_codes_rejects_five_actions` |
| 3 | output_config envelope remains correct | `test_client_request_includes_structured_output_config` (pre-existing, re-verified) |
| 4 | HTTP 400 → bounded provider error | `test_http_400_raises_bounded_provider_error` |
| 5 | top-level [] → bounded provider error | `test_top_level_list_raises_bounded_provider_error` |
| 6 | top-level string → bounded provider error | `test_top_level_string_raises_bounded_provider_error` |
| 7 | top-level null → bounded provider error | `test_top_level_null_raises_bounded_provider_error` |
| 8 | missing content | `test_missing_content_raises_bounded_provider_error` |
| 9 | empty content | `test_empty_content_raises_bounded_provider_error` |
| 10 | content[0] non-text + content[1] valid text → reject | `test_non_text_first_block_rejected_even_with_valid_second_block` |
| 11 | two text blocks are not concatenated | `test_two_text_blocks_are_not_concatenated`, `test_two_text_blocks_first_invalid_is_not_rescued_by_second` |
| 12 | empty first text | `test_empty_first_text_raises_bounded_provider_error` |
| 13 | malformed first block | `test_malformed_first_block_not_a_dict_raises_bounded_provider_error`, `test_first_block_missing_text_field_raises_bounded_provider_error` |
| 14 | refusal does not parse text | `test_refusal_does_not_parse_text_even_if_valid_plan_present` |
| 15 | max_tokens does not parse partial text | `test_max_tokens_does_not_parse_partial_text` |
| 16 | capitalization mutants fail local validation | `test_capitalization_mutants_fail_local_validation` |
| 17 | invalid JSON uses exactly one call | `test_invalid_json_response_makes_exactly_one_network_call` (+ pre-existing `test_invalid_json_falls_back_with_exactly_one_attempt_no_repair`) |
| 18 | schema-invalid JSON uses exactly one call | `test_schema_invalid_response_makes_no_second_network_call` (pre-existing, re-verified) |
| 19 | oversized action_codes: one call, deterministic fallback | `test_oversized_action_codes_uses_exactly_one_call_and_falls_back` |
| 20 | no provider text leakage | `test_no_provider_text_leakage_in_bounded_error` (+ every `LLMClientError.detail` is a fixed bounded string throughout) |

All use production parser paths (`AnthropicLLMClient.complete`,
`parse_demo_plan`, `request_plan`) and a mocked HTTP transport
(`unittest.mock.patch.object(httpx.AsyncClient, "post", ...)`), never a live
Anthropic call.

---

# 9. Test results

| Suite | Result |
|---|---|
| A1 (`test_legal_fact_contracts.py`, `test_fact_conflict_resolver.py`) | **81 passed** |
| Demo targeted (extractor + router + generation + e2e) | **167 passed, 0 failed** |
| Full backend (`backend_lite/tests`) | **1098 passed, 0 failed** |
| `compileall` (contracts/services/runtime) | passed |
| Frontend build (pinned Node v20.19.4, `npm run build`) | passed |
| `git diff --check` | clean |

Demo total moved from 147 (V1) to 167 (V2): +20 new targeted tests, plus 2
tests replaced in place (old `maxItems==4` assertion → absence assertion, and
the addition of the five/four-action cardinality test as a new function
rather than a modification of an existing one — net +1 vs. the removed
assertion, +20 wholly new tests = +21 gross, −1 removed assertion folded into
a replacement test = **+20 net** in `test_demo_llm_generation.py`, from 29 to
49 tests in that file). Full backend: 931 baseline + 167 demo = 1098.

---

# 10. Preserved behavior (re-verified, not changed)

Scenario classification, bounded extraction, safety-defer-before-scenario-
matching, backend deterministic rendering, trusted-fact-only amount,
backend-only source metadata, and all four scenario families are unchanged —
none of their source files were touched in this task, and their full test
suites (extractor 63, router 20, e2e 35) all still pass unmodified. The V1
structured-output request shape (`output_config.format.type=json_schema`),
single-provider-call guarantee, and refusal/max_tokens/network/timeout
classification are all unchanged except for the two remediated behaviors in
§5–§6 above.

---

# 11. Known limitations and residual risk

- As in V1, the exact wire shape Anthropic's live API expects for
  `output_config` (and whether it silently ignores unrecognized keywords such
  as the removed `maxItems`, or would have hard-rejected the whole request)
  has not been live-verified in this task — live testing remains explicitly
  out of scope. Removing `maxItems` is the textually-safer choice regardless
  of which behavior the live API has, since local validation independently
  enforces the same cardinality limit either way.
- No live request was made or attempted in this task, per instruction.

---

# 12. Final verdict

**VIETLAW_DEMO_ANTHROPIC_STRUCTURED_OUTPUT_V2_READY_FOR_CODEX**

```
RAW_MAX_ITEMS_PRESENT=no
LOCAL_ACTION_CODES_MAX_LENGTH=4
RAW_SCHEMA_SUPPORTED=passed

CONTENT_ZERO_TEXT_REQUIRED=yes
LATER_TEXT_BLOCK_ACCEPTED=no
MULTI_TEXT_CONCATENATION=no
MALFORMED_TOP_LEVEL_BOUNDED=yes

REPAIR_PATH_REMOVED=yes
MAX_PROVIDER_CALLS_PER_TURN=1
MODEL_TEXT_EXPOSED=0

A1_TESTS_PASSED=81
TARGETED_TESTS_PASSED=167
FULL_BACKEND_TESTS_PASSED=1098
FRONTEND_BUILD=passed_with_node20

LIVE_REQUEST_MADE=no
FILES_OUTSIDE_BOUNDARY_CHANGED=0
CODEX_REVERIFIED=no
TRACKED_FILES_STAGED=0
COMMIT_CREATED=no
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
REPORT_AT_PROJECT_ROOT=yes
```
