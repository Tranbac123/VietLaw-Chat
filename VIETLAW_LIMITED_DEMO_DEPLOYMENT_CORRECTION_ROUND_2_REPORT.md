# VietLaw Limited Demo — Deployment Correction Round 2 Report

`IMPLEMENTER=CLAUDE_CODE_SONNET`.

```
VERDICT=VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_READY_FOR_REVIEW
STARTING_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
FINAL_HEAD=5079454d90730ac9f7fb23d18fe6b8a5578229a4
BRANCH=feature/conversational-rental-deposit-demo-v2
INDEX_EMPTY=yes
COMMITS_CREATED=0
STAGED_FILES=0
PUSH_PERFORMED=no
DEPLOY_PERFORMED=no
CLOUD_RESOURCES_CREATED=0
LIVE_PROVIDER_CALLS=0
```

> **Correction notice (Final Documentation Cleanup, post Round 2
> independent verification):** an independent re-verification
> (`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_VERIFICATION_V1.md`,
> verdict `..._PASS_WITH_NONBLOCKING_FINDINGS`, `HIGH_FINDINGS=0`,
> `MEDIUM_FINDINGS=0`, `LOW_FINDINGS=3`) found three nonblocking
> documentation/report defects in this report and in
> `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md`, all since fixed
> documentation-only, with no source, test, legal-data, MODE_2D, Docker, or
> environment-configuration change: (1) `FOCUSED_MODE_2D_TESTS` below
> originally read `552 passed; 1057 deselected` with no selector given —
> corrected to the actual, reproducible `-k "fast_demo or mode_2d or
> MODE_2D"` result, `259 passed; 1350 deselected`; (2) the frontend
> production-build rejection-matrix prose below originally said "all 11
> required rejected values" while actually enumerating 12 configured
> invalid values plus 1 separate missing-value case (13/13 rejected
> total) — corrected below; (3) the deployment checklist's rotating-
> `X-Forwarded-For` deployment-day gate previously asked for both "two
> different machines/networks" AND "the SAME real client (same
> machine/network, unchanged)" in the same step — a direct contradiction,
> now split into two separate steps (same-client/same-bucket, and a
> distinct second-client/distinct-bucket check). See
> `VIETLAW_LIMITED_DEMO_FINAL_DOCUMENTATION_CLEANUP_REPORT.md` for the
> full audit trail. Every other claim in this report (the fixes
> themselves, their behavior, and their Docker/regression verification)
> was independently confirmed accurate and is unchanged.

This round responds to
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_VERIFICATION_V1.md`
(`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_VERIFICATION_BLOCKED`,
`HIGH_FINDINGS=0`, `MEDIUM_FINDINGS=4`, `LOW_FINDINGS=3`). All 7 findings
are fixed and independently re-verified below (local tests, a local Docker
build via Colima, and local frontend build/typecheck/test — no cloud
resources, no real credentials, nothing staged/committed/pushed/deployed).

## 1. Findings closed

```
MEDIUM_01_CLOSED=yes
MEDIUM_02_CLOSED=yes
MEDIUM_03_CLOSED=yes
MEDIUM_04_CLOSED=yes
LOW_01_CLOSED=yes
LOW_02_CLOSED=yes
LOW_03_CLOSED=yes
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS=0
```

### MEDIUM-01 — exact traffic inventory is not enforced by health

**Fix.** `TrafficPackHealthStatus` (`backend_lite/app/dependencies.py`)
extended with bounded structured fields: `total_rule_count`,
`enabled_rule_count`, `disabled_rule_count`, `enabled_rule_ids`,
`exact_inventory_valid`. New frozen constants
`EXPECTED_TOTAL_TRAFFIC_ROWS=15`, `EXPECTED_ENABLED_TRAFFIC_RULES=3`,
`EXPECTED_DISABLED_TRAFFIC_RULES=12`, and
`EXPECTED_ENABLED_TRAFFIC_RULE_IDS` (the three real enabled rule IDs read
from `data/traffic_rules.json`, never derived at runtime from the pack
itself). `TrafficSourcePack` (`traffic_source_pack.py`) gained two
read-only introspection properties, `total_rule_count`/
`disabled_rule_count` (no selection/citation logic touched).
`_build_legal_fallback_orchestrator` computes `exact_inventory_valid` as
an exact equality across all four dimensions. `routes_health.py` now gates
on `not required or (loaded and exact_inventory_valid)` — a pack that
PARSES successfully but has been mutated now fails health exactly like a
pack that fails to parse at all. `HealthResponse` gained
`traffic_pack_exact_inventory_valid: bool`; no path, exception text, or
mismatch detail is exposed.

```
EXACT_TRAFFIC_PACK_HEALTH_GATE=yes
TOTAL_TRAFFIC_ROWS=15
FINAL_ENABLED_TRAFFIC_RULES=3
DISABLED_TRAFFIC_RULES=12
WRONG_ENABLED_RULE_COUNT_STATUS=503
WRONG_ENABLED_RULE_IDS_STATUS=503
WRONG_DISABLED_RULE_COUNT_STATUS=503
CORRECT_TRAFFIC_PACK_STATUS=200
```

**Tests** (`backend_lite/tests/test_health.py`, 10 total incl. 6 new;
`backend_lite/tests/unit/test_traffic_source_pack.py`, +1 new): unmutated
control pack → 200; 2 enabled rules → 503; 4 enabled rules (via a
structurally-valid duplicate) → 503; 3 enabled rules with one renamed
(unexpected) ID → 503; 14 total rows → 503; 16 total rows (wrong disabled
count) → 503; flag-disabled + pack unavailable → still 200 (unaffected).
Every mutation test asserts `traffic_pack_loaded=True` (the pack DID
parse) alongside `traffic_pack_exact_inventory_valid=False`, proving this
is a distinct, additional gate, not a load-failure re-test.

**Docker-verified** (§7): a live container with a 2-enabled-rule mutated
pack (served via a Docker named volume, since bind-mounting arbitrary host
paths was unavailable in this sandbox) returned `503` with
`traffic_pack_loaded:true, traffic_enabled_rule_count:2,
traffic_pack_exact_inventory_valid:false`; the real, unmutated pack
returned `200` with `traffic_pack_exact_inventory_valid:true`.

### MEDIUM-02 — entrypoint chown follows symlinks outside /data

**Fix.** `docker-entrypoint.py::_chown_tree` rewritten around
`os.scandir()` with explicit no-follow semantics: every entry (including
the root `/data` itself) is `os.lstat`-checked immediately before
`os.chown(..., follow_symlinks=False)`, narrowing the TOCTOU window to the
single syscall gap between check and change. The instant ANY entry (file
or directory) turns out to be a symlink, `SymlinkUnderDataError` is
raised — caught in `main()` and reported as one bounded stderr line, then
`SystemExit(1)`, never a traceback, never a continuation as root. Directory
symlinks are never followed into recursion (plain `os.scandir` semantics
already guarantee this). `chmod 777` is never used anywhere in this file.

```
SYMLINK_CHOWN_ESCAPE_POSSIBLE=no
SYMLINKS_UNDER_DATA_REJECTED=yes
APPLICATION_PROCESS_UID=999
APPLICATION_PROCESS_GID=999
APPLICATION_CAN_CONTINUE_AS_ROOT=no
```

**Tests** (`backend_lite/tests/test_docker_entrypoint.py`, 6 cases,
loading the standalone script via `importlib` since it lives outside the
`backend_lite` package): plain nested directories/files repaired to the
caller's own uid/gid, existing "database" file remains
readable/writable; a file symlink under `/data` → `SymlinkUnderDataError`,
outside target's ownership/mtime provably unchanged; a directory symlink
under `/data` → same rejection, external directory untouched; a symlink
found deep in nested directories is still caught; a symlink found AFTER
an ordinary sibling was already chowned still rejects startup (partial
repair before rejection is harmless since the container never starts
either way).

**Docker-verified** (§7, using two separately-mounted named volumes to
prove a genuine ownership boundary, not two paths on the same
filesystem): a file symlink `/data/link -> /outside/target.txt` (both
pre-set to `0:0`) → container exits 1 with
`docker-entrypoint.py: rejecting startup -- symlink found under /data:
/data/link`; the outside target's ownership was independently confirmed
`0:0` both before and after (never touched). A directory symlink
`/data/dirlink -> /outside_dir` (containing `/outside_dir/sensitive/f.txt`,
pre-set `0:0`) → same rejection; the external directory's contents
confirmed still `0:0` after.

### MEDIUM-03 — production accepts http://localhost and embeds it in the bundle

**Fix.** Validation extracted to a new, `import.meta.env`-free module
`frontend/src/lib/apiBaseUrl.ts` (so it is importable from BOTH the
runtime bundle AND `vite.config.ts`, a Node/build-time context).
`normalizeApiBaseUrl(configuredValue, isDev)` now takes an explicit `isDev`
boolean: `http:` is permitted ONLY when `isDev === true` AND the hostname
is `localhost`/`127.0.0.1`/`[::1]` — in production (`isDev=false`), every
`http:` URL is rejected, with no loopback exception at all.
`frontend/src/api/client.ts` now imports from this module and passes
`import.meta.env.DEV` at its one call site (the DCE-critical inline
`import.meta.env.DEV` ternary for the `'http://localhost:8000'` dev
fallback literal is untouched — passing the same substituted boolean as a
function ARGUMENT does not reintroduce that string anywhere new).
`vite.config.ts` was rewritten to call `loadEnv(mode, cwd, '')` and the
SAME `normalizeApiBaseUrl`, throwing (failing the `vite build` command
itself, before any bundling) when `mode === 'production'` and the
configured value is missing or invalid.

```
PRODUCTION_HTTPS_ONLY=yes
PRODUCTION_HTTP_LOCALHOST_ACCEPTED=no
INVALID_API_URL_ACCEPTED=no
MISSING_PRODUCTION_API_URL_BUILD_SUCCEEDS=no
NO_LOCALHOST_IN_PRODUCTION_BUNDLE=yes
```

**Tests** (`frontend/src/test/apiBaseUrl.test.ts`, 30 total incl. 15 new):
plain https accepted in both environments; the 8 previously-rejected
malformed/unsafe values rejected in BOTH dev and prod explicitly;
`http://localhost:8000`/`http://127.0.0.1:8000`/`http://[::1]:8000`
rejected when `isDev=false`, accepted when `isDev=true`; a non-loopback
`http://` URL rejected in both environments.

**Build-verified** (direct `npx vite build --mode production` invocations,
one per value, checking the real process exit code): 12 configured
invalid values (`http://localhost:8000`, `http://127.0.0.1:8000`,
`http://[::1]:8000`, `http://backend.example.com` (non-loopback HTTP),
`javascript:alert(1)`, `not-a-url`, `/backend`, `//attacker.example`,
`ftp://example.com`, `https://user:pass@example.com`,
`https://example.com?token=x`, `https://example.com/#fragment`) plus 1
separate missing-value case (no `VITE_API_BASE_URL` set at all) — 13/13
rejected, each with exit code `1`, build never produces a `dist/`. Both
required accepted values
(`https://backend.example.com`, `https://backend.example.com/`) → exit
code `0`; the resulting `dist/assets/*.js` contains the correctly
normalized origin and zero occurrences of `localhost:8000` in either
case. `npx vite build --mode development` with no `VITE_API_BASE_URL` set
at all → exit code `0` (local development convenience preserved).

### MEDIUM-04 — correction report contradicted actual behavior

**Fix.** `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_REPORT.md`
now carries a correction notice at the top stating precisely which of its
original claims (`MEDIUM_01_CLOSED`, `MEDIUM_02_CLOSED`,
`MEDIUM_04_CLOSED`, `MEDIUM_FINDINGS=0`, and the READY verdict) were
incorrect as originally written, and points to this report for the
current, re-verified state. The report itself is left as a historical
record, not rewritten in place, per this task's own instruction.

### LOW-01 — mountinfo escapes are not decoded

**Fix.** `storage_readiness.py` gained `_decode_mountinfo_path()`,
decoding the four octal escapes the Linux kernel actually emits in
`/proc/self/mountinfo` (`\040` space, `\011` tab, `\012` newline, `\134`
backslash — per `fs/proc_namespace.c`'s `mangle()`), applied to field 5
before the equality comparison in `_is_mount_point()`. An unrecognized
escape sequence is left as a literal backslash rather than raising (a
subsequent equality comparison simply fails to match, which is already
this module's fail-closed default). Literal `/data` (containing none of
these bytes) behavior is unchanged.

```
MOUNTINFO_ESCAPES_DECODED=yes
ACTUAL_DATA_MOUNT_REQUIRED=yes
EPHEMERAL_PRODUCTION_FALLBACK_POSSIBLE=no
```

**Tests** (`backend_lite/tests/test_storage_readiness.py`, 19 total incl.
8 new): all four escapes individually decoded correctly; a realistic
escaped path (`/data\040with\040space`) decodes to the correct literal;
an unrecognized escape (`\999`) is left literal without raising; a
trailing lone backslash does not crash; exact `/data` mount accepted; a
NESTED mount alone (e.g. `/data/nested`) correctly rejected as not proving
the root itself is mounted; malformed mountinfo text fails closed (no
match, `False`); an end-to-end `validate_persistent_storage` call against
a mount path containing a real space, escaped in the fake mountinfo text,
succeeds.

### LOW-02 — recursive chown cold-start cost undocumented

**Fix.** `docker-entrypoint.py`'s own docstring, `Dockerfile.backend`'s
inline comments, `DEPLOY_RAILWAY_CLOUDFLARE.md` (Step 3),
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md` ("Failure behavior"),
and `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md` (the volume item) now
all state explicitly: recursive ownership repair is O(number of
files/directories on the volume), and a volume accumulating a very large
number of files over time may see a correspondingly longer container cold
start — an accepted limited-demo trade-off, not tuned or bounded further.

### LOW-03 — real Railway X-Real-IP behavior needs deployment-day smoke

**Fix.** The `X-Real-IP`/rate-limiter implementation itself is UNCHANGED
this round (per the task's explicit instruction: "Do not change the
current X-Real-IP implementation unless a new defect is found" — none
was). `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md` gained a new "After
public Railway deployment (deployment-day manual gate)" section with the
exact 5-step procedure from the task (two different attacker-controlled
`X-Forwarded-For` values from the same real client must share a bucket;
confirm Railway supplies a valid `X-Real-IP`; confirm identity cannot be
overridden; fall back to conservative per-conversation/concurrency limits
if unverifiable). `VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md` and
`DEPLOY_RAILWAY_CLOUDFLARE.md` cross-reference this as a deployment-day
gate, explicitly distinct from any local proof.

## 2. Docker smoke tests (Colima)

Colima started (`--cpu 2 --memory 4 --disk 20`) for this round; all
containers/volumes/images cleaned up and Colima stopped afterward. The
same local Docker-credential-helper workaround as Round 1 was used
(`DOCKER_CONFIG`/`DOCKER_HOST` environment variables scoped to these
commands only; the user's global `~/.docker/config.json` was never
modified). Bind-mounting arbitrary host paths into the Colima VM was
unavailable in this sandbox for paths outside the pre-configured mount
set; mutated-pack and symlink-escape scenarios were instead staged via
Docker named volumes populated through a short-lived helper container
(`docker cp`), which is filesystem-equivalent for every property these
tests assert (ownership, ownership-escape, and file contents) and does
not change what was verified.

```
DOCKER_BUILD=passed
ROOT_OWNED_VOLUME_SMOKE=passed (chowned to 999:999; Uvicorn PID 1 confirmed UID/GID 999 via /proc/1/status)
FILE_SYMLINK_SMOKE=passed (startup rejected; outside target ownership/mtime unchanged, verified across two independently mounted named volumes)
DIRECTORY_SYMLINK_SMOKE=passed (startup rejected; external directory contents unchanged)
READ_ONLY_VOLUME_SMOKE=passed (startup rejected with a clean one-line message, no traceback)
NO_VOLUME_SMOKE=passed (ProductionStorageError, uncaught, container exits before Uvicorn starts)
TRAFFIC_INVENTORY_HEALTH_SMOKE=passed (unmutated pack -> 200, exact_inventory_valid=true; 2-enabled-rule mutated pack -> 503, loaded=true, exact_inventory_valid=false)
CORS_EXACT_ORIGIN=passed (configured origin echoed; unconfigured origin gets no Access-Control-Allow-Origin header)
X_FORWARDED_FOR_ROTATION_LOCAL=cannot bypass (first 200, second 429 against a live rate-limited container)
DEPOSIT_FLOW_SMOKE=passed (200, with VIETLAW_FAST_DEMO_V2_ENABLED=1 and VIETLAW_LLM_ENABLED=0 -- no live provider call)
RED_LIGHT_THREE_CITATIONS=passed (trust_level=curated_verified, 3 sources)
PHONE_RULE_DISABLED=passed (trust_level=general_guidance, 0 sources)
PERSISTENCE_RESTART_SMOKE=passed (docker restart; chat list intact)
PERSISTENCE_RECREATE_SMOKE=passed (docker rm -f + new container against the same named volume; chat list intact, UID 999 re-confirmed)
TEMP_CONTAINERS_REMOVED=yes
TEMP_IMAGES_REMOVED=yes
TEMP_VOLUMES_REMOVED=yes
MUTATED_DATA_COPIES_REMOVED=yes
COLIMA_STOPPED=yes
```

One process note: the traffic-pack/deposit/citation smoke checks initially
appeared to fail (a red-light message misrouted to a generic high-risk
response) because the FIRST smoke container omitted
`VIETLAW_FAST_DEMO_V2_ENABLED=1` — the deployment checklist's own
documented requirement for the traffic-pack and rental-deposit verticals
to be reachable at all. This was traced to the missing env var (confirmed
by reproducing the identical behavior via a bare `TestClient` call outside
Docker entirely, with and without that flag) rather than any defect in
this round's changes, and the smoke container was corrected to match the
documented production configuration before re-testing; all listed results
above are from the corrected, checklist-compliant container.

## 3. Full regression

```
BACKEND_LITE_TESTS=1609 passed
FOCUSED_MODE_2D_TESTS=259 passed; 1350 deselected (selector: -k "fast_demo or mode_2d or MODE_2D")
PLATFORM_EVALUATION_TESTS=214 passed
LEGAL_BETA_EVALUATION_TURNS=49; 0 findings
ACTUAL_HARD_CONSTRAINT_COUNT=9 (8 printed by the runner + the structurally-enforced exact-citation-shape constraint, unchanged from Round 1)
FRONTEND_TESTS=209 passed (12 files)
TYPECHECK=passed (tsc --noEmit)
VALID_PRODUCTION_BUILD=passed (both accepted VITE_API_BASE_URL values; 0 occurrences of localhost:8000 in either dist/assets/*.js)
INVALID_PRODUCTION_BUILDS_REJECTED=13/13 passed (12 configured invalid values + 1 missing value; exit code 1 each, verified individually)
COMPILEALL=passed (backend_lite, docker-entrypoint.py)
GIT_DIFF_CHECK=clean
SECRET_SCAN=clean (no real credentials in any changed/new file)
DOCKER_SMOKE_TESTS=passed (see §2)
```

```
MODE_2D_PRESERVED=yes
MODE_2E_REINTRODUCED=no
PRODUCTION_APPLICABLE_CLAUSE_2_PATHS=0
FINAL_ENABLED_TRAFFIC_RULES=3
PHONE_RULE_ENABLED=no
REGRESSION_PASS=yes
```

No legal rule, citation, traffic selector, rental-deposit behavior, or
frozen MODE_2D file was modified this round. The two additions to
`TrafficSourcePack` (`total_rule_count`, `disabled_rule_count`) are
read-only introspection properties over already-loaded data, never
touched by `select_rule`, `find`, or any citation-shape validator; the
frozen expected-inventory constants in `dependencies.py` are deployment
health metadata, not a change to what the pack itself contains or how it
is selected from.

## 4. Readiness verdicts

```
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS=0
EXACT_TRAFFIC_PACK_HEALTH_GATE=yes
SYMLINK_CHOWN_ESCAPE_POSSIBLE=no
PRODUCTION_HTTPS_ONLY=yes
MOUNTINFO_ESCAPES_DECODED=yes
REGRESSION_PASS=yes
DOCKER_SMOKE_TESTS=passed
MODE_2D_PRESERVED=yes

READY_FOR_INDEPENDENT_DEPLOYMENT_REVIEW=yes
READY_FOR_LIMITED_DEMO_DEPLOYMENT=yes (pending the deployment-day X-Real-IP smoke gate documented in the checklist -- never provable locally)
READY_FOR_GENERAL_PUBLIC_BETA=no (this remains a LIMITED demo: single-process/single-replica rate limiting, no distributed abuse defense, no live official-search provider, unchanged from every prior round's scope)
```

```
VERDICT=VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_READY_FOR_REVIEW
```

All changes remain uncommitted and unstaged (`INDEX_EMPTY=yes`,
`STAGED_FILES=0`); `HEAD` is unchanged at
`5079454d90730ac9f7fb23d18fe6b8a5578229a4`.
