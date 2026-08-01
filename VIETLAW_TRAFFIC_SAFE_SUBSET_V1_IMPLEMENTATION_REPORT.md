# VIETLAW TRAFFIC SAFE SUBSET V1 — Implementation Report

> ## CORRECTION NOTICE (Legal Correction Round 1 — current status)
>
> An independent targeted legal re-review
> (`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_V1.md`, verdict
> `VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_BLOCKED`) found this report's
> "4 verified rules, `CURATED_VERIFIED` only on selector `MATCH`" claims
> **partially inaccurate**:
>
> - **Rule D (motorcycle hand-held phone use) was NOT actually safe.**
>   HIGH-01: its selector's required facts (`phone_handheld=yes`,
>   `vehicle_in_operation=yes`) proved only that the rider was holding the
>   device while the vehicle moved -- not the separate legal element of
>   Điều 7 khoản 4 điểm đ, "sử dụng điện thoại" (actually USING it). An
>   adversarial probe explicitly denying use still produced a `MATCH`. Rule
>   D is now `disabled_pending_legal_correction`; only Rules A-C (motorcycle/
>   car red light, motorcycle driver no-helmet) remain enabled.
> - **The "`CURATED_VERIFIED` only emitted on selector MATCH`" claim below
>   was false as stated.** MEDIUM-02: `_clarification_response()` (the
>   function that ASKS a clarifying question) set
>   `trust_level=curated_verified` even when the selector outcome was
>   `MISSING_FACT`, not `MATCH`. A clarification is a question, not a legal
>   conclusion -- it now carries `trust_level=None`.
> - **The one-citation-per-rule model was insufficient (MEDIUM-01).** The
>   licence-point-deduction basis and, for red-light rules, Luật
>   36/2024/QH15 Điều 11's signal-priority rule were prose-only inside
>   `source_excerpt`, with no separate official URL a user could open. Every
>   enabled rule now carries a structured `legal_citations` list (§3 of the
>   original body below describes only the OLD single-citation shape); see
>   `VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_REPORT.md` for
>   the full current record.
>
> This body text is left exactly as originally written (audit history, not
> erased or rewritten) with the corrections above layered on top. Treat any
> claim below of "4 enabled rules", "Rule D", or "`CURATED_VERIFIED` only on
> MATCH" as describing the PRE-Round-1 state, not current behavior.

`IMPLEMENTER=CLAUDE_CODE_SONNET`. Repository: this working tree. Branch:
`feature/conversational-rental-deposit-demo-v2`. Starting and ending
`HEAD`: `5079454d90730ac9f7fb23d18fe6b8a5578229a4` (unchanged — zero commits
were created; see §12).

## 1. Why this round exists

An independent legal-accuracy review
(`VIETLAW_PUBLIC_BETA_V0_TRAFFIC_LEGAL_ACCURACY_REVIEW_V1.md`) found the
entire original 8-topic, 11-row curated traffic pack legally unsafe to
serve as-is:

```
VIETLAW_TRAFFIC_LEGAL_ACCURACY_REVIEW_BLOCKED
HIGH_FINDINGS=10
MEDIUM_FINDINGS=1
VERIFIED_RULES=0
RULES_TO_DISABLE=11
RUNTIME_RULE_SELECTION_CORRECT=no
```

The objective of this round was narrow and defensive: disable every unsafe
rule, rebuild only a small primary-source-verified subset, fail closed for
everything outside that subset, and preserve MODE_2D and the Correction
Round 1/2 fixes untouched. This report documents that work.

## 2. Rule lifecycle: disabling the unsafe pack

`data/traffic_rules.json` (`schema_version: 2`,
`pack_name: "curated_traffic_safe_subset_v1"`) now carries a `status`
field per row: `enabled` or `disabled_pending_legal_correction`.

- `OLD_TRAFFIC_RULES_DISABLED=11` — every original row (`traffic_red_light`
  ×2, `traffic_no_helmet` ×1, `traffic_alcohol` ×2, `traffic_speeding` ×1,
  `traffic_driver_license` ×2, `traffic_phone_use` ×1,
  `traffic_passenger_limit` ×1, `traffic_vehicle_modification` ×1) is now
  `disabled_pending_legal_correction`, each carrying a `disabled_reason`
  string citing the specific HIGH/MEDIUM finding from the legal review.
  Their original `source_excerpt` text is preserved verbatim for audit
  purposes; every other new required field is null/empty.
- `OLD_ENABLED_TRAFFIC_RULES=0` — confirmed by
  `test_traffic_source_pack.py::test_curated_pack_loads_from_the_real_data_file`.
- `DISABLED_RULES_RETURNED_BY_LOOKUP=0` — `TrafficSourcePack.__init__`
  indexes only `status == ENABLED` rows into its internal `_by_key`/
  `_enabled_rules` collections at construction time. `find()` and
  `select_rule()` read only from those collections — a disabled row is
  structurally unreachable, not merely filtered at call time. This is the
  single strongest guarantee available against `DISABLED_RULES_WITH_CURATED_VERIFIED`.

## 3. Safe Subset V1: exactly four enabled rules

`NEW_ENABLED_SAFE_RULES=4`

`ENABLED_RULE_IDS`:
- `traffic_red_light__motorcycle__safe_v1` (Rule A)
- `traffic_red_light__car__safe_v1` (Rule B)
- `traffic_no_helmet__motorcycle__driver_safe_v1` (Rule C)
- `traffic_phone_use__motorcycle__handheld_safe_v1` (Rule D)

`ARTICLE_CLAUSE_POINT_MAPPING`:

| Rule | Topic | Vehicle | Article | Clause | Point | Penalty | Points | Official URL |
|---|---|---|---|---|---|---|---|---|
| A | red_light | motorcycle | 7 | 7 | c | 4,000,000–6,000,000đ | 4 | vbpl.vn ItemID=173920 |
| — (points basis) | — | — | 7 | 13 | b | — | — | (same document, in `source_excerpt`) |
| B | red_light | car | 6 | 9 | b | 18,000,000–20,000,000đ | 4 | vbpl.vn ItemID=173920 |
| — (points basis) | — | — | 6 | 16 | b | — | — | (same document, in `source_excerpt`) |
| C | no_helmet | motorcycle (driver only) | 7 | 2 | h | 400,000–600,000đ | — | vbpl.vn ItemID=173920 |
| D | phone_use | motorcycle (hand-held) | 7 | 4 | đ | 800,000–1,000,000đ | 4 | vbpl.vn ItemID=173920 |
| — (points basis) | — | — | 7 | 13 | b | — | — | (same document, in `source_excerpt`) |

`PRIMARY_SOURCE_URLS`:
- `https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=173920&Keyword=` (Nghị
  định 168/2024/NĐ-CP full text) — used by all 4 enabled rules.
- `https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=170620` (Luật Trật tự,
  an toàn giao thông đường bộ 36/2024/QH15, signal-priority Điều 11) —
  cited in the legal review; embedded as prose in Rules A/B's
  `source_excerpt`, not a second `official_url` field (the schema carries
  one primary URL per rule).

`ENABLED_RULES_WITH_PRIMARY_URL=4`, `ENABLED_RULES_WITH_ARTICLE_CLAUSE_POINT=4`
(every enabled rule has non-null `article_number`, `clause_number`,
`point_number` — enforced at load time, see §4).

Per-rule verbatim `answer_template` (the text actually rendered):

- **A**: "Nếu người điều khiển xe máy không chấp hành đèn đỏ, không thuộc
  trường hợp đang thực hiện hiệu lệnh của người điều khiển giao thông và
  không xét nhánh gây tai nạn, mức phạt là 4.000.000 - 6.000.000 đồng và bị
  trừ 4 điểm giấy phép lái xe."
- **B**: "Nếu người điều khiển ô tô không chấp hành đèn đỏ, không thuộc
  trường hợp thực hiện hiệu lệnh của người điều khiển giao thông và không
  xét nhánh gây tai nạn, mức phạt là 18.000.000 - 20.000.000 đồng và bị trừ
  4 điểm giấy phép lái xe."
- **C**: "Người điều khiển xe mô tô, xe gắn máy không đội mũ bảo hiểm hoặc
  đội mũ bảo hiểm nhưng không cài quai đúng quy cách bị phạt 400.000 -
  600.000 đồng."
- **D**: "Người điều khiển xe mô tô, xe gắn máy dùng tay cầm và sử dụng
  điện thoại hoặc thiết bị điện tử khác khi đang điều khiển xe bị phạt
  800.000 - 1.000.000 đồng và bị trừ 4 điểm giấy phép lái xe."

`DUPLICATE_RULE_IDS_ACCEPTED=0`, `AMBIGUOUS_ENABLED_SELECTORS=0` — both
enforced at `TrafficSourcePack.from_file` load time (duplicate `rule_id`
across ALL rows, and duplicate enabled `(topic_id, vehicle_type)` key,
both raise `TrafficSourcePackError`); proven by
`test_duplicate_rule_id_is_rejected` and
`test_duplicate_enabled_selector_is_rejected`.

## 4. New structured facts and the selector

`backend_lite/app/contracts/traffic.py` gained 7 new `TrafficFacts` fields,
every one defaulting to `"unknown"` (never inferred from silence):
`signal_type`, `traffic_controller_override`, `accident_caused`,
`helmet_subject`, `helmet_status`, `phone_handheld`, `vehicle_in_operation`
— plus `RuleStatus` and `RuleSelectionOutcome` enums.

`TrafficSourcePack.select_rule(topic_id, facts) -> TrafficRuleSelection`
(`backend_lite/app/services/traffic_source_pack.py`) is the single place
rule selection happens. Each `TrafficRuleRecord` carries `required_facts`
(a list of field names that must be non-`"unknown"` to match) and
`excluded_facts` (a list of `[field_name, disqualifying_value]` pairs —
if the CURRENT fact equals that value, the rule is excluded). This one
mechanism implements both "must ask about this field" and "this field has
a known, disqualifying value" without a third "required value" concept.

`SELECTOR_OUTCOMES_IMPLEMENTED`:
- `MATCH` → `_build_curated_traffic_response` (only path to `CURATED_VERIFIED`)
- `MISSING_FACT` → ask exactly one clarification for `selection.missing_field`
  (task §4: "at most one clarification at a time" — enforced per-turn;
  fields are asked in sequence across turns for multi-field rules, e.g.
  Rule D's `phone_handheld` then `vehicle_in_operation`)
- `NO_SAFE_RULE` → fall through to the next tier (official search if
  enabled, else general guidance); never asked about, never curated
- `AMBIGUOUS` → fall through to general guidance + `logging.warning` (task
  §6); structurally unreachable via the real pack (see §6's constraint)

Two fields (`traffic_controller_override`, `accident_caused`) are
deliberately never in any rule's `required_facts` — only in
`excluded_facts` — implementing task §3/§4's `no_or_not_reported`
semantics: `"unknown"` is always safe to proceed on, only an explicit
`"yes"` excludes. This is exactly why the `answer_template` text uses
conditional "Nếu... không thuộc trường hợp..." wording.

`backend_lite/app/services/traffic_classifier.py` gained bounded,
deterministic Vietnamese cue-list detectors for all 7 new fields (same
normalize-then-substring-match discipline as the rest of the module, never
a general NLP parser), plus 5 new field-specific clarification-answer
parsers wired into the existing `parse_clarification_answer` dispatcher.
Two correctness fixes were required during self-testing before this design
was sound:

1. **Negation-blindness in `accident_caused`/`traffic_controller_override`**:
   the first draft used a bare substring check, so "...không gây tai nạn"
   (did NOT cause an accident — a REQUIRED positive-test probe) was
   misread as `accident_caused="yes"`. Fixed by routing both detectors
   through the same clause-scoped `_is_negated_at` negation guard the
   topic-cue detector already used (`_any_cue_unnegated`).
2. **Cross-topic fact leakage**: the first draft ran all 7 new detectors
   unconditionally on every message, so e.g. "Tôi lái ô tô vượt đèn đỏ."
   (a red-light message) would incidentally set `helmet_subject="driver"`
   via the `_HELMET_DRIVER_CUES` "tôi lái" cue. Fixed by scoping each
   group of detectors to only run when the matching topic was actually
   detected for that message.

Two topic-cue coverage gaps were also found and fixed during testing (both
required positive/negative probes from task §9):
`"khong cai quai"` added to the `no_helmet` topic cues (a required positive
probe never says "không đội mũ", only "không cài quai"), and a bare
`"vuot den"` cue plus `mg l`/`khi tho` (alcohol) and a digit-passenger-count
regex fallback (passenger_limit) added so the disabled-topic probes reach
the selector's `NO_SAFE_RULE` path rather than falling through as
unrecognized non-traffic text.

## 5. Trust-level gating (task §7)

`_build_curated_traffic_response` (in
`backend_lite/app/services/legal_fallback_orchestrator.py`) is reachable
ONLY from `select_rule`'s `MATCH` branch — never from `MISSING_FACT`,
`NO_SAFE_RULE`, or `AMBIGUOUS`. Since `select_rule` only ever matches an
`ENABLED` rule (structurally, per §2), and `TrafficSourcePack.from_file`
rejects any `ENABLED` row missing `official_url`/`article_number`/
`clause_number`/`point_number` at LOAD time (defense-in-depth, not just a
runtime hope), every `CURATED_VERIFIED` response is guaranteed to carry a
primary source URL and full citation:

- `DISABLED_RULES_WITH_CURATED_VERIFIED=0`
- `INCOMPLETE_RULES_WITH_CURATED_VERIFIED=0`
- `AMBIGUOUS_MATCHES_WITH_CURATED_VERIFIED=0`

`point_number` (e.g. "c", "b", "h", "đ") has no dedicated field on the wire
`SourceObject` schema (`backend_lite/app/schemas/content.py` is outside
this task's permitted-files list and was NOT modified — verified: `git
diff --stat -- backend_lite/app/schemas/content.py` shows zero change from
this session). It is surfaced as free text in the rendered `summary` and in
`sources[0].snippet`/`relevance_note` (via `rule.source_excerpt`, which
also carries the rule's SECOND citation — e.g. Rule A's separate
licence-point-deduction basis, Điều 7 khoản 13 điểm b) — never dropped,
never a new wire field.

## 6. Explicitly unsupported topics (task §8)

`ALCOHOL_ENABLED=no`, `SPEEDING_ENABLED=no`, `DRIVER_LICENSE_ENABLED=no`,
`PASSENGER_LIMIT_ENABLED=no`, `VEHICLE_MODIFICATION_ENABLED=no`.

`DISABLED_TOPIC_IDS`: `traffic_alcohol`, `traffic_speeding`,
`traffic_driver_license`, `traffic_passenger_limit`,
`traffic_vehicle_modification`.

Unsupported SUBCASES of otherwise-enabled topics are also confirmed never
curated (via `NO_SAFE_RULE`'s `excluded_facts` match, or a genuine
`MISSING_FACT`/no-matching-vehicle fallthrough for the impersonal path):
passenger (not driver) helmet, red-light accident branch, yellow-light
signal, hands-free/mounted phone use, vehicle-stopped phone use, and car
phone use (no enabled car+phone_use rule exists).

## 7. Required test probes (task §9/§10) — all verified

`backend_lite/tests/unit/test_traffic_safe_subset_v1.py` (new, 35 tests)
exercises every verbatim probe message from task §9/§10 end-to-end through
`LegalFallbackOrchestrator`, not just `classify()`/`select_rule()` in
isolation:

- Rule A/B/C/D positive probes: exact penalty range, points, and
  `Điều X khoản Y điểm Z` citation text all asserted present in the
  rendered response.
- Rule A/B/C/D negative/ambiguous probes (controller-override, yellow
  light, accident branch, unclear signal, passenger helmet, correctly-worn
  helmet, hands-free phone, mounted phone, stopped vehicle, car phone use):
  never `curated_verified` with non-empty sources.
- Disabled-topic exact probes (`0.2 mg/l khí thở`, `vượt tốc độ 10 km/h`,
  `quên mang bằng lái`, `chở 3 người`, `thay lốp nhỏ`): all confirmed
  `trust_level=general_guidance`, `clarifying_questions=[]`, `sources=[]`,
  no `"Điều"`/`"đồng"` amount substring in the summary.
- Trust-gating tests: a `MATCH` always carries a `vbpl.vn` URL and
  non-null `article_number`; a `NO_SAFE_RULE` outcome never carries sources.
- Adversarial/conversation tests (task §10): a fresh topic mentioned while
  a DIFFERENT topic's clarification is pending switches immediately and
  resolves on its own terms (new test — not previously covered); third-
  party/hypothetical/negated attribution facts never persist.

`test_traffic_source_pack.py` (rewritten, 30 tests) exercises
`select_rule` directly for every required selector-outcome shape: exact
match, missing fact (`vehicle_type` and a topic-specific field), disabled
topic, no rule for a topic id at all, wrong vehicle type, every individual
excluding fact for Rules A/C/D, and an `AMBIGUOUS` case (constructed
directly, bypassing `from_file`'s load-time guard, since the real pack
cannot produce it) — plus load-time integrity checks: duplicate rule_id,
duplicate enabled selector, missing official_url, missing each of
article/clause/point (rejected only when the row is `enabled`; a disabled
row with incomplete metadata is accepted, since it can never be selected).

## 8. Regression (task §13)

All commands below were run in this working tree; no live providers or web
search were invoked at any point.

| Check | Result |
|---|---|
| Focused MODE_2D suite (`-k "fast_demo or mode_2d or MODE_2D"`) | 259 passed |
| `resolve_deposit_applicable_clause` (3 representative fact states) | `None`, `None`, `None` |
| Frozen MODE_2D files (`git diff --stat` on all 7) | zero changes |
| All traffic classifier / source-pack / orchestrator / integration tests | included below |
| Complete `backend_lite` suite | **1515 passed** |
| `evaluation/legal_beta_v0` runner | 49 turns, **0 findings**, all 6 hard constraints `0` |
| Attribution / M-01 / M-02 / query-privacy / landing-copy subset (`-k`) | 19 passed |
| Frontend tests (`npm run test -- --run`) | 171 passed (11 files) |
| Frontend typecheck (`tsc --noEmit`) | clean |
| Frontend build (`tsc && vite build`) | succeeded |
| `python3 -m compileall backend_lite evaluation data` | exit 0 |
| `git diff --check` | exit 0, no whitespace errors |
| Secret scan (api_key/secret/password/token/BEGIN/sk- pattern grep over changed files) | no findings (only benign matches: test fixture `api_key="test-key"`, the word "tokens" in a comment) |

`evaluation/legal_beta_v0` hard constraints, this run:

```
UNSUPPORTED_CITATION_RATE=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
MODE_2D_CLAUSE_2_OUTPUTS=0
DISABLED_RULE_CURATED_ANSWERS=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0
```

(`cases.py` was rebuilt for the new pack: the 4 Safe Subset V1 rules with
citation checks, the 5 disabled topics plus 4 unsupported subcases, and the
`clarification_state_machine` category's Cases B/D/E/F/G rebuilt against
Rule D's two sequentially-askable fields, since their original fields
(speed/alcohol/passenger/modification) now live on disabled topics. `run.py`
gained the `DISABLED_RULE_CURATED_ANSWERS` counter and a documented, fixed
`AMBIGUOUS_RULE_CURATED_ANSWERS=0` — proven structurally unreachable by the
real pack, verified directly against `select_rule` in
`test_traffic_source_pack.py`.)

### M-01 through M-04 status (Correction Rounds 1-2, unrelated code defects in the same vertical)

- `M01_REMAINED_CLOSED=yes` — third-party/hypothetical/educational/negated
  attribution still gates persistence; re-verified via
  `test_third_party_message_answers_but_never_persists_facts`,
  `test_hypothetical_message_answers_but_never_persists_facts`,
  `test_negated_message_never_persists_and_never_answers_as_curated`, and
  new adversarial tests in `test_traffic_safe_subset_v1.py`.
- `M02_REMAINED_CLOSED=yes` (superseded by M-02-R, itself still closed) —
  an unrelated turn still releases a pending clarification; re-verified via
  `test_unrelated_turn_releases_pending_vehicle_clarification` and the new
  `test_fresh_traffic_topic_while_a_different_topic_is_pending_switches_immediately`.
- `M03_REMAINED_CLOSED=yes` — landing-page copy still reads "đang trong quá
  trình hoàn thiện", never the overclaiming original text; confirmed via
  grep and the existing `landingChatState.test.tsx` (part of the 171
  passing frontend tests).
- `M04_REMAINED_CLOSED=yes` — `build_search_query` still minimizes
  names/addresses/contact values; all 8 redaction tests in
  `test_legal_fallback_orchestrator.py` pass unchanged.
- `M02R_REMAINED_CLOSED=yes` — the typed `RESOLVED`/`UNKNOWN_VALUE`/
  `UNRELATED` parser (extended this round with 5 new field parsers) still
  refuses to treat an unrelated numeric message as a valid answer; the
  `case_a_numeric_unrelated_no_contamination` shape is re-proven against
  Rule D's `vehicle_in_operation` field in both the orchestrator unit tests
  and the evaluation dataset.

### MODE_2D invariants

```
MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
ARTICLE_328_ONLY_FOR_DEPOSIT=yes
RESOLVER_ALWAYS_RETURNS_NONE=yes
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
```

## 9. Scope discipline

Files touched this round: `data/traffic_rules.json`,
`backend_lite/app/contracts/traffic.py`,
`backend_lite/app/services/traffic_classifier.py`,
`backend_lite/app/services/traffic_source_pack.py`,
`backend_lite/app/services/legal_fallback_orchestrator.py`,
`backend_lite/tests/unit/test_traffic_classifier.py`,
`backend_lite/tests/unit/test_traffic_source_pack.py`,
`backend_lite/tests/unit/test_legal_fallback_orchestrator.py` (rewritten
where it depended on now-disabled topics),
`backend_lite/tests/unit/test_traffic_safe_subset_v1.py` (new),
`backend_lite/tests/integration/test_public_beta_v0_legal_fallback_e2e.py`
(rewritten where it depended on now-disabled topics),
`evaluation/legal_beta_v0/cases.py`, `evaluation/legal_beta_v0/run.py`,
this report, and a correction notice added to
`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md` (history preserved, not
erased). `backend_lite/app/contracts/legal_fallback_state.py` needed no
change (its `TrafficFacts` field already carries safe defaults for the new
fields automatically).

Not touched: all 7 frozen MODE_2D files, `official_legal_search.py` /
`official_legal_domain_allowlist.py` (provider wiring), frontend deployment
configuration, rate limiting, Docker/Railway/Cloudflare files,
`schemas/content.py` (the wire `SourceObject` contract — confirmed via
`git diff --stat` showing zero change this session), and every unrelated
legal domain (labor, land, civil dispute).

## 10. Report corrections

A correction notice was added to the top of
`VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_REPORT.md` (above the existing
Correction Round 1/2 notices, which addressed unrelated code-correctness
defects in the same vertical) stating that the original 11-rule traffic
pack was found legally blocked and is now entirely disabled, and that only
the four Safe Subset V1 rules documented here may emit `CURATED_VERIFIED`.
No prior report text was erased.

## 11. Commit discipline

```
COMMITS_CREATED=0
STAGED_FILES=0
```

`git rev-parse HEAD` before and after this round:
`5079454d90730ac9f7fb23d18fe6b8a5578229a4` (unchanged). All work in this
round remains in the working tree, uncommitted and unstaged, per the
task's explicit instruction. No `git add`, `git commit`, `git push`, or
deploy command was run. No live legal-search provider or live web search
was called at any point — `FakeOfficialLegalSearchService` and
`FakeLLMClient` were the only providers used throughout.

## 12. Final verdict

All required conditions for readiness are met:

- All 11 original unsafe traffic rules are disabled
  (`disabled_pending_legal_correction`), structurally unreachable by any
  lookup or selector call.
- Exactly four safe rules are enabled, each independently re-verified
  against the primary source (Nghị định 168/2024/NĐ-CP, Luật 36/2024/QH15)
  and citing full article/clause/point metadata plus a `vbpl.vn` primary
  URL.
- Zero ambiguous curated answers (structurally unreachable; proven both
  by the load-time duplicate-selector guard and a direct `select_rule`
  unit test bypassing that guard).
- Zero disabled-rule curated answers (structurally unreachable; disabled
  rows are never indexed for lookup).
- MODE_2D remains completely frozen: zero diff on all 7 frozen files,
  `resolve_deposit_applicable_clause` still always returns `None`, zero
  production `applicable_clause == 2` paths.
- Zero newly identified HIGH or MEDIUM findings during this round's own
  self-testing (two correctness bugs — accident-negation blindness and
  cross-topic fact leakage — were found and fixed BEFORE being reported
  here, per the same "verify before claiming done" discipline established
  in prior correction rounds).

```
VIETLAW_TRAFFIC_SAFE_SUBSET_V1_READY_FOR_LEGAL_REVIEW
```
