# VietLaw-Chat MVP Audit Report

## 1. Executive Summary

- Overall status: FAIL
- Readiness for implementation/demo: 30/100
- Top 5 risks:
  1. Backend/API implementation is effectively absent: `backend/__init__.py` is empty; no `/api/health`, `/api/analyze`, `/api/chats`, SQLite store, AI Core, RAG, or safety runtime exists.
  2. Frontend implementation is effectively absent: `frontend/__init__.py` is empty; no `web/` or Vite app, no localStorage session handling, no chat rendering.
  3. Runtime data violates frozen safety/data policy: `data/legal_snippets.json` has `safety_policy` count 0, has 16 `old VietLaw branding` occurrences, and has 7 `hệ thống phải` occurrences.
  4. `scripts/run_eval.py` drifts from eval spec: default case paths are wrong, `requires_sources:false` is treated as "forbid sources", and `must_include` scans `safety_notice`.
  5. Markdown snippet relocation is not staged consistently: old tracked root files are deleted and new domain-folder files are untracked, so a clean checkout/commit may lose the authoring source.

Verdict: do not demo this as an implemented MVP yet. The specs are detailed and mostly coherent, and data count/build mechanics are close, but runtime product code is missing and data/eval semantics still drift from the frozen policy.

## 2. What Was Audited

Checked:

- Root: `README.md`, `.gitignore`, git status.
- Specs: `docs/api_contract.md`, `docs/ai_core_spec.md`, `docs/frontend_ui_spec.md`, `docs/rag_spec.md`, `docs/safety_policy.md`.
- Other docs: `docs/product_thesis.md`, `docs/archive/data_card.md`, `docs/archive/demo_script.md`, `docs/archive/evaluation_plan.md`.
- Data: `data/legal_snippets.json`, `data/golden_cases.json`, `data/demo_cases.json`, `data/unsafe_patterns.json`, `data/snippets_md/**/*.md`.
- Scripts: `scripts/build_snippets.py`, `scripts/run_eval.py`.
- Implementation folders: `backend/`, `frontend/`.
- Security/build metadata: `.env*`, dependency manifests, runtime DB/log patterns, `.gitignore`.

Not found:

- `.env.example`
- `requirements.txt`, `pyproject.toml`
- `package.json`, lock files
- `web/`
- `backend/app/*`
- test suite

## 3. Commands Run

- `git status --short --untracked-files=all`: working tree is dirty; old `data/snippets_md/*.md` tracked files deleted, new categorized Markdown files untracked.
- `rg --files -g '!node_modules' -g '!.venv' -g '!.git'`: repo contains specs, data, scripts, empty backend/frontend packages.
- `find . -maxdepth 3 -type d ...`: found `backend`, `frontend`, `data`, `data/snippets_md/*`, `docs`, `docs/archive`, `scripts`.
- `rg -n "old VietLaw branding|old VietLaw branding|old VietLaw branding" ...`: found old branding in `data/legal_snippets.json`, `data/snippets_md/**/*.md`, and `docs/product_thesis.md`.
- `rg -n "hệ thống phải|old VietLaw branding" data docs README.md scripts ...`: found runtime data and authoring Markdown safety wording violations.
- `python3 -m py_compile scripts/run_eval.py scripts/build_snippets.py`: passed.
- `python3 -m py_compile backend/__init__.py frontend/__init__.py`: passed because files are empty placeholders.
- JSON load/count command: `golden_cases=25`, `demo_cases=6`, `unsafe_patterns=dict`, `legal_snippets=26`; all valid JSON.
- `python3 scripts/build_snippets.py --output /private/tmp/vietlaw_legal_snippets_audit.json`: passed, built 26 snippets. I used a temp output to avoid rewriting dirty runtime data during audit.
- `python3 scripts/run_eval.py --base-url http://localhost:8000`: failed before API call because default paths point to repo root `golden_cases.json`/`demo_cases.json`.
- `python3 scripts/run_eval.py --base-url http://localhost:8000 --cases data/golden_cases.json data/demo_cases.json`: with approved localhost access, loaded 33 checks but every API call returned HTTP 404 from `/api/analyze`; this is not a valid VietLaw-Chat backend.
- `git check-ignore -v .env`: ignored by `.gitignore:26`.
- `git check-ignore -v data/legal_snippets.json`: not ignored, good.
- `git check-ignore -v data/vietlaw_chat.sqlite3`: ignored by `.gitignore:78`.
- Secret sweep with `rg -n "API_KEY|OPENAI_API_KEY|AI_API_KEY|sk-..."`: no real key found; only README placeholder.

## 4. Findings by Severity

### Blockers

#### B-01: Backend API and AI Core are not implemented

- File/path: `backend/__init__.py`
- Evidence: file exists but has 0 lines. No `backend/app/main.py`, `schemas.py`, `chat_store.py`, `rag_retriever.py`, `response_builder.py`, or FastAPI route files exist.
- Why it matters: frozen contract requires `GET /api/health`, `POST /api/analyze`, `POST /api/chats`, `GET /api/chats?session_id=...`, and `GET /api/chats/{chat_id}`. None can be satisfied.
- Required fix: implement backend app, API schemas, storage, AI Core pipeline, RAG, safety guard, and response builder.
- Owner suggestion: backend/AI-core owner.

#### B-02: Chat storage requirement is not implemented

- File/path: `backend/`
- Evidence: no SQLite store code or schema exists. Required tables from `docs/api_contract.md` and `docs/ai_core_spec.md` are absent.
- Why it matters: no `chat_id` continuity, no `session_id` boundary checks, no user/assistant message persistence, no same-chat follow-up context, and no protection against orphan chats.
- Required fix: implement `chats(chat_id, session_id, title, created_at, updated_at, deleted_at)` and `messages(message_id, chat_id, role, content_type, content_text, content_json, created_at)` with response-validated assistant storage.
- Owner suggestion: backend owner.

#### B-03: Frontend is not implemented

- File/path: `frontend/__init__.py`, missing `web/`
- Evidence: `frontend/__init__.py` is empty. README recommended structure and frontend spec expect a Vite-style `web/src/*` app, but no `package.json` or UI source exists.
- Why it matters: no localStorage `session_id`, no `chat_id` source-of-truth flow, no structured message rendering, no source/safety notice UI, no unsupported-language normal response rendering.
- Required fix: create frontend app aligned with `docs/frontend_ui_spec.md`.
- Owner suggestion: frontend owner.

#### B-04: Safety snippets violate runtime data policy

- File/path: `data/legal_snippets.json`, `data/snippets_md/high_risk/*.md`, `data/snippets_md/traffic/011_traffic_safety_001.md`, `data/snippets_md/household_business/018_business_safety_001.md`, `data/snippets_md/general/024_general_no_source_001.md`
- Evidence: `safety_policy_count=0`; safety snippets are `source_type: curated_note`. Runtime JSON contains `hệ thống phải` at lines including `data/legal_snippets.json:257`, `422`, `447`, `472`, `497`, `522`, `548`.
- Why it matters: `docs/safety_policy.md` requires safety-oriented snippets to use `source_type: safety_policy` and user-facing wording, not internal instructions like "Hệ thống phải...".
- Required fix: rewrite safety snippets as user-facing text and mark them `source_type: safety_policy`; rebuild `data/legal_snippets.json`.
- Owner suggestion: data/safety owner.

#### B-05: Eval runner default command is broken and semantics drift

- File/path: `scripts/run_eval.py`
- Evidence: default paths use `repo_root / "golden_cases.json"` and `repo_root / "demo_cases.json"` at lines 299-300, but files live under `data/`. `visible_include_text()` includes `safety_notice` at lines 127-135. `requires_sources is False` fails if sources exist at lines 192-195.
- Why it matters: requested default `python scripts/run_eval.py --base-url http://localhost:8000` cannot load cases. Eval semantics do not match frozen rules: `requires_sources:false` means "not required", not "forbidden"; `must_include` must not pass because of safety boilerplate.
- Required fix: default to `data/golden_cases.json` and `data/demo_cases.json`; add `requires_no_sources`; exclude `safety_notice` from `must_include` and `must_not_include`.
- Owner suggestion: eval/tooling owner.

### High

#### H-01: Old branding remains in runtime/user-facing data and current docs

- File/path: `data/legal_snippets.json`, `data/snippets_md/**/*.md`, `docs/product_thesis.md`
- Evidence: `rg` found 16 `old VietLaw branding` occurrences in `data/legal_snippets.json`; many authoring Markdown files still use `source_name: "old VietLaw branding ..."`; `docs/product_thesis.md` still starts with `# old VietLaw branding Product Thesis`.
- Why it matters: project freeze says current name is `VietLaw-Chat`. Runtime data and non-archive docs still expose the old brand.
- Required fix: replace old branding in runtime data and active docs; archive-only historical mentions can be classified minor if intentionally retained.
- Owner suggestion: product/data owner.

#### H-02: Markdown authoring relocation is not committed consistently

- File/path: `data/snippets_md/`
- Evidence: `git status` shows 26 old tracked root Markdown files deleted and 26 new categorized files under `civil_dispute/`, `traffic/`, `household_business/`, `high_risk/`, `general/` untracked.
- Why it matters: a commit made without staging the new files would remove authoring source while keeping generated JSON. This breaks the required Markdown authoring workflow.
- Required fix: stage deletes plus new foldered Markdown files together, or restore previous layout. Ensure build script recursive behavior stays covered.
- Owner suggestion: data owner.

#### H-03: Runtime `/api/analyze` is unavailable on localhost

- File/path: runtime check against `http://localhost:8000/api/analyze`
- Evidence: eval with explicit case paths returned HTTP 404 for every case after sandbox-approved localhost access.
- Why it matters: either no backend is running, or a different service is on port 8000. Live golden/demo eval cannot run.
- Required fix: implement/start VietLaw-Chat backend and verify `/api/health` plus `/api/analyze` before live eval.
- Owner suggestion: backend owner.

#### H-04: AI Core module mapping is entirely missing

- File/path: `backend/`
- Evidence: no implementation files for `schemas.py`, `chat_store.py`, `context_builder.py`, `language_detector.py`, `input_normalizer.py`, `domain_classifier.py` or equivalent, `risk_classifier.py`, `unsafe_detector.py`, `decision_policy.py`, `rag_retriever.py`, `prompt_builder.py`, `llm_client.py`, `output_parser.py`, `citation_guard.py`, `safety_guard.py`, `response_builder.py`.
- Why it matters: all LLM boundary rules, `used_source_ids` validation, citation guard, safety escalation-only behavior, and response-builder ownership are currently only specs.
- Required fix: implement modules or explicit equivalents and add tests for each frozen boundary.
- Owner suggestion: backend/AI-core owner.

### Medium

#### M-01: `.env.example` is documented but missing

- File/path: README lines 543-545 and 689-700; missing `.env.example`
- Evidence: README recommended structure includes `.env.example` and lists required env vars, but no `.env.example` exists.
- Why it matters: setup and secret hygiene are less reproducible; implementers may create undocumented local envs.
- Required fix: add `.env.example` with provider-neutral `AI_API_KEY`, `AI_MODEL_NAME`, `CHAT_DB_PATH`, `LEGAL_SNIPPETS_PATH`, `UNSAFE_PATTERNS_PATH`, etc.
- Owner suggestion: backend/platform owner.

#### M-02: No dependency manifests or tests exist

- File/path: repo root, `backend/`, `frontend/`
- Evidence: no `requirements.txt`, `pyproject.toml`, `package.json`, lock file, or `tests/` directory found.
- Why it matters: build/test audit cannot install, run backend, build frontend, or run pytest/npm tests.
- Required fix: add minimal manifests and test suite as implementation lands.
- Owner suggestion: backend/frontend owners.

#### M-03: No-diacritics coverage was not discoverable by audit query

- File/path: `data/golden_cases.json`, `data/demo_cases.json`
- Evidence: search for `khong dau`, `không dấu`, and case ids containing `no_diacritics` returned none. This may be a naming/content issue if cases exist without explicit marker.
- Why it matters: frozen spec treats Vietnamese without diacritics as a hard-fail condition if unsupported.
- Required fix: add clearly named no-diacritics golden/demo cases or annotate existing ones.
- Owner suggestion: eval owner.

#### M-04: `unsafe_patterns.json` and `run_eval.py` disagree on `must_include`

- File/path: `data/unsafe_patterns.json`, `scripts/run_eval.py`
- Evidence: `data/unsafe_patterns.json` matching rules say `must_include_excludes_fields: ["safety_notice"]`; `scripts/run_eval.py` includes `safety_notice` in `visible_include_text()`.
- Why it matters: eval may pass because of boilerplate rather than actual assistant content.
- Required fix: make matcher exclude safety notice for `must_include`.
- Owner suggestion: eval/safety owner.

### Low

#### L-01: Active docs do not reference `docs/archive`, but archive still has audit-relevant wording

- File/path: `docs/archive/data_card.md`
- Evidence: `rg` found no README/spec references to `docs/archive/*`. Archive contains examples mentioning `hệ thống phải` as negative examples, which is acceptable if not runtime-linked.
- Why it matters: low risk, but reviewers may confuse archive material with source of truth.
- Required fix: keep archive clearly marked as archive; do not use archive docs as runtime/spec references.
- Owner suggestion: docs owner.

#### L-02: `frontend/` vs `web/` naming drift

- File/path: `frontend/`, README lines 593-615, `docs/frontend_ui_spec.md` implementation plan
- Evidence: repo has empty `frontend/`; docs recommend `web/`.
- Why it matters: minor now because there is no UI, but implementation should pick one path before scaffolding.
- Required fix: choose `web/` or update specs to `frontend/` consistently.
- Owner suggestion: frontend owner.

## 5. Contract Drift Matrix

| Area | Spec Source | Current State | Status | Fix Needed |
| ---- | ----------- | ------------- | ------ | ---------- |
| API schema | `docs/api_contract.md` | No backend routes or schema models exist | FAIL | Implement FastAPI routes and response/error schemas |
| chat/session | `docs/api_contract.md`, `docs/ai_core_spec.md` | No SQLite chat store, no `session_id` boundary logic | FAIL | Implement storage and `chat_not_found` checks |
| safety notice | `docs/safety_policy.md` | Exact text exists in docs/scripts/data config, but no backend response builder | FAIL | Centralize constant in backend response builder |
| unsafe high_risk | `docs/safety_policy.md`, `data/unsafe_patterns.json` | Patterns exist, runtime detector absent | FAIL | Implement raw unsafe input detection independent per turn |
| RAG source object | `docs/rag_spec.md`, `docs/api_contract.md` | `data/legal_snippets.json` valid shape, but no retriever/runtime mapper | PARTIAL | Implement retriever and source object mapping |
| used_source_ids | `docs/ai_core_spec.md`, `docs/rag_spec.md` | Spec only; no parser/citation guard | FAIL | Implement whitelist parser and subset guard |
| markdown-to-json data workflow | `docs/rag_spec.md`, `scripts/build_snippets.py` | Recursive build works to temp output; git staging is inconsistent | PASS_WITH_WARNINGS | Stage relocated Markdown and rebuild after safety fixes |
| eval semantics | README, `docs/safety_policy.md`, `scripts/run_eval.py` | JSON valid and follow-up supported, but default paths and matcher semantics drift | FAIL | Fix paths, source semantics, safety_notice exclusion |
| frontend rendering | `docs/frontend_ui_spec.md` | No UI implementation | FAIL | Build web/frontend app and structured renderers |

## 6. Data/Eval Integrity Check

- golden case count: 25
- demo case count: 6
- legal snippet count: 26
- safety_policy source count: 0, expected at least 8
- `old VietLaw branding` string count in `data/legal_snippets.json`: 16
- `"hệ thống phải"` count in `data/legal_snippets.json`: 7
- `run_eval.py` status: `py_compile` passed; default command fails due wrong paths; explicit data paths load 33 checks but localhost `/api/analyze` returns HTTP 404; matcher semantics drift.
- `build_snippets.py` status: `py_compile` passed; recursive build to temp output passed with 26 snippets; default write command intentionally not run against dirty `data/legal_snippets.json`.
- snippet JSON integrity: 26 unique ids; required fields present; statuses all `active`; source types are `official_source:7`, `curated_note:16`, `procedure:3`, `safety_policy:0`.
- eval data semantics: `golden_008` and `golden_011` correctly have `acceptable_domain: ["high_risk"]`; English unsupported case exists as `golden_024`; follow-up cases exist as `golden_025` and `demo_civil_deposit_followup`; explicit no-diacritics case was not discoverable by audit query.

## 7. Recommended Next Actions

### Must fix before coding

- Decide implementation path names: use `web/` as specs say, or update specs to `frontend/`.
- Fix data safety snippets first: `source_type: safety_policy`, user-facing wording, no `old VietLaw branding`, no `hệ thống phải`.
- Fix `scripts/run_eval.py` default paths and matcher semantics before using it as acceptance gate.
- Add `.env.example` and minimal dependency manifests.

### Must fix before demo recording

- Implement backend routes, SQLite chat store, AI Core modules, RAG retriever, citation guard, safety guard, and response builder.
- Implement frontend localStorage `session_id`, returned `chat_id` flow, chat sidebar/detail loading, structured renderers, source panel, safety notice rendering, and unsupported-language normal response rendering.
- Run `python scripts/build_snippets.py` after data fixes and commit both Markdown and generated JSON.
- Run live eval against the correct backend and require demo cases 100%, unsafe refusal 100%, safety notice 100%, follow-up pass.

### Can defer after MVP

- DELETE `/api/chats/{chat_id}` if the UI does not require deletion; keep it documented as optional.
- Advanced RAG backend beyond deterministic in-memory keyword retrieval.
- Account login, cross-device chat sync, long-term memory, OCR, voice, bilingual legal answering.
- Large legal database ingestion.

## 8. Final Verdict

Không nên bắt đầu demo backend/frontend như một MVP đã chạy được. Nên bắt đầu code implementation sau khi sửa các drift dữ liệu/eval blocker ở trên, vì các lỗi này sẽ làm acceptance test sai ngay cả khi backend được viết đúng.

Phần nên code trước: backend schemas + SQLite chat store + `/api/health` + `/api/analyze` skeleton + response builder constant. Sau đó thêm deterministic classifiers/safety/RAG, rồi frontend structured rendering.
