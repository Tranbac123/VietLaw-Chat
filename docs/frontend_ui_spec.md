# VietLaw-Chat Frontend UI Specification — MVP v1

**Status:** MVP v1 aligned with `docs/api_contract.md` and `docs/ai_core_spec.md`  
**Freeze date:** 2026-07-10  
**Owner:** Frontend / Product owner  
**Review rule:** after this version is accepted, any UI change that affects API shape, chat/session semantics, safety rendering, source rendering, or evaluation expectations must be approved by both frontend/product owner and backend/AI-core owner.

---

## 1. Purpose

This document defines the frontend UX/UI specification for **VietLaw-Chat MVP**.

The frontend must demonstrate a working AI product, not a production legal platform. It should show that the system can:

- accept Vietnamese legal questions in everyday language;
- create and continue a chat thread through `chat_id`;
- preserve basic chat continuity in the same browser/demo session through `session_id`;
- render structured AI output from `POST /api/analyze`;
- show legal domain, risk level, decision, summary, clarifying questions, checklist, next steps, sources, and safety notice;
- display RAG sources without letting the frontend invent or rewrite legal citations;
- make clear that VietLaw-Chat does not replace lawyers, courts, police, public authorities, or official legal advice.

The MVP UI should prioritize **clarity, safety, demo stability, and implementation speed** over complex product features.

---

## 2. MVP Scope

### 2.1. In Scope

The frontend MVP supports:

- Vietnamese text chat.
- Single-page web app.
- Demo case buttons.
- Basic chat sidebar.
- Create new chat.
- Open previous chat in the same `session_id`.
- Send messages via `POST /api/analyze`.
- Reuse returned `chat_id` for follow-up questions in the same chat.
- Render structured assistant responses.
- Render source panel.
- Render safety notice for every assistant response.
- Loading, empty, validation, and error states.
- Lightweight debug panel for metadata, hidden by default.

### 2.2. Out of Scope

The frontend MVP does **not** include:

- English legal answering UI.
- Voice input/output.
- OCR.
- File upload.
- User accounts/login.
- Payment.
- Admin dashboard.
- Cross-device chat sync.
- Long-term personal memory UI.
- Cross-chat memory UI.
- Legal document drafting workspace.
- Mobile-native app.
- Production-grade accessibility/audit system.

### 2.3. Future Roadmap, Not MVP

Future versions may add:

- Vietnamese-English bilingual UI.
- Voice conversation.
- OCR/file upload.
- Account-based chat sync.
- More legal domains.
- Better source exploration.

These future features must not complicate the MVP UI unless explicitly moved into MVP scope.

---

## 3. Product Positioning in UI

The UI must position VietLaw-Chat as:

```text
Trợ lý định hướng pháp lý ban đầu bằng tiếng Việt.
```

The UI must not position it as:

- AI lawyer;
- luật sư AI;
- legal decision maker;
- official legal authority;
- tool that guarantees legal outcomes;
- tool that replaces lawyers or public authorities.

Recommended subtitle:

```text
VietLaw-Chat giúp người dân và hộ kinh doanh nhỏ mô tả vấn đề pháp lý, xác định nhóm rủi ro, chuẩn bị giấy tờ cần thiết, xem nguồn tham khảo và biết khi nào nên hỏi luật sư hoặc cơ quan chức năng.
```

Do not use exaggerated claims such as:

- Tư vấn pháp lý chính xác 100%.
- Thay thế luật sư.
- Giúp bạn thắng kiện.
- Tự động xử lý mọi vụ việc pháp lý.

---

## 4. Source of Truth

The frontend must treat these files as source of truth:

| Source | Frontend role |
|---|---|
| `docs/api_contract.md` | API shape, endpoint behavior, chat/session semantics, error behavior |
| `docs/ai_core_spec.md` | AI behavior, same-chat context, safety/RAG assumptions |
| `docs/safety_policy.md` | Required safety positioning and forbidden UI claims |
| `data/demo_cases.json` | Demo buttons and demo video flow |
| `data/golden_cases.json` | Evaluation expectations that frontend must not obscure |

If this file conflicts with `docs/api_contract.md`, the API contract wins for API shape and endpoint behavior.

---

## 5. Required Page Structure

The MVP can be a single-page web app.

Recommended layout:

```text
App Shell
├── Header
├── Left Sidebar: chat list + new chat
└── Main Chat Area
    ├── Hero / empty state
    ├── Demo case buttons
    ├── Message list
    ├── Composer
    └── Safety footer / limitation note
```

A simpler one-column layout is acceptable only if time is very limited, but the final demo should include at least:

- visible chat area;
- visible demo buttons;
- visible structured result panel;
- visible source panel;
- visible safety notice.

---

## 6. Required UI Sections

### 6.1. Header

Header must include:

- Product name: `VietLaw-Chat`.
- Badge: `MVP Demo`.
- Short positioning line.

Example:

```text
VietLaw-Chat — MVP Demo
Trợ lý định hướng pháp lý ban đầu bằng tiếng Việt
```

### 6.2. Hero / Empty State

Show this before the user sends a message in a new chat.

Recommended copy:

```text
Bạn có thể mô tả một vấn đề pháp lý đời thường bằng tiếng Việt. VietLaw-Chat sẽ phân loại vấn đề, xác định mức rủi ro, hỏi thêm khi thiếu thông tin, gợi ý giấy tờ cần chuẩn bị, hiển thị nguồn tham khảo và nhắc khi nào nên gặp luật sư hoặc cơ quan chức năng.
```

Also show a short privacy reminder:

```text
Không nhập số CCCD, tài khoản ngân hàng, địa chỉ cụ thể hoặc thông tin cá nhân nhạy cảm trong bản demo.
```

### 6.3. Chat Sidebar

Sidebar should include:

- `New Chat` button.
- List of chats for current `session_id`.
- Chat title.
- Last message preview.
- Optional domain/risk badges.
- Updated time.

Rules:

- Frontend must load chats using `GET /api/chats?session_id=...`.
- `session_id` is required.
- If no chats exist, show empty sidebar text.
- Deleted chats should disappear after successful delete if delete is implemented.
- Sidebar is not legal memory across users; it is only the current demo/browser session.

### 6.4. Demo Case Buttons

The UI should provide 3 main demo buttons and 1 optional safety demo.

Required demo cases:

| Button Label | Input Question |
|---|---|
| Demo 1: Tiền cọc thuê nhà | Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì? |
| Demo 2: Giấy phạt giao thông | Tôi bị phạt giao thông nhưng không hiểu lỗi ghi trong biên bản. |
| Demo 3: Bán đồ ăn online | Tôi muốn bán đồ ăn online ở quê thì cần giấy tờ gì? |

Optional safety demo:

| Button Label | Input Question |
|---|---|
| Safety: Né phạt giao thông | Làm sao để né phạt giao thông? |

Recommended follow-up demo after Demo 1:

```text
Vậy tôi cần chuẩn bị giấy tờ gì?
```

Expected behavior: frontend must send this follow-up using the same `chat_id` returned by the first response.

Button behavior:

- Clicking a demo button fills the composer.
- Optional auto-submit is allowed.
- Button should be visible during screen recording.
- Demo button must not hardcode assistant response.

### 6.5. Composer

Composer requirements:

- Textarea input.
- Submit button label: `Gửi` or `Phân tích`.
- Disable submit when input is empty after trim.
- Trim whitespace before sending.
- Preserve the user’s original wording for display.
- Show loading state after submit.
- Prevent duplicate submit while request is in flight.
- Do not ask users to enter sensitive personal data.

Input placeholder:

```text
Nhập câu hỏi pháp lý của bạn, ví dụ: "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả..."
```

Helper text:

```text
Bản MVP hiện hỗ trợ tiếng Việt. Không nhập số CCCD, tài khoản ngân hàng, địa chỉ cụ thể hoặc thông tin cá nhân nhạy cảm.
```

### 6.6. Message List

Message list must render:

- user messages as plain text;
- assistant messages as structured result cards;
- messages in the order returned by backend.

For `GET /api/chats/{chat_id}`, backend returns messages sorted ascending by `created_at`; frontend must preserve this order and must not reverse unless intentionally rendering newest-last in the same visual order.

---

## 7. Session and Chat State

### 7.1. `session_id`

Frontend must create a stable `session_id` and store it in `localStorage`.

Recommended key:

```text
vietlaw_chat_session_id
```

Rules:

- Generate `session_id` on first app load if missing.
- Reuse the same `session_id` for every request in the browser/demo session.
- Send `session_id` with every `POST /api/analyze` request.
- Send `session_id` with `GET /api/chats?session_id=...`.
- Do not treat `session_id` as secure authentication.
- Do not store personal identifiers inside `session_id`.

Recommended format:

```text
session_<uuid>
```

### 7.2. `chat_id`

Frontend state must track current `chat_id`.

Rules:

- If user starts a new chat, current `chat_id` is empty until backend returns one.
- First message in a new chat sends no `chat_id` but must send `session_id`.
- Backend creates and returns `chat_id`.
- Frontend must store returned `chat_id` and reuse it for follow-up messages in that chat.
- Opening a chat from sidebar sets current `chat_id`.
- Starting a new chat clears current `chat_id` and message list.

### 7.3. No Cross-chat Memory in UI

Frontend must not imply that VietLaw-Chat uses information from other chats to answer the current chat.

Allowed wording:

```text
VietLaw-Chat có thể hiểu các câu hỏi tiếp theo trong cùng một cuộc trò chuyện.
```

Not allowed:

```text
VietLaw-Chat nhớ toàn bộ lịch sử của bạn ở mọi cuộc trò chuyện.
```

---

## 8. API Client Behavior

### 8.1. Required API Functions

Frontend should implement these functions:

```ts
createSessionId(): string
listChats(sessionId: string): Promise<ChatListResponse>
createChat(sessionId: string, title?: string): Promise<ChatCreateResponse>
getChat(chatId: string): Promise<ChatDetailResponse>
analyze(request: AnalyzeRequest): Promise<AnalyzeResponse>
deleteChat(chatId: string): Promise<DeleteChatResponse>
```

`deleteChat` is optional for MVP.

### 8.2. Analyze Request

Frontend sends messages through `POST /api/analyze`.

New chat first message:

```json
{
  "question": "Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?",
  "user_type": "citizen",
  "session_id": "demo-session-001",
  "language": "vi"
}
```

Follow-up in same chat:

```json
{
  "question": "Vậy tôi cần chuẩn bị giấy tờ gì?",
  "user_type": "citizen",
  "chat_id": "chat_001",
  "session_id": "demo-session-001",
  "language": "vi"
}
```

Rules:

- Always include `session_id`.
- Include `chat_id` only when continuing an existing chat.
- Do not send full chat history from frontend.
- Backend is responsible for loading same-chat history.
- Frontend must not call the LLM directly.
- Frontend must not expose API keys.

### 8.3. Analyze Response Handling

On successful `POST /api/analyze`, frontend must:

1. Append or render the user message.
2. Store returned `chat_id` as current chat id.
3. Render assistant structured response.
4. Refresh chat sidebar or update the current chat summary locally.
5. Show safety notice.
6. Show sources if any.

Frontend must not assume the requested `chat_id` equals the returned `chat_id`; it must use the returned value as source of truth.

---

## 9. TypeScript Types

Frontend should define types aligned with `docs/api_contract.md`.

```ts
type ContractVersion = "v1";

type UserType = "citizen" | "household_business" | "foreign_visitor" | "unknown";

type Language = "vi";

type Domain =
  | "civil_dispute"
  | "traffic"
  | "household_business"
  | "administrative"
  | "high_risk"
  | "unknown";

type RiskLevel = "low" | "medium" | "high";

type Decision =
  | "answer_with_guidance"
  | "ask_clarifying_questions"
  | "recommend_professional_help"
  | "refuse_unsafe_request"
  | "unsupported";

type SourceType =
  | "official_source"
  | "procedure"
  | "legal_snippet"
  | "curated_note"
  | "safety_policy"
  | "demo_only";

type Source = {
  id: string;
  title: string;
  source_name: string;
  url?: string | null;
  snippet: string;
  source_type: SourceType;
  last_checked: string;
};

type AnalyzeRequest = {
  question: string;
  user_type?: UserType;
  chat_id?: string;
  session_id: string;
  language?: Language;
};

type AnalyzeResponse = {
  contract_version: ContractVersion;
  request_id: string;
  chat_id: string;
  user_message_id: string;
  assistant_message_id: string;
  domain: Domain;
  risk_level: RiskLevel;
  decision: Decision;
  summary: string;
  clarifying_questions: string[];
  checklist: string[];
  next_steps: string[];
  sources: Source[];
  safety_notice: string;
  confidence: {
    domain: number;
    risk: number;
    answer: number;
  };
  metadata: {
    retrieval_count: number;
    has_sources: boolean;
    retrieval_strategy?: string;
    used_llm: boolean;
    model_name: string;
    used_current_chat_history: boolean;
    history_message_count: number;
    unsafe_intent_detected: boolean;
    high_risk_detected: boolean;
    detected_topic?: string | null;
    safety_flags: string[];
    guards_applied: {
      citation_guard: boolean;
      safety_guard: boolean;
      fallback_used: boolean;
    };
    [key: string]: unknown;
  };
};

type ChatSummary = {
  chat_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
  domain?: Domain | null;
  risk_level?: RiskLevel | null;
  message_count: number;
};

type ChatListResponse = {
  contract_version: ContractVersion;
  session_id: string;
  chats: ChatSummary[];
};

type ChatCreateResponse = {
  contract_version: ContractVersion;
  chat_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type DeleteChatResponse = {
  contract_version: ContractVersion;
  chat_id: string;
  deleted: boolean;
};

type ContentType = "text" | "structured";

type ChatMessage = {
  message_id: string;
  chat_id: string;
  role: "user" | "assistant";
  content_type: ContentType;
  content_text: string | null;
  content_json: AnalyzeContent | null;
  created_at: string;
};

type AnalyzeContent = Pick<
  AnalyzeResponse,
  | "domain"
  | "risk_level"
  | "decision"
  | "summary"
  | "clarifying_questions"
  | "checklist"
  | "next_steps"
  | "sources"
  | "safety_notice"
  | "confidence"
  | "metadata"
>;

type ChatDetailResponse = {
  contract_version: ContractVersion;
  chat_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

type ApiErrorResponse = {
  contract_version: ContractVersion;
  request_id: string;
  error: {
    code: "invalid_request" | "chat_not_found" | "retrieval_error" | "llm_error" | "internal_error";
    message: string;
  };
  safety_notice: string;
};
```

The backend response schemas above remain authoritative and must include all fields required by `docs/api_contract.md`. Frontend types may intentionally omit additive response-envelope fields such as `contract_version`, `request_id`, `session_id`, or top-level `safety_notice` when a component does not need them for rendering. Ignoring those additive fields does not remove the backend requirement to return them.

---

## 10. Message Rendering Contract

Frontend must switch by `content_type`.

### 10.1. User Message

For:

```json
{
  "message_id": "msg_user_001",
  "chat_id": "chat_001",
  "role": "user",
  "content_type": "text",
  "content_text": "Tôi thuê nhà, chủ nhà giữ tiền cọc...",
  "content_json": null,
  "created_at": "2026-07-10T14:00:00+07:00"
}
```

Render plain message bubble.

### 10.2. Assistant Message

For:

```json
{
  "message_id": "msg_asst_001",
  "chat_id": "chat_001",
  "role": "assistant",
  "content_type": "structured",
  "content_text": null,
  "content_json": {
    "domain": "civil_dispute",
    "risk_level": "medium",
    "decision": "ask_clarifying_questions",
    "summary": "...",
    "clarifying_questions": [],
    "checklist": [],
    "next_steps": [],
    "sources": [],
    "safety_notice": "...",
    "confidence": {
      "domain": 0.85,
      "risk": 0.75,
      "answer": 0.7
    },
    "metadata": {}
  },
  "created_at": "2026-07-10T14:00:03+07:00"
}
```

Render structured result card.

Frontend must not try to infer structure by checking whether `content` is a string or object. The field `content_type` is the switch.

---

## 11. Structured Result Panel

The result panel must render these fields from assistant structured content:

1. Domain badge.
2. Risk badge.
3. Decision badge.
4. Summary.
5. Clarifying questions.
6. Checklist.
7. Next steps.
8. Sources.
9. Safety notice.

Optional debug fields from top-level response metadata can be hidden under a debug accordion.

---

## 12. UI Labels

Use these Vietnamese labels.

| API Field | UI Label |
|---|---|
| `domain` | Nhóm vấn đề |
| `risk_level` | Mức rủi ro |
| `decision` | Hướng xử lý |
| `summary` | Tóm tắt vấn đề |
| `clarifying_questions` | Cần hỏi thêm |
| `checklist` | Giấy tờ/thông tin nên chuẩn bị |
| `next_steps` | Bước tiếp theo |
| `sources` | Nguồn tham khảo |
| `safety_notice` | Lưu ý an toàn |
| `metadata` | Thông tin kỹ thuật |

Do not label summary as:

- Kết luận pháp lý.
- Phán quyết.
- Tư vấn chính thức.

---

## 13. Domain Display

Map backend domain values to user-friendly labels.

| Domain | UI Label |
|---|---|
| `civil_dispute` | Tranh chấp dân sự |
| `traffic` | Giao thông / xử phạt |
| `household_business` | Hộ kinh doanh / kinh doanh nhỏ |
| `administrative` | Thủ tục hành chính |
| `high_risk` | Vụ việc rủi ro cao |
| `unknown` | Chưa xác định / ngoài phạm vi |

---

## 14. Risk Level Display

Map backend risk values to user-friendly labels.

| Risk | UI Label | Meaning |
|---|---|---|
| `low` | Thấp | Câu hỏi thông tin, checklist hoặc thủ tục cơ bản |
| `medium` | Trung bình | Có tranh chấp, tiền bạc, giấy phạt, hợp đồng hoặc dữ kiện cần kiểm tra |
| `high` | Cao | Có rủi ro hình sự, công an, bạo lực, tiền lớn, đất đai hoặc yêu cầu không an toàn |

Rules:

- Risk badge should be visually clear.
- Do not use frightening language.
- `high` should be prominent but calm.

---

## 15. Decision Display

Map backend decision values to user-friendly labels.

| Decision | UI Label |
|---|---|
| `answer_with_guidance` | Có thể định hướng ban đầu |
| `ask_clarifying_questions` | Cần thêm thông tin |
| `recommend_professional_help` | Nên hỏi luật sư/cơ quan chức năng |
| `refuse_unsafe_request` | Không thể hỗ trợ yêu cầu không an toàn |
| `unsupported` | Ngoài phạm vi bản MVP |

---

## 16. Summary Section

UI label:

```text
Tóm tắt vấn đề
```

Rules:

- Render as a normal paragraph.
- Avoid making it look like legal judgment.
- Do not display as final legal conclusion.

---

## 17. Clarifying Questions Section

UI label:

```text
Cần hỏi thêm
```

Rules:

- Show only if `clarifying_questions.length > 0`.
- Render as numbered list.
- Keep questions easy to read.
- Do not auto-submit answers to questions in MVP unless user types a follow-up.

---

## 18. Checklist Section

UI label:

```text
Giấy tờ/thông tin nên chuẩn bị
```

Rules:

- Show only if `checklist.length > 0`.
- Render as bullet list or checkbox-style visual list.
- Do not store checked state in MVP unless trivial.
- Do not imply the checklist is legally exhaustive.

---

## 19. Next Steps Section

UI label:

```text
Bước tiếp theo
```

Rules:

- Show only if `next_steps.length > 0`.
- Render as numbered list.
- Must look like safe initial guidance.
- Must not look like official legal instruction.

---

## 20. Sources Panel

UI label:

```text
Nguồn tham khảo
```

Each source should show:

- `title`;
- `source_name`;
- `snippet`;
- `url` if available;
- `source_type` as a small badge;
- `last_checked` if there is room.

Rules:

- Do not fabricate source display data.
- Do not rewrite source titles.
- Do not invent URLs.
- Do not display `official` unless `source_type` supports it.
- If `sources.length === 0`, show a cautious no-source note.

No-source note:

```text
Bản MVP chưa tìm thấy nguồn phù hợp cho câu hỏi này. Câu trả lời chỉ nên được xem là định hướng ban đầu và bạn nên kiểm tra thêm với luật sư hoặc cơ quan chức năng.
```

Recommended source type labels:

| `source_type` | UI Label |
|---|---|
| `official_source` | Nguồn chính thức |
| `procedure` | Thủ tục hành chính |
| `legal_snippet` | Trích đoạn pháp lý |
| `curated_note` | Ghi chú đã chọn lọc |
| `safety_policy` | Quy tắc an toàn |
| `demo_only` | Nguồn demo |

---

## 21. Safety Notice Display

The safety notice must always be visible in every assistant structured response.

Required exact text:

```text
Thông tin này chỉ mang tính định hướng ban đầu, không thay thế tư vấn pháp lý chính thức. Nếu vụ việc có tranh chấp lớn, rủi ro hình sự, quyền lợi quan trọng hoặc bạn không chắc nên làm gì, hãy tham khảo luật sư hoặc cơ quan chức năng.
```

Rules:

- Display near bottom of assistant result card.
- Do not hide inside collapsed debug section.
- Use label: `Lưu ý an toàn`.
- If backend error response includes `safety_notice`, error UI must also show it.
- If backend response is malformed and safety notice is missing, frontend should show the same fallback safety notice.

Implementation rule:

- Define this fallback safety notice in exactly one frontend constant file, for example `web/src/constants/safety.ts`.
- Add a code comment that this text comes from `docs/api_contract.md` Section 12 and must be updated there first if it ever changes.
- Do not duplicate the safety notice literal across components.

---

## 22. Metadata and Confidence Display

`confidence` and `metadata` are internal/debug information.

Rules:

- Do not show `confidence` as legal certainty.
- Hide confidence by default.
- If shown in demo/debug mode, label it as `Thông tin kỹ thuật nội bộ`.
- Do not expose raw prompts, stack traces, provider errors, or hidden logs.
- It is acceptable to show a compact debug trace such as:
  - retrieved source count;
  - whether same-chat history was used;
  - safety flags;
  - whether citation/safety guards ran.

Not allowed:

```text
Độ chắc chắn pháp lý: 85%
```

Allowed:

```text
Debug: domain=0.85, risk=0.75, retrieval_count=2
```

---

## 23. Loading State

When the user submits a question, show loading state.

Recommended text:

```text
Đang phân tích câu hỏi và tìm nguồn liên quan...
```

Behavior:

- Disable submit button.
- Keep user input visible in the chat thread.
- Avoid layout jump.
- Show spinner or skeleton if available.
- Do not create fake assistant content before backend response.

Timeout copy:

```text
Hệ thống đang mất nhiều thời gian hơn bình thường. Bạn có thể thử lại sau vài giây.
```

---

## 24. Error State

If backend returns error response, show safe error UI.

Recommended generic copy:

```text
Hệ thống chưa thể phân tích câu hỏi này. Bạn có thể thử lại hoặc mô tả vụ việc rõ hơn.
```

Map error codes:

| Error Code | UI Behavior |
|---|---|
| `invalid_request` | Show validation message near composer |
| `chat_not_found` | Ask user to start a new chat or reload sidebar |
| `retrieval_error` | Show retry-safe system issue message |
| `llm_error` | Show retry-safe system issue message |
| `internal_error` | Show generic safe error message |

Rules:

- Always show safety notice if provided.
- Do not show raw stack trace.
- Do not show API key.
- Do not show raw provider error.
- Do not show hidden prompts.

---

## 25. Unsupported Language / Unsupported Topic UI

For unsupported English/non-Vietnamese input, backend returns a normal successful assistant response with `decision: unsupported`.

Frontend must render it as a normal assistant structured message, not as a red error state.

Rules:

- Frontend must render the backend-provided `summary`, `clarifying_questions`, `checklist`, `next_steps`, `sources`, and `safety_notice` fields.
- Frontend must not hardcode unsupported-language copy.
- Frontend must not replace backend-provided unsupported text with a local message.
- Frontend may style the `unsupported` decision badge, but the explanatory content remains backend-owned.

Example backend-owned content may say that the MVP currently supports Vietnamese legal questions only and bilingual support belongs to a future version. This example is not frontend copy and must not be hardcoded in UI components.

For unsupported non-legal Vietnamese input, render `decision: unsupported` with the backend-provided calm explanation.

---

## 26. Required Components

Recommended component structure:

```text
web/src/
├── App.tsx
├── api/
│   └── client.ts
├── types/
│   └── api.ts
├── components/
│   ├── AppShell.tsx
│   ├── Header.tsx
│   ├── ChatSidebar.tsx
│   ├── NewChatButton.tsx
│   ├── DemoCaseButtons.tsx
│   ├── ChatThread.tsx
│   ├── MessageList.tsx
│   ├── UserMessageBubble.tsx
│   ├── AssistantStructuredMessage.tsx
│   ├── Composer.tsx
│   ├── DomainBadge.tsx
│   ├── RiskBadge.tsx
│   ├── DecisionBadge.tsx
│   ├── ClarifyingQuestions.tsx
│   ├── ChecklistPanel.tsx
│   ├── NextStepsPanel.tsx
│   ├── SourcePanel.tsx
│   ├── SafetyNotice.tsx
│   ├── LoadingState.tsx
│   ├── ErrorState.tsx
│   └── DebugPanel.tsx
├── constants/
│   └── safety.ts
└── utils/
    └── session.ts
```

Keep components small. Avoid putting all UI logic into `App.tsx`.

---

## 27. State Management

MVP can use React state and effects. A heavy global state library is not required.

Minimum state:

```ts
type AppState = {
  sessionId: string;
  chats: ChatSummary[];
  currentChatId: string | null;
  messages: ChatMessage[];
  input: string;
  isLoading: boolean;
  error: string | null;
};
```

Rules:

- `sessionId` comes from localStorage.
- `currentChatId` comes from selected chat or returned analyze response.
- `messages` comes from `GET /api/chats/{chat_id}` or local optimistic append after analyze response.
- `isLoading` must block duplicate submits.

---

## 28. Frontend Flow

### 28.1. App Startup

```text
1. Load or create session_id from localStorage.
2. Call GET /api/chats?session_id=...
3. Render sidebar.
4. Show empty state if no current chat selected.
```

### 28.2. New Chat

```text
1. User clicks New Chat.
2. Clear currentChatId.
3. Clear messages.
4. Show demo buttons and composer.
5. First submit calls POST /api/analyze without chat_id but with session_id.
6. Store returned chat_id.
7. Refresh sidebar.
```

Calling `POST /api/chats` before the first message is allowed, but not required for the simplest MVP flow.

### 28.3. Send Message

```text
1. Validate input is not empty after trim.
2. Build AnalyzeRequest.
3. Include session_id.
4. Include chat_id if currentChatId exists.
5. Call POST /api/analyze.
6. Use returned chat_id as source of truth.
7. Append/render user and assistant messages.
8. Refresh sidebar or update current chat preview.
9. Clear composer.
```

When appending locally after `POST /api/analyze`, the response does not return full `ChatMessage` objects. Frontend must construct them deterministically from the response:

```text
User message:
- message_id = response.user_message_id
- chat_id = response.chat_id
- role = "user"
- content_type = "text"
- content_text = the exact question string sent in AnalyzeRequest
- content_json = null

Assistant message:
- message_id = response.assistant_message_id
- chat_id = response.chat_id
- role = "assistant"
- content_type = "structured"
- content_text = null
- content_json = pick AnalyzeContent fields from AnalyzeResponse
```

`AnalyzeContent` fields are:

```text
domain, risk_level, decision, summary, clarifying_questions, checklist, next_steps, sources, safety_notice, confidence, metadata
```

Reloading the same chat through `GET /api/chats/{chat_id}` must render equivalent user and assistant messages. This is an acceptance check against optimistic-render/storage-render drift.

### 28.4. Open Existing Chat

```text
1. User clicks chat in sidebar.
2. Set currentChatId.
3. Call GET /api/chats/{chat_id}.
4. Render messages in returned order.
```

---

## 29. Demo-friendly Requirements

The UI must be easy to record in a 60–90 second demo.

Requirements:

- App loads without login.
- Demo buttons are visible.
- Result panel is readable on laptop screen.
- Sources and safety notice are visible without too many clicks.
- Follow-up message can be shown in same chat.
- Safety refusal case can be shown if core cases are stable.
- No distracting animations.
- No legal-looking government seal that implies official authority.
- No raw JSON in main UI except optional debug panel.

Recommended demo flow:

1. Open app.
2. Click Demo 1: Tiền cọc thuê nhà.
3. Show domain/risk/questions/checklist/source/safety.
4. Send follow-up: `Vậy tôi cần chuẩn bị giấy tờ gì?`.
5. Show the system understands same chat context.
6. Click New Chat.
7. Click Demo 2 or Demo 3.
8. Optional: show safety refusal for `Làm sao để né phạt giao thông?`.

---

## 30. Visual Style

Recommended style:

- Clean.
- Serious.
- Minimal.
- Readable.
- Professional.
- Not playful.
- Not overly colorful.

Use:

- clear cards;
- readable font size;
- enough spacing;
- neutral background;
- subtle badges;
- clear source panel;
- highlighted safety notice.

Avoid:

- flashy gradients;
- excessive animation;
- gamified UI;
- official-looking seals;
- scary warning UI;
- tiny legal text.

---

## 31. Accessibility and Clarity

Rules:

- Use plain Vietnamese.
- Avoid unnecessary legal jargon.
- Keep font readable in screen recording.
- Buttons must be obvious.
- Source links must be accessible by keyboard if implemented.
- Use semantic HTML where possible.
- Do not rely only on color to convey risk.

---

## 32. Privacy and Sensitive Data UI

The frontend should discourage sensitive personal data entry.

Show helper text near composer or empty state:

```text
Không nhập số CCCD, tài khoản ngân hàng, địa chỉ cụ thể hoặc thông tin cá nhân nhạy cảm trong bản demo.
```

Do not ask for:

- full name;
- citizen ID number;
- phone number;
- exact address;
- bank account;
- sensitive private details.

If user enters sensitive data anyway, frontend does not need to block MVP, but future versions may add client-side warnings.

---

## 33. Testing Requirements

Frontend should have minimum tests or manual acceptance checks for:

### 33.1. Session and Chat

- Creates `session_id` if missing.
- Reuses `session_id` after reload.
- Sends `session_id` with `/api/analyze`.
- Stores returned `chat_id`.
- Reuses `chat_id` for follow-up.
- Loads chats with `GET /api/chats?session_id=...`.
- Renders loaded messages by `content_type`.
- Locally appended messages after `/api/analyze` render equivalently after reload through `GET /api/chats/{chat_id}`.

### 33.2. Rendering

- Renders domain/risk/decision badges.
- Renders summary.
- Renders clarifying questions only when non-empty.
- Renders checklist only when non-empty.
- Renders next steps only when non-empty.
- Renders sources panel.
- Renders no-source note when `sources: []`.
- Renders safety notice every time.

### 33.3. Safety and Error

- Unsafe request shows refusal result, not normal legal advice.
- Unsupported language shows `unsupported` assistant response, not red error.
- Backend error shows safe error UI and safety notice.
- No raw stack trace/provider error is displayed.

### 33.4. Demo Cases

- Demo 1 works.
- Demo 1 follow-up works in same chat.
- Demo 2 works.
- Demo 3 works.
- Optional safety demo works.

---

## 34. Implementation Order

Recommended implementation order:

1. Define TypeScript API types in `web/src/types/api.ts`.
2. Implement API client in `web/src/api/client.ts`.
3. Implement `session_id` utility.
4. Implement static layout: header, sidebar, main chat area.
5. Implement demo buttons and composer.
6. Implement `POST /api/analyze` flow.
7. Implement structured assistant renderer.
8. Implement source panel and safety notice.
9. Implement chat sidebar loading.
10. Implement open existing chat.
11. Implement error/loading states.
12. Polish demo UI.

Do not start with visual polish before API types and message rendering are correct.

---

## 35. File-level Implementation Guidance

| File | Class/Function | Change | Why | Trade-off |
|---|---|---|---|---|
| `web/src/types/api.ts` | API types | Add `AnalyzeRequest`, `AnalyzeResponse`, `ChatSummary`, `ChatMessage`, `ContentType` | Enforce API contract in frontend | Slightly more upfront typing |
| `web/src/utils/session.ts` | `getOrCreateSessionId()` | Store stable `session_id` in localStorage | Required for chat listing and analyze new chat | Not secure auth; MVP only |
| `web/src/constants/safety.ts` | `SAFETY_NOTICE` | Define the fallback safety notice once | Prevent duplicated safety text drift | Must stay aligned with API contract |
| `web/src/api/client.ts` | `analyze()` | POST question + session/chat ids | Main AI flow | Must handle 400/404/503 safely |
| `web/src/api/client.ts` | `listChats()` | GET chats by session_id | Sidebar | Requires backend chat store |
| `web/src/api/client.ts` | `getChat()` | Load messages | Open previous chat | Must render by `content_type` |
| `web/src/components/ChatSidebar.tsx` | `ChatSidebar` | Render chat list and new chat | Chatbox UX | More UI than single form |
| `web/src/components/Composer.tsx` | `Composer` | Validate input, submit, loading state | Prevent invalid/duplicate requests | Need state handling |
| `web/src/components/AssistantStructuredMessage.tsx` | Renderer | Render content_json sections | Avoid raw LLM parsing | More components |
| `web/src/components/SourcePanel.tsx` | `SourcePanel` | Render approved sources only | RAG transparency | Sources may be empty |
| `web/src/components/SafetyNotice.tsx` | `SafetyNotice` | Always visible | Legal safety | Takes screen space |

---

## 36. Freeze Notes

For MVP v1:

1. Frontend uses `POST /api/analyze` as the main message endpoint.
2. Frontend must always send `session_id`.
3. Frontend must store and reuse returned `chat_id`.
4. Frontend must render assistant messages by `content_type`.
5. Frontend must not parse raw LLM text.
6. Frontend must not invent source data.
7. Frontend must always show safety notice.
8. Frontend must treat `confidence` as debug/internal only.
9. Frontend must not imply cross-chat memory.
10. Voice, bilingual answering, OCR, upload, login, and long-term memory are V2+ backlog, not MVP v1.
