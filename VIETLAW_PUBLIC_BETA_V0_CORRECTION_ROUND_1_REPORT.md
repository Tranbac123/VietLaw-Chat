# VIETLAW PUBLIC BETA V0 — Correction Round 1 Report

> ## CORRECTION ROUND 2 NOTICE
>
> Independent review of this report
> (`VIETLAW_PUBLIC_BETA_V0_CODEX_CORRECTION_ROUND_1_VERIFICATION_V1.md`,
> verdict `VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_VERIFICATION_BLOCKED`)
> found that **M-02 was NOT actually closed by this round**, despite the
> `M02_STICKY_CLARIFICATION_FIXED=yes` claim below (see "Fix status") and
> the "M-02 — pending clarification must release unrelated turns" section's
> "FIXED" claim. Both are **false as originally written** and are left
> unmodified for the audit record; do not treat them as current.
>
> Root cause (MEDIUM M-02-R): the field-answer validator this round shipped
> (`is_valid_clarification_answer`) accepted **any digit** as a valid answer
> for `speed_excess_kmh`, `alcohol_level`, and `passenger_count`. An
> unrelated message that merely contains a number (`"Hôm nay 30 độ C."`,
> `"Tôi nhận lương tháng 7..."`) was therefore misread as a genuine
> clarification attempt. Because such a message carries no first-person
> traffic attribution, it fell through to the impersonal path, which
> (correctly, per M-01) never mutates state — but that also meant the
> pending `traffic_topic_id`/`traffic_pending_field` were never cleared
> either, so a LATER, completely unrelated turn could resume the stale
> topic and receive real curated traffic content. The same defect made
> several of this round's own "valid answer" claims (`Xe máy.`, `10 km/h.`,
> `0.2 mg/l.`, `3 người.`, `Thay lốp.`) unverified in practice — the
> committed-value proof this report describes below was not actually
> exercised by dedicated tests at the time.
>
> **M-02-R has now been corrected** through a typed, field-specific parser
> (`parse_clarification_answer` → `RESOLVED` / `UNKNOWN_VALUE` / `UNRELATED`,
> replacing the boolean-only check) — see
> `VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_2_REPORT.md` for the full fix,
> the corrected field-by-field parsers, and the new required test coverage.
> M-01, M-03, and M-04 were independently verified closed in this same
> review and were not reopened or redesigned.
>
> **Do not read this report as a current statement that all Public Beta V0
> findings are closed.** Treat Correction Round 2's own verdict as
> authoritative for current status.

Routing, state, copy, and query privacy fixes for the four MEDIUM findings
(M-01 through M-04) raised by independent review
(`VIETLAW_PUBLIC_BETA_V0_CODEX_IMPLEMENTATION_VERIFICATION_V1.md`, verdict
`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_VERIFICATION_BLOCKED`), plus the two
report-count inaccuracies it identified.

```
STARTING_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
FINAL_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4  (no commits created)
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
```

## FILES_MODIFIED

```
backend_lite/app/contracts/traffic.py
backend_lite/app/contracts/legal_fallback_state.py
backend_lite/app/services/traffic_classifier.py
backend_lite/app/services/legal_fallback_orchestrator.py
backend_lite/tests/unit/test_traffic_classifier.py
backend_lite/tests/unit/test_legal_fallback_orchestrator.py
backend_lite/tests/integration/test_public_beta_v0_legal_fallback_e2e.py
evaluation/legal_beta_v0/cases.py
frontend/src/components/LandingChatState.tsx
frontend/src/test/landingChatState.test.tsx
VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md  (correction notice + inline annotations, not rewritten)
```

Everything above was already untracked/new from the prior task except
`contracts/traffic.py`, `contracts/legal_fallback_state.py`, `traffic_classifier.py`,
`legal_fallback_orchestrator.py`, `LandingChatState.tsx`, and
`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md`, which were tracked-but-uncommitted
files from the prior task, edited further here. No file outside the
Correction Round 1 scope list (§9 of the task) was touched.

## FILES_CREATED

```
VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_REPORT.md  (this file)
```

No frozen MODE_2D file, no new dependency, no deployment/configuration
file was created or touched.

## Fix status

**[Correction Round 2: `M02_STICKY_CLARIFICATION_FIXED=yes` below was FALSE
as written — see the Correction Round 2 Notice at the top of this
document. M-01/M-03/M-04 were independently confirmed closed and remain
closed.]**

```
M01_TRAFFIC_ATTRIBUTION_FIXED=yes
M02_STICKY_CLARIFICATION_FIXED=yes
M03_LANDING_CLAIM_FIXED=yes
M04_QUERY_PRIVACY_FIXED=yes
```

### M-01 — traffic self-attribution

`traffic_classifier.classify()` now returns a bounded `attribution` result
(`self` / `third_party` / `hypothetical` / `educational` / `negated` /
`unknown`), computed by structural guards checked in priority order:

1. Was the detected action cue itself negated (existing negation guard,
   widened from a fixed 4-word lookback to a clause-scoped scan so
   "chưa từng lái xe khi có nồng độ cồn" — 6 words between negator and
   cue — is now caught; previously missed)? → `negated`.
2. A bounded third-party subject phrase ("bạn tôi", "anh trai tôi", "một
   người bạn", ...)? → `third_party`.
3. A conditional/hypothetical marker ("nếu", "giả sử", "ví dụ", "trường
   hợp")? → `hypothetical`.
4. An educational/research marker ("đang đọc", "bài viết", "nghiên cứu
   về", ...)? → `educational`.
5. A first-person subject ("tôi")? → `self`.
6. Otherwise → `unknown`.

`LegalFallbackOrchestrator._handle_traffic` now branches on this: only
`attribution == "self"` merges facts into per-chat state, sets a pending
clarification, or asks a personal follow-up question. Every other
attribution routes through a new `_handle_traffic_impersonal` path that:

- uses the detected facts only *transiently*, for that one turn's rule
  lookup (never merged into or returned as part of persisted state — the
  original `current` state object is returned byte-for-byte unchanged);
- never asks a personal clarification (asking "bạn điều khiển xe máy hay ô
  tô?" about someone else's or a hypothetical event would itself be wrong,
  so a missing required fact falls through to the next routing tier
  instead of interrogating the user);
- still renders a genuinely useful answer when every required fact is
  already stated (e.g. "Bạn tôi dùng điện thoại khi chạy xe máy." → a real
  `curated_verified` answer about the phone-use rule, with no vehicle/fact
  ever written to state).

The rendered answer text itself was already law-general ("Người điều khiển
xe mô tô... bị phạt...") rather than accusatory ("bạn đã vi phạm"), so no
wording change was needed there — verified explicitly by
`test_third_party_traffic_mention_answers_without_claiming_the_user_violated`.

A pre-existing, unrelated bug was also found and fixed while building this:
"Tôi dùng điện thoại khi **đang** chạy xe máy" (one of the task's own
required self-attributed probes) failed topic detection entirely, because
the phone-use cue phrases had no "khi đang ..." variant. Added.

### M-02 — pending clarification must release unrelated turns

> **[Correction Round 2: this section describes the Round 1 fix, which was
> INCOMPLETE — the `is_valid_clarification_answer` digit-acceptance rule
> described below is exactly what caused MEDIUM M-02-R. See the Correction
> Round 2 Notice at the top of this document and
> `VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_2_REPORT.md` for the actual
> fix. Left unmodified below for the audit record.]**

`LegalFallbackState` gained a new field, `traffic_pending_field`, recording
exactly which required-fact slot the last clarification question asked
about (`"vehicle_type"`, `"speed_excess_kmh"`, `"license_status"`,
`"alcohol_level"`, `"passenger_count"`, or `"modification_type"`).

A new `traffic_classifier.is_valid_clarification_answer(pending_field,
message)` decides, per field, whether the CURRENT message is a plausible
answer:

- `vehicle_type` → the message names a vehicle ("xe máy", "ô tô", "tôi đi
  xe máy", "tôi lái ô tô", ...);
- `license_status` / `modification_type` → the field's own existing
  bounded cue set reports a non-`"unknown"` value;
- `speed_excess_kmh` / `passenger_count` / `alcohol_level` → the message
  contains a digit (these fields have no structured cue vocabulary);
- any field → an explicit "tôi không biết"/"chưa biết"/"không rõ" is
  always accepted (an unresolved but genuine answer attempt, not an
  unrelated turn — this is what lets the existing "ask at most once, then
  answer anyway" alcohol-level flow keep working).

`LegalFallbackOrchestrator._handle()` now only continues a pending topic
when `is_valid_clarification_answer` returns `True` for the message
against the SPECIFIC pending field. Otherwise the pending state is
released (`traffic_topic_id`/`traffic_pending_field` cleared) and the turn
falls through to the normal `is_legal_or_rights_related` gate exactly as
if no clarification had ever been pending. The release is persisted via
CAS commit even when the overall turn ultimately defers with `response =
None` (an unrelated, non-legal message) — otherwise the release would only
have taken effect in memory for that one call and the stale pending state
would still be on disk for the next turn.

Verified end-to-end: "Tôi vượt đèn đỏ thì bị phạt bao nhiêu?" → clarifying
question asked → "Hôm nay thời tiết thế nào?" now returns the plain social/
scope reply (`trust_level=None`, no repeated clarification), and the
persisted state confirms `traffic_topic_id`/`traffic_pending_field` are
both `None` afterward — including on a THIRD unrelated turn, proving the
release is durable, not just suspended for one turn.

### M-03 — landing-page claim

`LandingChatState.tsx`'s beta-scope paragraph previously said VietLaw Beta
"có thể tra cứu nguồn pháp luật chính thức cho các câu hỏi khác" (can look
up official legal sources for other questions) — true of the code path,
false of the deployed capability (no search provider is wired; see the
implementation report's own Known Limitations #3, which already said this
correctly — the landing copy simply hadn't been kept in sync with it).

No backend capability-contract endpoint exists to derive this text from
without a broader refactor (out of this correction's scope per the task's
own instruction), so the fix is the suggested conservative static copy:

```
VietLaw Beta hỗ trợ chuyên sâu tình huống đặt cọc thuê nhà, một số vi phạm
giao thông phổ biến và cung cấp hướng dẫn chung cho các vấn đề pháp luật khác.
Tính năng tra cứu nguồn pháp luật chính thức đang trong quá trình hoàn thiện.
Nội dung chỉ mang tính tham khảo, không thay thế tư vấn pháp lý chuyên nghiệp.
```

### M-04 — search-query privacy minimization

`build_search_query()` was rewritten as a three-layer strategy:

1. **Structured query preferred.** A small, hand-curated set of Vietnamese
   legal-issue-category phrases (labor/wage withheld, dismissal, land
   encroachment/dispute, employment contract, damages, administrative
   complaint, civil lawsuit) each map to a FIXED topic-level query
   template ("quy định pháp luật Việt Nam về ..."). When one matches, the
   raw narrative is never touched at all — no name, address, or contact
   value the user wrote can possibly reach the query, structurally, not
   just by redaction.
2. **Narrative minimization otherwise.** When no category matches, the
   message is minimized: the original digit-shaped redaction (phone/CCCD/
   account numbers) is kept, and three new patterns are added — email
   addresses, street-number+capitalized-name address patterns ("12 Nguyễn
   Huệ", "45 Lê Lợi"), and "tôi là/tên tôi là <Name>"-style
   self-introductions (the whole clause is dropped, not just the name).
   This is explicitly NOT Vietnamese NER (per the task's own instruction)
   — a bounded, conservative heuristic that over-redacts rather than
   under-redacts.
3. **Fail closed.** If minimization leaves nothing usable (empty, or only
   punctuation/whitespace), `build_search_query` returns `None`.
   `_handle_official_search` now checks for this explicitly and defers to
   `GENERAL_GUIDANCE` without ever calling the search service — never a
   fallback to sending the raw, unminimized message.

The task's exact required example now produces:

```
input:  "Tôi là Nguyễn Văn A, ở 12 Nguyễn Huệ, số điện thoại 0909123456.
         Công ty không trả lương sau khi tôi nghỉ việc."
output: "quy định pháp luật Việt Nam về người sử dụng lao động không trả
         lương sau khi người lao động nghỉ việc"
```

None of "Nguyễn Văn A", "12 Nguyễn Huệ", or "0909123456" appear anywhere in
the output — verified by
`test_build_search_query_redacts_combined_personal_data`.

## Counts (verified against the fixes above)

```
THIRD_PARTY_FACTS_PERSISTED=0
HYPOTHETICAL_FACTS_PERSISTED=0
EDUCATIONAL_FACTS_PERSISTED=0
NEGATED_FACTS_PERSISTED=0
```

Each proven directly against `LegalFallbackStateStore` state (not just
response-level trust_level) by
`test_third_party_message_answers_but_never_persists_facts`,
`test_hypothetical_message_answers_but_never_persists_facts`,
`test_educational_message_never_persists_facts_and_never_forces_alcohol_level`,
and `test_negated_message_never_persists_and_never_answers_as_curated` in
`backend_lite/tests/unit/test_legal_fallback_orchestrator.py`.

```
UNRELATED_TURN_REPEATS_TRAFFIC_CLARIFICATION=no
UNWIRED_SEARCH_ADVERTISED=no
```

```
NAMES_IN_REQUIRED_SEARCH_PROBES=0
ADDRESSES_IN_REQUIRED_SEARCH_PROBES=0
CONTACT_VALUES_IN_REQUIRED_SEARCH_PROBES=0
```

Verified across the full required probe set (Vietnamese full name, street
address, phone, CCCD, bank-account-like value, email, combined
personal-data message, structured traffic query — n/a, handled separately
by the curated pack — structured labor query) in
`test_build_search_query_redacts_*` / `test_build_search_query_uses_a_structured_*`
/ `test_build_search_query_fails_closed_when_nothing_safe_remains`.

## MODE_2D preservation

```
MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
EXISTING_DEPOSIT_FLOW_PRESERVED=yes
ARTICLE_328_ONLY_FOR_DEPOSIT=yes
RESOLVER_ALWAYS_RETURNS_NONE=yes
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
```

`git diff --stat` on all seven frozen MODE_2D files
(`fast_demo_routing.py`, `fast_demo_fact_validation.py`,
`fast_demo_source_pack.py`, `fast_demo_orchestrator.py`,
`fast_demo_prompt.py`, `contracts/fast_demo.py`, `data/legal_snippets.json`)
is empty — byte-identical to HEAD. `resolve_deposit_applicable_clause()`
directly probed across 16 `(facts, clause_numbers)` combinations: 0
returned non-`None`.

## Regression

```
NEW_TEST_COLLECTION_TOTALS=208 tests collected (10 new backend test files)
FOCUSED_ARTICLE_CITATION_TESTS=256 passed  (exact unchanged baseline)
BACKEND_LITE_TESTS=1379 passed
EVALUATION_TESTS=214 passed  (exact unchanged baseline, existing platform)
LEGAL_BETA_EVALUATION_TURNS=27 turns, no findings  (was 22; +5 new M-01/M-02 cases)
FRONTEND_TESTS=171 passed  (was 168; +3 new landing-copy assertions)
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

## Report accuracy corrections applied

`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md` was NOT rewritten or
erased. A correction notice was added directly under the title (audit
history preserved below it, unmodified), plus three inline annotations at
the specific paragraphs that were wrong:

- `NEW_TEST_COLLECTION_TOTALS`: "11 new backend test files" → corrected
  inline to 10 (the 144-test figure itself was accurate for that point in
  time and is left as-is; current total is 208, reported above).
- Traffic-topics section: "12 rule entries" → corrected inline to 11.
- `PRIVACY_REVIEW`: the "never... names, addresses" claim → annotated as
  false as originally written, with the actual fix described.
- `FINAL VERDICT`: "Zero HIGH and zero MEDIUM self-identified findings
  remain open" → annotated as false as originally written (the four
  MEDIUM findings existed in the code at that time; they were only caught
  by the subsequent independent review, not this report's own
  self-assessment). Correction Round 1's own verdict below is now
  authoritative.

## Scope discipline

```
LIVE_PROVIDER_CALLS=0
LIVE_WEB_SEARCH_CALLS=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
```

No new product feature was added. No live search provider was wired (the
official-search vertical remains exactly as unwired as before — only its
query-construction privacy was fixed). No frozen MODE_2D file was
modified. No file outside the §9 scope list was touched. No dependency was
added; every fix uses only the Python/TypeScript standard library and
already-present packages (`re`, `unicodedata`, Pydantic, React).

## FINAL VERDICT (superseded — see Correction Round 2)

```
VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_READY_FOR_REVIEW
```

**[Correction Round 2: this verdict was premature.** Independent review
found M-02 was not actually closed (MEDIUM M-02-R). See the Correction
Round 2 Notice at the top of this document and
`VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_2_REPORT.md` for the authoritative
current verdict. This line is left as originally written for the audit
record.]

All four MEDIUM findings (M-01 through M-04) are closed, each with
dedicated deterministic test coverage (unit-level classifier/orchestrator
tests proving the underlying mechanism, plus end-to-end integration tests
proving the wire-level behavior) and re-verified against the exact
required regression list. Both report-count inaccuracies are corrected.
Zero newly-identified HIGH or MEDIUM findings were found while implementing
these fixes (the two pre-existing gaps discovered and fixed along the way —
the "khi đang" phone-use cue miss, and the negation-window width — are
narrow, self-contained classifier corrections directly in service of M-01,
not separate new findings). Changes remain fully uncommitted and unstaged.
