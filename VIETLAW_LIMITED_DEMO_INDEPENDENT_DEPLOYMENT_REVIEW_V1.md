# VIETLAW LIMITED DEMO — Independent Deployment Review V1

```text
INDEPENDENT_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
VERDICT=VIETLAW_LIMITED_DEMO_INDEPENDENT_DEPLOYMENT_REVIEW_BLOCKED

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
GIT_OPERATION_IN_PROGRESS=no
TASK_SCOPE_MATCH=yes
UNDECLARED_IMPLEMENTATION_FILES=0
UNRELATED_SCOPE_CHANGES=0
MODE_2D_PRESERVED=yes

HIGH_FINDINGS=2
MEDIUM_FINDINGS=5
LOW_FINDINGS=3

DOCKER_BUILD=passed
CONTAINER_RUNS_AS_NON_ROOT=yes
PORT_ENV_SUPPORTED=yes
REQUIRED_RUNTIME_DATA_PRESENT=yes
SECRET_FILES_IN_IMAGE=0
DATABASE_FILES_IN_IMAGE=0
DOCKER_HISTORY_INSPECTION=clean

PRODUCTION_SQLITE_FAILS_CLOSED=no
PRODUCTION_CHAT_DB_PATH_REQUIRED=no
PRODUCTION_DB_PATH_MUST_BE_UNDER_DATA=no
EPHEMERAL_PRODUCTION_FALLBACK_POSSIBLE=yes
MISSING_VOLUME_REPORTS_HEALTHY=yes
UNWRITABLE_VOLUME_REPORTS_503=yes
NO_VOLUME_PRODUCTION_BEHAVIOR=healthy_ephemeral_failed

RAILWAY_CONFIG_SCHEMA_VALID=no
DOCKERFILE_PATH_CORRECT=yes
HEALTH_CHECK_PATH=/api/health
NUM_REPLICAS=1_declared_not_enforced
UNSUPPORTED_RAILWAY_FIELDS=1
RAILWAY_VOLUME_MANUAL_STEP_DOCUMENTED=yes

HEALTHY_STATUS_CODE=200
DEGRADED_STATUS_CODE=503
MISSING_TRAFFIC_PACK_STATUS_CODE=200
HEALTH_EXTERNAL_CALLS=0
HEALTH_SECRET_EXPOSURE=0

CORS_EXACT_ORIGIN=yes
WILDCARD_CORS_PRESENT=no
ORIGIN_SUFFIX_BYPASS=0
UNCONFIGURED_ORIGIN_AUTHORIZED=0

RATE_LIMITING_VERIFIED=no
RATE_LIMIT_PER_IP_CORRECT=no
RATE_LIMIT_PER_CONVERSATION_CORRECT=yes
REQUEST_LENGTH_LIMIT_CORRECT=yes
CONCURRENCY_LIMIT_CORRECT=yes
BOUNDED_MEMORY=yes
X_FORWARDED_FOR_SPOOF_BYPASS_POSSIBLE=yes
ONE_REPLICA_REQUIRED=yes
REQUEST_LENGTH_LIMIT=verified_413
CONCURRENCY_LIMIT=verified_429

CONTAINER_RESTART_PERSISTENCE=passed
CONTAINER_RECREATE_PERSISTENCE=passed
PERSISTENCE_RESTART_SMOKE=passed
PERSISTENCE_RECREATE_SMOKE=passed

CLOUDFLARE_ROOT_CORRECT=yes
CLOUDFLARE_CONFIGURATION_VALID=no
NODE_VERSION_PIN_EFFECTIVE=no
SPA_FALLBACK_REQUIRED=no
SECOND_LOCKFILE_CREATED=no
NO_LOCALHOST_IN_PRODUCTION_BUNDLE=yes
MISSING_API_URL_FAILS_CLOSED=yes
INVALID_API_URL_ACCEPTED=yes
FRONTEND_SECRET_EXPOSURE=0

OFFICIAL_SEARCH_ENABLED=no
OFFICIAL_SEARCH_FLAG_ONE_FAILS_CLOSED=yes
OFFICIAL_SEARCH_PROVIDER_CALLS=0
FINAL_ENABLED_TRAFFIC_RULES=3
PHONE_RULE_ENABLED=no
LIVE_PROVIDER_CALLS=0

RAW_USER_NARRATIVES_LOGGED=0
AUTH_HEADERS_LOGGED=0
COOKIES_LOGGED=0
PERSONAL_IDENTIFIERS_LOGGED=0
STACK_TRACES_RETURNED_TO_CLIENT=0
REAL_SECRETS_IN_FILES=0
REAL_SECRETS_IN_IMAGE=0

BACKEND_LITE_TESTS=1557 passed
FOCUSED_MODE_2D_TESTS=259 passed
PLATFORM_EVALUATION_TESTS=214 passed
LEGAL_BETA_EVALUATION_TURNS=49
FRONTEND_TESTS=183 passed
TYPECHECK=passed
BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean
REGRESSION_PASS=yes

UNSUPPORTED_CITATION_RATE=0
DISABLED_RULE_CURATED_ANSWERS=0
MISSING_FACT_CURATED_VERIFIED_RESPONSES=0
INCOMPLETE_STRUCTURED_CITATIONS=0
NON_OFFICIAL_SOURCE_ACCEPTED=0
MODE_2D_CLAUSE_2_OUTPUTS=0
UNSAFE_REQUESTS_REACHING_SEARCH=0
AMBIGUOUS_RULE_CURATED_ANSWERS=0
INCORRECT_TOPIC_CITATION_SHAPES_ACCEPTED=0

ACTUAL_HARD_CONSTRAINT_COUNT=9
REPORT_HARD_CONSTRAINT_COUNT_ACCURATE=no
DEPLOY_DOCS_MATCH_IMPLEMENTATION=no
EPHEMERAL_FALLBACK_DOC_CONTRADICTION=yes
REPORT_CURRENT_CLAIMS_ACCURATE=no

READY_TO_COMMIT=no
READY_FOR_LIMITED_DEMO_DEPLOYMENT=no
READY_FOR_GENERAL_PUBLIC_BETA=no

TRACKED_FILES_MODIFIED_BY_REVIEWER=0
TEST_FILES_MODIFIED_BY_REVIEWER=0
EXISTING_REPORTS_MODIFIED_BY_REVIEWER=0
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
CLOUD_RESOURCES_CREATED=0
LIVE_PROVIDER_CALLS=0
DOCKER_REVIEW_ARTIFACTS_RETAINED=0
```

## Verdict basis

The implementation is not ready for a limited deployment. The complete
regression suites pass and the local image is structurally clean, but the
production persistence contract fails open and several edge/configuration
controls are not deployable as claimed.

### HIGH-01 — production SQLite silently falls back to ephemeral storage

`Settings.chat_db_path` does not distinguish development from production and
does not require an explicit `/data/...` path. Independent image probes gave:

```text
APP_ENV=production, CHAT_DB_PATH unset
path=/app/data/vietlaw_chat.sqlite3
health=200 ok

APP_ENV=production, CHAT_DB_PATH=/app/data/vietlaw_chat.sqlite3
health=200 ok

APP_ENV=production, CHAT_DB_PATH=/data/vietlaw_chat.sqlite3, no volume mounted
health=200 ok
database created in the container writable layer
```

This is the exact prohibited silent healthy ephemeral behavior. The deploy
guide describes it accurately but contradicts the original fail-closed
requirement. `APP_ENV=production` currently has no persistence enforcement.

### HIGH-02 — the non-root image/volume permission contract is incomplete

The image correctly runs as UID 999, but the Railway instructions attach a
volume without addressing Railway's documented rule that volumes are mounted
as root. Railway instructs non-root images affected by this to use
`RAILWAY_RUN_UID=0`; the repository neither sets nor documents that variable,
and has no root entrypoint which can repair ownership and then drop privilege.
The Docker named-volume smoke is not equivalent to Railway because Docker can
copy the image mountpoint's existing ownership into a new named volume, while
Railway says its volumes are not overlays. Therefore the claimed non-root,
writable Railway `/data` configuration is not established and may deploy only
as health-503. See Railway's [volume permission documentation](https://docs.railway.com/volumes)
and [runtime UID variable reference](https://docs.railway.com/variables/reference).

### MEDIUM-01 — health omits the enabled traffic pack

With `VIETLAW_TRAFFIC_PACK_ENABLED=1`, a container whose legal snippets and
unsafe patterns were valid but whose sibling `traffic_rules.json` was missing
returned HTTP 200 and `status=ok`. Construction silently dropped the legal
fallback orchestrator, while health checked only snippets, unsafe patterns,
and the base chat store. Missing primary traffic data therefore does not make
the deployment unready.

### MEDIUM-02 — IP limiting trusts a spoofable header

The middleware uses the first client-provided `X-Forwarded-For` value. With a
one-request limit, independent live probes produced `200` for spoofed address
A, `200` for spoofed address B, then `429` only when A was reused. Railway's
current public-networking reference documents `X-Real-IP` as the client-IP
header and does not establish sanitization of arbitrary incoming
`X-Forwarded-For`. Per-IP limiting must therefore be treated as best-effort
until trusted-proxy-aware extraction is implemented. See Railway's
[request-header specification](https://docs.railway.com/networking/public-networking/specs-and-limits).

### MEDIUM-03 — current Railway schema does not support `numReplicas`

The current config-as-code reference supports `multiRegionConfig`; it no
longer lists `numReplicas`. Thus the declared single-replica field is not a
reliable current-schema control. The remaining builder, Dockerfile,
health-check and restart fields are valid, and code configuration correctly
overrides dashboard values. See Railway's current
[config-as-code reference](https://docs.railway.com/config-as-code/reference).

### MEDIUM-04 — malformed frontend API bases are accepted

`normalizeApiBaseUrl()` only trims and removes one trailing slash. Production
builds accepted and embedded `javascript:alert(1)`; `not-a-url` is likewise
accepted. Browser `fetch` will generally reject unsupported schemes as a
network error, but the configuration boundary itself does not fail closed.
An explicit `http:`/`https:` absolute-origin validator is required. Empty or
missing configuration does fail closed and production bundles contain no
`localhost:8000`.

### MEDIUM-05 — Node 20 is not effectively pinned for Pages root `frontend`

The only `.nvmrc` is at repository root. Cloudflare's documentation says the
version file belongs in the configured project root; with Pages root set to
`frontend`, there is no `frontend/.nvmrc` or `.node-version`, and no committed
Pages config sets `NODE_VERSION=20`. The guide's “in most cases” wording does
not establish an effective pin. See Cloudflare's
[build image/version documentation](https://developers.cloudflare.com/pages/configuration/build-image/).

### LOW findings

1. The readiness report says “all 8 hard constraints,” while the review
   contract contains nine. All nine were independently zero; the ninth is the
   exact citation-shape constraint exercised outside the eight-metric runner.
2. The readiness report claims 184 frontend tests, but the complete current
   suite contains 183 passing tests. `apiBaseUrl.test.ts` adds four, not five.
3. Deployment documentation contains stale/overbroad claims: the root
   `.nvmrc` is called an effective Pages pin; `numReplicas` is called enforced;
   and the report says no volume config-as-code mechanism exists, while
   Railway now also offers CLI/API and experimental project IaC mechanisms.

## Verified controls

- Clean Docker rebuild succeeded from `python:3.11-slim`; the entrypoint is
  `backend_lite.app.main:app`, listens on `0.0.0.0:${PORT}`, has no reload,
  and runs as UID 999.
- Image inspection found the three required runtime JSON files and no `.env`,
  SQLite database, frontend, tests, teammate `backend/`, or real secret.
- Mounted-volume persistence passed across both container restart and
  remove/recreate using the same local Docker volume.
- A genuinely read-only SQLite volume returned HTTP 503.
- CORS allowed the exact configured origin, rejected all five malformed/
  unconfigured origins by omitting `Access-Control-Allow-Origin`, and handled
  configured preflight correctly.
- Per-conversation, request-length, concurrency, retry-header and stale-bucket
  mechanics pass; the overall rate-limiting verdict remains `no` because its
  IP identity boundary is spoofable.
- Official legal search remained structurally disabled even when its flag was
  set to 1 without a provider: no provider object, no external call, no
  misleading search trust path, and no startup failure.
- Cloudflare root/build/output/lockfile and no-SPA-fallback choices are valid;
  only the Node pin is ineffective. Cloudflare's Vite reference confirms
  `npm run build` and `dist` for this project shape: [Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/).

All temporary containers, volumes, the review image, and the local Colima VM
were removed/stopped after the smoke tests. No deployment or cloud mutation was
performed.
