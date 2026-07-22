# VietLaw-Chat Backend — API Reference (as built)

**Status:** Implemented — production backend  
**Backend:** `backend` (`app.main:create_app`), default port `8000`  
**Contract:** conforms to `docs/api_contract.md` MVP v1  
**Owner:** Trí  
**Last updated:** 2026-07-22  
**Scope rule:** this document describes the API **as implemented** by `backend/`. The abstract, product-owned contract is `docs/api_contract.md`; if the two disagree, the frozen contract wins and this file is corrected. For the deterministic no-key test server, see `docs/backend_lite_api.md`.

---

## 1. Purpose

`backend/` is the production VietLaw-Chat backend: a FastAPI service wrapping the full AI Core pipeline (normalization → language gate → unsafe detection → triage → risk → decision → RAG → LLM → guards → response build). It calls a real LLM provider (Anthropic or an OpenAI-compatible endpoint) and requires an API key.

Use this document to integrate the frontend or any HTTP client against the production backend. It defines every endpoint, the exact request/response fields, error envelopes, enumerations, and configuration served by the running process.

`backend_lite/` is a separate deterministic reference server used for frontend and contract testing without a model or key. It runs on port `8010`; production runs on port `8000`. They never share a database.

---

## 2. Base URL and versioning

| Item              | Value                                                      |
| ----------------- | --------------------------------------------------------: |
| Base URL (local)  | `http://127.0.0.1:8000`                                    |
| API prefix        | `/api`                                                     |
| Contract version  | `v1` (returned as `contract_version` in every response)    |
| Content type      | `application/json` (UTF-8)                                  |

Every response body — success and error — carries `contract_version: "v1"`.

---

## 3. Conventions

1. All responses are structured JSON. The frontend must not parse raw LLM text; it renders the structured fields only.
2. **The LLM generates content only** — `summary`, `clarifying_questions`, `checklist`, `next_steps`, `used_source_ids`. The backend owns `chat_id`, `request_id`, message ids, `sources`, `safety_notice`, `confidence`, and `metadata`. The LLM never fabricates sources, URLs, article numbers, or metadata.
3. The LLM is called **only on guidance decisions** (`answer_with_guidance`, `ask_clarifying_questions`). Refusal, escalation, and unsupported responses use pre-vetted templates — no model call.
4. `session_id` is the no-login ownership boundary; it is required on analyze and every session-scoped chat operation. It is not authentication.
5. Every successful response and every error response includes `safety_notice`.
6. `chat_id` is server-owned. Omit it on `POST /api/analyze` to start a new chat; pass it to continue one. The server never returns `chat_id: null`.
7. Chat isolation: same-chat history may inform a follow-up; cross-chat memory is disabled. A `chat_id` that does not belong to the supplied `session_id` is treated as not found (`404`).
8. No API key, stack trace, provider error, or internal prompt is ever exposed to the client; each error code returns a fixed safe message.

---

## 4. Endpoint summary

| Method   |               Endpoint | Auth boundary        | Purpose                                            |
| -------- | ---------------------: | -------------------- | -------------------------------------------------- |
| `GET`    |          `/api/health` | none                 | Liveness/readiness of RAG, safety data, chat store |
| `POST`   |         `/api/analyze` | `session_id` (body)  | Run the AI Core pipeline, return structured answer |
| `POST`   |           `/api/chats` | `session_id` (body)  | Create a new chat thread                           |
| `GET`    |           `/api/chats` | `session_id` (query) | List chat threads for a session                    |
| `GET`    | `/api/chats/{chat_id}` | `session_id` (query) | Get one chat thread with its messages              |
| `DELETE` | `/api/chats/{chat_id}` | `session_id` (query) | Soft-delete a chat thread                          |

CORS preflight (`OPTIONS`) is handled for allowed origins (see §10).

---

## 5. `GET /api/health`

Readiness probe. No parameters. Never calls the LLM.

**Response `200` — `HealthResponse`**

| Field              | Type                    | Notes                                            |
| ------------------ | ----------------------- | ------------------------------------------------ |
| `status`           | `"ok"` \| `"degraded"`  | `ok` only when all three flags below are true    |
| `service`          | string                  | Always `vietlaw-chat-backend`                    |
| `contract_version` | `"v1"`                  |                                                  |
| `rag_loaded`       | bool                    | Legal snippets loaded (count > 0)                |
| `safety_loaded`    | bool                    | Unsafe/high-risk patterns loaded                 |
| `chat_store_ready` | bool                    | SQLite reachable (`SELECT 1`)                    |

```json
{
  "status": "ok",
  "service": "vietlaw-chat-backend",
  "contract_version": "v1",
  "rag_loaded": true,
  "safety_loaded": true,
  "chat_store_ready": true
}
```

---

## 6. `POST /api/analyze`

Primary endpoint. Stores the user turn, runs the pipeline, and stores the validated assistant turn. On guidance paths the LLM authors the content fields; a provider failure surfaces as `503 llm_error`.

### 6.1. Request — `AnalyzeRequest`

| Field        | Type              | Required | Default     | Constraints                     |
| ------------ | ----------------- | -------- | ----------- | ------------------------------- |
| `question`   | string            | yes      | —           | length 3–3000 (trimmed)         |
| `session_id` | string \| null    | yes\*    | `null`      | max 128                         |
| `chat_id`    | string \| null    | no       | `null`      | omit to start a new chat        |
| `user_type`  | `UserType` (§9)   | no       | `"unknown"` | enum                            |
| `language`   | string            | no       | `"vi"`      |                                 |

> The content field is `question`, **not** `message`.  
> \* Per the contract `session_id` is required for analyze. The pipeline requires it whenever `chat_id` is omitted (creating a new chat); when a `chat_id` is supplied, a provided `session_id` is validated against the chat's owner.

```json
{
  "question": "Tôi bị nợ tiền không trả, phải làm gì?",
  "session_id": "s1",
  "chat_id": null,
  "user_type": "citizen",
  "language": "vi"
}
```

### 6.2. Response `200` — `AnalyzeResponse`

| Field                  | Type               | Notes                                             |
| ---------------------- | ------------------ | ------------------------------------------------- |
| `contract_version`     | `"v1"`             |                                                   |
| `request_id`           | string             | `req_<hex>`                                       |
| `chat_id`              | string             | Created if the request omitted one                |
| `user_message_id`      | string             | Stored user turn id                               |
| `assistant_message_id` | string             | Stored assistant turn id                          |
| `domain`               | `Domain` (§9)      | `high_risk` overrides topical domains             |
| `risk_level`           | `RiskLevel` (§9)   |                                                   |
| `decision`             | `Decision` (§9)    |                                                   |
| `summary`              | string             | LLM- or template-authored                         |
| `clarifying_questions` | string[]           |                                                   |
| `checklist`            | string[]           |                                                   |
| `next_steps`           | string[]           |                                                   |
| `sources`              | `Source[]` (§9)    | Curated RAG only; never LLM-invented              |
| `safety_notice`        | string             | Always present                                    |
| `confidence`           | object             | `{domain, risk, answer}`, each `0.0`–`1.0`        |
| `metadata`             | `Metadata` (§6.3)  | Diagnostic / rendering hints                      |

### 6.3. `metadata` fields

| Field                       | Type            | Notes                                       |
| --------------------------- | --------------- | ------------------------------------------- |
| `retrieval_count`           | int             | Sources retrieved                           |
| `has_sources`               | bool            |                                             |
| `retrieval_strategy`        | string          | e.g. keyword/content-gated strategy id      |
| `used_llm`                  | bool            | False on templated (refuse/escalate) paths  |
| `model_name`                | string          | Resolved model identifier                   |
| `used_current_chat_history` | bool            | Whether same-chat context was used          |
| `history_message_count`     | int             |                                             |
| `unsafe_intent_detected`    | bool            |                                             |
| `high_risk_detected`        | bool            |                                             |
| `detected_topic`            | string \| null  | Topical sub-label (may differ from domain)  |
| `safety_flags`              | string[]        |                                             |
| `guards_applied`            | object          | `{citation_guard, safety_guard, fallback_used}` |
| `llm_parse_error`           | bool \| null    | Debug: LLM output failed to parse           |
| `retrieval_error_recovered` | bool \| null    | Debug                                       |
| `citation_guard_notes`      | string \| null  | Debug                                       |
| `safety_guard_notes`        | string \| null  | Debug                                       |

---

## 7. Chat persistence endpoints

### 7.1. `POST /api/chats` — create

Request `ChatCreateRequest`:

| Field        | Type           | Required | Default | Constraints  |
| ------------ | -------------- | -------- | ------- | ------------ |
| `session_id` | string         | yes      | —       | length 1–128 |
| `title`      | string \| null | no       | `null`  | max 160      |

Response `200` — `ChatCreateResponse`: `contract_version`, `chat_id`, `session_id`, `title`, `created_at`, `updated_at`.

### 7.2. `GET /api/chats?session_id=…` — list

Query: `session_id` (required, 1–128). Deleted chats are excluded.

Response `200` — `ChatListResponse`: `contract_version`, `session_id`, `chats: ChatListItem[]`.

`ChatListItem`: `chat_id`, `title`, `created_at`, `updated_at`, `last_message_preview` (nullable), `domain` (nullable), `risk_level` (nullable), `message_count`.

### 7.3. `GET /api/chats/{chat_id}?session_id=…` — detail

Query: `session_id` (required, 1–128). Session ownership is validated before any field is returned; missing / deleted / wrong-session all return `404 chat_not_found` without revealing the owner.

Response `200` — `ChatDetail`: `contract_version`, `chat_id`, `session_id`, `title`, `created_at`, `updated_at`, `messages: MessageOut[]`.

`MessageOut`: `message_id`, `role` (`user` \| `assistant`), `content_type` (`text` \| `structured`), `content_text` (nullable), `content_json` (nullable object), `created_at`. Messages are ordered ascending by `created_at`, tie-broken by `message_id`. Assistant `content_json` mirrors the analyze content (`domain`, `risk_level`, `decision`, `summary`, `clarifying_questions`, `checklist`, `next_steps`, `sources`, `safety_notice`).

### 7.4. `DELETE /api/chats/{chat_id}?session_id=…` — soft delete

Query: `session_id` (required, 1–128). Same `404 chat_not_found` for missing / deleted / wrong-session.

Response `200` — `DeleteChatResponse`: `contract_version`, `chat_id`, `deleted: true`.

---

## 8. Error model

Every error uses the same envelope, produced by the central error handlers. Raw exception text is never forwarded; each code maps to a fixed, safe Vietnamese message.

**`ErrorResponse`**

| Field              | Type          | Notes                              |
| ------------------ | ------------- | ---------------------------------- |
| `contract_version` | `"v1"`        |                                    |
| `request_id`       | string        | `req_err_<hex>`                    |
| `error`            | object        | `{ code, message }`                |
| `safety_notice`    | string        | Always present                     |

**Codes and status**

| Code             | HTTP  | When                                                          |
| ---------------- | ----: | ------------------------------------------------------------- |
| `invalid_request`| `400` | Body/query fails validation (mapped from FastAPI 422)         |
| `chat_not_found` | `404` | Chat missing, deleted, or not owned by the `session_id`       |
| `retrieval_error`| `503` | RAG/retrieval data temporarily unavailable                    |
| `llm_error`      | `503` | AI provider failed or unavailable                             |
| `internal_error` | `500` | Unhandled backend error (no stack trace leaked)               |

```json
{
  "contract_version": "v1",
  "request_id": "req_err_391cba88d906",
  "error": { "code": "invalid_request", "message": "Dữ liệu yêu cầu không hợp lệ." },
  "safety_notice": "Thông tin này chỉ mang tính định hướng ban đầu…"
}
```

---

## 9. Enumerations

| Name         | Values                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `Domain`     | `civil_dispute`, `traffic`, `household_business`, `administrative`, `high_risk`, `unknown`                                |
| `RiskLevel`  | `low`, `medium`, `high`                                                                                                   |
| `Decision`   | `answer_with_guidance`, `ask_clarifying_questions`, `recommend_professional_help`, `refuse_unsafe_request`, `unsupported` |
| `UserType`   | `citizen`, `household_business`, `sme`, `unknown`                                                                         |
| `SourceType` | `official_source`, `procedure`, `legal_snippet`, `curated_note`, `safety_policy`, `demo_only`                            |

`Source` object: `id`, `title`, `source_name`, `url` (nullable), `snippet`, `source_type`, `last_checked`.

---

## 10. Configuration

Environment variables (loaded from `.env`; case-insensitive; unknown keys ignored). Data-path defaults anchor to the repo root, so the server is independent of the working directory.

| Variable                | Default                                | Purpose                                          |
| ----------------------- | -------------------------------------- | ------------------------------------------------ |
| `APP_ENV`               | `development`                          | Environment label                                |
| `LOG_LEVEL`             | `info`                                 | Log verbosity                                    |
| `FRONTEND_ORIGIN`       | `http://localhost:5173`                | Allowed CORS origin(s); comma-separated for many |
| `AI_PROVIDER`           | `""`                                   | `anthropic` \| `openai` \| `""` (infer)          |
| `AI_API_KEY`            | `""`                                   | Provider key (**required** for analyze)          |
| `AI_MODEL_NAME`         | `api-model`                            | Model id                                         |
| `AI_BASE_URL`           | `""`                                   | OpenAI-compatible base URL; presence infers `openai` |
| `LLM_TIMEOUT`           | `30.0`                                 | Seconds                                          |
| `LLM_MAX_RETRIES`       | `1`                                    | Transport retries before `llm_error`             |
| `CHAT_DB_PATH`          | `<repo>/data/vietlaw_chat.sqlite3`     | SQLite chat DB (gitignored)                      |
| `LEGAL_SNIPPETS_PATH`   | `<repo>/data/legal_snippets.json`      | Curated RAG input                                |
| `UNSAFE_PATTERNS_PATH`  | `<repo>/data/unsafe_patterns.json`     | Unsafe/high-risk patterns                        |
| `MIN_CONTENT_SCORE`     | `2`                                    | RAG content-gate threshold                       |
| `TOP_K`                 | `3`                                    | Max sources returned                             |
| `MAX_RESULTS_ABSOLUTE`  | `5`                                    | Hard retrieval cap                               |
| `HISTORY_WINDOW`        | `10`                                   | Recent same-chat messages used as context        |

`AI_*` variables are provider-neutral; the backend is the only component that calls the AI API.

**CORS.** Origins come from `FRONTEND_ORIGIN` (comma-split). Credentials allowed; methods `GET, POST, DELETE, OPTIONS`; headers `Content-Type, Accept`.

---

## 11. Run and verify

The app is a factory (no import-time side effects), so run it with `--factory`:

```bash
# from repo root, in a venv with backend/requirements.txt installed, .env with AI_API_KEY
uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000

curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"question":"Tôi bị nợ tiền không trả","session_id":"s1"}'
```

Tests:

```bash
cd backend && PYTHONPATH=. python -m pytest -q
```

---

## 12. Limitations

- Analyze requires a valid `AI_API_KEY`; without a reachable provider, guidance requests return `503 llm_error`. (For key-free frontend testing, use `backend_lite` on port 8010.)
- RAG is keyword/content-gated over the curated MVP dataset, not semantic vector retrieval.
- No login; `session_id` is an ownership boundary, not strong authentication.
- Same-chat requests are not serialized in-process; concurrent multi-tab submits for one chat can interleave.
- A pipeline failure after the user message is stored leaves a user-only partial turn; an invalid assistant response is never stored.
