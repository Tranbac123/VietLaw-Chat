# VietLaw Public Beta V0 — Independent Implementation Verification

INDEPENDENT_REVIEWER=CODEX

VERDICT=VIETLAW_PUBLIC_BETA_V0_IMPLEMENTATION_VERIFICATION_BLOCKED

## Preconditions and scope

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4

BRANCH=feature/conversational-rental-deposit-demo-v2

INDEX_EMPTY=yes

GIT_OPERATION_IN_PROGRESS=no

TASK_SCOPE_MATCH=yes

The worktree is the requested repository and the index was empty. Three modified
pre-existing reports (MODE_2B, official-source migration, and Phase C) were
preserved and are administrative-only. The task-owned tracked changes are the
declared backend wiring/contracts, frontend trust presentation, and one additive
SourcePanel test; task-owned untracked paths are the fallback modules, ten backend
tests, traffic data, two frontend tests/components, the evaluation runner, and the
two implementation reports. No task-owned dependency, deployment/configuration,
`.env`, legal-snippet, or secret-bearing file was found.

DECLARED_FILES_MATCH_ACTUAL=yes

UNDECLARED_IMPLEMENTATION_FILES=0

UNRELATED_SCOPE_CHANGES=0

DEPENDENCIES_ADDED=0

SECRETS_FOUND=0

`git diff --check` passed. Targeted secret scanning found only the existing
`api_key` variable and literal `"test-key"` test fixtures, not credentials.

## Frozen MODE_2D boundary

MODE_2D_PRESERVED=yes

MODE_2E_REINTRODUCED=no

EXISTING_DEPOSIT_FLOW_PRESERVED=yes

ARTICLE_328_ONLY_FOR_DEPOSIT=yes

RESOLVER_ALWAYS_RETURNS_NONE=yes

PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0

The seven specified MODE_2D files are byte-identical to HEAD. Inspection of the
complete production path confirms `resolve_deposit_applicable_clause()` remains
unconditionally `None`; new traffic and official-search `SourceObject`s explicitly
use `applicable_clause=None`.

## Route, safety, and traffic findings

ROUTE_ORDER_CORRECT=no

SAFETY_PRECEDENCE_PRESERVED=yes

NONLEGAL_FALLBACK_BLOCKED=no

The structural order is correct for ordinary turns: baseline safety, Fast Demo
social/capability/deposit routes, then fallback only for a non-unsafe Fast Demo
scope response. FAST DEMO disabled leaves the fallback unreachable; disabling the
traffic flag disables the entire new vertical; official search is off by default
and no service is instantiated.

The required social, deposit, unsafe, bribery, unauthorized-government-access,
and non-legal probes did not invoke the fallback. Their fake LLM/search activity
was zero except for the one deliberately supplied fake deposit plan. No live
provider or web request was used.

MEDIUM M-01 — `traffic_classifier.classify()` treats hypothetical/educational
and third-party statements as the current user's admitted facts. For example,
`Nếu một người vượt đèn đỏ khi đi xe máy thì bị phạt sao?` persisted
`vehicle_type=motorcycle` and returned a curated answer; `Bạn tôi dùng điện thoại
khi chạy xe máy.` likewise persisted a motorcycle/phone-use fact and returned a
curated answer. This contradicts the required self-attribution contract. The
current unit tests explicitly assert this incorrect behavior.

MEDIUM M-02 — a pending traffic clarification traps a later unrelated turn. After
`Tôi vượt đèn đỏ thì bị phạt bao nhiêu?`, the unrelated `Hôm nay thời tiết thế
nào?` returned the same vehicle clarification with `curated_verified` rather
than deferring to the normal non-legal scope route. This violates both the
non-legal gate and the requirement that pending clarification not stick to an
unrelated turn.

TRAFFIC_TOPICS_PRESENT=yes

TRAFFIC_STRUCTURE_VALID=yes

TRAFFIC_LEGAL_ACCURACY_CERTIFIED=no

TRAFFIC_CLARIFICATION_BOUNDED=no

TRAFFIC_ATTRIBUTION_FAILS_CLOSED=no

The parsed pack contains 11 rules covering all eight declared topics. Every URL
passes the configured exact-host HTTPS allowlist; all document numbers are
`168/2024/NĐ-CP`; article/clause fields are null; and there are no duplicate
`(topic_id, vehicle_type)` keys. Vehicle-specific lookup itself fails closed.
This review does not certify the traffic penalties or the report's claimed
research-time verification.

## Official source, general guidance, trust, and state

LIVE_SEARCH_PROVIDER_WIRED=no

OFFICIAL_SEARCH_DEPLOYABLE_AS_IS=no

ALLOWLIST_ENFORCED=yes

EVIDENCE_GATE_FAILS_CLOSED=yes

GENERAL_GUIDANCE_FAILS_CLOSED=yes

The source-search feature is default-off and dependencies wires no concrete
provider. The implementation enforces HTTPS, exact allowlisted hostname, no
credentials/explicit port, literal private/loopback/link-local rejection,
redirect validation, 500,000-byte cap, eight-second timeout, five candidates,
and deterministic evidence checks. Insufficient/conflicting/unavailable results
and provider failures fall back to deterministic general guidance. Search cannot
currently produce a deployed sourced answer because no provider/page finder is
wired and the HTTP candidate builder does not extract document identity.

MEDIUM M-03 — landing-page copy says VietLaw Beta “có thể tra cứu nguồn pháp luật
chính thức cho các câu hỏi khác,” but the implementation cannot perform such a
search in deployment. This conflicts with the otherwise accurate implementation
report limitation and materially overstates user-visible capability.

MEDIUM M-04 — `build_search_query()` redacts phone, 9/12-digit ID, and account
number patterns, but retains names and addresses verbatim. A probe retained
`Nguyễn Văn A` and `12 Nguyễn Huệ` while redacting the phone/CCCD. No provider is
wired or was called, so no sensitive value was transmitted in this review;
however this contradicts the report/contracts' claim that names are excluded and
does not meet the future-provider query-minimization contract.

TRUST_LEVEL_MAPPING_CORRECT=yes

STATE_ISOLATION_PRESERVED=yes

SENSITIVE_QUERY_DATA_REDACTED=no

The backend label map exactly matches the three required Vietnamese strings.
The frontend fields are optional/backward compatible; the badge states are
visually distinct; general guidance renders its warning and no empty citation
panel; official-source metadata is only rendered for `retrieved_at` sources.
Deposit responses do not receive fallback trust fields. The dedicated state table
and chat-keyed CAS preserve cross-chat separation in the integration test, and
retrieved evidence is separate from traffic facts. The new store lacks dedicated
CAS regression coverage, but code follows the established store convention.

## Test-quality and report audit

FOCUSED_ARTICLE_CITATION_TESTS=256 passed

NEW_BACKEND_TESTS=144 passed

BACKEND_LITE_TESTS=1315 passed

EVALUATION_TESTS=214 passed

LEGAL_BETA_EVALUATION_TURNS=22 passed

FRONTEND_TESTS=168 passed

TYPECHECK=passed

BUILD=passed

COMPILEALL=passed

GIT_DIFF_CHECK=passed

SECRET_SCAN=passed_no_credentials

The new-test arithmetic is 10 files, not the report's claimed 11:

- traffic classifier 24; source pack 8; legal intent 13; trust 8;
  allowlist 25; source validator 11; HTTP search 17; fallback orchestrator 16;
  fallback safety 11; integration 11 — total 144.

All new tests call production code; the integration test exercises actual
runtime wiring; fakes traverse the real evidence gate; and no skips/xfails were
found. The one existing modified test (`sourcePanel.test.tsx`) is additive (46
assertion lines added, none removed). However, test quality is insufficient for
the two M findings: the classifier test deliberately accepts hypothetical and
third-party attribution, and no test proves that a pending vehicle clarification
releases an unrelated later turn. There is also no dedicated test for the traffic
flag-off behavior or the new state-store CAS.

REPORT_MATERIAL_CLAIMS_ACCURATE=no

Verified report claims include the unchanged MODE_2D boundary, exact regression
totals, default-off/unwired official search, no rate limiter/dedicated events,
and the article/clause limitation. Contradicted claims include “no HIGH or
MEDIUM finding remains,” the self-attribution/one-clarification description,
and the assertion that search queries never carry names. The report also says 11
new backend test files and 12 traffic rules; actual counts are 10 and 11.
`TRAFFIC_RULES_OFFICIALLY_VERIFIED=yes` is not independently certifiable in
this implementation review and must remain subject to the separate legal review.
The architecture report's traffic-flag table conflicts with the implementation:
actual flag-off disables the entire vertical, not only the traffic tier.

## Readiness and prerequisites

HIGH_FINDINGS=0

MEDIUM_FINDINGS=4

LOW_FINDINGS=3

READY_FOR_TARGETED_LEGAL_REVIEW=no

READY_FOR_LIMITED_DEMO_DEPLOYMENT=no

READY_FOR_GENERAL_PUBLIC_BETA=no

Before deployment, correct M-01 through M-04 and re-run adversarial/runtime
coverage. Then complete: traffic legal-accuracy review; rate limiting; hosting
configuration; explicit environment-flag configuration; API-key protection;
anonymous-browser smoke testing; and, if official search is advertised, a real
provider/page-finder with document-identity extraction and DNS/connected-address
validation.

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
