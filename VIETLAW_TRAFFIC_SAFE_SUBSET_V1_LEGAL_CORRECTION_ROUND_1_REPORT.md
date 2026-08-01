# VIETLAW TRAFFIC SAFE SUBSET V1 — Legal Correction Round 1 Report

> ## CORRECTION NOTICE (Legal Correction Round 2 — current status)
>
> An independent final verification of this round
> (`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_
> V1.md`, verdict `..._VERIFICATION_BLOCKED`, 0 HIGH / 1 MEDIUM / 2 LOW)
> found:
>
> - **MEDIUM-01**: `_REQUIRED_CITATION_SHAPE_BY_TOPIC["traffic_no_helmet"]`
>   (§4 below) only checked the counts of roles it explicitly listed
>   (`primary_penalty`, `licence_point_deduction`) and never mentioned
>   `signal_interpretation` at all — so an enabled helmet row carrying an
>   EXTRA `signal_interpretation` citation (one that has nothing to do with
>   Điều 7 khoản 2 điểm h) passed load-time validation silently, contrary
>   to this report's own claim of "requires exactly 1 primary_penalty and 0
>   licence_point_deduction." Fixed in Legal Correction Round 2: the
>   validator now compares the citations' role multiset for EXACT equality
>   against the configured shape (via `Counter`), so a role absent from a
>   topic's shape is rejected outright, not merely un-checked.
> - **LOW-01**: the machine-readable `EVALUATION_TESTS=141` field below
>   (§11) is mislabeled. `141` is the passing count across the 4 affected
>   backend test files, NOT the count of a separate, larger "platform
>   evaluation suite" (`evaluation/tests/`, 214 tests) that this report
>   never actually ran or reported on. See the inline annotation at that
>   field.
> - **LOW-02**: §6 below states
>   `test_rule_d_disabled_never_produces_a_curated_answer` contains "the
>   exact HIGH-01 adversarial probe" — the pytest test actually uses the
>   shorter "Tôi cầm điện thoại nhưng chưa sử dụng điện thoại." and never
>   contains the full sentence "...khi đang chạy xe máy nhưng chưa sử dụng
>   điện thoại." verbatim. The full sentence DOES appear in
>   `evaluation/legal_beta_v0/cases.py`, and both were independently
>   re-probed live through the FastAPI runtime by the reviewer with a safe
>   result either way — this is a report/test-coverage description
>   mismatch, not a runtime defect.
>
> See `VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_2_REPORT.md`
> for the full current record. This body text is left exactly as
> originally written (audit history, not erased or rewritten) with the
> corrections above layered on top.

`IMPLEMENTER=CLAUDE_CODE_SONNET`.

```
STARTING_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
FINAL_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
```

## 1. Why this round exists

A targeted independent legal re-review of the Safe Subset V1 pack
(`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_V1.md`) returned:

```
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_BLOCKED
HIGH_FINDINGS=1
MEDIUM_FINDINGS=2
```

- **HIGH-01**: Rule D's (motorcycle hand-held phone use) selector could
  `MATCH` even when the user explicitly denied *using* the phone.
  `phone_handheld=yes` + `vehicle_in_operation=yes` proves only that the
  rider held the device while the vehicle moved — not the separate legal
  element of Điều 7 khoản 4 điểm đ, "sử dụng điện thoại" (actually using
  it). The reviewer's adversarial probe ("Tôi dùng tay cầm điện thoại khi
  đang chạy xe máy nhưng chưa sử dụng điện thoại.") produced a `MATCH`
  despite the explicit denial.
- **MEDIUM-01**: the pack carried only one structured citation per rule.
  A red-light rule's licence-point-deduction basis and Luật 36/2024/QH15
  Điều 11's signal-priority basis were prose-only inside `source_excerpt`,
  with no separate official URL the user could open.
- **MEDIUM-02**: `_clarification_response()` set
  `trust_level=curated_verified` even when the selector outcome was
  `MISSING_FACT`, not `MATCH` — misrepresenting an unresolved question as
  an already-verified legal conclusion.

This round fixes exactly these three findings, disables Rule D, does not
expand traffic scope, and does not repair alcohol/speeding/driver-licence/
passenger-limit/vehicle-modification/passenger-helmet.

## 2. Final enabled traffic scope

```
FINAL_ENABLED_TRAFFIC_RULES=3
PHONE_RULE_ENABLED=no
DISABLED_TRAFFIC_RULES=12
```

`traffic_phone_use__motorcycle__handheld_safe_v1` is now
`status=disabled_pending_legal_correction`, carrying `disabled_reason`
citing HIGH-01 verbatim and the exact adversarial probe that exposed it.
Every field the enabled-row load-time validator would otherwise require
(`article_number`/`clause_number`/`point_number`/`legal_citations`) was
cleared to `null`/`[]`, matching the pattern already established for the
11 originally-disabled rows.

Final enabled rules, exactly:

```
traffic_red_light__motorcycle__safe_v1
traffic_red_light__car__safe_v1
traffic_no_helmet__motorcycle__driver_safe_v1
```

Every disabled phone question (including the exact HIGH-01 adversarial
probe) now falls to `GENERAL_GUIDANCE` with `clarifying_questions=[]`,
`sources=[]`, and no penalty amount in the summary — verified by
`test_rule_d_disabled_never_produces_a_curated_answer` (6 parametrized
probes) and `test_rule_d_disabled_falls_through_to_general_guidance_with_
no_citation`.

## 3. Trust level for clarification (MEDIUM-02)

`legal_fallback_orchestrator.py::_clarification_response` now sets
`trust_level=None`, `trust_label=None`, `trust_explanation=None` instead of
`TrustLevel.CURATED_VERIFIED`. `CURATED_VERIFIED` is reachable from exactly
one place in the module — `_build_curated_traffic_response`, itself only
ever called from `_resolve_traffic_topic`'s `RuleSelectionOutcome.MATCH`
branch.

```
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
CLARIFICATION_RESPONSES_WITH_SOURCES=0
MATCH_RESPONSES_WITH_CURATED_VERIFIED=3   (Rules A/B/C, one positive case each)
```

Required test (task §2):

```
Tôi vượt đèn đỏ.
```

Verified directly: initial response asks "Bạn điều khiển xe máy hay ô tô?"
with `trust_level=None`, `sources=[]`, no penalty conclusion; after
"Xe máy." resolves the missing fact, the selector outcome becomes `MATCH`
and the response carries `trust_level=curated_verified` with 3 structured
sources.

The frontend's `SourcePanel`/`StructuredAnswer` already treat a falsy
`trust_level` as "render no trust badge" (`content.trust_level &&` guard),
so this is a purely additive behavioral tightening — no new frontend
branch was needed for the None case itself.

## 4. Multi-provision citation model (MEDIUM-01)

`backend_lite/app/contracts/traffic.py` gained `CitationRole` (`Literal[
"primary_penalty", "licence_point_deduction", "signal_interpretation"]`)
and `TrafficLegalCitation` (`citation_role`, `document_name`,
`document_number`, `article_number`, `clause_number`, `point_number:
str | None`, `official_url`, `relevance_note`). `TrafficRuleRecord` gained
`legal_citations: list[TrafficLegalCitation]`, now the SOURCE OF TRUTH for
a curated response's `sources` — the legacy single `article_number`/
`clause_number`/`point_number`/`official_url` fields are kept only for
backward-compatible load-time checks and mirror the `primary_penalty`
citation.

```
MULTI_PROVISION_SOURCE_MODEL_IMPLEMENTED=yes
RED_LIGHT_MOTORCYCLE_SOURCE_COUNT=3
RED_LIGHT_CAR_SOURCE_COUNT=3
HELMET_SOURCE_COUNT=1

PRIMARY_FINE_CITATIONS_COMPLETE=yes
POINT_DEDUCTION_CITATIONS_COMPLETE=yes
SIGNAL_INTERPRETATION_CITATIONS_COMPLETE=yes
```

Per-rule citations populated exactly per task §4:

| Rule | primary_penalty | licence_point_deduction | signal_interpretation |
|---|---|---|---|
| A (motorcycle red light) | NĐ 168/2024/NĐ-CP Điều 7 khoản 7 điểm c | NĐ 168/2024/NĐ-CP Điều 7 khoản 13 điểm b | Luật 36/2024/QH15 Điều 11 khoản 1-4 |
| B (car red light) | NĐ 168/2024/NĐ-CP Điều 6 khoản 9 điểm b | NĐ 168/2024/NĐ-CP Điều 6 khoản 16 điểm b | Luật 36/2024/QH15 Điều 11 khoản 1-4 |
| C (driver no-helmet) | NĐ 168/2024/NĐ-CP Điều 7 khoản 2 điểm h | — (none for điểm h) | — |

`TrafficSourcePack._validate_legal_citations` (load time) rejects an
enabled row with: no `legal_citations`; not exactly one `primary_penalty`;
any citation missing `official_url`/`document_number`/article+clause; a
`primary_penalty`/`licence_point_deduction` missing `point_number`
(`signal_interpretation` may legitimately omit one — Luật 36 Điều 11's
rule spans khoản 1-4, no single điểm); a duplicate `(role, article,
clause, point)` location; or a per-topic shape mismatch (`traffic_red_
light` requires exactly 1+1+1 of the three roles; `traffic_no_helmet`
requires exactly 1 primary_penalty and 0 licence_point_deduction). A
disabled row is exempt — it can never be selected or shown.

`legal_fallback_orchestrator.py::_build_citation_sources` builds one
`SourceObject` per `legal_citations` entry. `schemas/content.py::
SourceObject` gained two additive optional fields, `point_number: str |
None` and `citation_role: str | None` (plus a companion `clause_number:
str | None` string field, needed because `applicable_clause`/
`clause_numbers` are integer-only and cannot represent a khoản range like
"1-4" without loss) — MODE_2D's wire meaning is completely unchanged
(these fields are simply absent/null for every non-traffic-citation
source).

## 5. Wire response and frontend rendering

`SourcePanel.tsx` gained `TrafficCitationBlock` (Vietnamese headings
`Căn cứ mức phạt` / `Căn cứ trừ điểm GPLX` / `Quy tắc tín hiệu giao thông`,
mirrored exactly from the backend's own `_CITATION_ROLE_LABELS`). When
every safe source in a response carries a non-null `citation_role`, all of
them render directly (no click-to-expand), each its own card with its own
official URL — never merged, never empty.

**A real bug was found and fixed while wiring this, before being reported
here**: `lib/sourceUrl.ts::selectSafeSources` de-duplicates by URL. Rule
A/B's `primary_penalty` and `licence_point_deduction` citations legitimately
share ONE document's URL (Nghị định 168 has no per-article deep link), so
href-based de-duplication would have silently collapsed two distinct
citations into one card — exactly what task §6 forbids. Since
`lib/sourceUrl.ts` is outside this round's permitted-files list, the fix
(`selectSafeSourcesByIdentity`, keying on `id` with an href fallback when
`id` is empty) was implemented locally inside `SourcePanel.tsx`, which the
task does permit; `lib/sourceUrl.ts` itself was not modified. A pre-existing
test (`presentation.test.tsx::"de-duplicates repeated URLs"`) encoded the
old href-based assumption and was updated to reflect the new, intentional
id-based behavior, plus a new test proving the href fallback still applies
when `id` is genuinely empty.

```
RED_LIGHT_MOTORCYCLE_SOURCE_COUNT=3
RED_LIGHT_CAR_SOURCE_COUNT=3
HELMET_SOURCE_COUNT=1
```

MODE_2D and official-source-search source rendering are unchanged (12
pre-existing `sourcePanel.test.tsx` tests pass unmodified); 7 new tests
cover the traffic multi-citation path (all 3 headings render directly, two
citations sharing a URL are not collapsed, each card links to its own URL,
`signal_interpretation` is never labeled as the penalty provision, a
"khoản 1-4" range renders without inventing a điểm, a single-citation rule
still uses its own role heading not the generic one, and a mixed traffic/
non-traffic response falls back to the existing disclosure).

## 6. Required legal behavior tests — all verified

**Motorcycle red light** (`test_rule_a_positive_motorcycle_red_light`):
`4.000.000–6.000.000 đồng`, `trừ 4 điểm`, 3 structured sources, `Điều 7
khoản 7 điểm c`, `Điều 7 khoản 13 điểm b`, `Điều 11` all present.

**Car red light** (`test_rule_b_positive_car_red_light`): `18.000.000–
20.000.000 đồng`, `trừ 4 điểm`, 3 structured sources, `Điều 6 khoản 9 điểm
b`, `Điều 6 khoản 16 điểm b`, `Điều 11` all present.

**Driver helmet** (`test_rule_c_positive_not_wearing`): `400.000–600.000
đồng`, exactly 1 structured source (`citation_role="primary_penalty"`),
`Điều 7 khoản 2 điểm h` present.

**Phone** — all 4 required probes plus the exact HIGH-01 adversarial probe
produce no curated result:

```
Tôi dùng tay cầm điện thoại khi đang chạy xe máy.
Tôi cầm điện thoại nhưng chưa sử dụng điện thoại.  (verbatim task probe)
Tôi dùng điện thoại khi xe đang chạy.  (verbatim task probe, no false MATCH)
Tôi dùng tai nghe rảnh tay.
```

verified via `test_rule_d_disabled_never_produces_a_curated_answer`
(parametrized, 6 messages) and `test_rule_d_disabled_falls_through_to_
general_guidance_with_no_citation`: `trust_level=general_guidance`,
`sources=[]`, `specific penalty absent`.

## 7. Clarification tests — all verified

For each of the three enabled rules, a `MISSING_FACT` turn was tested and
confirmed: `trust_level != curated_verified` (in fact `None`),
`sources=[]`, penalty amount absent. The correctly-answered follow-up then
produces `selector outcome=MATCH`, `trust_level=curated_verified`, and all
expected sources present (`test_vehicle_ambiguity_then_short_vehicle_only_
followup_resolves`, `test_multi_field_topic_asks_each_missing_field_in_its_
own_turn` rebuilt against Rule C's `helmet_subject`/`helmet_status` fields
since Rule D, which previously exercised this multi-field shape, is now
disabled).

Unrelated-turn release and fresh-topic-while-pending switching were also
re-verified: `test_unrelated_turn_releases_pending_vehicle_clarification`,
`test_fresh_traffic_topic_while_a_different_topic_is_pending_switches_
immediately`. M-02-R (the typed `RESOLVED`/`UNKNOWN_VALUE`/`UNRELATED`
parser) remains closed — the `case_a`/`case_b`/`case_g`-style tests were
rebuilt against Rule C's `helmet_status` field (previously Rule D's
`vehicle_in_operation`) and all pass.

## 8. Attribution and safety regression

```
THIRD_PARTY_FACTS_PERSISTED=0
HYPOTHETICAL_FACTS_PERSISTED=0
EDUCATIONAL_FACTS_PERSISTED=0
NEGATED_FACTS_PERSISTED=0
CROSS_TOPIC_FACT_LEAKS=0
STALE_TOPICS_AFTER_UNRELATED_TURNS=0
```

Third-party/hypothetical/negated/educational tests were re-verified,
rebuilding the third-party probe from a phone-use message (now disabled)
to a red-light message ("Bạn tôi đi xe máy vượt đèn đỏ.") that still fully
resolves through the impersonal path in one message. Cross-topic isolation
and pending-clarification release are covered by the dedicated adversarial
tests in `test_traffic_safe_subset_v1.py` and the M-02-R suite in
`test_legal_fallback_orchestrator.py`.

## 9. Evaluation updates

`evaluation/legal_beta_v0/cases.py` was rebuilt: Rule D's positive case
moved to `disabled_topic` (using the exact HIGH-01 adversarial probe);
Rules A/B's citation checks now require all 3 structured citations'
locator text; the `clarification_state_machine` category's cases B/D/E/F/G
were rebuilt against Rule C's `helmet_subject`/`helmet_status` fields; every
ASK-turn expectation across the dataset was corrected from
`curated_verified` to `None` (MEDIUM-02). `run.py` gained two new hard
constraints — `MISSING_FACT_CURATED_VERIFIED_RESPONSES` (any turn with
non-empty `clarifying_questions` and `trust_level=curated_verified`) and
`INCOMPLETE_STRUCTURED_CITATIONS` (any `curated_verified` response whose
sources are missing document/article/clause identity, or missing
`point_number` on a `primary_penalty`/`licence_point_deduction` citation) —
plus its citation-text blob now also searches `relevance_note` (not just
`snippet`), since a citation's full locator text lives there.

```
Hard constraints (this run):
UNSUPPORTED_CITATION_RATE=0
DISABLED_RULE_CURATED_ANSWERS=0
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
INCOMPLETE_STRUCTURED_CITATIONS=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
MODE_2D_CLAUSE_2_OUTPUTS=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0

49 turns evaluated, 0 findings.
```

## 10. M-01 through M-04 / MODE_2D status

```
M01_REMAINED_CLOSED=yes
M02R_REMAINED_CLOSED=yes
M03_REMAINED_CLOSED=yes
M04_REMAINED_CLOSED=yes

MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
```

All 7 frozen MODE_2D files show zero diff (`git diff --stat`).
`resolve_deposit_applicable_clause` was re-probed directly against 3
representative fact states and returned `None` in every case.
`schemas/content.py` was modified this round (permitted for this task
specifically) but only with two additive optional `SourceObject` fields
(`point_number`, `citation_role`) plus a companion `clause_number` string
field — MODE_2D's existing `document_title`/`article_number`/
`applicable_clause`/`clause_numbers` fields and their meaning are
completely unchanged, and the frontend's MODE_2D rendering tests
(`sourcePanel.test.tsx`'s original 12 cases) pass unmodified.

## 11. Regression

| Check | Result |
|---|---|
| Complete `backend_lite` suite | **1526 passed** |
| Focused MODE_2D suite (`-k "fast_demo or mode_2d or MODE_2D"`) | 259 passed |
| Traffic source-pack + safe-subset + orchestrator + Public Beta integration tests | 141 passed (across the 4 affected files) |
| `evaluation/legal_beta_v0` runner | 49 turns, **0 findings**, all 8 hard constraints `0` |
| Frontend tests (`npm run test -- --run`) | 179 passed (11 files) |
| Frontend typecheck (`tsc --noEmit`) | clean |
| Frontend build (`tsc && vite build`) | succeeded |
| `python3 -m compileall backend_lite evaluation data` | exit 0 |
| `git diff --check` | exit 0, no whitespace errors |
| Secret scan (api_key/secret/password/BEGIN/sk- pattern grep over this round's changed files) | no findings (only a benign test fixture `api_key="test-key"`) |

```
BACKEND_LITE_TESTS=1526
FOCUSED_MODE_2D_TESTS=259
EVALUATION_TESTS=141
# ^ CORRECTED (Legal Correction Round 2, LOW-01): this field is mislabeled.
#   141 is AFFECTED_BACKEND_TESTS (the 4 traffic-related backend test
#   files), NOT a count of the separate platform evaluation suite
#   (`evaluation/tests/`), which this report never ran. See
#   VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_2_REPORT.md for
#   AFFECTED_BACKEND_TESTS=141 and PLATFORM_EVALUATION_TESTS=214 reported
#   as two distinct, correctly-labeled fields.
LEGAL_BETA_EVALUATION_TURNS=49
FRONTEND_TESTS=179
TYPECHECK=clean
BUILD=success
COMPILEALL=exit_0
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean
```

No live provider or live web search was called at any point;
`FakeOfficialLegalSearchService` and `FakeLLMClient` were the only
providers used throughout.

## 12. Scope discipline

Files touched this round: `data/traffic_rules.json`,
`backend_lite/app/contracts/traffic.py`,
`backend_lite/app/services/traffic_source_pack.py`,
`backend_lite/app/services/legal_fallback_orchestrator.py`,
`backend_lite/app/schemas/content.py`,
`backend_lite/tests/unit/test_traffic_source_pack.py`,
`backend_lite/tests/unit/test_legal_fallback_orchestrator.py`,
`backend_lite/tests/unit/test_traffic_safe_subset_v1.py`,
`backend_lite/tests/integration/test_public_beta_v0_legal_fallback_e2e.py`,
`frontend/src/api/types.ts`, `frontend/src/components/SourcePanel.tsx`,
`frontend/src/test/sourcePanel.test.tsx`,
`frontend/src/test/presentation.test.tsx`,
`evaluation/legal_beta_v0/cases.py`, `evaluation/legal_beta_v0/run.py`,
this report, and correction notices added to both
`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_IMPLEMENTATION_REPORT.md` and
`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md` (history preserved, not
erased).

Not touched: the traffic classifier's phone fact model (`phone_handheld`/
`vehicle_in_operation` detectors in `traffic_classifier.py` are unchanged —
no `phone_use` fact or negation/evidence handling was added, per the
task's explicit "do not redesign phone classification" instruction), all 7
frozen MODE_2D files, official-search provider wiring, rate limiting,
Docker/Railway/Cloudflare files, and every other legal domain.
`frontend/src/lib/sourceUrl.ts` was also deliberately left untouched (see
§5) even though its href-based de-duplication needed correcting — the fix
was implemented locally inside the permitted `SourcePanel.tsx` instead.

## 13. Commit discipline

```
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
LIVE_PROVIDER_CALLS=0
LIVE_WEB_SEARCH_CALLS=0
```

`git rev-parse HEAD` before and after this round:
`5079454d90730ac9f7fb23d18fe6b8a5578229a4` (unchanged). All work remains
in the working tree, uncommitted and unstaged, per the task's explicit
instruction.

## 14. Final verdict

- Exactly three rules are enabled; Rule D is disabled with a
  `disabled_reason` citing HIGH-01.
- `CURATED_VERIFIED` is now reachable only via `select_rule`'s `MATCH`
  outcome — a clarification ask carries `trust_level=None`.
- Structured citations are complete for all three enabled rules (red-light
  rules: primary_penalty + licence_point_deduction + signal_interpretation;
  helmet rule: primary_penalty only), each independently traceable with its
  own official URL, enforced both at load time and by a dedicated
  evaluation hard constraint.
- Zero HIGH or MEDIUM findings were newly identified during this round's
  own self-testing (one real bug — the `SourcePanel` URL-based
  de-duplication silently merging distinct citations — was found and fixed
  before being reported here, matching the "verify before claiming done"
  discipline established in prior correction rounds).
- MODE_2D remains completely frozen: zero diff on all 7 frozen files,
  `resolve_deposit_applicable_clause` still always returns `None`, zero
  production `applicable_clause == 2` paths.

```
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_READY_FOR_REVIEW
```
