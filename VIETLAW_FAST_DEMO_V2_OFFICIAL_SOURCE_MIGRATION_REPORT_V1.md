# VietLaw Fast Demo V2 — Official-Source Migration Report V1

Date: 2026-07-29 (Asia/Ho_Chi_Minh)
Revision: V1 rev-6 (accepted by owner)
Implementer: `CLAUDE_CODE_SONNET`

## CURRENT VERDICT

`VIETLAW_OFFICIAL_SOURCE_MIGRATION_ACCEPTED_BY_OWNER`

Both independent reviews passed and the owner has accepted the migration:

```text
MIGRATION_COMMIT=2dc883fa8547599d4400d3e1721a0941f60f20a5
CORRECTION_COMMIT=1471cd98209301ae506ff922f8a08c975f50aee3
INITIAL_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS_OPEN=0
OFFICIAL_SOURCE_MIGRATION_ACCEPTED=yes
```

The initial independent review found only nonblocking findings (subsequently
closed as LOW-01/LOW-02, see "CORRECTION ROUND 1" below); the correction's
own independent re-verification returned a clean pass with zero open
findings of any severity.

### Final invariants confirmed

```text
DOCUMENT_NUMBER=91/2015/QH13
PRIMARY_OFFICIAL_SOURCE_CORRECT=yes
LEGACY_ACTIVE_SOURCE_REMOVED=yes
EXACT_HOST_VALIDATION_ACTIVE=yes
MALFORMED_PORT_REJECTED=yes
BUILD_FAILURE_ATOMIC=yes
CURATED_URLS_CHANGED_BY_CORRECTION=no
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
MODE_2_STARTED=no
```

Two commits together constitute the accepted migration:

```text
2dc883fa8547599d4400d3e1721a0941f60f20a5  fix(data): migrate civil code to official sources
1471cd98209301ae506ff922f8a08c975f50aee3  fix(data): harden official source URL validation
```

containing exactly the two owned tracked paths for the correction --
`backend_lite/app/services/official_source_hosts.py` and
`backend_lite/tests/unit/test_official_source_hosts.py` -- on top of, not
amending, `2dc883fa8547599d4400d3e1721a0941f60f20a5`. No curated URL, legal
data, or Markdown authoring file changed by the correction; rendered output
is byte-identical to the already owner-accepted state, so no browser
recheck was required.

```text
LOW01_CLOSED=yes
LOW02_CLOSED=yes
CORRECTION_COMMIT=1471cd98209301ae506ff922f8a08c975f50aee3
CORRECTION_OWNED_TRACKED_PATHS=2
CURATED_URLS_CHANGED=no
DATA_FILES_CHANGED=no
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
SCENARIO_BEHAVIOR_CHANGED=no
BROWSER_RECHECK_REQUIRED=no
MODE_2_STARTED=no
```

This report itself is being updated for owner acceptance as a separate,
documentation-only commit, `docs(data): accept official source migration`
(see the final machine-readable block at the end of this document once
that commit exists).

Everything below down to
**"CORRECTION ROUND 1"** is the unmodified rev-3 record of the accepted
migration commit, kept for the audit trail.

---

The owner's browser checkpoint passed: reveal behavior and pacing unchanged,
the source link points to the official Công báo URL for 91/2015/QH13, the
link opens the correct document, the legacy `vbpl.moj.gov.vn` URL is never
rendered, no duplicate source appears, and the sourceless response still
renders no empty source section. All validation was rerun and passed with the
same totals. One commit was created:

```text
2dc883fa8547599d4400d3e1721a0941f60f20a5  fix(data): migrate civil code to official sources
```

containing exactly the eight implementation/data/test paths from §9 -- no
report was committed. `OWNER_OFFICIAL_SOURCE_MIGRATION_BROWSER_CONFIRMATION=yes`.
MODE_2 was **not** started and no live provider call was spent. Not pushed,
merged, or deployed.

The broken legacy Civil Code source URL (`vbpl.moj.gov.vn`, `ItemID=95942`) has
been replaced with the verified official Công báo Chính phủ URL for
Bộ luật Dân sự 91/2015/QH13, with the Cổng Thông tin Chính phủ URL recorded as
a documented backup and the vbpl.vn entry as an optional tertiary reference.
Legal content, chunk identifiers, retrieval behavior, and Fast Demo UI
behavior are unchanged.

**rev-2 correction (closed):** rev-1 added the exact-host allowlist
(`official_source_hosts.py`) but only unit-tested it in isolation -- it was
not wired into any active build or validation path, so a deceptive or
unauthorized URL could still reach `data/legal_snippets.json` for the bounded
Civil Code IDs undetected. `scripts/build_snippets.py` now calls
`is_trusted_official_host` on `source_url`, `official_backup_url`, and
`official_tertiary_url` for exactly `civil_deposit_001`, `civil_contract_001`,
and `civil_contract_002`, and requires a new `official_document_number:
"91/2015/QH13"` frontmatter field on each, failing the build deterministically
(nonzero exit, no output file written) if any check fails. See §5 and §5b
below.

```text
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
SCENARIO_BEHAVIOR_CHANGED=no
LEGACY_BROKEN_SOURCE_ACTIVE=no
LEGACY_BROKEN_SOURCE_RENDERED=no
PRIMARY_OFFICIAL_SOURCE_RENDERED=yes
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no
```

## 1. Repository identity

| Item | Value |
|---|---|
| Worktree | `/Users/tranvanbac/Documents/AI/ai-agent/VietLaw-Chat-conversational-demo-v2` |
| Branch | `feature/conversational-rental-deposit-demo-v2` |
| Starting/accepted Phase C HEAD | `8751417404f658b3053fb6e078e648134f75a4d5` |
| Commits created this task | 1 -- `2dc883fa8547599d4400d3e1721a0941f60f20a5` (`fix(data): migrate civil code to official sources`); this correction round's LOW-01/LOW-02 fixes are on top of it, uncommitted |

## 2. Verified document identity

```text
DOCUMENT_TITLE=Bộ luật Dân sự
DOCUMENT_NUMBER=91/2015/QH13
ISSUED_DATE=2015-11-24
EFFECTIVE_DATE=2017-01-01
```

No prior reference to the incorrect `92/2015/QH13` existed anywhere in the
tracked repository (confirmed by repository-wide search before any change),
so there was nothing to remove. A test now asserts `92/2015/QH13` remains
absent from the active source data going forward
(`test_incorrect_document_number_92_absent_from_active_source_data`).

## 3. Source occurrence inventory (before any change)

Repository-wide search for `vbpl.moj.gov.vn` / `ItemID=95942`:

| Path | Classification | Action |
|---|---|---|
| `data/legal_snippets.json` (3 entries: `civil_deposit_001`, `civil_contract_001`, `civil_contract_002`) | canonical legal/source data | `source_url` replaced |
| `data/snippets_md/civil_dispute/001_civil_deposit_001.md`, `002_civil_contract_001.md`, `003_civil_contract_002.md` | canonical authoring source (compiles to the JSON above) | `source_url` replaced; backup/tertiary URLs documented |
| `evaluation/fakes/mutants.py` (`VALID_SOURCE["url"]`) | evaluation golden fixture (represents the currently-valid state, not historical evidence) | URL replaced; `last_checked` corrected to match |
| `VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md` (§8, describing the state as of Phase C) | stale historical evidence | **left unchanged** — it accurately records what was true when Phase C was written; rewriting it would falsify the audit trail |

Repository-wide search for `91/2015/QH13` and `92/2015/QH13` (before any
change): **zero occurrences of either**, anywhere. No document-number
reference existed to correct or to guard against reintroducing incorrectly.

Repository-wide search for `civil_deposit_001` and `Điều 328`: extensively
referenced across backend tests, evaluation cases, docs, and architecture
notes — all by source **ID**, never by URL. None of these needed to change;
they are evidence that the chunk identity itself is untouched by this
migration.

Repository-wide search for `source_url`: only the three canonical/authoring
pairs above carry the legacy URL. Other snippets with a `source_url`
(`business_registration_*`, `business_food_*`, `traffic_law_001`,
`traffic_accident_001`) cite different, unrelated, already-valid government
hosts (`vpcp.dichvucong.gov.vn`, `vbpl.vn`, `chinhphu.vn`) and were **not**
touched — they are out of scope for a Civil Code migration and changing them
would have altered other scenarios' behavior.

No "allowed source hosts" mechanism existed anywhere in the repository before
this task; it did not need removing, only adding (§5).

Frontend test fixtures (`frontend/src/test/responseReveal.test.tsx`, using a
synthetic `https://example.org/dieu-328`) are unrelated synthetic test data,
not the real production URL, and were left unchanged.

## 4. Primary / backup / tertiary classification

The backend's `SnippetRecord`/`SourceObject` schema supports exactly **one**
URL per source (`source_url: str | None`, `SourceObject.url`, both
`extra="forbid"`/`extra="ignore"` respectively) — so the model in play is
"one URL per source" (§3 of the task), not "multiple official URLs already
supported."

```text
primary  (source_url, rendered)    = https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm
backup   (authoring metadata only) = https://vanban.chinhphu.vn/default.aspx?docid=183188&pageid=27160
tertiary (authoring metadata only, optional) = https://vbpl.vn/van-ban/chi-tiet/bo-luat-dan-su-so-91-2015-qh13--95942
```

The backup and tertiary URLs are recorded as new frontmatter fields
(`official_backup_url`, `official_tertiary_url`) in the three `.md` authoring
files — the smallest existing metadata mechanism, since the frontmatter is
already free-form `key: value` text that the compiler (`scripts/
build_snippets.py`) only ever extracts a fixed, known set of keys from. Adding
these two keys required **no change** to the compiler, the JSON output
schema, or the API-facing `SourceObject` model — confirmed by rebuilding
`legal_snippets.json` from the updated Markdown and diffing: only `source_url`
and `last_checked` changed on the three entries; no new JSON key appeared.

```text
SOURCE_MODEL=one_url_per_source
BACKUP_URL_MECHANISM=markdown_frontmatter_extra_field
BACKUP_URL_IN_RUNTIME_API_SCHEMA=no
UNRELATED_SCHEMA_MIGRATION_REQUIRED=no
```

No automatic runtime network fallback was added (the architecture does not
already support one, and none was requested). No multi-vendor/multi-source
abstraction was introduced.

## 5. Exact host allowlist

New module `backend_lite/app/services/official_source_hosts.py`:

```text
OFFICIAL_SOURCE_HOSTS = {
  "congbao.chinhphu.vn",
  "vanban.chinhphu.vn",
  "vbpl.vn",
}
```

`is_trusted_official_host(url)` requires:

* `scheme == "https"` exactly (rejects `http://...`);
* no embedded userinfo (`parsed.username`/`parsed.password` both `None` —
  rejects `https://user@congbao.chinhphu.vn/x`, which would otherwise still
  parse to an allowed `hostname`);
* `parsed.hostname` present and an **exact** (not suffix/prefix) match
  against the three-host set.

Exact-string equality alone is what rejects both required deceptive
examples without any extra logic: `evil.congbao.chinhphu.vn.example.com`
and `congbao.chinhphu.vn.evil.example` are each a different, non-equal
hostname string; a suffix (`endswith`) check would have wrongly accepted the
second one.

**This allowlist is intentionally narrow and is not wired into the generic
frontend source-safety check** (`frontend/src/lib/sourceUrl.ts`). That module
already accepts any well-formed absolute `http(s)` URL for **any** legal
snippet across the whole app (traffic, business, civil), and its own tests
already assert `http://example.gov.vn/a` and `https://thuvienphapluat.vn/...`
as safe. Retrofitting a three-host allowlist into that shared module would
have rejected the already-valid `chinhphu.vn` and `vpcp.dichvucong.gov.vn`
sources used by unrelated traffic/business scenarios — a real
`SCENARIO_BEHAVIOR_CHANGED=yes` regression the task's own invariants forbid.
The new allowlist is therefore a standalone, narrowly-scoped Civil Code
data-integrity check, not a replacement for the general frontend safety
check, which is unchanged.

```text
OFFICIAL_HOST_ALLOWLIST_SIZE=3
FRONTEND_GENERIC_SAFETY_CHECK_MODIFIED=no
FRONTEND_GENERIC_SAFETY_CHECK_HOST_SCOPE=unrestricted (unchanged, by design)
```

**Correction (rev-2): wired into the build, not just unit-tested.** rev-1 of
this migration shipped `is_trusted_official_host` with 13 passing unit tests,
but nothing in the actual build/ingestion path called it — a deceptive or
unauthorized URL typed into the three bounded `.md` authoring files could
still have compiled successfully into `data/legal_snippets.json`. §5b below
closes that gap.

## 5b. Build-time enforcement (rev-2 correction)

`scripts/build_snippets.py` now imports `is_trusted_official_host` (repo root
added to `sys.path`, matching the existing pattern in
`scripts/smoke_real_api.py`) and calls a new
`validate_official_source_metadata(snippet_id, meta, path)` from inside
`parse_snippet()`, immediately before it returns — i.e. on every single build,
not as an optional or separate step.

Scope is exactly the three bounded IDs:

```text
OFFICIAL_SOURCE_BOUNDED_IDS = {
  "civil_deposit_001",
  "civil_contract_001",
  "civil_contract_002",
}
```

For each of these three IDs, the build now requires:

* `source_url`, `official_backup_url`, and `official_tertiary_url` are each
  non-empty and pass `is_trusted_official_host` (HTTPS, exact host, no
  embedded credentials);
* a new `official_document_number` frontmatter field equals exactly
  `"91/2015/QH13"` — any other value, including `"92/2015/QH13"`, or a
  missing field, fails the build.

Any failure raises `SnippetBuildError`, which `main()` already treats as a
hard, deterministic failure: nonzero exit, clear message naming the offending
ID/field, and **no output file is written** (`build()` parses every snippet
into a Python list first and only calls `output_file.write_text(...)` after
every snippet — including all 26, not just the three bounded ones — has
already passed; a failure on snippet 1 of 26 never reaches the write).

Snippets outside the bounded set (`traffic_law_001`,
`business_registration_*`, etc.) are untouched: `validate_official_source_
metadata` returns immediately for any ID not in the bounded set, so their
existing hosts (`chinhphu.vn`, `vpcp.dichvucong.gov.vn`) continue to build
successfully exactly as before.

```text
BUILD_TIME_ENFORCEMENT_ADDED=yes
ENFORCEMENT_SCOPE=civil_deposit_001,civil_contract_001,civil_contract_002
UNRELATED_SNIPPET_IDS_AFFECTED=0
BUILD_FAILS_DETERMINISTICALLY=yes
PARTIAL_OUTPUT_ON_FAILURE=no
```

### Proof (manual failure-injection, before the automated tests below existed)

Three corrupted copies of the real authoring directory were built against
directly from the command line:

| Injected defect | Result |
|---|---|
| `source_url` → `https://congbao.chinhphu.vn.evil.example/x` (suffix trick) | `ERROR: ... is not an exact allowed official host` — exit 1, no output file |
| `official_document_number` → `"92/2015/QH13"` | `ERROR: ... official_document_number must be exactly '91/2015/QH13', got '92/2015/QH13'` — exit 1, no output file |
| `official_backup_url` line removed entirely | `ERROR: ... requires a non-empty official_backup_url` — exit 1, no output file |

The unmodified real authoring data was rebuilt and diffed against the
previously committed JSON: byte-identical (§6 below), confirming the new
validation is satisfied by the actual curated data, not just by contrived
passing fixtures.

## 6. Legal-content invariants

Diffing `data/legal_snippets.json` before/after: only `source_url` and
`last_checked` changed on the three affected entries. `id`, `domain`,
`title`, `source_name`, `text`, `plain_language_summary`, `tags`,
`risk_notes`, `source_type`, and `status` are byte-identical.

```text
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
SCENARIO_BEHAVIOR_CHANGED=no
```

`last_checked` was bumped from `2026-07-10` to `2026-07-29` on the three
affected entries only, reflecting the actual re-verification date of the
source URL — not a content change.

## 7. Removal of the broken source from active behavior

Confirmed via a live backend-response test
(`test_rental_deposit_fixture_renders_new_primary_url_end_to_end`) and a
direct curl against the running fixture: the rental-deposit fixture's
`sources[]` now contains the Công báo URL and the legacy
`vbpl.moj.gov.vn` URL is absent. Confirmed via `test_legacy_broken_url_
absent_from_active_source_data` that no entry in `legal_snippets.json`
carries the old URL. The legacy URL remains, unmodified, only inside the
Phase C historical report (§3 above) and inside this report's own inventory
section, both clearly non-active audit text.

```text
LEGACY_BROKEN_SOURCE_ACTIVE=no
LEGACY_BROKEN_SOURCE_RENDERED=no
PRIMARY_OFFICIAL_SOURCE_RENDERED=yes
```

## 8. Tests added

`backend_lite/tests/unit/test_official_source_hosts.py` (24 tests total —
18 from rev-1 plus 6 new build-enforcement tests in rev-2 — zero provider
calls):

| # | Proves |
|---|---|
| 1 | canonical Civil Code document number `91/2015/QH13` is present in the primary URL slug |
| 2 | primary URL is the Công báo URL, for all three affected snippet IDs |
| 3 | the official backup URL is recorded in the `.md` authoring frontmatter for all three files, and is itself a trusted host |
| 4 | the legacy broken URL is absent from `legal_snippets.json`, and rejected by the host allowlist |
| 5 | the three exact official hosts are accepted |
| 6 | deceptive subdomain, suffix trick, embedded credentials, broad `*.gov.vn`, and bare `chinhphu.vn` are each rejected |
| 7 | *(frontend, existing, unchanged)* the generic source-safety module already asserts HTTPS/well-formed URLs render as clickable links — no new frontend test needed since the new URL exercises no new code path there |
| 8 | the rental-deposit fixture renders the new primary URL end-to-end through the real FastAPI app with a `FakeLLMClient` |
| 9 | *(existing, unchanged)* `SourcePanel`/`selectSafeSources` already render no source section for a sourceless response; confirmed still passing |
| 10 | full `backend_lite` + `evaluation` suites pass unchanged in every other respect |
| 11 | every test above uses `FakeLLMClient` / static JSON fixtures; zero live provider calls |
| **12** *(rev-2)* | `test_real_authoring_data_passes_build_validation`: the actual committed `.md` files build successfully end-to-end through `scripts.build_snippets.build()`, and the unrelated `traffic_law_001` snippet's own (non-allowlisted) `chinhphu.vn` host builds unaffected |
| **13** *(rev-2)* | `test_build_fails_on_deceptive_civil_code_host`: a `.md`-level suffix-trick host (`congbao.chinhphu.vn.evil.example`) injected into a temp copy of the real authoring tree makes `build()` raise `SnippetBuildError` and write no output file |
| **14** *(rev-2)* | `test_build_fails_on_http_civil_code_url`: an `http://` scheme on the same field fails the build the same way |
| **15** *(rev-2)* | `test_build_fails_on_wrong_document_number`: `official_document_number: "92/2015/QH13"` fails the build with a message naming the field |
| **16** *(rev-2)* | `test_build_fails_on_missing_backup_url`: removing the `official_backup_url` line entirely fails the build |
| **17** *(rev-2)* | `test_build_validation_scoped_to_bounded_civil_code_ids_only`: the identical suffix-trick host injected into `traffic_law_001` (outside the bounded set) builds **successfully** — proving the check does not leak onto unrelated snippets |

No live-network test was added to the automated suite; URL reachability is a
manual/report-level check (§10), not a CI assertion.

### Regression caught during validation

`evaluation/fakes/mutants.py`'s `VALID_SOURCE` fixture is reconciled against
`data/legal_snippets.json` by `evaluation.dataset.Corpus.fabrication_reasons`,
which requires an exact match on **both** `url` and `last_checked`. Updating
only the URL left the fixture's `last_checked` (`2026-07-10`) stale against
the newly bumped JSON value (`2026-07-29`), which failed 10 previously-passing
evaluation oracle tests (`no_fabricated_source`, faithfulness/usefulness
checks that depend on it). Caught by running the full `evaluation` suite;
fixed by updating `VALID_SOURCE["last_checked"]` to `2026-07-29` to match.

## 9. Exact changed paths

```text
M data/legal_snippets.json
M data/snippets_md/civil_dispute/001_civil_deposit_001.md   (+ official_document_number, rev-2)
M data/snippets_md/civil_dispute/002_civil_contract_001.md  (+ official_document_number, rev-2)
M data/snippets_md/civil_dispute/003_civil_contract_002.md  (+ official_document_number, rev-2)
M evaluation/fakes/mutants.py
M scripts/build_snippets.py                                 (rev-2: build-time enforcement)
A backend_lite/app/services/official_source_hosts.py
A backend_lite/tests/unit/test_official_source_hosts.py     (18 → 24 tests, rev-2)
```

```text
PACKAGE_FILES_MODIFIED=0
DEPENDENCY_FILES_MODIFIED=0
ENV_FILE_MODIFIED=no
SECRET_SCAN_HITS=0
UNRELATED_FILES_MODIFIED=0
```

## 10. Validation

| Check | Result |
|---|---|
| New official-source/host tests (focused) | **24 passed** (18 rev-1 + 6 rev-2 build-enforcement) |
| Complete Backend Lite suite | **904 passed** (880 + 24 new) |
| Complete evaluation suite | **214 passed** |
| Curated retrieval/evaluation tests relevant to `civil_deposit_001` | included in the 214 above; all pass |
| Frontend typecheck | passed |
| Frontend production build | passed — 167.52 kB JS |
| Complete frontend suite | **146 passed** (unchanged) |
| `compileall backend_lite/app evaluation scripts` | passed |
| `git diff --check` | clean, no whitespace/conflict-marker issues |

```text
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no
```

External URL reachability (manual, not part of the automated suite):

```text
CONGBAO_URL_MANUALLY_OPENED=yes
CONGBAO_URL_RESOLVES_TO_CORRECT_DOCUMENT=yes
```

## 11. Backend restart

The Fast Demo fixture backend (`scratchpad/phase_c_demo_server.py`) loads
`data/legal_snippets.json` once at process startup via
`JsonSnippetStore.__init__` → `reload()`, so it does **not** pick up the new
URL through Vite-style hot reload. It was stopped and restarted; confirmed via
a direct `curl` against the running process that the rental-deposit fixture
now returns `sources[0].url ==
"https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm"` and that
the sourceless fixture message still returns `sources: []`.

```text
BACKEND_RESTART_REQUIRED=yes
BACKEND_RESTARTED=yes
FRONTEND_RESTART_REQUIRED=no
```

**rev-2 note:** the build-time enforcement correction in §5b changes only
`scripts/build_snippets.py` and adds `official_document_number` to the `.md`
frontmatter; rebuilding produces a byte-identical `data/legal_snippets.json`
to the one already loaded (confirmed by diff). No second backend restart was
needed for this correction; the browser fixture already running from rev-1
remains valid and was left running per instruction.

```text
REV2_BACKEND_RESTART_REQUIRED=no
REV2_BACKEND_RESTARTED=no
```

## 12. Owner browser checkpoint — PASSED

Result: `OWNER_OFFICIAL_SOURCE_MIGRATION_BROWSER_PASS`. The owner confirmed:
reveal behavior and pacing unchanged; the source link points to the official
Công báo URL for `91/2015/QH13`; the link opens the correct document; the
legacy `vbpl.moj.gov.vn` URL is never rendered; no duplicate source appears;
the sourceless response still renders no empty source section.

* **Frontend URL: http://127.0.0.1:5173**
* Backend: `127.0.0.1:8010`, restarted for rev-1 to load the migrated source
  data; unchanged for rev-2/rev-3 (§5b, §11 rev-2 note)
* Live provider calls spent: **0**

### What was tested

Sent:

```text
tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc
```

Confirmed: reveal pacing unchanged from the accepted Phase C behavior;
`Nguồn tham khảo` appears; the link points to
`https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm`; it opens
the correct `91/2015/QH13` document; the old `vbpl.moj.gov.vn` URL never
appears; no duplicate source.

Then sent:

```text
tôi đặt cọc thuê nhà, trường hợp không nguồn thì sao
```

Confirmed: no source block, no empty heading.

All required validation was rerun and passed with the same totals (§14). One
commit was created:

```text
2dc883fa8547599d4400d3e1721a0941f60f20a5  fix(data): migrate civil code to official sources
```

containing exactly the eight paths in §9 — `data/legal_snippets.json`, the
three `.md` authoring files, `evaluation/fakes/mutants.py`,
`scripts/build_snippets.py`, and the two new `official_source_hosts.py`
files. This report was **not** committed and remains untracked/unstaged.
Not pushed, merged, or deployed. MODE_2 not started.

## 13. Restrictions honored

```text
MODE_2_STARTED=no
LIVE_LLM_PROVIDER_CALLED=no
PROMPT_BEHAVIOR_MODIFIED=no
MULTI_VENDOR_SUPPORT_ADDED=no
LEGAL_CONTENT_REWRITTEN=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_SCOPE_EXPANDED=no
BROAD_GOVERNMENT_DOMAIN_TRUST_ADDED=no
PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
```

## 14. Machine-readable verdict

```text
VIETLAW_OFFICIAL_SOURCE_MIGRATION_READY_FOR_INDEPENDENT_REVIEW

STARTING_HEAD=8751417404f658b3053fb6e078e648134f75a4d5
MIGRATION_COMMIT=2dc883fa8547599d4400d3e1721a0941f60f20a5
COMMITS_CREATED=1
COMMIT_PATH_COUNT=8

DOCUMENT_TITLE=Bo luat Dan su
DOCUMENT_NUMBER=91/2015/QH13
ISSUED_DATE=2015-11-24
EFFECTIVE_DATE=2017-01-01
INCORRECT_DOCUMENT_NUMBER_92_PRESENT=no

PRIMARY_URL=https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm
BACKUP_URL=https://vanban.chinhphu.vn/default.aspx?docid=183188&pageid=27160
TERTIARY_URL=https://vbpl.vn/van-ban/chi-tiet/bo-luat-dan-su-so-91-2015-qh13--95942
BACKUP_URL_MECHANISM=markdown_frontmatter_extra_field
BACKUP_URL_IN_RUNTIME_API_SCHEMA=no

OFFICIAL_SOURCE_HOSTS=congbao.chinhphu.vn,vanban.chinhphu.vn,vbpl.vn
OFFICIAL_HOST_ALLOWLIST_SIZE=3
HTTP_REJECTED=yes
DECEPTIVE_SUBDOMAIN_REJECTED=yes
SUFFIX_TRICK_REJECTED=yes
EMBEDDED_CREDENTIALS_REJECTED=yes
BROAD_GOV_VN_REJECTED=yes
BARE_CHINHPHU_VN_REJECTED=yes
FRONTEND_GENERIC_SAFETY_CHECK_MODIFIED=no

BUILD_TIME_ENFORCEMENT_ADDED=yes
ENFORCEMENT_SCOPE=civil_deposit_001,civil_contract_001,civil_contract_002
ENFORCED_FIELDS=source_url,official_backup_url,official_tertiary_url,official_document_number
BUILD_FAILS_ON_DECEPTIVE_HOST=yes
BUILD_FAILS_ON_HTTP_URL=yes
BUILD_FAILS_ON_WRONG_DOCUMENT_NUMBER=yes
BUILD_FAILS_ON_MISSING_REQUIRED_FIELD=yes
PARTIAL_OUTPUT_ON_BUILD_FAILURE=no
UNRELATED_SNIPPET_BUILD_UNAFFECTED=yes
REAL_AUTHORING_DATA_PASSES_BUILD=yes
REBUILT_JSON_BYTE_IDENTICAL_TO_PRIOR=yes

LEGACY_BROKEN_SOURCE_ACTIVE=no
LEGACY_BROKEN_SOURCE_RENDERED=no
PRIMARY_OFFICIAL_SOURCE_RENDERED=yes

LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
SCENARIO_BEHAVIOR_CHANGED=no

NEW_OFFICIAL_SOURCE_TESTS=24 passed
BACKEND_LITE_TESTS=904 passed
EVALUATION_TESTS=214 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no

BACKEND_RESTART_REQUIRED=yes
BACKEND_RESTARTED=yes
FRONTEND_RESTART_REQUIRED=no

PACKAGE_FILES_MODIFIED=0
ENV_FILE_MODIFIED=no
SECRET_SCAN_HITS=0
UNRELATED_FILES_MODIFIED=0

TRACKED_WORKTREE_CLEAN=no (unrelated pre-existing dirty file: VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md, from the prior Phase C task, not touched by or staged in this migration commit)
MIGRATION_TRACKED_FILES_CLEAN=yes
REPORT_TRACKED=no
REPORT_STAGED=no

OWNER_OFFICIAL_SOURCE_MIGRATION_BROWSER_CONFIRMATION=yes

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
```

*(This block described the state at rev-3, before Codex's LOW-01/LOW-02
review. It is superseded by the correction-round block at the very end of
this document -- see below.)*

---
---

# CORRECTION ROUND 1 -- CODEX LOW-01/LOW-02

Independent review of commit `2dc883fa8547599d4400d3e1721a0941f60f20a5`
returned two LOW findings. Both are corrected and now committed as
`1471cd98209301ae506ff922f8a08c975f50aee3` (`fix(data): harden official
source URL validation`), on top of that same commit -- it was **not**
amended. A second independent verification of this correction returned
`VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS`.

## Codex findings

| ID | Severity | Finding |
|---|---|---|
| LOW-01 | Low | `is_trusted_official_host()` parsed `parsed.hostname` but never inspected `parsed.port`. A malformed port (`:evil`) or an out-of-range port (`:65536`) raises `ValueError` when `urlsplit(...).port` is accessed lazily -- since nothing accessed it, these inputs never reached that code path and the function's behavior on a ported URL was unproven. Separately, no test asserted that an explicit port (including the semantically-harmless default `:443`) is rejected, even though none of the three verified URLs carry one. |
| LOW-02 | Low | The report's own §1 repository-identity table stated "Commits created this task: 0 (implementation left uncommitted per instruction)" while §12/§14 elsewhere in the same document correctly recorded that commit `2dc883fa8547599d4400d3e1721a0941f60f20a5` had already been created and owner-accepted -- a direct contradiction inside one report. |

## LOW-01 correction — port validation

`backend_lite/app/services/official_source_hosts.py`:

```python
try:
    port = parsed.port
except ValueError:
    return False
if port is not None:
    return False
```

Placed after the existing hostname check, before the final allowlist
membership comparison. `parsed.port` is accessed inside `try/except
ValueError` exactly as specified -- a non-numeric port (`:evil`) or an
out-of-range one (`:65536`, confirmed by direct testing to raise
`Port out of range 0-65535`) is caught and rejected. A present-but-valid
port (`:443`, `:0`) is rejected too: `port is not None` is true for both,
and none of the three verified URLs carry any explicit port, so an explicit
port of any kind is a mismatch from the verified form rather than something
to silently normalize away.

### Proof

`backend_lite/tests/unit/test_official_source_hosts.py`, 5 new unit tests:

* `test_malformed_textual_port_rejected` -- `https://congbao.chinhphu.vn:evil/x`
* `test_explicit_default_https_port_rejected` -- `https://congbao.chinhphu.vn:443/x`
* `test_out_of_range_port_rejected` -- `https://congbao.chinhphu.vn:65536/x`
* `test_explicit_zero_port_rejected` -- `https://congbao.chinhphu.vn:0/x`
* `test_valid_curated_urls_still_accepted_after_port_check` -- the three
  real verified URLs (primary, backup, and the vbpl.vn tertiary) still pass,
  proving the new check does not regress any already-accepted host

Plus 1 new build-level regression test,
`test_build_fails_on_malformed_port_civil_code_url`: the primary URL in a
temp copy of `001_civil_deposit_001.md` is replaced with
`https://congbao.chinhphu.vn:evil/van-ban/luat-so-91-2015-qh13-18397.htm`,
and `scripts.build_snippets.build()` is asserted to raise
`SnippetBuildError` (matching "not an exact allowed official host") and to
write no output file -- the same deterministic build-failure contract as
the other bounded-ID checks in §5b.

```text
LOW01_PORT_CHECK_ADDED=yes
MALFORMED_PORT_REJECTED=yes
OUT_OF_RANGE_PORT_REJECTED=yes
EXPLICIT_DEFAULT_PORT_REJECTED=yes
EXPLICIT_ZERO_PORT_REJECTED=yes
VALID_CURATED_URLS_STILL_ACCEPTED=yes
BUILD_FAILS_ON_MALFORMED_PORT=yes
NEW_UNIT_TESTS=5
NEW_BUILD_TESTS=1
```

No curated URL was changed: `data/legal_snippets.json` and the three `.md`
authoring files are untouched by this correction (confirmed by `git diff
--stat` showing zero changes to `data/`) -- only
`backend_lite/app/services/official_source_hosts.py` and its test file were
modified.

## LOW-02 correction — report contradiction removed

§1's repository-identity table previously read:

```text
Commits created this task: 0 (implementation left uncommitted per instruction)
```

This was stale: it was accurate at the time §1 was first written (before the
owner's browser pass), but the report was never updated there when the
commit was actually created and accepted in rev-3. Corrected to:

```text
Commits created this task: 1 -- 2dc883fa8547599d4400d3e1721a0941f60f20a5
(fix(data): migrate civil code to official sources); this correction round's
LOW-01/LOW-02 fixes are on top of it, uncommitted
```

matching what §12 and §14 already correctly stated elsewhere in the same
document. No other report field was found to contradict this.

```text
LOW02_REPORT_CONTRADICTION_FIXED=yes
SECTION_1_COMMITS_CREATED_CORRECTED=yes
```

## Files changed

Committed as `1471cd98209301ae506ff922f8a08c975f50aee3`
(`fix(data): harden official source URL validation`), exactly two paths --
LOW-01's fix and its tests:

```text
M backend_lite/app/services/official_source_hosts.py    LOW-01: port validation
M backend_lite/tests/unit/test_official_source_hosts.py  LOW-01: 6 new tests (5 unit + 1 build)
```

LOW-02's correction is report-only and, per instruction, is **not** part of
any commit: this migration report (`VIETLAW_FAST_DEMO_V2_OFFICIAL_SOURCE_
MIGRATION_REPORT_V1.md`) remains untracked and unstaged, same as every prior
revision.

No legal data, authoring markdown, package dependency, `.env`, or unrelated
file was touched.

```text
LEGAL_DATA_MODIFIED=0
AUTHORING_MARKDOWN_MODIFIED=0
PACKAGE_FILES_MODIFIED=0
CORRECTION_OWNED_TRACKED_PATHS=2
```

## Validation

| Check | Result |
|---|---|
| Focused official-source tests | **30 passed** (24 + 6 new) |
| Complete Backend Lite suite | **910 passed** (904 + 6 new) |
| Complete evaluation suite | **214 passed** |
| Complete frontend suite | **146 passed** (unchanged) |
| Frontend typecheck | passed |
| Frontend production build | passed -- 167.52 kB JS |
| `compileall backend_lite/app evaluation scripts` | passed |
| `git diff --check` | clean |

```text
AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no
```

No browser recheck was performed: curated source data and every rendered URL
are byte-identical to the already-accepted commit, so nothing observable in
the running fixture changed.

```text
BROWSER_RECHECK_PERFORMED=no
BROWSER_RECHECK_REQUIRED=no
RENDERED_URLS_BYTE_IDENTICAL=yes
```

## Restrictions honored

```text
MODE_2_STARTED=no
PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
MIGRATION_COMMIT_AMENDED=no
CORRECTION_COMMIT_AMENDED=no
UNRELATED_FILES_MODIFIED=no
```

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
The block at the end of the rev-3 section above describes a prior,
now-superseded state and must not be read as current.

```text
VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_READY_FOR_OWNER_ACCEPTANCE

MIGRATION_COMMIT=2dc883fa8547599d4400d3e1721a0941f60f20a5
CORRECTION_COMMIT=1471cd98209301ae506ff922f8a08c975f50aee3
CORRECTION_COMMIT_MESSAGE=fix(data): harden official source URL validation
CORRECTION_OWNED_TRACKED_PATHS=2
INDEPENDENT_CORRECTION_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS

CODEX_LOW01_FINDING=port_not_validated
CODEX_LOW01_STATUS=fixed
CODEX_LOW02_FINDING=report_commits_created_contradiction
CODEX_LOW02_STATUS=fixed

MALFORMED_PORT_REJECTED=yes
OUT_OF_RANGE_PORT_REJECTED=yes
EXPLICIT_DEFAULT_PORT_REJECTED=yes
EXPLICIT_ZERO_PORT_REJECTED=yes
VALID_CURATED_URLS_STILL_ACCEPTED=yes
BUILD_FAILS_ON_MALFORMED_PORT=yes

CURATED_URLS_CHANGED=no
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
SCENARIO_BEHAVIOR_CHANGED=no

NEW_TESTS_THIS_ROUND=6
OFFICIAL_SOURCE_TESTS=30 passed
BACKEND_LITE_TESTS=910 passed
EVALUATION_TESTS=214 passed
FRONTEND_TESTS=146 passed
FRONTEND_TYPECHECK=passed
FRONTEND_BUILD=passed
COMPILEALL=passed
GIT_DIFF_CHECK=clean

AUTOMATED_PROVIDER_CALLS=0
LIVE_PROVIDER_CALLS_USED=0
MODE_2_STARTED=no

BROWSER_RECHECK_PERFORMED=no
BROWSER_RECHECK_REQUIRED=no

TRACKED_WORKTREE_CLEAN=no (unrelated pre-existing dirty file: VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md, from the prior Phase C task, not touched by or staged in this correction commit)
CORRECTION_TRACKED_FILES_CLEAN=yes
COMMITS_CREATED_THIS_ROUND=1
REPORT_STAGED=no
REPORT_TRACKED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
```

*(This block described the state at rev-5, before owner acceptance. It is
superseded by the owner-acceptance block at the very end of this document --
see below.)*

---
---

# OWNER ACCEPTANCE

Documentation-only. No implementation, test, data, Markdown authoring,
dependency, or `.env` file changed in this section or its commit.

```text
VIETLAW_OFFICIAL_SOURCE_MIGRATION_ACCEPTED_BY_OWNER

MIGRATION_COMMIT=2dc883fa8547599d4400d3e1721a0941f60f20a5
CORRECTION_COMMIT=1471cd98209301ae506ff922f8a08c975f50aee3
INITIAL_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS_OPEN=0
OFFICIAL_SOURCE_MIGRATION_ACCEPTED=yes
```

Both independent reviewer verdicts are now closed with zero open findings of
any severity: the initial review's nonblocking findings became LOW-01/LOW-02,
both fixed and committed in `1471cd98209301ae506ff922f8a08c975f50aee3`; that
correction's own independent re-verification returned a clean
`VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS`.

## Final invariants confirmed

```text
DOCUMENT_NUMBER=91/2015/QH13
PRIMARY_OFFICIAL_SOURCE_CORRECT=yes
LEGACY_ACTIVE_SOURCE_REMOVED=yes
EXACT_HOST_VALIDATION_ACTIVE=yes
MALFORMED_PORT_REJECTED=yes
BUILD_FAILURE_ATOMIC=yes
CURATED_URLS_CHANGED_BY_CORRECTION=no
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
MODE_2_STARTED=no
```

* `DOCUMENT_NUMBER=91/2015/QH13` -- verified and asserted by test (§2, §8).
* `PRIMARY_OFFICIAL_SOURCE_CORRECT=yes` -- the rendered source link is the
  Công báo URL for this exact document (§4, §7).
* `LEGACY_ACTIVE_SOURCE_REMOVED=yes` -- `vbpl.moj.gov.vn` is absent from
  every active data path (§7).
* `EXACT_HOST_VALIDATION_ACTIVE=yes` -- wired into the build, not just
  unit-tested in isolation (§5b).
* `MALFORMED_PORT_REJECTED=yes` -- LOW-01's port check (correction round 1).
* `BUILD_FAILURE_ATOMIC=yes` -- `build()` writes the output file only after
  every snippet parses and validates; a failure on any one snippet leaves no
  partial JSON (§5b).
* `CURATED_URLS_CHANGED_BY_CORRECTION=no` / `LEGAL_TEXT_SEMANTICS_CHANGED=no`
  / `CHUNK_IDS_CHANGED=no` / `RETRIEVAL_BEHAVIOR_CHANGED=no` -- confirmed by
  diff at each revision (§6, correction round 1).
* `MODE_2_STARTED=no` -- not started at any point across this migration.

## Files changed (owner-acceptance commit only)

```text
M VIETLAW_FAST_DEMO_V2_OFFICIAL_SOURCE_MIGRATION_REPORT_V1.md
```

No implementation, test, legal data, Markdown authoring file, dependency, or
`.env` file was touched. The pre-existing unstaged modification to
`VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md` (from the prior
Phase C task) and every untracked Codex verification report were left
exactly as they were -- neither staged nor committed here.

```text
IMPLEMENTATION_FILES_CHANGED=0
TEST_FILES_CHANGED=0
DATA_FILES_CHANGED=0
DEPENDENCY_FILES_CHANGED=0
PHASE_C_REPORT_STAGED=no
CODEX_REPORTS_STAGED=no
```

---

## Authoritative machine-readable block (current state of this report)

This is the **only** authoritative machine-readable block in this document.
All earlier machine-readable blocks in this document describe prior,
now-superseded states and must not be read as current.

```text
VIETLAW_OFFICIAL_SOURCE_MIGRATION_ACCEPTED_BY_OWNER

MIGRATION_COMMIT=2dc883fa8547599d4400d3e1721a0941f60f20a5
CORRECTION_COMMIT=1471cd98209301ae506ff922f8a08c975f50aee3
ACCEPTANCE_COMMIT=994965b86c92594e709b01c53c95ef3a6fd1cce3

INITIAL_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_INDEPENDENT_VERIFICATION_PASS_WITH_NONBLOCKING_FINDINGS
CORRECTION_INDEPENDENT_VERDICT=VIETLAW_OFFICIAL_SOURCE_MIGRATION_CORRECTION_VERIFICATION_PASS
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS_OPEN=0
OFFICIAL_SOURCE_MIGRATION_ACCEPTED=yes

DOCUMENT_NUMBER=91/2015/QH13
PRIMARY_OFFICIAL_SOURCE_CORRECT=yes
LEGACY_ACTIVE_SOURCE_REMOVED=yes
EXACT_HOST_VALIDATION_ACTIVE=yes
MALFORMED_PORT_REJECTED=yes
BUILD_FAILURE_ATOMIC=yes
CURATED_URLS_CHANGED_BY_CORRECTION=no
LEGAL_TEXT_SEMANTICS_CHANGED=no
CHUNK_IDS_CHANGED=no
RETRIEVAL_BEHAVIOR_CHANGED=no
MODE_2_STARTED=no

IMPLEMENTATION_FILES_CHANGED=0
TEST_FILES_CHANGED=0
DATA_FILES_CHANGED=0
DEPENDENCY_FILES_CHANGED=0

TRACKED_WORKTREE_CLEAN=no (unrelated pre-existing dirty file: VIETLAW_FAST_DEMO_V2_PHASE_C_RESPONSE_REVEAL_REPORT_V1.md)
COMMITS_CREATED_THIS_ROUND=1
REPORT_STAGED=no
REPORT_TRACKED=no

PUSH_PERFORMED=no
MERGE_PERFORMED=no
DEPLOY_PERFORMED=no
PHASE_D_STARTED=no
```
