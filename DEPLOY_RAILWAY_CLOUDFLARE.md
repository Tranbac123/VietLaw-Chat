# VietLaw Limited Demo — Railway + Cloudflare Pages Deploy Guide

> **Correction notice (Deployment Correction Round 1):** an independent
> review found this guide understated what happens without the volume
> (Step 3), overstated the root `.nvmrc` as an effective Pages pin (Step 7),
> and described `numReplicas` as an enforced setting. This document has been
> corrected in place; see
> `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_REPORT.md` for the
> full set of fixes. The original readiness report itself is left as a
> historical record with its own correction notice, not silently rewritten.

> **Correction notice (Deployment Correction Round 2):** a second
> independent re-verification found the traffic-pack health check (Step 6),
> the volume-ownership repair (Step 3), and the frontend API URL step
> (Step 8) still had gaps: health accepted a mutated traffic pack as
> healthy; the entrypoint followed a file symlink under `/data` and
> chowned a target outside the volume; and a production build accepted
> `http://localhost`/`http://127.0.0.1`. This guide is corrected in place
> again; see `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_REPORT.md`
> for the full set of fixes. No actual Railway/Cloudflare deployment has
> occurred at any point in this repository's history -- every verification
> referenced by any correction notice was performed locally (pytest,
> local Docker via Colima, local `vite build`), never against a live
> Railway or Cloudflare project.

This is a step-by-step guide for the repository owner to perform the ACTUAL
deployment. **None of these steps were executed as part of preparing this
guide or the rest of the deployment-readiness work** — no Railway project,
Cloudflare Pages project, or public domain was created; no code was pushed;
nothing was deployed. Everything here was validated locally (backend test
suite, a local Docker build + container smoke test, a local frontend
production build + static-serve check) — see
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_READINESS_REPORT_V1.md` for exact commands
and results.

This is a **limited demo** deployment, not a production launch. See
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md` for the constraints
that shape every step below (single backend replica, SQLite-on-volume, no
official legal search, in-process rate limiting).

## Prerequisites

- A Railway account with billing configured (the free tier may not include
  a persistent volume).
- A Cloudflare account with Pages enabled.
- Push access to this repository (or a fork the owner controls).
- The reviewed commit the owner intends to deploy, already on the intended
  branch.

## Step 1 — Push the reviewed commit

```bash
git push origin <branch>
```

Deploy only a commit that has already passed the regression suite in
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_READINESS_REPORT_V1.md` (or an equivalent
later run). Do not deploy directly from an uncommitted working tree.

## Step 2 — Create the Railway project (backend)

1. In the Railway dashboard: **New Project → Deploy from GitHub repo**.
2. Select this repository and the branch/commit to deploy.
3. Railway will detect a Dockerfile. Under the service's **Settings →
   Build**, explicitly set:
   - **Builder**: Dockerfile
   - **Dockerfile Path**: `Dockerfile.backend`
   - (Root directory should remain the repository root — the Dockerfile's
     `COPY` paths are written relative to the repo root, not
     `backend_lite/`.)

`railway.toml` (repository root) already declares the Dockerfile path and
the health-check/restart settings; Railway will read it automatically once
the service exists, but verify the dashboard reflects it after the first
deploy. **`numReplicas` is NOT part of Railway's config-as-code schema and
is not set here** (Deployment Correction Round 1, MEDIUM-03) — exactly one
replica is instead a MANUAL setting: Service → **Settings →
Scaling/Replicas → 1**. Verify this after every configuration import and
after every dashboard change; nothing in `railway.toml` enforces it. See
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md`, "Why one replica", for
why a second replica is unsafe with this SQLite-on-a-volume design.

## Step 3 — Attach the persistent volume

1. Service → **Settings → Volumes → Add Volume**.
2. **Mount path**: `/data`
3. Pick a size appropriate for a limited demo (a few GB is generous headroom
   for SQLite chat history at this scale).

**This step is not optional — do it before the first deploy.** Deployment
Correction Round 1 (HIGH-01) closed the previous silent-ephemeral-fallback
behavior: the backend now REFUSES to start in `APP_ENV=production` unless
`CHAT_DB_PATH` resolves under `/data` AND `/data` is verified (via
`/proc/self/mountinfo`, not merely `exists()`) to be an actual mounted
Railway volume. Deploying without this step no longer "still starts and
answers requests" — the container exits immediately with a
`ProductionStorageError` in the logs, and Railway's health check never
turns healthy. There is no ephemeral-storage fallback to accidentally rely
on; attaching the volume is a hard prerequisite, not an optimization.

Railway also mounts a fresh volume **root-owned**, regardless of the
image's declared user. `docker-entrypoint.py` (Deployment Correction Round
1, HIGH-02) handles this automatically: the container starts as root just
long enough to `chown` `/data` (and any existing database file on it) to
the application's own user, then drops privileges and execs Uvicorn as
that unprivileged user (UID 999) before any request is served — no manual
`RAILWAY_RUN_UID` override is needed for this to work.

Ownership repair is symlink-safe (Deployment Correction Round 2, MEDIUM-02):
if ANY symlink is found anywhere under `/data` (a file or directory
symlink), the container refuses to start rather than following it (an
earlier version's `chown` call followed a file symlink and changed
ownership of a file OUTSIDE `/data` — a concrete ownership escape, since
fixed). A normal deployment never places a symlink on this volume, so this
should never be observed in practice; if it is, treat it as a signal to
investigate, not something to bypass. This recursive repair walks every
file and directory on the volume once per container start — its cost is
O(number of entries on the volume), so a volume accumulating a very large
number of files over time may see a correspondingly longer cold start;
this is an accepted limited-demo trade-off.

## Step 4 — Set backend environment variables

Service → **Variables**. Set every variable listed in `.env.example`'s
"VietLaw Limited Demo — Railway deployment configuration" section. At
minimum:

```text
APP_ENV=production
LOG_LEVEL=info
BACKEND_MODE=lite
CHAT_DB_PATH=/data/vietlaw_chat.sqlite3
VIETLAW_FAST_DEMO_V2_ENABLED=1
VIETLAW_TRAFFIC_PACK_ENABLED=1
VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED=0
CORS_ORIGINS=https://<your-project>.pages.dev
VIETLAW_RATE_LIMIT_ENABLED=1
VIETLAW_RATE_LIMIT_PER_IP_PER_MINUTE=20
VIETLAW_RATE_LIMIT_PER_CONVERSATION_PER_MINUTE=12
VIETLAW_MAX_MESSAGE_CHARS=3000
VIETLAW_MAX_CONCURRENT_REQUESTS=4
VIETLAW_TRUST_PROXY_HEADERS=1
```

`VIETLAW_TRUST_PROXY_HEADERS=1` (Deployment Correction Round 1, MEDIUM-02)
tells the rate limiter to trust Railway's own edge-supplied `X-Real-IP`
header for per-client identity. `X-Forwarded-For` is never trusted for this
regardless of this setting — it is attacker-controlled end-to-end (any
client can set it directly against this backend), and the independent
deployment review demonstrated a rotating-`X-Forwarded-For` bypass of the
per-IP limit before this fix. Only set this to `1` in the actual Railway
deployment, where `X-Real-IP` is genuinely edge-supplied; leave it unset for
local development.

`CORS_ORIGINS` cannot be finalized until Step 8 (Cloudflare Pages assigns
its own domain on first deploy) — set it to a placeholder now, come back
and correct it in Step 9.

If the limited demo is meant to also run the live FAST DEMO V2 rental-
deposit conversation (an LLM-backed flow, separate from the fully
deterministic traffic pack), also set `VIETLAW_LLM_ENABLED=1`,
`VIETLAW_LLM_MODEL`, and a real `ANTHROPIC_API_KEY` — directly in the
Railway dashboard's Variables UI, never committed to the repository.

**Do not set `VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED=1`.** No live-search-
provider integration exists in this codebase (see
`legal_fallback_orchestrator.py`'s docstring); enabling the flag without a
real provider does not add a capability, it only risks over-claiming one.

## Step 5 — Generate the backend's public domain

Service → **Settings → Networking → Generate Domain**. Railway assigns a
`*.up.railway.app` URL and internally maps `$PORT`; `Dockerfile.backend`'s
`CMD` already binds `0.0.0.0:${PORT}`, so no further networking
configuration is needed.

## Step 6 — Verify the health endpoint

```bash
curl -i https://<your-backend>.up.railway.app/api/health
```

Expect `HTTP/2 200` and
`{"status":"ok","rag_loaded":true,"safety_loaded":true,"chat_store_ready":true,"traffic_pack_required":true,"traffic_pack_loaded":true,"traffic_enabled_rule_count":3,"traffic_pack_exact_inventory_valid":true,...}`.
A `503` with `"status":"degraded"` means a data file failed to load, the
SQLite volume isn't writable, or (Deployment Correction Round 1, MEDIUM-01;
tightened Round 2, MEDIUM-01) `VIETLAW_TRAFFIC_PACK_ENABLED=1` but the
curated traffic pack either failed to load/construct OR loaded with the
wrong inventory — health now requires EXACTLY 15 total rows, exactly 3
enabled rules, exactly 12 disabled rows, and the enabled rule IDs equal to
exactly `traffic_red_light__motorcycle__safe_v1`,
`traffic_red_light__car__safe_v1`,
`traffic_no_helmet__motorcycle__driver_safe_v1` — not merely "the file
parsed." Check the service logs before proceeding (the health response
body itself never includes a path, exception text, or the specific
mismatch). If the container never reaches a running state at all (no
health response, ever), see Step 3: this now means either the production
persistent-storage validation rejected the configuration, or a symlink was
found under `/data`, and the process exited before Uvicorn started.

## Step 7 — Create the Cloudflare Pages project (frontend)

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to
   Git**.
2. Select this repository and branch.
3. Framework preset: **Vite** (or "None", setting the fields manually as
   below).
4. **Root directory**: `frontend`
5. **Build command**: `npm run build`
6. **Build output directory**: `dist`
7. `frontend/.nvmrc` (content `20`) is the effective Node version pin
   (Deployment Correction Round 1, MEDIUM-05) — Cloudflare Pages reads a
   `.nvmrc`/`.node-version` from the configured **project root**, which is
   `frontend` (Step 4 above), not the repository root; a `.nvmrc` at the
   repository root has no effect here and was previously miscited as the
   pin. As defense in depth, also set the **Node.js version** build
   environment variable `NODE_VERSION=20` explicitly in the Pages project's
   build settings if the picker is shown.
8. Use the existing `package-lock.json` (already committed) — do not
   generate a new lockfile or switch package managers.

## Step 8 — Set the frontend's build-time API URL

Pages project → **Settings → Environment variables → Production**. Add:

```text
VITE_API_BASE_URL=https://<your-backend>.up.railway.app
```

using the REAL Railway domain from Step 5, with the exact scheme
`https://` — **not** `http://`. This is a build-time value embedded into
the static bundle (Vite convention — see
`frontend/.env.production.example`), not a secret and not read at request
time; there is nothing else to configure for the frontend to know where its
backend is.

Deployment Correction Round 2 (MEDIUM-03) made this a BUILD-TIME gate, not
only a runtime one: `vite.config.ts` validates `VITE_API_BASE_URL` itself
and fails the `npm run build` command outright (Cloudflare Pages will show
the build as FAILED, not deployed) if the value is missing, malformed, or
uses `http://` — including `http://localhost`/`http://127.0.0.1`/
`http://[::1]`, which an earlier version of this validation incorrectly
still accepted even in a production build. There is no longer a code path
where an invalid or missing value produces a successfully deployed bundle
that only fails later in the browser — see
`VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_REPORT.md` for the
exact accepted/rejected value list and the local `vite build` verification
performed for each.

## Step 9 — Deploy the frontend, then correct the backend's CORS origin

1. Trigger the Pages deploy (push, or **Retry deployment** if the project
   was just created before Step 8's variable was set — Pages only embeds
   env vars set BEFORE the build that uses them).
2. Once deployed, Cloudflare shows the project's `*.pages.dev` URL (and any
   custom domain, if configured).
3. Go back to Railway → the backend service → **Variables** → update
   `CORS_ORIGINS` to the REAL Pages URL from step 2 (comma-separate a
   second entry only if a custom domain is intentionally also served, e.g.
   `https://vietlaw-demo.pages.dev,https://demo.example.com`). Never a
   wildcard or a `*.pages.dev` suffix pattern.
4. Redeploy the backend service (Railway redeploys automatically on a
   variable change, or trigger it manually) so the new CORS origin takes
   effect.

## Step 10 — Browser smoke test

Open the Cloudflare Pages URL in a real browser and manually verify:

- the landing page renders with no console errors;
- sending "Tôi đã đặt cọc thuê nhà 20 triệu cho chủ nhà." gets a real
  response (the deposit flow, if FAST DEMO V2/LLM is configured) or a safe
  fallback (if not);
- sending "Tôi đi xe máy vượt đèn đỏ, không gây tai nạn." gets a
  `curated_verified` trust badge with 3 red-light citation cards (Căn cứ
  mức phạt / Căn cứ trừ điểm GPLX / Quy tắc tín hiệu giao thông);
- sending "Tôi dùng tay cầm điện thoại khi đang chạy xe máy." (the disabled
  phone rule) gets general guidance, never a specific penalty;
- the browser devtools Network tab shows requests going to the Railway
  domain, never `localhost`;
- no CORS error appears in the console.

This step is inherently manual (it requires an actual deployed instance and
a real browser) and was NOT performed as part of preparing this guide.

## Known limitations (repeated from the architecture report)

- Single backend replica only — see
  `VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md`, "Why one replica".
- The rate limiter is in-process and resets on every restart/redeploy.
- Official legal search is off; there is no live-search-provider
  integration to turn on.
- This SQLite-on-a-single-volume design does not horizontally scale and is
  not intended to.

## Rollback

See `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CHECKLIST.md`, "Rollback", for the full
procedure (feature-flag disablement, Railway/Pages deployment rollback,
volume backup restore).
