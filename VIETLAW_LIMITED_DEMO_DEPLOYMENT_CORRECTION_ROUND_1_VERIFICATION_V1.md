# VietLaw Limited Demo — Deployment Correction Round 1 Independent Re-verification V1

```text
INDEPENDENT_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
VERDICT=VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_VERIFICATION_BLOCKED

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
TASK_SCOPE_MATCH=yes
UNDECLARED_IMPLEMENTATION_FILES=0
UNRELATED_SCOPE_CHANGES=0

HIGH_FINDINGS=0
MEDIUM_FINDINGS=4
LOW_FINDINGS=3

PRODUCTION_SQLITE_FAILS_CLOSED=yes
PRODUCTION_CHAT_DB_PATH_REQUIRED=yes
PRODUCTION_DB_PATH_MUST_BE_UNDER_DATA=yes
ACTUAL_DATA_MOUNT_REQUIRED=yes
EPHEMERAL_PRODUCTION_FALLBACK_POSSIBLE=no
SQLITE_FILE_CREATED_BEFORE_VALIDATION=0

VOLUME_OWNERSHIP_REPAIRED=yes
APPLICATION_PROCESS_UID=999
APPLICATION_PROCESS_GID=999
APPLICATION_PROCESS_IS_PID_1=yes
SYMLINK_CHOWN_ESCAPE_POSSIBLE=yes
READ_ONLY_VOLUME_REJECTED=yes
APPLICATION_CAN_CONTINUE_AS_ROOT=no

TRAFFIC_PACK_HEALTH_REQUIRED=yes
EXACT_TRAFFIC_PACK_HEALTH_GATE=no
TRAFFIC_ENABLED_PACK_MISSING_STATUS=503
TRAFFIC_INVALID_PACK_STATUS=503
WRONG_ENABLED_RULE_COUNT_STATUS=200
WRONG_ENABLED_RULE_IDS_STATUS=200
WRONG_DISABLED_RULE_COUNT_STATUS=200
TRAFFIC_DISABLED_PACK_MISSING_STATUS=200

X_FORWARDED_FOR_TRUSTED=no
X_REAL_IP_USED=yes
X_FORWARDED_FOR_SPOOF_BYPASS_POSSIBLE=no
RATE_LIMIT_PER_IP_CORRECT=yes

RAILWAY_CONFIG_SCHEMA_VALID=yes
UNSUPPORTED_RAILWAY_FIELDS=0
NUM_REPLICAS_FIELD_PRESENT=no
MULTI_REGION_CONFIG_PRESENT=no
SINGLE_REPLICA_MANUAL_GATE_DOCUMENTED=yes

INVALID_API_URL_ACCEPTED=yes
PRODUCTION_HTTP_NONLOCAL_ACCEPTED=no
MISSING_API_URL_FAILS_CLOSED=yes
NO_LOCALHOST_IN_PRODUCTION_BUNDLE=no
TRAILING_SLASH_NORMALIZED=yes

NODE_VERSION_PIN_EFFECTIVE=yes
SECOND_LOCKFILE_CREATED=no
CLOUDFLARE_ROOT_CORRECT=yes

HEALTHY_STATUS_CODE=200
DEGRADED_STATUS_CODE=503
HEALTH_EXTERNAL_CALLS=0
HEALTH_INTERNAL_PATH_EXPOSURE=0

DEPLOY_DOCS_MATCH_IMPLEMENTATION=no
REPORT_CURRENT_CLAIMS_ACCURATE=no
STALE_DEPLOYMENT_CLAIMS=4

DOCKER_BUILD=passed
PERSISTENCE_RESTART_SMOKE=passed
PERSISTENCE_RECREATE_SMOKE=passed
TEMP_CONTAINERS_REMOVED=yes
TEMP_IMAGES_REMOVED=yes
TEMP_VOLUMES_REMOVED=yes
COLIMA_STOPPED=yes

BACKEND_LITE_TESTS=1588 passed
FOCUSED_MODE_2D_TESTS=259 passed; 1329 deselected
PLATFORM_EVALUATION_TESTS=214 passed
LEGAL_BETA_EVALUATION_TURNS=49; 0 findings
FRONTEND_TESTS=194 passed; 12 files
TYPECHECK=passed
BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean

MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
REGRESSION_PASS=yes
LIVE_PROVIDER_CALLS=0

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
```

## Verdict basis

The correction closes both prior production-storage findings: production startup rejects an unset/default path, a relative path, paths outside `/data`, traversal, an ordinary unmounted `/data`, and a read-only mount. `build_container()` validates before constructing any SQLite-backed store. A real named Docker volume was recognized as a mount, repaired to `999:999`, and Uvicorn ran as PID 1 with UID/GID 999. Restart and remove/recreate smoke checks retained six previously created chats. No-volume and read-only-volume runs exited nonzero.

The correction is nevertheless blocked by four MEDIUM findings.

### MEDIUM-01 — exact traffic inventory is not a health invariant

`_build_legal_fallback_orchestrator()` treats any successfully parsed `TrafficSourcePack` as loaded and records only `enabled_rule_count`. `routes_health.py` gates on `required && loaded`; it never checks total rows, disabled rows, or the frozen enabled-ID set. Independent mutations produced these healthy states:

- two enabled rules: `loaded=True`, `enabled_rule_count=2`, health semantics remain 200;
- three enabled rules with an unexpected enabled ID: `loaded=True`, count 3, health remains 200;
- fourteen total rows / eleven disabled rows: `loaded=True`, count 3, health remains 200.

Thus `WRONG_ENABLED_RULE_COUNT_STATUS`, `WRONG_ENABLED_RULE_IDS_STATUS`, and `WRONG_DISABLED_RULE_COUNT_STATUS` are all 200. Missing, malformed, and citation-shape-invalid packs do fail loading and yield 503 when the flag is enabled; a missing pack remains healthy when the flag is disabled. The narrower load gate works, but it is not the required exact 15/3/12 gate.

### MEDIUM-02 — entrypoint chown follows file symlinks outside `/data`

`_chown_tree()` uses `os.chown()` on entries yielded by `os.walk()`. Although `os.walk()` does not recurse through directory symlinks by default, `os.chown()` follows a symlink. A container probe created `/data/link -> /outside/target`; before the call the target and link both had UID 0, and afterward the outside target had UID 999 while the symlink itself remained UID 0. This is a concrete ownership escape outside `/data`.

### MEDIUM-03 — production explicitly accepts localhost HTTP

`normalizeApiBaseUrl()` has no environment parameter and accepts `http://localhost` and `http://127.0.0.1` in every build. An actual Node 20.19.4 production build with `VITE_API_BASE_URL=http://localhost:8000` succeeded, and the emitted JavaScript contained `localhost:8000`. Therefore the implementation does not enforce “local HTTP in development only”; `INVALID_API_URL_ACCEPTED=yes` and the universal production-bundle claim is false. The valid HTTPS production build did correctly contain the configured origin and zero localhost occurrences. IPv6 loopback (`http://[::1]`) is rejected because it is not on the two-host allowlist.

### MEDIUM-04 — correction report and deployment claims contradict behavior

`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_REPORT.md` says all findings are closed, explicitly argues that enabled count is not a hard-failure trigger, claims strict frontend production URL behavior, and reports zero MEDIUM findings. Those claims contradict the required frozen traffic inventory, the production-localhost build probe, and the symlink escape. The report also does not disclose the escape.

## LOW findings

1. `_is_mount_point()` compares raw mountinfo field 5 and does not decode Linux mountinfo escapes such as `\040`. An injected genuine mount path containing a space, represented with `\040`, was rejected. This is fail-closed and does not affect the fixed literal `/data` production mount, so it is LOW rather than a persistence bypass. A nested mount alone was correctly rejected as not proving the root itself is mounted.
2. Recursive chown of a large existing volume is not documented as a limited-demo startup-time trade-off. The documents explain ownership repair but do not state the potentially linear cold-start cost.
3. Railway's current public-networking documentation identifies `X-Real-IP` as the client remote IP, but the reviewed documentation does not explicitly promise an anti-spoof replacement/sanitization contract. The local trusted-mode implementation is correct and never reads `X-Forwarded-For`; a real Railway-edge smoke test remains a deployment-day gate.

## Other verified behavior

- A non-loopback Docker client produced `200, 429` while rotating only `X-Forwarded-For`; a new valid `X-Real-IP` received an independent 200 bucket. The earlier same-container localhost probe was not used as authority because Uvicorn itself trusts loopback proxy headers by default.
- The live container health body was 200 and reported `traffic_pack_required=true`, `traffic_pack_loaded=true`, and count 3. CORS echoed only the exact configured origin.
- The deposit smoke returned 200. With deterministic routing enabled and a placeholder credential that was never called, the red-light motorcycle response was `curated_verified` with three citations; the disabled phone rule returned `general_guidance` with zero citations.
- Health performs no LLM, official-search, government-site, or other external call and exposes no internal path/exception detail.
- `railway.toml` contains only the reviewed build/health/restart keys. Current Railway documentation lists those configuration concepts; `numReplicas` is absent, and the one-replica constraint is correctly documented as manual.
- `frontend/.nvmrc` contains `20`, the documented Pages project root is `frontend`, and `frontend/package-lock.json` is the only lockfile. Current Cloudflare Pages documentation recognizes `.nvmrc` and `NODE_VERSION` at the project root.
- All nine legal hard constraints remain zero: the legal runner prints eight zero metrics and the ninth exact citation-shape constraint remains covered structurally by the passing backend tests.
- No MODE_2D frozen behavior, legal rule, citation, retrieval path, dependency, secret, remote, or cloud resource was changed or used by this review.

Official references checked on 2026-07-31:

- Railway config-as-code reference: https://docs.railway.com/config-as-code/reference
- Railway public-network request headers: https://docs.railway.com/networking/public-networking/specs-and-limits
- Cloudflare Pages build image/version files: https://developers.cloudflare.com/pages/configuration/build-image/
- Cloudflare Pages monorepo root configuration: https://developers.cloudflare.com/pages/configuration/monorepos/

## Cleanup and restrictions

All review-created Docker containers, the Docker network, named volume, and tagged image were removed; Colima was stopped. The generated frontend `dist/` directory was removed after bundle inspection. The Git index remains empty. This report is the only persistent file created by the reviewer and is intentionally untracked and unstaged.
