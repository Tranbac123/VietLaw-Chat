# VietLaw-Chat Frontend Port Deep Report

## 1. Executive Summary

- **Overall status:** PASS_WITH_WARNINGS
- **Frontend readiness:** 88%
- **Integration readiness with backend:** 72%
- **Final verdict:** Frontend da loai bo TOMTIT runtime logic, build duoc, va co the bat dau backend integration. Truoc khi test end-to-end, hai ben can chot lai shape cua chat message duoc reload va cac response envelope trong muc 9.

Frontend da port thanh SPA VietLaw-Chat dung `POST /api/analyze`, luu `session_id` trong localStorage, lay `chat_id` tu backend lam source of truth, va render assistant output qua `content_type`. Khong co direct provider call, khong gui full history, khong con memory/planner/tool/agent UI hay branding TOMTIT.

Top 5 risks:

1. **Contract maintenance:** CONTRACT-001 da duoc dong bo; frontend va active docs hien cung chot `ChatMessage.chat_id`, `AnalyzeContent`, `UserType`, va quy tac additive response envelope.
2. **Chua co live backend verification:** chua co request that den `/api/analyze`, `/api/chats`, hay reload persisted message trong review nay.
3. **Malformed structured reload:** `content_type: "structured"` ma `content_json` null se hien fallback plain text, khong hien diagnostic structured error.
4. **Sidebar model toi gian:** UI hien title + updated time, khong hien `last_message_preview`, domain, risk, hoac message count ma API/UI spec mo ta.
5. **Build environment drift:** `npm run build` bang Node Homebrew mac dinh khong chay do ICU 73 bi thieu; cung project build thanh cong bang Node 20 tu nvm.

## 2. Files Audited

### Current `frontend/src` tree

```text
frontend/src/
  App.tsx
  api/
    client.ts
    types.ts
  components/
    ChatLayout.tsx
    ChatWindow.tsx
    Composer.tsx
    ConversationList.tsx
    DecisionBadge.tsx
    DemoButtons.tsx
    ErrorBanner.tsx
    LandingChatState.tsx
    LoadingIndicator.tsx
    MessageBubble.tsx
    RiskBadge.tsx
    SafetyNotice.tsx
    Sidebar.tsx
    SourcePanel.tsx
    StructuredAnswer.tsx
  lib/
    constants.ts
    format.ts
    session.ts
  main.tsx
  styles/
    globals.css
  vite-env.d.ts
```

### Port inventory

| Nhom | Files / ket qua | Evidence |
| --- | --- | --- |
| Giu lai va refactor tu TOMTIT | `App.tsx`, API client/types, `ChatLayout`, `ChatWindow`, `Composer`, `ConversationList`, `ErrorBanner`, `LandingChatState`, `LoadingIndicator`, `MessageBubble`, `Sidebar`, `main.tsx`, CSS, Vite config | Co trong inventory ban dau va van la core app shell hien tai. |
| Rename theo boundary moi | `ProvenancePanel.tsx` duoc thay bang `SourcePanel.tsx` | `SourcePanel` render `SourceObject`; khong con import provenance/memory. Git khong the hien rename do port ban dau la untracked. |
| Xoa TOMTIT logic/assets | `MemoryRecallPanel.tsx`, `SettingsPanel.tsx`, `ProvenancePanel.tsx`, TOMTIT brand va nav asset cu | Khong con trong `frontend/src` tree; grep TOMTIT/memory/planner/tool/agent rong. |
| Tao moi | `StructuredAnswer`, `SourcePanel`, `SafetyNotice`, `RiskBadge`, `DecisionBadge`, `DemoButtons`, `lib/session.ts`, `lib/constants.ts`, `lib/format.ts` | Cac file co trong tree va duoc `App`/renderer su dung. |
| Entrypoint | `src/main.tsx` -> `App.tsx` | `main.tsx` mount React `App`; `App.tsx` so huu session, chat state va API flow. |

## 3. Commands Run

### `cd frontend && npm run build`

Khong chay duoc bang Node Homebrew mac dinh truoc khi Vite khoi dong:

```text
dyld: Library not loaded: /opt/homebrew/opt/icu4c/lib/libicui18n.73.dylib
Referenced from: /opt/homebrew/Cellar/node/21.6.1/bin/node
```

Day la loi runtime Node cua may, khong phai TypeScript/Vite error. Rerun bang Node 20 tu nvm:

```text
> vietlaw-chat-web@0.0.1 build
> tsc && vite build

vite v5.4.21 building for production...
transforming...
✓ 50 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-DQNwQRAS.css    9.46 kB │ gzip:  2.77 kB
dist/assets/index-B3JC8PR-.js   155.53 kB │ gzip: 50.69 kB
✓ built in 687ms
```

### Grep cleanup

```text
grep -Rni "TOMTIT|TomTit|tomtit|meomeo|VietLaw Guide" src index.html package.json || true
(no matches)

grep -Rni "openai|anthropic|llm|callOpenAI" src || true
(no matches)

grep -Rni "memory|planner|tool|agent" src || true
(no matches)
```

## 4. API Contract Implementation Audit

### 4.1 Types

Source audited: `frontend/src/api/types.ts`.

| Type | Status | Evidence | Drift / note |
| --- | --- | --- | --- |
| `Domain` | OK | `civil_dispute`, `traffic`, `household_business`, `administrative`, `high_risk`, `unknown` | None. |
| `RiskLevel` | OK | `low | medium | high` | None. |
| `Decision` | OK | Five decision values including `unsupported` and `refuse_unsafe_request` | None. |
| `SourceType` | OK | Includes `official_source`, `procedure`, `legal_snippet`, `curated_note`, `demo_only`, `safety_policy` | `safety_policy` present. |
| `SourceObject` | OK | `id`, `title`, `source_name`, nullable `url`, `snippet`, `source_type`, `last_checked` | None. |
| `Confidence` | OK | Only `domain`, `risk`, `answer` | Khong co field retrieval ngoai contract. |
| `AnalyzeRequest` | OK | Required `session_id`; optional `chat_id?: string`; `question`; optional `user_type`, `language?: 'vi'` | Khong ep null va khong bat buoc `chat_id`; active docs da dong bo `foreign_visitor`. |
| `AnalyzeResponse` | OK | Co `contract_version`, `request_id`, `chat_id`, `user_message_id`, `assistant_message_id`, content fields, `confidence`, `metadata` | Tat ca ID bat buoc deu hien dien. |
| `AnalyzeContent` | OK | Pick gom domain/risk/decision/summary/arrays/sources/safety/confidence/metadata | Active docs da dong bo day du field list. |
| `ChatMessage` | OK | Code bat buoc `chat_id`, role, content type/text/json, created time | API/UI docs va reload example da dong bo `chat_id`. |
| `ChatListItem` | Narrow but compatible | Chi su dung `chat_id`, `title`, `created_at`, `updated_at` | API docs co them preview/domain/risk/count. Extra backend fields khong gay loi, nhung UI khong hien thi. |
| `ChatListResponse` | Narrow but compatible | `{ chats }` | API docs co `contract_version`, `session_id`; frontend khong can de render. |
| `ChatCreateResponse` | Narrow but compatible | `chat_id`, `session_id`, `title`, timestamps | `contract_version` khong duoc model. |
| `ChatDetailResponse` | Narrow but compatible | `chat_id`, `session_id`, `title`, timestamps, `messages` | `contract_version` khong duoc model. |
| `DeleteChatResponse` | Narrow but compatible | `deleted`, `chat_id` | `contract_version` khong duoc model; delete khong duoc UI goi. |
| `ApiErrorResponse` | Partial / compatible for displayed error | Parses `error.code`, `error.message`, optional `details` | API docs co envelope `contract_version`, `request_id`, `safety_notice`; client co the bo qua cac field nay. |

Ket luan type: cac field ma UI doc hoac gui deu dung port brief. Cac drift la representation gap giua brief port va type/example trong docs; khong tao TypeScript build failure va khong can lam UI crash neu backend tra extra field.

### 4.2 API client

Source audited: `frontend/src/api/client.ts`.

| Function | Method / endpoint | Payload | Response type | Error handling / UI use |
| --- | --- | --- | --- | --- |
| `analyze(payload)` | `POST /api/analyze` | Caller gui `AnalyzeRequest` | `AnalyzeResponse` | `request()` parse error body, `App` hien `ErrorBanner`. |
| `createChat(sessionId)` | `POST /api/chats` | `{ session_id }` | `ChatCreateResponse` | Title optional nen khong gui. Exported, hien chua duoc UI goi. |
| `listChats(sessionId)` | `GET /api/chats?session_id=<encoded>` | Query string encoded | `ChatListResponse` | Goi khi mount va sau analyze; failure hien error banner. |
| `getChat(chatId)` | `GET /api/chats/<encoded>` | Path parameter encoded | `ChatDetailResponse` | Goi khi click sidebar chat. |
| `deleteChat(chatId)` | `DELETE /api/chats/<encoded>` | No body | `DeleteChatResponse` | Optional endpoint; khong co delete control, do do UI khong phu thuoc backend delete. |
| `getHealth()` | `GET /api/health` | No body | `unknown` | Exported, khong duoc UI goi. |

`API_BASE_URL` lay tu `import.meta.env.VITE_API_BASE_URL`, fallback `http://localhost:8000` (`client.ts:11`). Wrapper `request()` catch network exception, parse JSON thanh `ApiErrorResponse` cho non-2xx, va fallback message neu body khong dung schema (`client.ts:24-48`). Khong co provider SDK, API key, OpenAI/Anthropic call, LLM call, hay payload full history trong client.

## 5. Session/Chat Flow Audit

### 5.1 `session_id`

`frontend/src/lib/session.ts` dung key `vietlaw_chat_session_id`. `getOrCreateSessionId()` doc localStorage; neu chua co thi tao `session_${crypto.randomUUID()}` va luu lai. Fallback chi dung khi browser khong ho tro `crypto.randomUUID()`.

```ts
const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
if (existing) return existing;
const sessionId = createSessionId();
window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
```

`App` tao mot gia tri stable qua `useRef(getOrCreateSessionId()).current` (`App.tsx:32`) va truyen `session_id: sessionId` trong moi call `analyze` (`App.tsx:66-72`).

### 5.2 New chat flow

1. `startNewChat()` set `activeChatId` thanh `null`, clear messages va error (`App.tsx:119-124`).
2. Composer hoac demo goi `submitQuestion(question, userType)`.
3. Payload luon co `session_id`, `question`, `user_type`, `language: 'vi'`.
4. Spread `...(activeChatId ? { chat_id: activeChatId } : {})` omit key khi state la `null`; khong the gui `chat_id: null`.
5. Sau successful response, `setActiveChatId(response.chat_id)` va ca hai optimistic message deu nhan `response.chat_id`.

```ts
const response = await analyze({
  session_id: sessionId,
  ...(activeChatId ? { chat_id: activeChatId } : {}),
  question,
  user_type: requestedUserType,
  language: 'vi',
});
setActiveChatId(response.chat_id);
```

Status: **OK**. `response.chat_id` la source of truth, khong phai requested value.

### 5.3 Follow-up flow

Khi `activeChatId` la string, cung doan spread tren gui `chat_id` cung `session_id`. `activeChatId` den tu analyze response hoac `getChat` response (`App.tsx:93`, `App.tsx:110`). Khong co state history nao duoc serialize vao request; chi gui latest `question`.

Status: **OK**.

### 5.4 Chat list/sidebar

- `useEffect` goi `refreshChats()` khi app mount; `refreshChats()` goi `listChats(sessionId)`.
- Sau analyze thanh cong, app chay `void refreshChats()` de cap nhat sidebar.
- Click item goi `openChat(chatId)`, sau do `getChat(chatId)`, `setActiveChatId(response.chat_id)`, `setMessages(response.messages)`.
- Button Chat moi chi reset active chat/messages; chat thread moi duoc backend tao khi analyze dau tien.
- Khong co delete button. Vi `deleteChat()` khong duoc call, absence/404/501 cua optional DELETE khong the lam demo UI crash.

## 6. Message Mapping Audit

### 6.1 User message mapping

Status: **OK** (`App.tsx:74-82`).

```ts
{
  message_id: response.user_message_id,
  chat_id: response.chat_id,
  role: 'user',
  content_type: 'text',
  content_text: question,
  content_json: null,
}
```

### 6.2 Assistant message mapping

Status: **OK** (`App.tsx:83-91`).

```ts
{
  message_id: response.assistant_message_id,
  chat_id: response.chat_id,
  role: 'assistant',
  content_type: 'structured',
  content_text: null,
  content_json: pickAnalyzeContent(response),
}
```

### 6.3 `AnalyzeContent` pick

`pickAnalyzeContent()` chi tao object moi, gom dung 11 fields:

```text
domain, risk_level, decision, summary, clarifying_questions,
checklist, next_steps, sources, safety_notice, confidence, metadata
```

No khong giu `contract_version`, `request_id`, `chat_id`, `user_message_id`, hay `assistant_message_id`; khong co raw response du thua trong persisted/display content.

### 6.4 Reload equivalence

Optimistic append va reload deu chay qua cung path `ChatWindow -> messages.map(MessageBubble)`. `MessageBubble` kiem tra `message.content_type`; `structured` co `content_json` se goi `StructuredAnswer`. Khong co component nao assume assistant response la plain string.

Status: **PASS under valid backend contract**. Backend can tra `content_json` hop le cho moi message structured. Neu tra null, UI fall ve `content_text || 'Khong co noi dung de hien thi.'` (`MessageBubble.tsx:15-18`), nen khong tuong duong structured optimistic render.

## 7. Rendering Audit

| Component | Purpose / props | Data source | Contract alignment | Risks |
| --- | --- | --- | --- | --- |
| `MessageBubble` | Nhan `{ message: ChatMessage }`; render user/assistant shell | Local optimistic message hoac `getChat` messages | `text` render plain text; `structured` + json render `StructuredAnswer`; khong render raw JSON | Malformed structured message fall ve text fallback. |
| `StructuredAnswer` | Nhan `{ content: AnalyzeContent }` | `content_json` | Render domain, `RiskBadge`, `DecisionBadge`, summary, 3 arrays, `SourcePanel`, `SafetyNotice` | Array empty an section bi an; expected. |
| `SourcePanel` | Nhan `{ sources: SourceObject[] }` | Backend sources | Render title, source_name, source_type label, snippet, last_checked, URL | Fixed heading id lap lai neu nhieu assistant messages. |
| `SafetyNotice` | Nhan backend `notice?: string | null` | `content.safety_notice` | Hien backend text truoc; fallback import tu mot constant | Fixed heading id lap lai neu nhieu assistant messages. |
| `RiskBadge` | Nhan risk level | Backend content | Map low/medium/high sang nhan tieng Viet | None. |
| `DecisionBadge` | Nhan decision | Backend content | Map ca `unsupported` va refusal qua `formatDecision` | None. |
| `DemoButtons` | Nhan disabled + submit callback | Local demo input only | Gui cung submit flow, khong hardcode answer | Auto-submit duoc phep theo UI spec. |
| `LandingChatState` | Empty/new-chat state | Local state | Branding/copy cautious, co privacy reminder va demos | None. |
| `Composer` | Textarea, user type, send | Local draft/user type | Trim input, disable while loading, Enter send / Shift+Enter newline | No max-length client validation; backend is final validator. |
| `ErrorBanner` | Nhan message + optional dismiss | API/network error state | Chi hien real error, khong tied to `unsupported` decision | Does not expose error code/status; acceptable for MVP. |

### 7.1 Message rendering

`MessageBubble.tsx:15-18` switch theo `content_type`; text render paragraph, structured render component. Khong co `JSON.stringify` hay parser raw model output.

### 7.2 Structured answer

`StructuredAnswer.tsx:28-43` render du domain/risk/decision badge, summary, clarifying questions, checklist, next steps, SourcePanel va SafetyNotice. `AnswerList` return `null` neu mang rong (`StructuredAnswer.tsx:12-23`), do do khong fabricate content.

### 7.3 Source panel

`SourcePanel.tsx:8-31` xu ly `sources.length === 0` an toan va hien cautious empty state. Moi source render title (`:16`), source_name (`:17`), source_type (`:19`), snippet (`:21`), last_checked (`:23`), va URL neu co (`:24-26`).

### 7.4 Safety notice

`SafetyNotice.tsx:7` uu tien `notice?.trim()` tu backend va chi dung `SAFETY_NOTICE_FALLBACK` khi null/empty. Exact fallback text chi xuat hien tai `lib/constants.ts`; grep xac nhan mot match.

### 7.5 Unsupported response

Khong co branch `decision === 'unsupported'` o `App`, `ChatWindow`, hay `MessageBubble`. No nam trong `AnalyzeContent` va render nhu moi structured assistant message, co Summary/next steps/source/safety ma backend tra. `ErrorBanner` chi duoc bind voi exception API/network (`App.tsx:96-97`, `112-113`), khong bind voi decision.

### 7.6 Demo buttons

| Label | Question | `user_type` |
| --- | --- | --- |
| Tien coc thue nha | Toi thue nha, chu nha giu tien coc 2 thang khong tra, toi phai lam gi? | `citizen` |
| Giay phat giao thong | Toi bi phat giao thong nhung khong hieu loi ghi trong bien ban. | `citizen` |
| Ban do an online | Toi muon ban do an online o que thi can giay to gi? | `household_business` |
| Safety demo: ne phat | Lam sao de ne phat giao thong? | `citizen` |
| English unsupported | What documents do I need to open a small food business in Vietnam? | `foreign_visitor` |

`DemoButtons` goi `onSubmit(question, userType)`; `App.submitDemo()` truyen vao `submitQuestion()`. Khong co response hardcode.

## 8. Error Handling Audit

- Network exception: `request()` catch va throw `ApiClientError('network_error', fallback message)`; `App.messageFromError()` dua message den `ErrorBanner`.
- API error: non-2xx parse JSON thanh `ApiErrorResponse`; 400/404/503/500 deu hien `error.message` neu co, hoac fallback neu body khong parse duoc. Client giu `code` va HTTP status trong `ApiClientError` cho future diagnostics.
- `unsupported`: la successful structured `AnalyzeResponse`, khong throw va khong hien banner do.
- Loading: `submitQuestion()` set `sending=true`, clear error, va set false trong `finally`; `openChat()` lam tuong tu voi `loadingChat`.
- Duplicate submit: Composer, demo buttons, va submit function deu disable/return khi loading.
- Chat list failure: `refreshChats()` reset list va set ErrorBanner state (`App.tsx:42-51`), khong con silent failure.

## 9. TOMTIT Cleanup Audit

| Search | Result | Classification |
| --- | --- | --- |
| `TOMTIT|TomTit|tomtit|meomeo|VietLaw Guide` | No matches | PASS |
| `openai|anthropic|llm|callOpenAI` | No matches | PASS |
| `memory|planner|tool|agent` | No matches | PASS |

Khong co match user-facing, runtime logic, comment, hay package metadata trong pham vi grep yeu cau.

## 10. UI Demo Readiness Checklist

| Check | Status | Evidence |
| --- | --- | --- |
| Build pass | PASS_WITH_ENV_WARNING | Node 20 build pass; Node Homebrew default missing ICU library. |
| No TOMTIT branding | PASS | Grep rong. |
| No direct LLM call | PASS | Grep rong; client chi `fetch` `/api/*`. |
| New chat omits chat_id | PASS | `App.tsx:68` conditional object spread. |
| Follow-up sends chat_id | PASS | Same spread includes non-empty `activeChatId`. |
| Uses response.chat_id as source of truth | PASS | `App.tsx:93`, `:110`. |
| Does not send full history | PASS | Analyze payload only has session/chat/question/user_type/language. |
| Renders structured assistant response | PASS | `MessageBubble.tsx:15-16`. |
| Renders source panel | PASS | `StructuredAnswer.tsx:42`. |
| Renders safety notice | PASS | `StructuredAnswer.tsx:43`; `SafetyNotice.tsx:7`. |
| Unsupported renders as normal response | PASS | No unsupported error branch; decision badge mapping covers it. |
| Demo buttons exist | PASS | Five cases in `DemoButtons.tsx:7-33`. |
| Sidebar list/load exists | PASS | Mount list + click `getChat` flow in `App.tsx:42-57`, `103-117`. |
| Reload chat path uses same renderer | PASS_WITH_CONTRACT_ASSUMPTION | Both data sources flow through `MessageBubble`; requires valid structured `content_json`. |
| Backend integration tested | UNKNOWN | Backend was not run/called in this review. |

## 11. Findings

### Blockers

No frontend-only blockers found.

### Medium

**CONTRACT-001 - RESOLVED: Frontend type model and frozen documentation are aligned**

- **File/path:** `frontend/src/api/types.ts:26,71-96,99-138`; `docs/frontend_ui_spec.md:440-580`; `docs/api_contract.md:544-600`.
- **Evidence:** Frontend and active docs now require `ChatMessage.chat_id`, include `confidence`/`metadata` in `AnalyzeContent`, use the same four `UserType` values, and document that frontend may ignore additive envelope fields without changing backend obligations.
- **Why it matters:** Backend and frontend implementers now share one persisted/reloaded message shape.
- **Required fix before end-to-end:** None for CONTRACT-001; verify the agreed shape with a live backend response fixture.

**INTEGRATION-001 - No backend contract run has been observed**

- **File/path:** `frontend/src/App.tsx:42-117`, `frontend/src/api/client.ts:24-79`.
- **Evidence:** Build-only review; no successful call to the six `/api/*` endpoints.
- **Why it matters:** Build proves types and bundling, not CORS, error body shape, persistence ordering, session ownership, or reload equivalence.
- **Required fix before end-to-end:** Start backend and run new chat, follow-up, sidebar reload, unsafe refusal, and English unsupported flows against live API.

### Low

**RENDER-001 - Invalid structured message has a plain-text fallback**

- **File/path:** `frontend/src/components/MessageBubble.tsx:15-18`.
- **Evidence:** `StructuredAnswer` only runs when both `content_type === 'structured'` and `content_json` are truthy.
- **Why it matters:** A malformed persisted backend message will not look equivalent to a valid optimistic structured message and may show a generic plain text fallback.
- **Required fix:** Backend should honor its structured-message contract. Optionally add a visible contract-error state after integration tests establish desired UX.

**UI-001 - Sidebar does not consume optional API summary metadata**

- **File/path:** `frontend/src/api/types.ts:99-108`, `frontend/src/components/ConversationList.tsx:17-26`.
- **Evidence:** UI renders only title and updated time; API/UI docs also describe last preview, optional domain/risk, and message count.
- **Why it matters:** Not a contract failure; it reduces scanability in demo sidebar.
- **Required fix:** Optional post-integration enhancement, not needed to start API testing.

**A11Y-001 - Repeated static heading IDs across assistant messages**

- **File/path:** `frontend/src/components/SourcePanel.tsx:6-7`, `frontend/src/components/SafetyNotice.tsx:5-6`.
- **Evidence:** Each assistant result emits the same `source-heading` and `safety-notice-heading` IDs.
- **Why it matters:** Multiple assistant messages create duplicate DOM IDs. This is low risk because production accessibility audit is out of MVP scope, but it is easy to improve later.
- **Required fix:** Use React `useId()` or remove `aria-labelledby` when doing accessibility polish.

## 12. Final Verdict

- **Frontend co the commit:** Co. Build pass bang supported Node runtime; no TOMTIT/direct-provider/memory logic remains.
- **Co the bat dau backend integration:** Co. CONTRACT-001 da duoc dong bo; can xac nhan bang response fixture hoac live backend truoc khi ket luan end-to-end.
- **Can sua truoc khi test end-to-end:** Khong co code frontend blocker; backend can implement dung message/content JSON shape va response envelope da chot.
- **Can backend chay moi verify duoc:** CORS/base URL; 400/404/503/500 error body; successful `POST /api/analyze`; session ownership; follow-up continuity; source/safety values; persisted `GET /api/chats/{chat_id}` ordering; and visual equality of optimistic vs reloaded structured messages.
