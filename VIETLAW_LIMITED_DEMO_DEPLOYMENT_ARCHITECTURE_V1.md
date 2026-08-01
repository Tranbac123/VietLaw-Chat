# VietLaw Limited Demo — Deployment Architecture V1

> **Correction notice (Deployment Correction Round 1):** an independent
> review found the SQLite persistence contract, the "one replica" section,
> and the rate-limiter's IP-identity claim understated real risk (a
> misconfigured deploy previously started successfully on ephemeral
> storage, and `X-Forwarded-For` was spoofable in a way this document
> characterized as "not realistic" for a Railway-fronted deployment, which
> an independent live probe disproved). This document has been corrected in
> place; see `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_REPORT.md`
> for the full set of fixes.

> **Correction notice (Deployment Correction Round 2):** a second
> independent re-verification found three of the Round 1 fixes themselves
> incomplete: the traffic-pack health check accepted a mutated pack (wrong
> enabled count/IDs/total rows) as healthy since it only checked "did it
> load," not "does it match the frozen inventory"; the Docker entrypoint's
> ownership repair FOLLOWED a file symlink under `/data` and changed
> ownership of a target outside the volume; and the frontend accepted
> `http://localhost`/`http://127.0.0.1` in an actual production build.
> This document has been corrected in place again; see
> `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_REPORT.md` for the
> full set of fixes.

This document describes the architecture PREPARED for a limited-demo
deployment. No cloud resources were created and no deployment was
performed while writing it — see
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_READINESS_REPORT_V1.md` for what was
actually verified (locally, with a local Docker build and a local frontend
production build) versus what remains a manual owner action (see
`DEPLOY_RAILWAY_CLOUDFLARE.md`).

## Components

```text
Browser
  |  HTTPS
  v
Cloudflare Pages -- static React/Vite frontend (frontend/, npm run build -> dist/)
  |  HTTPS (fetch, JSON)
  v
Railway -- one FastAPI backend replica (backend_lite/, Dockerfile.backend)
  |
  v
Railway persistent volume, mounted at /data
  |
  v
One SQLite file: /data/vietlaw_chat.sqlite3
  (chat history, FAST DEMO V2 state, legal-fallback state, and
   idempotency receipts all live here as separate TABLES in the
   same file -- not separate files; see config.py::Settings.chat_db_path
   and dependencies.py::build_container)
```

Deployment Correction Round 1 (HIGH-01) made this diagram's `/data` mount a
HARD requirement, not just an intended configuration: `build_container`
calls `storage_readiness.py::validate_persistent_storage` before
constructing any store, and refuses to start in `APP_ENV=production` unless
`CHAT_DB_PATH` resolves under `/data` AND `/data` is verified (via
`/proc/self/mountinfo`, not merely `Path.exists()`) to be an actual mounted
filesystem, not a directory the image's own writable layer happened to
create. There is no ephemeral-storage fallback path left in production --
prior wording describing one has been removed throughout this document.

Curated legal data (`data/legal_snippets.json`, `data/traffic_rules.json`,
`data/unsafe_patterns.json`) is READ-ONLY and ships baked into the backend
image — it is not on the volume and does not need to persist across
restarts; a new image redeploy is how it gets updated.

`backend/` (a separate implementation owned by another team member) is
never built, started, or referenced by any file in this deployment
configuration.

## Network flow

1. The browser loads the Cloudflare Pages static bundle over HTTPS.
2. The bundle's JS makes `fetch()` calls to `VITE_API_BASE_URL` (embedded
   at Pages build time) — the Railway backend's public HTTPS domain.
3. The backend's `CORSMiddleware` checks the request's `Origin` header
   against the exact-origin allowlist in `CORS_ORIGINS`; only a match gets
   `Access-Control-Allow-Origin` in the response (see
   `backend_lite/app/main.py`).
4. `RateLimitMiddleware` (feature-flagged, `VIETLAW_RATE_LIMIT_ENABLED`)
   checks `POST /api/analyze` specifically against message-length,
   per-IP, per-conversation, and concurrency limits before the request
   reaches routing.
5. The FastAPI route handler reads/writes the single SQLite database on
   the mounted volume.
6. The response returns back through the same path; no server-side
   session state exists outside that one SQLite file (a redeploy loses
   only the rate limiter's in-memory counters, never chat data).

No component in this flow calls a live LLM or a live legal-search provider
unless the owner explicitly configures `VIETLAW_LLM_ENABLED`/
`ANTHROPIC_API_KEY` for the FAST DEMO V2 rental-deposit conversation.
`VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` must remain `0`: no concrete
search-provider integration exists in this codebase for it to enable (see
`legal_fallback_orchestrator.py`'s docstring and
`dependencies.py::_build_legal_fallback_orchestrator`'s "Known
limitations" note) — turning the flag on would not add a capability, only
misrepresent one.

## Trust boundaries

- **Browser <-> Cloudflare Pages**: standard HTTPS static-asset delivery;
  no secrets are involved (a `VITE_*` variable is embedded in the public
  bundle, never a credential).
- **Browser <-> Railway backend**: the only boundary that carries user
  input. Exact-origin CORS limits which web origins a browser will permit
  a credentialed cross-origin call from; the rate limiter and message-
  length cap bound abuse from any origin (a non-browser client isn't
  stopped by CORS at all, since CORS is a browser-enforced convention, not
  a server-side access control — the rate limiter and length cap are the
  actual server-side defenses).
- **Railway backend <-> SQLite volume**: trusted, same-machine (same
  container, mounted volume) I/O — no network boundary, no additional
  auth needed.
- **Railway backend <-> official legal search / live LLM**: OFF by
  default and, for official search, structurally unimplemented regardless
  of the flag. If FAST DEMO V2's LLM path is enabled, `ANTHROPIC_API_KEY`
  is the one real secret in this whole deployment — it must be set only
  as a Railway dashboard variable, never committed, never embedded in the
  frontend bundle (Vite `VITE_*` variables are NOT a place for it).

## SQLite limitation

All persistent state (deposit-flow chat state, traffic-pack per-chat
state, request idempotency receipts, and raw chat/message history) shares
ONE SQLite file. SQLite handles concurrent access from multiple
CONNECTIONS within a single process fine (this backend already does that
for its own request handling), but:

- it does not tolerate multiple independent OS PROCESSES writing
  concurrently as gracefully as a client/server database would under real
  concurrent load (lock contention increases latency and, under enough
  concurrent writers, can produce `database is locked` errors);
- it has no built-in replication or multi-region story.

This is an accepted, explicit trade-off for a LIMITED DEMO, not a
production data-tier choice — see "Why one replica" below for the
consequence that actually matters operationally.

## Why one replica is required

Two independent reasons, either one alone would be sufficient:

1. **SQLite correctness under concurrent writers.** Two backend processes
   (two Railway replicas) both opening the SAME file on the SAME mounted
   volume are two independent OS processes writing to one SQLite
   database — a configuration SQLite tolerates only under careful
   WAL-mode + retry-timeout tuning, neither of which this codebase's
   stores currently implement (they use SQLite's default rollback-journal
   mode with a fixed connect timeout — see e.g.
   `stores/sqlite_chat_store.py::_open_connection`). Running two replicas
   as-is risks intermittent `database is locked` errors under any real
   simultaneous traffic from both replicas.
2. **The in-process rate limiter's counters are per-process.**
   `guards/rate_limiter.py`'s `FixedWindowRateLimiter`/`ConcurrencyLimiter`
   live in one Python process's memory. With two replicas behind a load
   balancer, each replica would enforce the configured limit
   INDEPENDENTLY — a client alternating between replicas could send up to
   2x the configured `VIETLAW_RATE_LIMIT_PER_IP_PER_MINUTE` before either
   replica individually notices, silently undermining the whole point of
   the limiter.

Exactly one replica is required for these reasons, but (Deployment
Correction Round 1, MEDIUM-03) `railway.toml` does NOT set `numReplicas` --
that field is not part of Railway's actual config-as-code schema and is
silently ignored if present. This is instead a MANUAL Railway dashboard
gate: Service → Settings → Scaling/Replicas → exactly 1, verified after
every configuration import and every dashboard change. Scaling this
configuration to more than one replica would require, at minimum,
migrating off single-file SQLite to a real client/server database and
replacing the in-process rate limiter with a shared store (e.g. Redis) --
both explicitly out of scope for "limited demo."

## Rate-limit limitation

`backend_lite/app/api/rate_limit_middleware.py` implements a bounded,
single-process, in-memory limiter (see its own module docstring and
`guards/rate_limiter.py`'s). It is feature-flagged
(`VIETLAW_RATE_LIMIT_ENABLED`, default off) and, when enabled, applies
ONLY to `POST /api/analyze` (never `/api/health` or any `GET
/api/chats*` read endpoint). Explicit limitations:

- resets to zero on every process restart or redeploy;
- only correct in aggregate with exactly one replica (see above);
- fixed-window, not sliding-window or token-bucket — a client can send a
  burst right at a window boundary that a stricter algorithm would have
  smoothed;
- (Deployment Correction Round 1, MEDIUM-02) keys on Railway's own
  edge-supplied `X-Real-IP` header, validated with `ipaddress.ip_address()`,
  when `VIETLAW_TRUST_PROXY_HEADERS=1`; falls back to the raw ASGI socket
  peer if that header is absent/malformed or trusted-proxy mode is off.
  `X-Forwarded-For` is NEVER used for this identity, in any mode -- an
  independent deployment review's live probe demonstrated that trusting its
  first entry let a client bypass the per-IP limit entirely simply by
  rotating the header value on each request, directly against this
  backend, with no proxy involved. This was previously (incorrectly)
  characterized here as "not a realistic concern for a Railway-fronted
  deployment"; the fix removes the trust in `X-Forwarded-For` rather than
  relying on network topology to prevent the bypass. This is still a
  single-process, single-replica limiter, not a hardened, horizontally
  scalable rate limiter.
- (Deployment Correction Round 2, LOW-03) all local testing above proves
  the LOCAL logic is correct (no `X-Forwarded-For` trust, `X-Real-IP`
  validated before use) — it does NOT and cannot prove what Railway's
  actual production edge puts in `X-Real-IP` for a real deployment. That
  is a deployment-day manual gate, not a local proof of Railway edge
  sanitization; see `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md`,
  "After public Railway deployment," for the exact steps. If it cannot be
  verified on the day, per-IP limiting must be treated as best-effort and
  the per-conversation/concurrency limits kept as the primary defense.

This is explicitly not a distributed production rate limiter and is not
meant to become one; see `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md`
for what changes if this demo ever needs to scale beyond one replica.

## Feature flags

| Flag | Deployment value | Effect when off |
|---|---|---|
| `VIETLAW_FAST_DEMO_V2_ENABLED` | `1` | The rental-deposit conversational flow and its routing layer never construct; the runtime behaves like the pre-FAST-DEMO-V2 baseline. |
| `VIETLAW_TRAFFIC_PACK_ENABLED` | `1` | The entire curated traffic vertical (all 3 enabled Safe Subset V1 rules) is never constructed; every traffic-shaped message falls through to the baseline/general pipeline instead. |
| `VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` | `0` (must stay 0) | No live web search is ever attempted; the legal-fallback vertical's non-curated answers are always `general_guidance`. |
| `VIETLAW_RATE_LIMIT_ENABLED` | `1` | `RateLimitMiddleware` becomes a pure pass-through; every request reaches routing unthrottled. |
| `VIETLAW_LLM_ENABLED` | owner's choice | Governs only FAST DEMO V2's own LLM call for the deposit conversation -- the traffic vertical never needs an LLM regardless of this flag. |

## Failure behavior

- **A curated data file fails to load** (`legal_snippets.json`,
  `unsafe_patterns.json`, or the traffic pack): `/api/health` reports
  `"status":"degraded"` with HTTP `503` (see `routes_health.py`) --
  Railway's health check fails, the deployment is marked unhealthy, and
  (per `railway.toml`'s restart policy) the container is restarted, which
  does not fix a genuinely missing/malformed file (a code or image issue,
  not a transient one) — this is a signal for the owner to investigate,
  not something that self-heals.
- **The SQLite volume is not writable**: `chat_store.ready` becomes
  `False`, which also degrades `/api/health` to `503` for the same
  Railway-visible signal.
- **`CHAT_DB_PATH`/`/data` misconfigured in production** (Deployment
  Correction Round 1, HIGH-01): not a `/api/health` degradation -- the
  container fails to START at all (`ProductionStorageError`, uncaught),
  before any SQLite file is ever created. This is a stricter, earlier
  failure than the SQLite-volume-not-writable case above, which assumes a
  real, correctly configured mount that later becomes unwritable.
- **`VIETLAW_TRAFFIC_PACK_ENABLED=1` but the traffic pack fails to
  load/construct, OR loads but does not match the frozen inventory**
  (Deployment Correction Round 1, MEDIUM-01; tightened in Round 2,
  MEDIUM-01): `/api/health` reports `"status":"degraded"` with HTTP `503`,
  same as a missing curated data file. "Match the frozen inventory" is an
  EXACT gate, not a load-success check: exactly 15 total rows, exactly 3
  enabled rules, exactly 12 disabled rows, and the enabled rule IDs equal
  to exactly `{traffic_red_light__motorcycle__safe_v1,
  traffic_red_light__car__safe_v1,
  traffic_no_helmet__motorcycle__driver_safe_v1}` -- a pack that PARSES
  successfully but has been mutated (wrong count, an extra/different
  enabled ID, a wrong total/disabled row count) now fails this check too,
  not only a pack that fails to parse at all. When the flag is off, the
  pack's absence is intentional and never affects this check. No path,
  exception text, or the mismatch detail itself is ever exposed in the
  response body -- only the boolean gate.
- **A freshly mounted Railway volume is root-owned** (Deployment Correction
  Round 1, HIGH-02; hardened in Round 2, MEDIUM-02): `docker-entrypoint.py`
  repairs ownership at container start (before Uvicorn runs) and drops
  privileges to the application's own UID -- this is transparent and
  requires no owner action, but a genuinely read-only volume still fails
  ownership repair and exits the container immediately, with a clear
  one-line error in the logs (never a raw traceback, never a silent
  continuation as root). Traversal is symlink-safe: ANY symlink found
  anywhere under `/data` (file or directory) also fails startup closed,
  with a clear one-line error -- the entrypoint does not follow it,
  chown it, or silently skip it, since an earlier version's `os.chown()`
  call followed a file symlink and changed ownership of a target OUTSIDE
  `/data` (a concrete ownership escape, found and fixed in Round 2). This
  recursive repair is O(number of files/directories on the volume) --
  a volume with a very large number of pre-existing files may see a
  correspondingly longer container cold-start time; this is an accepted
  limited-demo trade-off, not tuned or bounded further here.
- **The Anthropic/LLM provider is slow or down** (only relevant if FAST
  DEMO V2's LLM path is enabled): FAST DEMO V2's own timeout/fallback
  handling degrades that ONE conversation turn; it never blocks or fails
  `/api/health`, and never affects the fully deterministic traffic
  vertical.
- **A client exceeds the rate limit**: a structured `429` with
  `Retry-After`, never a 5xx, never a dropped connection.
- **An unexpected exception anywhere in a request**: caught by
  `register_error_handlers`'s catch-all handler, logged server-side with
  a full stack trace, and returned to the client as a generic
  `internal_error` message with NO stack trace, file path, or
  configuration detail (see `api/error_handlers.py`).

## Rollback strategy

Summarized here; the full step-by-step lives in
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md`, "Rollback":

1. Feature-flag off the traffic pack (`VIETLAW_TRAFFIC_PACK_ENABLED=0`) --
   the fastest, least disruptive option, and it never touches MODE_2D.
2. Roll back the Railway deployment to the last known-good build.
3. Roll back the Cloudflare Pages deployment to the last known-good build.
4. Restore a volume snapshot/backup, only if the DATA (not the code) is
   suspected corrupted, and only after backing up the current state first.
5. Remove the public domain(s), only as a last resort to take the demo
   fully offline.

No automatic destructive rollback exists anywhere in this configuration --
every one of the above is a deliberate, manual owner action.
