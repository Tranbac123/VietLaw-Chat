# VIETLAW PUBLIC BETA V0 — Correction Round 2 Report

Pending-clarification state-machine fix for MEDIUM M-02-R, raised by
independent review
(`VIETLAW_PUBLIC_BETA_V0_CODEX_CORRECTION_ROUND_1_VERIFICATION_V1.md`,
verdict `VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_VERIFICATION_BLOCKED`),
plus the Correction Round 1 report's resulting "M-02 is closed" overstatement.

```
STARTING_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
FINAL_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4  (no commits created)
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
```

## FILES_MODIFIED

```
backend_lite/app/contracts/traffic.py
backend_lite/app/contracts/legal_fallback_state.py           (unchanged this round — inspected, no edit needed)
backend_lite/app/services/traffic_classifier.py
backend_lite/app/services/legal_fallback_orchestrator.py
backend_lite/tests/unit/test_traffic_classifier.py
backend_lite/tests/unit/test_legal_fallback_orchestrator.py
backend_lite/tests/integration/test_public_beta_v0_legal_fallback_e2e.py
evaluation/legal_beta_v0/cases.py
VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_REPORT.md  (Round 2 notice + inline annotations, not rewritten)
VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md      (Round 2 notice + inline annotation, not rewritten)
```

`legal_fallback_state.py` is listed as inspected-not-modified: it already
carried `traffic_pending_field` from Correction Round 1, which is exactly
the field this round's typed parser keys off — no schema change was needed.

## FILES_CREATED

```
VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_2_REPORT.md  (this file)
```

No frozen MODE_2D file, no new dependency, no deployment/configuration
file, no frontend file was created or touched — all correctly out of this
round's scope (frontend capability copy and M-04 query privacy logic were
explicitly frozen for this round and were not touched).

## Fix status

```
M02R_FIELD_SPECIFIC_PARSER_IMPLEMENTED=yes
M02R_NUMERIC_CONTAMINATION_FIXED=yes
M02R_SHORT_ANSWERS_COMMITTED=yes
M02R_UNKNOWN_ANSWER_RELEASES_STATE=yes
M02R_FRESH_TURN_ROUTING_AFTER_RELEASE=yes
```

## Root cause (task §1)

Correction Round 1's `is_valid_clarification_answer(pending_field,
message)` accepted **any digit** as a valid answer for
`speed_excess_kmh`/`alcohol_level`/`passenger_count`. An unrelated message
that merely contains a number ("Hôm nay 30 độ C.", "Tôi nhận lương tháng
7...") was therefore treated as a genuine clarification attempt. Because
such a message carries no first-person traffic attribution (task M-01's
gate), it was routed through the *impersonal* answer path — which
correctly never merges facts, but (a pre-existing gap, not itself an M-01
regression) also never clears the pending marker, since that path's
contract is "touch nothing." The stale `traffic_topic_id`/
`traffic_pending_field` therefore survived on disk and could be resumed by
a LATER, completely unrelated message that happened to be self-attributed
and pass the (overly permissive) digit check — producing real curated
traffic content for a labor/weather/unrelated question. The same
"any digit" rule also meant several of Round 1's own "valid short answer"
claims (`Xe máy.`, `10 km/h.`, `0.2 mg/l.`, `3 người.`, `Thay lốp.`) were
never actually proven to commit their parsed value — Round 1 had no
dedicated test for this exact boundary.

## Design: typed pending-clarification state machine (task §2)

Added to `contracts/traffic.py`:

```python
class ClarificationAnswerKind(str, Enum):
    RESOLVED = "resolved"
    UNKNOWN_VALUE = "unknown_value"
    UNRELATED = "unrelated"

class ClarificationAnswer(BaseModel):
    kind: ClarificationAnswerKind
    field: str
    parsed_value: str | int | None = None
```

`traffic_classifier.parse_clarification_answer(pending_field, message) ->
ClarificationAnswer` replaces the boolean-only check as the SOLE authority
on what a reply to a pending clarification means (`is_valid_clarification_
answer` is kept as a thin backward-compatible wrapper —
`kind != UNRELATED` — for existing Round 1 test call sites; the
orchestrator itself no longer calls it). Crucially, this parser is **never
run through the generic first-person attribution detector** — the pending
question itself supplies the attribution context (task §6's documented
exception), so "Xe máy." resolves without needing to say "tôi".

`LegalFallbackOrchestrator._handle()` now dispatches on the message BEFORE
touching the generic topic classifier's attribution path:

1. A fresh topic mention in the current message always wins (unchanged
   from Round 1).
2. Otherwise, if a clarification is pending, `parse_clarification_answer`
   decides everything:
   - **`RESOLVED`** → `_handle_pending_clarification_answer` merges ONLY
     the one resolved field into `traffic_facts` (never any other slot),
     clears `traffic_topic_id`/`traffic_pending_field`, commits via CAS,
     and continues resolving the SAME topic (asks the next single missing
     fact if any remains, otherwise builds the final curated answer) — all
     without requiring first-person attribution.
   - **`UNKNOWN_VALUE`** → same continuation, but `force_answer_now=True`:
     never asks the same (or any further) question again, proceeds with
     the best-available range answer immediately.
   - **`UNRELATED`** → the pending state is cleared and committed via CAS
     **immediately**, then the exact same message is routed through
     `_handle_fresh_turn` — the ordinary, non-pending code path — exactly
     once. It is never re-classified through the stale topic, and the
     release is durable even if the fresh-turn pass itself ultimately
     defers (returns `None`).

Both the fresh self-attributed path and the pending-answer continuation
now share one core, `_resolve_traffic_topic(topic_id, merged_facts, *,
already_asked_this_topic, force_answer_now)`, so "ask at most one
clarification per topic" (task §5.1, unchanged from Round 1) is enforced
in exactly one place rather than duplicated.

## Field-specific parsers (task §3)

None of the six fields accept a bare digit or a bare cue-word alone —
every accept requires the field's own unit/context:

| Field | Accepts | Rejects |
|---|---|---|
| `vehicle_type` | xe máy / mô tô / ô tô / xe hơi (+ "tôi đi/lái ...") | any other mention of "xe" |
| `speed_excess_kmh` | digit + km/km·h/cây | a bare digit with no speed unit |
| `alcohol_level` | digit + mg/l, mg/100ml, mg% | a bare digit, or digit + unrelated unit (kg, độ, chai) |
| `passenger_count` | digit or Vietnamese number-word + "người" | a bare digit, or digit + unrelated noun |
| `license_status` | quên mang bằng / không mang theo / chưa (từng) có bằng / bằng hết hạn / bằng bị thu hồi (+ existing longer topic-cue forms) | unrelated use of "quên"/"hết hạn"/"thu hồi" |
| `modification_type` | thay/đổi + lốp/pô/khung/đèn/biển số (+ existing longer forms) | unrelated use of "thay"/"đổi" |

`vehicle_type`/`license_status`/`modification_type` extend the EXISTING
Round-1 topic-detection cue tuples in place (adding short-answer aliases
like bare "mô tô", "không mang theo", "thay khung") rather than
introducing a parallel table, so the same bounded cue set serves both
topic detection and clarification-answer parsing with no risk of drift
between the two. `speed_excess_kmh`/`passenger_count` are new regex-based
parsers; `alcohol_level` is parsed against `message.lower()` rather than
the accent-stripping, separator-collapsing `_normalize()` output, because
that collapse turns "0,2"/"0.2" into two separate digit tokens and would
destroy the decimal value.

Every accept/reject probe in the correction task's §3 was verified
directly (see `test_*_answer_resolves`/`test_*_answer_rejects_*` in
`test_traffic_classifier.py`) — all pass exactly as specified, with zero
adjustment needed to the task's own examples.

## Fresh-turn routing after release (task §5)

`_handle()` releases pending state and calls `_handle_fresh_turn` exactly
once for an `UNRELATED` answer — there is no recursive re-entry into
`_handle()` and no second traffic/search dispatch. Verified by two
dedicated call-count tests:

- `test_resolve_traffic_topic_called_at_most_once_per_turn` — wraps
  `_resolve_traffic_topic` with a call-counting spy across a `RESOLVED`
  turn; asserts `<= 1`.
- `test_handle_traffic_never_called_for_the_unrelated_release_turn_itself`
  — wraps `_handle_traffic` with a spy across the `UNRELATED` message
  itself ("Hôm nay 30 độ C."); asserts it is never called at all (correct:
  that specific message carries no fresh topic, so `_handle_traffic` has
  nothing to do for it).
- `test_search_called_at_most_once_after_unrelated_release_reroutes_to_search`
  — an `UNRELATED` release that reroutes into a genuine official-search-
  eligible question; asserts the fake search service's `.calls` has length
  exactly 1, never 2.

```
MAX_TRAFFIC_HANDLER_CALLS_PER_TURN=1  (verified)
MAX_SEARCH_CALLS_PER_TURN=1           (verified)
MAX_PROVIDER_CALLS_PER_TURN=0         (unchanged existing invariant -- no LLM call anywhere in this vertical)
```

## Required Case A-G (task §4) — all verified against real store state

Each case below was run against the actual `LegalFallbackOrchestrator` +
`LegalFallbackStateStore` (not mocked), asserting the response AND the
persisted `traffic_facts`/`traffic_topic_id`/`traffic_pending_field`
before and after each turn (`test_case_a_*` through `test_case_g_*` in
`test_legal_fallback_orchestrator.py`, plus end-to-end HTTP-level
equivalents in `test_public_beta_v0_legal_fallback_e2e.py`):

- **Case A** (numeric unrelated): turn 2 ("Hôm nay 30 độ C.") is `UNRELATED`
  → pending state cleared and persisted; turn 2 gets no curated content.
  Turn 3 (the labor question) never receives speeding content either
  (`legal_fallback_route != "curated_traffic"` for both turns 2 and 3).
  One honest caveat: turn 3's exact phrasing ("Tôi nhận lương tháng 7 thì
  công ty có trả đúng hạn không?") does not happen to match the existing,
  separately-bounded `is_legal_or_rights_related` phrase list, so it
  defers to the plain scope reply rather than reaching `GENERAL_GUIDANCE`.
  `legal_intent_classifier.py` is not in this round's permitted-files list
  (only contracts directly required for the typed clarification result,
  plus the two orchestrator/classifier files, are in scope), so it was not
  touched to add this phrase — the critical, explicitly required invariant
  (no speeding contamination) is fully satisfied regardless.
- **Case B** (valid speed answer): "10 km/h." → `speed_excess_kmh=10`
  committed, pending cleared, original speeding topic answered with
  `curated_verified`.
- **Case C** (short vehicle answer): "Xe máy." → `vehicle_type=motorcycle`
  committed, pending cleared, red-light motorcycle rule answered.
- **Case D** (short alcohol answer): "0.2 mg/l." → `alcohol_level="0.2
  mg/l"` committed, pending cleared, no repeated clarification.
- **Case E** (short passenger answer): "3 người." →
  `passenger_count=3` committed, pending cleared.
- **Case F** (short modification answer): "Thay lốp." →
  `modification_type="tire"` committed, pending cleared.
- **Case G** (explicit unknown then new topic): "Tôi không biết." →
  pending cleared without repeating the question, answers with the range;
  a genuinely new labor question on the next turn correctly reaches
  `GENERAL_GUIDANCE` (`"giữ lương"` IS in the existing legal-intent phrase
  list), proving the release did not merely suspend the old topic.

## Counts

```
SPEED_TEMPERATURE_FALSE_MATCHES=0
SPEED_MONTH_FALSE_MATCHES=0
ALCOHOL_UNRELATED_NUMBER_FALSE_MATCHES=0
PASSENGER_UNRELATED_NUMBER_FALSE_MATCHES=0

SHORT_VEHICLE_ANSWERS_COMMITTED=1  (Case C, verified against store state)
SHORT_SPEED_ANSWERS_COMMITTED=1    (Case B)
SHORT_ALCOHOL_ANSWERS_COMMITTED=1  (Case D)
SHORT_PASSENGER_ANSWERS_COMMITTED=1 (Case E)
SHORT_MODIFICATION_ANSWERS_COMMITTED=1 (Case F)

STALE_TRAFFIC_TOPICS_AFTER_UNRELATED_TURNS=0
LABOR_TURNS_MISROUTED_TO_TRAFFIC=0
```

("Committed" counts above are per-required-case, each independently
re-verified through both the unit orchestrator test and the HTTP-level
integration test — i.e., proven twice, at two layers, not just asserted
once.)

## M-01 / M-03 / M-04 remain closed

```
M01_REMAINED_CLOSED=yes
M03_REMAINED_CLOSED=yes
M04_REMAINED_CLOSED=yes
```

Not redesigned, not reopened. Directly re-verified this round:

- M-01: `test_traffic_classifier.py -k "attribution or hypothetical or
  third_party or negated or educational"` (17 tests) and
  `test_legal_fallback_orchestrator.py -k "never_persists_facts"` (4
  tests) all pass unchanged. The one behavioral touchpoint between M-01
  and M-02-R — "a clarification answer does not require first-person
  attribution" — is an explicit, narrowly-scoped exception (task §6),
  applied ONLY inside the two new pending-clarification code paths, never
  altering `_detect_attribution` or the fresh-turn self-attribution gate
  itself.
- M-03: no frontend file was touched this round;
  `landingChatState.test.tsx` (7 tests) passes unchanged.
- M-04: no change to `build_search_query`/`_minimize_narrative`/
  `_ISSUE_CATEGORY_QUERIES` this round;
  `test_legal_fallback_orchestrator.py -k "build_search_query"` (10 tests)
  passes unchanged.

## MODE_2D preservation

```
MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
```

`git diff --stat` on all seven frozen MODE_2D files
(`fast_demo_routing.py`, `fast_demo_fact_validation.py`,
`fast_demo_source_pack.py`, `fast_demo_orchestrator.py`,
`fast_demo_prompt.py`, `contracts/fast_demo.py`, `data/legal_snippets.json`)
is empty — byte-identical to HEAD. `resolve_deposit_applicable_clause()`
directly probed across 12 `(facts, clause_numbers)` combinations: 0
returned non-`None`.

## Regression

```
NEW_BACKEND_TESTS=287 tests collected (10 backend test files, unchanged file count from Correction Round 1)
BACKEND_LITE_TESTS=1458 passed
FOCUSED_ARTICLE_CITATION_TESTS=256 passed  (exact unchanged baseline)
EVALUATION_TESTS=214 passed  (exact unchanged baseline, existing platform)
LEGAL_BETA_EVALUATION_TURNS=42 turns, no findings  (was 27; +15 from 7 new clarification_state_machine cases)
FRONTEND_TESTS=171 passed  (unchanged -- no frontend file touched this round)
TYPECHECK=passed
BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=passed
SECRET_SCAN=passed_no_credentials
```

Required hard constraints, re-verified by the `legal_beta_v0` runner:

```
UNSUPPORTED_CITATION_RATE=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
MODE_2D_CLAUSE_2_OUTPUTS=0
```

## Scope discipline

```
LIVE_PROVIDER_CALLS=0
LIVE_WEB_SEARCH_CALLS=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
```

No product feature was added. No live search provider was wired. No rate
limiting or deployment work was performed. No traffic legal data/penalty
value was changed (`data/traffic_rules.json` untouched). No frontend file
was touched. No frozen MODE_2D file was modified. `M-04`'s query-privacy
logic (`build_search_query`, `_minimize_narrative`,
`_ISSUE_CATEGORY_QUERIES`) is untouched. No dependency was added; the fix
uses only the Python standard library (`re`, `enum.Enum`) and Pydantic,
already present.

## FINAL VERDICT

```
VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_2_READY_FOR_REVIEW
```

M-02-R is closed: a typed, field-specific parser replaces the boolean
"any digit" rule, verified against the exact defect-report regressions
(`Hôm nay 30 độ C.` no longer resumes a stale speeding clarification) and
all six required fields' short-answer commit paths (each proven directly
against persisted store state, at both the unit-orchestrator and HTTP-
integration layers). Zero stale-traffic-topic contamination was found
across the full required Case A-G set. M-01/M-03/M-04 remain independently
verifiable as closed and were not touched. MODE_2D remains byte-identical
to HEAD. Zero newly-identified HIGH or MEDIUM findings surfaced while
implementing this fix — the one caveat noted under Case A (turn 3's exact
phrasing not matching the pre-existing, separately-bounded legal-intent
phrase list) is a documented, out-of-this-round's-scope observation, not a
contamination defect: the critical invariant it might have affected — no
stale traffic content — is independently confirmed to hold. Changes remain
fully uncommitted and unstaged.
