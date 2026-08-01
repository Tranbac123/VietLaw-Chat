# VIETLAW TRAFFIC SAFE SUBSET V1 — Legal Correction Round 2 Report

`IMPLEMENTER=CLAUDE_CODE_SONNET`.

```
STARTING_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
FINAL_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
```

## 1. Why this round exists

An independent final verification of Legal Correction Round 1
(`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_V1.md`)
returned:

```
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_BLOCKED
HIGH_FINDINGS=0
MEDIUM_FINDINGS=1
LOW_FINDINGS=2
```

- **MEDIUM-01**: `_REQUIRED_CITATION_SHAPE_BY_TOPIC["traffic_no_helmet"]`
  only checked the counts of roles it explicitly listed (`primary_penalty`,
  `licence_point_deduction`) and never mentioned `signal_interpretation` at
  all. The reviewer's probe constructed an enabled `traffic_no_helmet` row
  carrying both a `primary_penalty` AND a `signal_interpretation` citation
  and confirmed `_validate_legal_citations()` did not raise —
  `HELMET_EXTRA_SIGNAL_INTERPRETATION_ACCEPTED=yes`. Current production
  data was not affected (the real helmet row only ever had one citation),
  but the load-time guarantee itself was not fail-closed against a future
  malformed row.
- **LOW-01**: the Round 1 report's `EVALUATION_TESTS=141` field conflated
  two different things — the count of passing tests across the 4 traffic-
  related backend test files (141) and a separate, larger "platform
  evaluation suite" (`evaluation/tests/`, 214 tests) that the report never
  actually ran or reported a count for under that name.
- **LOW-02**: the Round 1 report claimed
  `test_rule_d_disabled_never_produces_a_curated_answer` contained "the
  exact HIGH-01 adversarial probe," but the pytest parametrization actually
  used the shorter equivalent "Tôi cầm điện thoại nhưng chưa sử dụng điện
  thoại." — never the full verbatim sentence "...khi đang chạy xe máy
  nhưng chưa sử dụng điện thoại."

This round fixes exactly these three findings. It does not change any
legal conclusion, enabled rule, selector, traffic fact, frontend behavior,
MODE_2D file, or deployment configuration.

## 2. Exact citation shape validation (MEDIUM-01)

`backend_lite/app/services/traffic_source_pack.py`:

- Renamed `_REQUIRED_CITATION_SHAPE_BY_TOPIC` to
  `_EXACT_CITATION_SHAPE_BY_TOPIC` and removed its explicit
  `"licence_point_deduction": 0` entry for `traffic_no_helmet` (a role
  simply absent from a topic's shape now means "zero of this role, no
  exceptions" by construction, not by an explicit-but-incomplete zero
  entry that a reviewer could show was itself incomplete).
- `_validate_legal_citations()` now builds `Counter(role_counts)` (the
  citations' own role multiset) and `Counter(expected_shape)` (the
  configured shape) and requires them to be **exactly equal** —
  `collections.Counter` from the standard library, per the task's
  suggested approach. Neither Counter ever holds an explicit zero entry
  (each is built only from roles actually present), so equality does not
  depend on any Python-version-specific "Counter with zero counts"
  semantics.
- A redundant `sum(actual) == sum(expected)` total-count check is kept as
  defense in depth (task §1: "verify the total citation count equals the
  sum of expected counts"), even though it is unreachable once the
  `Counter` equality above holds.

This single change rejects every failure mode task §1 lists: a missing
required role, an extra role the shape never mentions (the exact MEDIUM-01
defect), a duplicate beyond the expected count, and a wrong count for any
listed role. An unknown `citation_role` string was already rejected earlier
in the pipeline, structurally, by the `CitationRole` `Literal` type on
`TrafficLegalCitation` at Pydantic construction time — confirmed by a new
dedicated test rather than assumed.

```
EXACT_CITATION_SHAPE_VALIDATION_IMPLEMENTED=yes
INCORRECT_TOPIC_CITATION_SHAPES_ACCEPTED=0
```

Direct reproduction of the reviewer's exact probe (constructed
independently, bypassing the production data file):

```python
row = enabled traffic_no_helmet rule with
      legal_citations=[primary_penalty, signal_interpretation]
TrafficSourcePack.from_file(...) raises TrafficSourcePackError:
  "enabled rule r1 (topic traffic_no_helmet) has citation role shape
   {'primary_penalty': 1, 'signal_interpretation': 1}, expected exactly
   {'primary_penalty': 1}"
```

## 3. Required rejection tests

Added to `backend_lite/tests/unit/test_traffic_source_pack.py` (45 tests
in the file total, up from 41):

- `test_helmet_rule_with_an_extra_signal_interpretation_citation_is_
  rejected` — the exact reviewer probe.
- `test_red_light_rule_with_two_primary_penalty_citations_is_rejected` —
  an extra `primary_penalty` on a topic that also has a per-topic exact
  shape (proves the generic and per-topic checks agree).
- `test_red_light_rule_with_an_extra_unrelated_citation_role_location_is_
  rejected` — a 4th, individually well-formed citation (a second
  `signal_interpretation` at a different legal location) added on top of
  an already-complete 3-role shape.
- `test_citation_with_an_unknown_role_is_rejected` — confirms the
  `CitationRole` `Literal` type rejects an unrecognized role value.
- (Pre-existing, unchanged) `test_no_helmet_rule_with_a_licence_point_
  deduction_citation_is_rejected` and `test_red_light_rule_missing_
  licence_point_deduction_citation_is_rejected` continue to cover "extra
  points citation" and "missing role" respectively.

```
HELMET_EXTRA_SIGNAL_CITATION_REJECTED=yes
HELMET_EXTRA_POINTS_CITATION_REJECTED=yes
RED_LIGHT_MISSING_ROLE_REJECTED=yes
RED_LIGHT_EXTRA_ROLE_REJECTED=yes
```

## 4. Production pack still loads correctly

`test_real_pack_red_light_rules_have_the_full_three_citation_shape` and
`test_real_pack_helmet_rule_has_exactly_one_primary_penalty_citation`
(pre-existing, unchanged) continue to pass, and were re-confirmed directly:

```
VALID_PRODUCTION_PACK_LOADS=yes
motorcycle red light: 3 citations (primary_penalty, licence_point_deduction, signal_interpretation)
car red light:        3 citations (primary_penalty, licence_point_deduction, signal_interpretation)
driver helmet:         1 citation  (primary_penalty)
```

## 5. Runtime behavior unchanged

No changes were made to `data/traffic_rules.json`'s legal values or
enabled/disabled status, `TrafficRuleSelection`/`select_rule()`, trust
gating, `schemas/content.py::SourceObject`, `SourcePanel.tsx`, the traffic
classifier, or `legal_fallback_orchestrator.py`. Confirmed directly:

```
FINAL_ENABLED_TRAFFIC_RULES=3
DISABLED_TRAFFIC_RULES=12
PHONE_RULE_ENABLED=no

MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
DISABLED_RULE_CURATED_ANSWERS=0

RED_LIGHT_MOTORCYCLE_SOURCE_COUNT=3
RED_LIGHT_CAR_SOURCE_COUNT=3
HELMET_SOURCE_COUNT=1

MULTI_PROVISION_SOURCE_MODEL_CORRECT=yes
PRIMARY_FINE_CITATIONS_COMPLETE=yes
POINT_DEDUCTION_CITATIONS_COMPLETE=yes
SIGNAL_INTERPRETATION_CITATIONS_COMPLETE=yes
```

## 6. Report label corrections (LOW-01)

`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_REPORT.md` gained
a Correction Round 2 notice at the top (history preserved, not erased) and
an inline annotation directly on the mislabeled `EVALUATION_TESTS=141`
field explaining the conflation and pointing to this report's correctly
labeled fields:

```
AFFECTED_BACKEND_TESTS=141
PLATFORM_EVALUATION_TESTS=214
```

`AFFECTED_BACKEND_TESTS=141` is the passing count across
`test_traffic_source_pack.py`, `test_traffic_safe_subset_v1.py`,
`test_legal_fallback_orchestrator.py`, and
`test_public_beta_v0_legal_fallback_e2e.py` (now 146, +5 for this round's
new tests — see §9). `PLATFORM_EVALUATION_TESTS=214` is the separate
`evaluation/tests/` pytest suite (oracles, runners, reporters, schema/case
tests), confirmed to still pass in full this round. Neither number is used
to describe the other anywhere in this report.

## 7. Phone-test description correction (LOW-02)

The distinction the reviewer required is now explicit, everywhere the
phone probes are discussed:

- **pytest phone probes**: `test_rule_d_disabled_never_produces_a_curated_
  answer` in `test_traffic_safe_subset_v1.py` — now 7 parametrized
  messages (was 6), including BOTH the full verbatim HIGH-01 sentence
  ("Tôi dùng tay cầm điện thoại khi đang chạy xe máy nhưng chưa sử dụng
  điện thoại.") and the shorter equivalent ("Tôi cầm điện thoại nhưng chưa
  sử dụng điện thoại.") that was already there, each now labeled in a
  code comment for exactly what it is.
- **evaluation dataset probes**: `evaluation/legal_beta_v0/cases.py`'s
  `disabled_phone_use_high_01` case already carried the full verbatim
  sentence (unchanged this round).
- **independent reviewer probes**: the reviewer's own live-runtime probe
  of all six original phone messages, confirmed safe in both prior
  verification rounds.

The exact required statement:

> The full HIGH-01 sentence was covered by evaluation and independent
> review. The pytest parametrized test used shorter equivalent
> phone-denial probes.

is now also true of pytest itself — the full sentence was added there too,
so pytest, the evaluation dataset, and the reviewer's own probes all now
cover the identical adversarial sentence, verified again as producing no
curated result:

```python
"Tôi dùng tay cầm điện thoại khi đang chạy xe máy nhưng chưa sử dụng điện thoại."
-> trust_level != curated_verified (general_guidance)
-> sources = []
-> "800.000"/"1.000.000" not in summary
```

## 8. Frozen boundaries

```
MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
RESOLVER_ALWAYS_RETURNS_NONE=yes
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
```

All 7 frozen MODE_2D files show zero diff (`git diff --stat`).
`resolve_deposit_applicable_clause` was re-probed directly against 3
representative fact states and returned `None` in every case. No live
provider or live web-search call was made at any point.

## 9. Regression

| Check | Result |
|---|---|
| Traffic source-pack tests | 45 passed (was 41; +4 new exact-shape rejection tests) |
| Safe-subset tests | 36 passed (was 35; +1 new full-sentence HIGH-01 test) |
| Fallback orchestrator tests | 45 passed (unchanged) |
| Public Beta integration tests | 20 passed (unchanged) |
| Complete `backend_lite` suite | **1531 passed** (was 1526; +5) |
| Focused MODE_2D suite (`-k "fast_demo or mode_2d or MODE_2D"`) | 259 passed |
| Platform evaluation suite (`evaluation/tests/`) | **214 passed** |
| `evaluation/legal_beta_v0` runner | 49 turns, **0 findings**, all 8 hard constraints `0` |
| Frontend tests (`npm run test -- --run`) | 179 passed (11 files) |
| Frontend typecheck (`tsc --noEmit`) | clean |
| Frontend build (`tsc && vite build`) | succeeded |
| `python3 -m compileall backend_lite evaluation data` | exit 0 |
| `git diff --check` | exit 0, no whitespace errors |
| Secret scan (api_key/secret/password/BEGIN/sk- pattern grep over this round's changed files) | no findings (only benign report-text mentions of the word "SECRET_SCAN" and a test fixture `api_key="test-key"`) |

```
AFFECTED_BACKEND_TESTS=146
BACKEND_LITE_TESTS=1531
FOCUSED_MODE_2D_TESTS=259
PLATFORM_EVALUATION_TESTS=214
LEGAL_BETA_EVALUATION_TURNS=49
FRONTEND_TESTS=179
TYPECHECK=clean
BUILD=success
COMPILEALL=exit_0
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean
```

```
UNSUPPORTED_CITATION_RATE=0
DISABLED_RULE_CURATED_ANSWERS=0
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
INCOMPLETE_STRUCTURED_CITATIONS=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
MODE_2D_CLAUSE_2_OUTPUTS=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0
INCORRECT_TOPIC_CITATION_SHAPES_ACCEPTED=0
```

## 10. M-01 through M-04 status

```
M01_REMAINED_CLOSED=yes
M02R_REMAINED_CLOSED=yes
M03_REMAINED_CLOSED=yes
M04_REMAINED_CLOSED=yes
```

None of this round's changes touched attribution, per-chat state, query
redaction, or landing-page copy; the full backend suite (which includes
every M-01/M-02-R/M-03/M-04 regression test) passes in full.

## 11. Scope discipline

Files touched this round: `backend_lite/app/services/traffic_source_pack.py`
(the `Counter`-based exact-shape validator), `backend_lite/tests/unit/
test_traffic_source_pack.py` (4 new rejection tests), `backend_lite/tests/
unit/test_traffic_safe_subset_v1.py` (1 new parametrized full-sentence
test), this report, and a correction notice plus inline annotation added
to `VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_REPORT.md`
(history preserved, not erased).

Not touched: `data/traffic_rules.json`, `backend_lite/app/contracts/
traffic.py`, `backend_lite/app/services/legal_fallback_orchestrator.py`,
`backend_lite/app/schemas/content.py`, any frontend file, the traffic
classifier, any of the 7 frozen MODE_2D files, official-search provider
wiring, rate limiting, Docker/Railway/Cloudflare files, and every other
legal domain.

## 12. Commit discipline

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

## 13. Final verdict

- `HIGH_FINDINGS=0`, `MEDIUM_FINDINGS=0` (MEDIUM-01 fixed).
- Exact citation shapes are now enforced by `Counter` equality — a role
  absent from a topic's configured shape is rejected outright if any
  citation carries it, not merely un-checked.
- Every one of the required rejection scenarios (helmet + extra signal,
  helmet + extra points, red-light missing role, red-light extra primary,
  red-light extra unrelated role/location, unknown role) is proven
  rejected by a dedicated test.
- The three enabled rules, their selectors, and their rendered response
  shapes (3/3/1 sources) are byte-for-byte unchanged from Round 1.
- All regression suites pass, including the platform evaluation suite
  (214 tests) now correctly and separately labeled from the 4 traffic-
  related backend test files (146 tests).
- MODE_2D remains completely frozen.

```
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_2_READY_FOR_REVIEW
```
