# VietLaw Public Beta V0 — Correction Round 1 Independent Verification

INDEPENDENT_REVIEWER=CODEX

VERDICT=VIETLAW_PUBLIC_BETA_V0_CORRECTION_ROUND_1_VERIFICATION_BLOCKED

## Preconditions and scope

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4

BRANCH=feature/conversational-rental-deposit-demo-v2

INDEX_EMPTY=yes

GIT_OPERATION_IN_PROGRESS=no

TASK_SCOPE_MATCH=yes

UNDECLARED_IMPLEMENTATION_FILES=0

UNRELATED_SCOPE_CHANGES=0

The index is empty and no Git operation is in progress. Correction Round 1
changes are limited to declared Public Beta V0 contracts/services/tests,
evaluation data, landing copy/tests, and reports. Pre-existing MODE_2B,
official-source-migration, and Phase-C report modifications remain separate.
No dependency, deployment/configuration, `.env`, or frozen MODE_2D
implementation path changed.

## Frozen MODE_2D

MODE_2D_PRESERVED=yes

MODE_2E_REINTRODUCED=no

ARTICLE_328_ONLY_FOR_DEPOSIT=yes

RESOLVER_ALWAYS_RETURNS_NONE=yes

PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0

All seven specified MODE_2D files are byte-identical to HEAD. The focused
article-citation suite passed with 256 tests.

## M-01 attribution

M01_CLOSED=yes

THIRD_PARTY_FACTS_PERSISTED=0

HYPOTHETICAL_FACTS_PERSISTED=0

EDUCATIONAL_FACTS_PERSISTED=0

NEGATED_FACTS_PERSISTED=0

`TrafficDetection.attribution` is the required bounded union. Only `self`
flows through persistent fact merging and pending clarification. Direct store
inspection for all eight specified non-self probes found default traffic facts
and no pending marker; self-attributed required probes classify and persist
their relevant facts. Impersonal answers are transient and non-accusatory.

## M-02 pending-clarification lifecycle

M02_CLOSED=no

UNRELATED_TURN_REPEATS_TRAFFIC_CLARIFICATION=no

SOCIAL_INTERVENING_TURN_CAUSES_LATER_STICKINESS=no

IDENTITY_INTERVENING_TURN_CAUSES_LATER_STICKINESS=no

DEPOSIT_INTERVENING_TURN_CAUSES_LATER_STICKINESS=no

The ordinary weather/social/identity route probes no longer repeat the traffic
question, and a first-person vehicle answer (`Tôi đi xe máy.`) resolves the
published happy path. The new release is durably committed when an unrelated
non-legal turn reaches fallback.

MEDIUM M-02-R — the field validator accepts **any digit** as an answer for
`speed_excess_kmh`, `alcohol_level`, and `passenger_count`. After a pending
speeding clarification, `Hôm nay 30 độ C.` is therefore treated as a
clarification attempt. Because it has no self attribution, the impersonal path
returns general guidance but retains `traffic_topic_id=traffic_speeding` and
`traffic_pending_field=speed_excess_kmh` on disk. A subsequent unrelated labor
question containing a number (`Tôi nhận lương tháng 7 thì công ty có trả đúng
hạn không?`) is self-attributed by the broad `tôi` rule, resumes the stale
speeding topic, and returns `curated_verified` traffic content. This is durable
cross-topic contamination.

The same state-retention problem is independently reproducible for a short
non-first-person vehicle answer (`Xe máy.`), `10 km/h.`, `0.2 mg/l.`,
`3 người.`, and `Thay lốp.`; they either preserve the pending marker or do not
commit their detected value. Thus the claimed six-field valid-answer contract
is not established. The correction tests cover the first-person happy path and
digit-free unrelated turn but miss this boundary.

## M-03 landing capability claim

M03_CLOSED=yes

UNWIRED_SEARCH_ADVERTISED=no

CONTRADICTORY_FRONTEND_CLAIMS=0

Visible landing copy now describes deposit/traffic support, general guidance
for other legal questions, and says official-source search is still being
completed. Repository-wide frontend matches of the former search wording are
only explanatory comments or a negative test assertion, not runtime-visible
claims.

## M-04 query privacy

M04_CLOSED=yes

NAMES_IN_REQUIRED_SEARCH_PROBES=0

ADDRESSES_IN_REQUIRED_SEARCH_PROBES=0

CONTACT_VALUES_IN_REQUIRED_SEARCH_PROBES=0

EMPTY_UNSAFE_QUERY_SEARCH_CALLS=0

CONVERSATION_HISTORY_SENT_TO_SEARCH=no

RAW_PRIVATE_DOCUMENT_SENT_TO_SEARCH=no

`build_search_query()` uses fixed structured templates for recognized legal
topics and otherwise removes the required name/address/contact values. All five
required probes were inspected directly: no required value survived; an
identifier-only self introduction returns `None`. `_handle_official_search()`
turns `None` into general guidance before any service call. The orchestrator
receives only the current question, never chat history or uploaded-document
content. No real search provider is wired or was invoked.

## Tests and reports

NEW_BACKEND_TEST_FILES=10

NEW_BACKEND_TESTS=208 passed

FOCUSED_ARTICLE_CITATION_TESTS=256 passed

BACKEND_LITE_TESTS=1379 passed

EVALUATION_TESTS=214 passed

LEGAL_BETA_EVALUATION_TURNS=27 passed

FRONTEND_TESTS=171 passed

TYPECHECK=passed

BUILD=passed

COMPILEALL=passed

GIT_DIFF_CHECK=passed

SECRET_SCAN=passed_no_credentials

The 208-test arithmetic is: classifier 66, source pack 8, legal intent 13,
trust 8, allowlist 25, source validator 11, HTTP search 17, fallback
orchestrator 34, fallback safety 11, integration 15. No skipped or xfailed
tests were found. Backend Lite was independently confirmed as 981 unit + 303
integration + 95 root tests. The 27-turn beta runner passed its four published
hard constraints, but none exercise the numeric stale-pending boundary above.

REPORT_CORRECTION_NOTICE_PRESENT=yes

REPORT_CURRENT_CLAIMS_ACCURATE=no

HISTORICAL_FALSE_CLAIMS_CLEARLY_SUPERSEDED=yes

The correction notice accurately supersedes the historical ten/eleven test-file
and eleven/twelve rule-count mistakes, the original privacy claim, and the
original zero-MEDIUM verdict. The current Correction Round 1 claim that M-02 is
closed and that all six field categories have dedicated adequate coverage is
contradicted by the independent numeric/short-answer probes above.

## Severity and readiness

HIGH_FINDINGS=0

MEDIUM_FINDINGS=2

LOW_FINDINGS=1

MEDIUM M-02-R is the functional sticky-state defect. The correction report's
material assertion that M-02 is closed is a second MEDIUM report overstatement.
The missing exact boundary tests are a LOW finding in addition to the functional
failure.

READY_FOR_TARGETED_TRAFFIC_LEGAL_REVIEW=no

READY_FOR_LIMITED_DEMO_DEPLOYMENT=no

READY_FOR_GENERAL_PUBLIC_BETA=no

Correction is needed before targeted legal review because a cross-topic answer
can be routed to unrelated curated traffic content. Limited deployment remains
blocked additionally on the stated traffic legal-accuracy and rate-limiting
prerequisites; general public beta remains unauthorized.

## Review restrictions

TRACKED_FILES_MODIFIED_BY_REVIEWER=0

TEST_FILES_MODIFIED_BY_REVIEWER=0

EXISTING_REPORTS_MODIFIED_BY_REVIEWER=0

COMMITS_CREATED=0

STAGED_FILES=0

PUSH_PERFORMED=no

DEPLOY_PERFORMED=no

LIVE_PROVIDER_CALLS=0

LIVE_WEB_SEARCH_CALLS=0
