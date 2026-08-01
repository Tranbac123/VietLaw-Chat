# VietLaw Limited Demo — Deployment Correction Round 2 Final Independent Verification V1

```text
INDEPENDENT_REVIEWER=CODEX_GPT_5_6_SOL_HIGH
VERDICT=VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS

HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
TASK_SCOPE_MATCH=yes
UNDECLARED_IMPLEMENTATION_FILES=0
UNRELATED_SCOPE_CHANGES=0

HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS=3

EXACT_TRAFFIC_PACK_HEALTH_GATE=yes
TOTAL_TRAFFIC_ROWS=15
FINAL_ENABLED_TRAFFIC_RULES=3
DISABLED_TRAFFIC_RULES=12
CORRECT_TRAFFIC_PACK_STATUS=200
WRONG_ENABLED_RULE_COUNT_STATUS=503
WRONG_ENABLED_RULE_IDS_STATUS=503
WRONG_DISABLED_RULE_COUNT_STATUS=503
TRAFFIC_INVALID_PACK_STATUS=503
TRAFFIC_DISABLED_PACK_MISSING_STATUS=200

SYMLINKS_UNDER_DATA_REJECTED=yes
SYMLINK_CHOWN_ESCAPE_POSSIBLE=no
OUTSIDE_TARGETS_MODIFIED=0
APPLICATION_PROCESS_UID=999
APPLICATION_PROCESS_GID=999
APPLICATION_PROCESS_IS_PID_1=yes
APPLICATION_CAN_CONTINUE_AS_ROOT=no

PRODUCTION_HTTPS_ONLY=yes
PRODUCTION_HTTP_LOCALHOST_ACCEPTED=no
INVALID_API_URL_ACCEPTED=no
MISSING_PRODUCTION_API_URL_BUILD_SUCCEEDS=no
NO_LOCALHOST_IN_PRODUCTION_BUNDLE=yes
TRAILING_SLASH_NORMALIZED=yes

MOUNTINFO_ESCAPES_DECODED=yes
PRODUCTION_SQLITE_FAILS_CLOSED=yes
ACTUAL_DATA_MOUNT_REQUIRED=yes
EPHEMERAL_PRODUCTION_FALLBACK_POSSIBLE=no
SQLITE_FILE_CREATED_BEFORE_VALIDATION=0

X_FORWARDED_FOR_TRUSTED=no
X_REAL_IP_USED=yes
X_FORWARDED_FOR_SPOOF_BYPASS_POSSIBLE=no
RAILWAY_X_REAL_IP_DEPLOYMENT_DAY_GATE_REQUIRED=yes

RAILWAY_CONFIG_SCHEMA_VALID=yes
UNSUPPORTED_RAILWAY_FIELDS=0
NUM_REPLICAS_FIELD_PRESENT=no
MULTI_REGION_CONFIG_PRESENT=no
SINGLE_REPLICA_MANUAL_GATE_DOCUMENTED=yes

DEPLOY_DOCS_MATCH_IMPLEMENTATION=yes
REPORT_CURRENT_CLAIMS_ACCURATE=no
STALE_DEPLOYMENT_CLAIMS=0

DOCKER_BUILD=passed
ROOT_OWNED_VOLUME_SMOKE=passed
FILE_SYMLINK_SMOKE=passed
DIRECTORY_SYMLINK_SMOKE=passed
READ_ONLY_VOLUME_SMOKE=passed
TRAFFIC_INVENTORY_HEALTH_SMOKE=passed
PERSISTENCE_RESTART_SMOKE=passed
PERSISTENCE_RECREATE_SMOKE=passed

TEMP_CONTAINERS_REMOVED=yes
TEMP_IMAGES_REMOVED=yes
TEMP_VOLUMES_REMOVED=yes
MUTATED_DATA_COPIES_REMOVED=yes
COLIMA_STOPPED=yes

BACKEND_LITE_TESTS=1609 passed
FOCUSED_MODE_2D_TESTS=259 passed; 1350 deselected (documented -k selector)
PLATFORM_EVALUATION_TESTS=214 passed
LEGAL_BETA_EVALUATION_TURNS=49; 0 findings
ACTUAL_HARD_CONSTRAINT_COUNT=9
FRONTEND_TESTS=209 passed; 12 files
TYPECHECK=passed
VALID_PRODUCTION_BUILD=passed
INVALID_PRODUCTION_BUILDS_REJECTED=13/13 passed (12 invalid values plus missing value)
COMPILEALL=passed
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean

MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
PHONE_RULE_ENABLED=no
REGRESSION_PASS=yes

READY_TO_COMMIT=yes
READY_FOR_LIMITED_DEMO_DEPLOYMENT=yes (subject to documented deployment-day Railway X-Real-IP gate)
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
```

## 1. Scope and preconditions

The repository root, branch, and HEAD exactly matched the requested values. The Git index was empty and no merge, rebase, cherry-pick, or revert operation was in progress. Round 2 implementation changes are confined to the declared deployment-health metadata, read-only traffic-pack introspection, storage mountinfo parsing, entrypoint hardening, frontend API-boundary validation/build gate, associated tests, and deployment documentation. No legal rule, citation, selector, retrieval behavior, dependency, secret, or frozen MODE_2D behavior entered Round 2 scope.

## 2. Exact traffic inventory gate

The frozen constants in `backend_lite/app/dependencies.py` independently specify 15 total rows, 3 enabled rows, 12 disabled rows, and exactly these enabled IDs:

- `traffic_red_light__motorcycle__safe_v1`
- `traffic_red_light__car__safe_v1`
- `traffic_no_helmet__motorcycle__driver_safe_v1`

`TrafficSourcePack` exposes read-only counts/IDs, and `_build_legal_fallback_orchestrator()` compares every dimension against the constants. `/api/health` requires both `loaded` and `exact_inventory_valid` when the flag is enabled.

Independent temporary-copy probes produced:

| Pack | Parsed/loaded | Health | Exact flag |
|---|---:|---:|---:|
| Correct 15/3/12 pack | yes | 200 | true |
| Two enabled | yes | 503 | false |
| Four enabled | yes | 503 | false |
| Three enabled with unexpected ID | yes | 503 | false |
| Fourteen total / eleven disabled | yes | 503 | false |
| Sixteen total / thirteen disabled | yes | 503 | false |
| Missing | no | 503 | false |
| Malformed JSON | no | 503 | false |
| Flag disabled, pack missing | no | 200 | false |

The response exposes only bounded booleans/counts; no path, exception, rule ID, or mismatch detail appeared. A live container with a structurally valid two-enabled-rule copy returned 503 with `loaded=true`, count 2, and exact flag false.

## 3. Ownership repair and residual race assessment

The traversal uses `os.scandir`, checks every visited path with `os.lstat`, rejects symlinks, calls `os.chown(..., follow_symlinks=False)`, and never recurses into directory symlinks. File, directory, and deeply nested symlinks each caused exit 1 with one bounded stderr line and no traceback or Uvicorn startup.

Three targets on a separately mounted outside volume were recorded before and after the probes. UID/GID, nanosecond mtime, content, and SHA-256 remained identical; `OUTSIDE_TARGETS_MODIFIED=0`. Ordinary nested directories and a pre-existing SQLite-like file were repaired from 0:0 to 999:999. Uvicorn then ran as PID 1 with all real/effective/saved/filesystem UID/GID values equal to 999.

Residual race assessment:

- Replacing the final component between `lstat` and `chown` cannot redirect the ownership change through a symlink because `follow_symlinks=False` acts on the link itself.
- Path-based recursive traversal cannot eliminate a race in which a privileged concurrent actor replaces an already-checked parent directory before a later `scandir`/child operation. Such an actor would need concurrent write/control of the mounted filesystem during the short pre-application entrypoint phase.
- A symlink discovered after earlier ordinary siblings were repaired can leave partial in-volume ownership changes, but startup exits immediately and no application runs.

The parent-component race is accepted for this bounded single-container limited-demo threat model: the entrypoint is the only application process at that time and the Railway-mounted volume/host is a trusted operational boundary. This is not a claim that path-based traversal is safe against a malicious concurrent host or storage administrator.

## 4. Frontend production boundary

The shared validator accepts HTTPS in both environments, permits loopback HTTP only when `isDev=true`, and rejects credentials, query strings, fragments, non-HTTP(S) schemes, relative/protocol-relative input, and non-loopback HTTP. `vite.config.ts` invokes the same validator before a production build and rejects a missing value.

Using Node 20.19.4, all twelve rejected configured values plus the missing-value case exited nonzero and produced no `dist/`. Both `https://backend.example.com` and its trailing-slash form built successfully. The valid production bundle contained the configured origin and contained none of `localhost:8000`, the malicious schemes/values, credentials, or query token. Runtime normalization strips the trailing slash before API paths are concatenated. Frontend unit tests also confirmed development accepts `localhost`, `127.0.0.1`, and `[::1]` HTTP.

## 5. Storage, Railway, rate limiting, and Docker

Mountinfo decoding handles `\040`, `\011`, `\012`, and `\134`; unknown or malformed sequences fail closed. Literal `/data` and an escaped genuine mount path match, while a nested mount without a root mount does not. Relative/outside/traversal paths, unreadable mountinfo, no volume, a plain unmounted `/data`, and read-only mounts all fail closed before SQLite construction. A real writable named volume starts successfully.

Current Railway documentation lists the reviewed Dockerfile, healthcheck, and restart configuration concepts. `railway.toml` contains no unsupported reviewed field, `numReplicas`, or multi-region configuration; exactly one replica is correctly documented as a manual dashboard gate. Railway's current public-network documentation describes `X-Real-IP` as the client remote IP, but it does not explicitly prove the replacement/sanitization behavior needed to close spoofing against a real deployment. The deployment-day manual gate therefore remains required.

The local implementation never reads `X-Forwarded-For`. A non-loopback Docker client rotating only that header received 200 then 429 from one shared bucket; a valid `X-Real-IP` is used only in trusted mode, and invalid/missing values fall back safely. CORS echoed only the configured exact origin. The deposit request returned safely, the motorcycle red-light answer was `curated_verified` with three sources, and the disabled phone rule remained `general_guidance` with zero sources. One chat persisted across both restart and remove/recreate against the same named volume.

Official references checked on 2026-08-01:

- Railway config-as-code reference: https://docs.railway.com/config-as-code/reference
- Railway public-network request headers: https://docs.railway.com/networking/public-networking/specs-and-limits

## 6. Regression and report audit

All complete suites and build/static checks passed. The legal runner printed eight zero hard-constraint metrics; the ninth exact topic-citation-shape constraint remains structurally enforced and covered by the passing backend suite. No provider call was configured or observed.

Three LOW, nonblocking documentation/report findings remain:

1. `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_REPORT.md` reports `FOCUSED_MODE_2D_TESTS=552 passed; 1057 deselected` without giving a command. Re-running the repository's documented selector, `-k "fast_demo or mode_2d or MODE_2D"`, against the current 1609-test suite produced **259 passed; 1350 deselected**. The 552 claim is not independently reproducible from the stated report.
2. The Round 2 report says “all 11 required rejected values” but enumerates twelve configured invalid values, then separately mentions the missing value. The independent matrix result is 12 configured-invalid rejections plus one missing-value rejection: 13/13.
3. The deployment checklist accurately identifies the Railway-edge check as manual, but step 1 of that procedure simultaneously says to use “two different machines/networks” and that both requests must originate from the “SAME real client (same machine/network, unchanged).” Those conditions are mutually inconsistent. The rotating-`X-Forwarded-For` same-bucket check must use one unchanged real client/network; separate networks are relevant to proving distinct real-client buckets.

Historical readiness/Round 1 reports are prominently marked historical or superseded, so their retained old inline totals and claims are not counted as current stale claims. The implementation facts in the current deployment guide, architecture, and checklist otherwise match the verified behavior.

## 7. Cleanup and restrictions

All reviewer-created Docker containers, network, named volumes, mutated data copy, derived image, and main test image were removed. Colima was stopped. Generated frontend `dist/`, build logs, temporary Docker configuration, and compile cache were removed. The Git index remains empty. This report is the only persistent file created by the reviewer and is intentionally untracked and unstaged.
