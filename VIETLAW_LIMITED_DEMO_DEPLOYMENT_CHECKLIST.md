# VietLaw Limited Demo — Deployment Checklist

> **Correction notice (Deployment Correction Round 1):** the `numReplicas`
> item below has been corrected to a manual dashboard gate (Railway's
> config-as-code schema does not support that field), and a volume-mount /
> traffic-pack-health verification item has been added. See
> `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_1_REPORT.md` for the
> full set of fixes.

> **Correction notice (Deployment Correction Round 2):** the health-check
> item below now requires the EXACT frozen traffic inventory, not just "the
> pack loaded"; a symlink-safety note has been added to the volume item;
> the frontend API URL item now states production is HTTPS-only (no
> `http://localhost` exception); and a new "After public Railway
> deployment" section adds the required manual `X-Real-IP`/rate-limit
> smoke test. See `VIETLAW_LIMITED_DEMO_DEPLOYMENT_CORRECTION_ROUND_2_REPORT.md`
> for the full set of fixes.

Companion to `DEPLOY_RAILWAY_CLOUDFLARE.md` (the step-by-step walkthrough)
and `VIETLAW_LIMITED_DEMO_DEPLOYMENT_ARCHITECTURE_V1.md` (why these
constraints exist). Use this as a literal checklist at deploy time; none of
its boxes were checked as part of preparing this document — no deployment
was performed.

## Before deploy

- [ ] The commit being deployed passed the full regression suite (see
      `VIETLAW_LIMITED_DEMO_DEPLOYMENT_READINESS_REPORT_V1.md` for the
      exact commands and last-known results).
- [ ] `git status` is clean on the deploy branch (no uncommitted local
      changes silently riding along).
- [ ] `VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` is `0` (or unset) in every
      environment this will be deployed to.
- [ ] `VIETLAW_TRAFFIC_PACK_ENABLED=1` and `VIETLAW_FAST_DEMO_V2_ENABLED=1`
      are set (both required for the traffic-pack and rental-deposit
      verticals to be reachable at all).
- [ ] `CORS_ORIGINS` contains only exact origins the owner controls — no
      `*`, no `*.pages.dev` suffix pattern.
- [ ] `CHAT_DB_PATH` points under `/data` (the mounted volume), not the
      image-relative default. This is now enforced at startup (Deployment
      Correction Round 1, HIGH-01): a deploy with this misconfigured, or
      with no volume actually attached, fails to start rather than silently
      falling back to ephemeral storage.
- [ ] The Railway volume is actually attached and mounted at `/data`
      (Service → Settings → Volumes) — not just a `CHAT_DB_PATH` value
      pointing there with nothing attached. The volume must contain only
      plain directories and regular files (Deployment Correction Round 2,
      MEDIUM-02): a symlink anywhere under `/data` makes the container
      refuse to start (`docker-entrypoint.py` fails closed rather than
      following it). A very large pre-existing file count on the volume
      increases container cold-start time roughly linearly (recursive
      ownership repair) — budget for this if migrating/restoring a large
      volume.
- [ ] `VIETLAW_TRUST_PROXY_HEADERS=1` is set (Deployment Correction Round 1,
      MEDIUM-02) so the rate limiter uses Railway's `X-Real-IP`, not the
      spoofable `X-Forwarded-For`, for per-client identity. This has only
      been verified LOCALLY — see "After public Railway deployment" below
      for the required deployment-day confirmation that Railway's actual
      edge behaves as expected.
- [ ] `VITE_API_BASE_URL` is set in the Cloudflare Pages **Production**
      environment variables, pointing at the real Railway backend domain
      with the `https://` scheme. Production is HTTPS-only (Deployment
      Correction Round 2, MEDIUM-03): `http://`, including
      `http://localhost`/`http://127.0.0.1`/`http://[::1]`, is rejected
      both at runtime and at `vite build` time — a missing or `http://`
      value now FAILS THE BUILD itself (Cloudflare Pages shows the build
      as failed), not merely a later runtime error in the browser.
- [ ] No real secret (API key, credential) appears in any committed file —
      re-run a secret scan over the diff being deployed if anything
      touched configuration.
- [ ] If this deploy changes the SQLite schema (a new table/column a store
      class expects), a backup of the current `/data` volume exists first
      (see "Rollback" below — Railway volume snapshots or a manual `sqlite3
      .backup` copy).
- [ ] Exactly 1 replica is set in the Railway dashboard (Service → Settings
      → Scaling/Replicas). `railway.toml` does NOT set `numReplicas`
      (Deployment Correction Round 1, MEDIUM-03 — Railway's config-as-code
      schema does not support that field, and it is silently ignored if
      present) — this is a MANUAL gate with no config-as-code enforcement;
      verify it after every configuration import or dashboard change, never
      scaled up for this SQLite-backed configuration.

## Deploy

- [ ] Railway backend service redeployed from the intended commit; build
      logs show `Successfully built`/`Successfully tagged` with no
      unexpected COPY of `.env`, `backend/`, or `frontend/`.
- [ ] `GET /api/health` on the new deployment returns `200` with
      `"status":"ok"` before routing real traffic to it, including
      `"traffic_pack_exact_inventory_valid":true` (Deployment Correction
      Round 2, MEDIUM-01) — a pack that merely "loaded" but does not match
      the frozen 15-total/3-enabled/12-disabled inventory now fails this
      check too.
- [ ] Cloudflare Pages frontend redeployed from the same commit; build logs
      show the `frontend/` root, `npm run build`, and `dist` output
      directory were used.
- [ ] A quick browser smoke test (see `DEPLOY_RAILWAY_CLOUDFLARE.md` step
      10) confirms: landing page loads, a curated traffic answer renders
      with its citation cards, no CORS error in the console, and the
      Network tab shows requests to the Railway domain (never
      `localhost`).
- [ ] `CORS_ORIGINS` on the backend has been updated to the ACTUAL
      Cloudflare Pages URL (not a placeholder) if the Pages project's
      domain wasn't already known when the backend was first configured.

## After deploy

- [ ] Watch Railway logs for the first several minutes for unexpected 5xx
      responses or repeated restarts.
- [ ] Confirm the mounted volume shows a growing `vietlaw_chat.sqlite3`
      file size as real traffic arrives (proves persistence is actually
      wired, not merely configured).
- [ ] Record the deployed commit hash somewhere the team can find it (a
      release note, a pinned message, etc.) so a rollback target is known
      later.

## After public Railway deployment (deployment-day manual gate)

Deployment Correction Round 2 (LOW-03): the rate limiter's local logic
(never trusting `X-Forwarded-For`, validating `X-Real-IP` before use) has
been proven correct by unit and Docker-local tests, but only a REAL
Railway deployment can prove what Railway's actual edge puts in
`X-Real-IP` for real traffic. This is a manual, deployment-day gate — not
something any local test, including this repository's own Docker smoke
tests, can substitute for.

1. From ONE unchanged real client/machine/network (do not switch machines,
   networks, or use a VPN/proxy change between the two requests), send two
   `POST /api/analyze` requests that each set a DIFFERENT,
   attacker-chosen `X-Forwarded-For` value.
2. Confirm the two requests share the SAME rate-limit bucket (the second
   one is limited according to the configured per-IP window, exactly as if
   no `X-Forwarded-For` header had been sent at all) — proving the deployed
   backend is not accidentally trusting the attacker-controlled header.
2a. Separately, as a distinct test, use a SECOND machine or network (or a
    VPN/proxy change) to send a request from a genuinely different real
    client. Confirm this distinct real client receives its OWN,
    independent rate-limit bucket (i.e., `X-Real-IP` correctly
    distinguishes real clients from one another) — this is what the
    two-machine setup is for; it must not be combined with step 1's
    same-client requirement.
3. Confirm Railway is actually supplying a valid `X-Real-IP` on requests it
   forwards (check backend logs or a temporary debug endpoint/log line) —
   an empty or missing `X-Real-IP` from Railway's edge would silently fall
   back to `request.client.host`, which may be Railway's own internal
   proxy address rather than the real client, collapsing all traffic into
   one shared bucket.
4. Confirm a client cannot override or spoof the edge-observed identity —
   i.e., that setting `X-Real-IP` directly (bypassing Railway's edge is
   not possible from the public internet, but confirm this assumption
   holds for the actual deployed network topology).
5. **If any of the above cannot be verified**, treat per-IP rate limiting
   as best-effort only for this deployment, and keep the conservative
   per-conversation (`VIETLAW_RATE_LIMIT_PER_CONVERSATION_PER_MINUTE`) and
   concurrency (`VIETLAW_MAX_CONCURRENT_REQUESTS`) limits enabled as the
   primary abuse defenses — do not rely on per-IP limiting alone.

## Rollback

Ordered from least to most disruptive — stop at the first step that
actually resolves the issue.

1. **Disable the traffic pack via feature flag** (a single traffic
   response was found wrong or unsafe, but the rest of the demo is fine):
   set `VIETLAW_TRAFFIC_PACK_ENABLED=0` on the Railway service and
   redeploy/restart. This disables ALL curated traffic behavior (every
   topic, not just one rule) without touching MODE_2D (the rental-deposit
   flow) at all — `_build_legal_fallback_orchestrator` in
   `dependencies.py` returns `None` when this flag is off, so the vertical
   is never constructed and every traffic-shaped message falls through to
   the pre-existing baseline/general-guidance path instead.
2. **Disable all public traffic behavior without touching MODE_2D**: same
   as step 1 -- there is no finer-grained "disable just the new
   verticals but keep everything else" switch needed, because
   `VIETLAW_TRAFFIC_PACK_ENABLED` and `VIETLAW_FAST_DEMO_V2_ENABLED` are
   already independent flags. Setting only the traffic flag to `0` leaves
   FAST DEMO V2's OWN rental-deposit conversation (MODE_2D) completely
   unaffected, since that flow does not depend on the traffic pack at all.
3. **Roll back the Railway deployment**: Railway dashboard → the service →
   **Deployments** → select the last known-good deployment → **Redeploy**.
   This reverts the running container image without touching the SQLite
   volume's data.
4. **Roll back the Cloudflare Pages deployment**: Pages project →
   **Deployments** → select the last known-good deployment → **Rollback to
   this deployment** (Cloudflare keeps prior deployments available for
   exactly this purpose; no rebuild needed).
5. **Restore a previous volume snapshot or backup** — only if the SQLITE
   DATA itself (not just the code) is suspected corrupted, and only after
   taking a fresh backup of the CURRENT (possibly bad) state first, in case
   the restore itself needs to be undone. This is the most disruptive step
   (a live restore risks losing any writes made after the restore point) and
   requires an explicit decision, never an automatic trigger.
6. **Disable public domains** (last resort — takes the demo fully offline):
   Railway service → **Settings → Networking → Remove Domain**, and/or
   pause the Cloudflare Pages project. Use this only if the demo itself
   must stop being reachable (e.g. an active safety incident), not for a
   routine rollback.

None of steps 3–6 above are automated by anything in this repository — each
is a deliberate, manual action the owner takes in the Railway/Cloudflare
dashboards. Nothing in this codebase performs an automatic destructive
rollback.
