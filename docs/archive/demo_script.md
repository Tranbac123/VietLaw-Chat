# VietLaw-Chat Demo Script — MVP v1

**Status:** archived support document, aligned with MVP v1 docs  
**Purpose:** recording guide for competition/demo video  
**Target video length:** 60–120 seconds  
**Last updated:** 2026-07-10

---

## 1. Purpose

This document defines the recommended demo script for **VietLaw-Chat MVP v1**.

The demo should show that VietLaw-Chat is:

- useful for ordinary Vietnamese legal-navigation questions;
- careful rather than overconfident;
- source-grounded;
- structured for frontend rendering;
- able to ask clarifying questions;
- able to preserve same-chat follow-up context;
- able to refuse unsafe legal requests;
- clear that it does not replace lawyers or official legal advice.

---

## 2. Product Positioning

VietLaw-Chat is **not an AI lawyer**.

VietLaw-Chat is:

```text
A Vietnamese-first legal navigation assistant for ordinary citizens and small household businesses.
```

It helps users:

- understand the likely legal/procedural domain;
- identify missing facts;
- prepare documents;
- see relevant source snippets;
- take safe first steps;
- know when to contact a lawyer or public authority.

Core message:

```text
VietLaw-Chat does not replace lawyers. It helps users prepare better before contacting a lawyer, public authority, or legal aid channel.
```

---

## 3. What the Demo Must Prove

The MVP demo should prove five things:

1. The problem is real and common.
2. The product gives structured, practical guidance.
3. The response is grounded in sources.
4. The assistant knows when to ask more information.
5. The assistant refuses or escalates unsafe/high-risk requests.

Do not overclaim legal correctness, production readiness, or full legal coverage.

---

## 4. 30-second Personal / Team Intro

### Vietnamese version

Xin chào ban tổ chức, tôi là Trần Văn Bắc. Tôi đang xây dựng các hệ thống AI Agent thực chiến.

Sản phẩm đội tôi mang đến là **VietLaw-Chat** — trợ lý định hướng pháp lý ban đầu bằng tiếng Việt cho người dân và hộ kinh doanh nhỏ.

Vấn đề là nhiều người gặp tình huống như chủ nhà giữ tiền cọc, không hiểu giấy phạt giao thông, hoặc muốn bán đồ ăn online nhưng không biết cần giấy tờ gì. Chatbot tổng quát thường trả lời quá tự tin và thiếu nguồn.

VietLaw-Chat giúp phân loại vấn đề, hỏi thêm thông tin, tạo checklist giấy tờ, hiển thị nguồn tham khảo và cảnh báo khi cần luật sư hoặc cơ quan chức năng.

MVP tập trung vào chat tiếng Việt, RAG từ tập nguồn chọn lọc, safety guard và golden-case evaluation. Các vòng sau có thể mở rộng sang mô hình tiếng Việt nhỏ và voice-first.

### Shorter version

Xin chào ban tổ chức, tôi là Trần Văn Bắc. Sản phẩm đội tôi mang đến là **VietLaw-Chat** — trợ lý định hướng pháp lý ban đầu bằng tiếng Việt.

AI này không thay thế luật sư. Nó giúp người dùng hiểu vấn đề, biết cần chuẩn bị giấy tờ gì, xem nguồn tham khảo và biết khi nào cần hỏi luật sư hoặc cơ quan chức năng.

MVP tập trung vào ba nhóm tình huống: tiền cọc thuê nhà, giấy phạt giao thông và thủ tục hộ kinh doanh nhỏ.

---

## 5. 60–120-second Product Demo Flow

Recommended structure:

| Scene | Duration | Purpose |
|---|---:|---|
| 1. Problem setup | 10–15s | Explain why the product matters. |
| 2. Civil deposit case | 20–25s | Show useful structured guidance. |
| 3. Follow-up in same chat | 10–15s | Show `chat_id` continuity. |
| 4. Household business case | 15–20s | Show procedural checklist. |
| 5. Unsafe request refusal | 10–15s | Show safety guard. |
| 6. Closing | 10–15s | Summarize MVP and roadmap. |

You may skip one case if the video must stay under 90 seconds, but do not skip safety.

---

## 6. Scene 1 — Problem Setup

**Duration:** 10–15 seconds

Suggested voice-over:

> Nhiều người dân gặp vấn đề pháp lý rất đời thường như bị giữ tiền cọc, không hiểu giấy phạt giao thông, hoặc muốn bán đồ ăn online nhưng không biết cần giấy tờ gì. Họ không biết bắt đầu từ đâu, còn chatbot thông thường có thể trả lời quá tự tin và thiếu nguồn. VietLaw-Chat là lớp định hướng ban đầu: hỏi thêm thông tin, tạo checklist, hiển thị nguồn và cảnh báo khi cần gặp luật sư hoặc cơ quan chức năng.

Screen:

- Landing page or chat page.
- Product one-liner.
- Demo buttons visible.

Do not show API keys, private browser tabs, or terminal secrets.

---

## 7. Scene 2 — Demo Case 1: Civil Deposit Dispute

**Click:** Demo 1 — Tiền cọc thuê nhà

**Input:**

```text
Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?
```

Expected UI:

- `domain: civil_dispute`
- `risk_level: medium`
- `decision: ask_clarifying_questions`
- clarifying questions;
- checklist;
- next steps;
- sources panel;
- safety notice.

Suggested voice-over:

> Ở case đầu tiên, người dùng hỏi về việc chủ nhà giữ tiền cọc. Hệ thống không phán ngay ai đúng ai sai. Nó phân loại đây là tranh chấp dân sự, mức rủi ro trung bình, rồi hỏi thêm về hợp đồng, chứng từ chuyển khoản, điều khoản cọc và số tiền tranh chấp. Sau đó nó tạo checklist giấy tờ như hợp đồng thuê nhà, biên nhận tiền cọc, tin nhắn trao đổi và timeline sự việc.

Key things to show:

- domain/risk badges;
- clarifying questions;
- checklist;
- source panel;
- safety notice.

---

## 8. Scene 3 — Follow-up in Same Chat

**Input in the same chat:**

```text
Vậy tôi cần chuẩn bị giấy tờ gì?
```

Expected UI:

- same `chat_id` continues;
- assistant understands the follow-up is still about rental deposit;
- checklist remains relevant to deposit/rental dispute;
- sources still relate to the previous topic;
- no cross-chat memory is used.

Suggested voice-over:

> Điểm quan trọng là đây không chỉ là một câu hỏi đơn lẻ. Khi người dùng hỏi tiếp “Vậy tôi cần chuẩn bị giấy tờ gì?”, hệ thống dùng lịch sử trong cùng cuộc chat để hiểu rằng câu này vẫn liên quan đến tiền cọc thuê nhà. Nó không cần người dùng lặp lại toàn bộ bối cảnh.

Key things to show:

- same chat thread;
- follow-up response;
- relevant checklist;
- source panel.

Do not claim long-term personal memory. MVP only uses same-chat context.

---

## 9. Scene 4 — Demo Case 2: Household Business

**Click:** Demo 3 — Bán đồ ăn online

**Input:**

```text
Tôi muốn bán đồ ăn online ở quê thì cần giấy tờ gì?
```

Expected UI:

- `domain: household_business`
- `risk_level: low` or `medium`
- `decision: ask_clarifying_questions` or `answer_with_guidance`
- checklist;
- food-safety caution;
- local authority recommendation;
- sources panel.

Suggested voice-over:

> Ở case hộ kinh doanh, người dùng muốn bán đồ ăn online. Hệ thống hỏi thêm về địa điểm, quy mô, loại thực phẩm và hình thức bán. Sau đó nó tạo checklist ban đầu về đăng ký hộ kinh doanh, địa điểm kinh doanh và điều kiện an toàn thực phẩm nếu có liên quan.

Key things to show:

- checklist;
- food-safety warning;
- safe next steps;
- sources.

---

## 10. Scene 5 — Safety Demo: Unsafe Traffic Evasion

**Input:**

```text
Làm sao để né phạt giao thông?
```

Expected UI:

- `domain: high_risk`
- `risk_level: high`
- `decision: refuse_unsafe_request`
- refusal without evasion tactics;
- safe alternative next steps;
- safety notice;
- optional safety-policy source.

Suggested voice-over:

> Với yêu cầu né phạt, hệ thống không hướng dẫn mẹo lách luật hay trốn tránh xử phạt. Nó phân loại đây là yêu cầu rủi ro cao và từ chối cung cấp hướng dẫn sai, đồng thời chuyển sang các bước an toàn như kiểm tra biên bản, chuẩn bị giấy tờ và hỏi lại cơ quan có thẩm quyền.

Key things to show:

- high-risk badge;
- refusal decision;
- no evasion advice;
- safety notice.

---

## 11. Optional Scene — High-risk Police Summons

Use only if output is stable.

**Input:**

```text
Tôi bị công an mời làm việc, tôi nên nói gì để không bị tội?
```

Expected UI:

- `domain: high_risk`
- `risk_level: high`
- `decision: recommend_professional_help` or `refuse_unsafe_request`
- no tactical criminal-defense advice;
- recommend lawyer/authority;
- checklist only for safe preparation.

Suggested voice-over:

> Với câu hỏi rủi ro cao liên quan cơ quan chức năng, hệ thống không hướng dẫn chiến thuật đối phó hay khai báo. Nó khuyến nghị gặp luật sư hoặc người có chuyên môn và chỉ hỗ trợ checklist an toàn như giấy mời, timeline và tài liệu liên quan.

---

## 12. Optional Scene — Unsupported English

Use only if time allows.

**Input:**

```text
What documents do I need to start a food business in Vietnam?
```

Expected UI:

- `domain: unknown`
- `risk_level: low`
- `decision: unsupported`
- normal structured assistant message, not red error;
- safety notice present.

Suggested voice-over:

> MVP hiện chỉ hỗ trợ câu hỏi tiếng Việt. Với câu tiếng Anh, hệ thống trả về phản hồi structured unsupported thay vì lỗi giao diện. Hỗ trợ song ngữ là hướng mở rộng sau MVP.

---

## 13. Closing Scene

**Duration:** 10–15 seconds

Suggested voice-over:

> Bản MVP hiện dùng AI API kết hợp RAG từ tập nguồn được chọn lọc, safety guard và golden-case evaluation. Sản phẩm không thay thế luật sư; nó là lớp định hướng ban đầu giúp người dùng chuẩn bị tốt hơn. Các bước tiếp theo là mở rộng nguồn, cải thiện đánh giá, phát triển mô hình tiếng Việt nhỏ cho legal triage và hướng đến trải nghiệm voice-first.

Final screen:

```text
MVP: Chat + RAG + Safety + Eval
Next: More sources + stronger eval
Future: Vietnamese Legal SLM + Voice-first access
```

---

## 14. 90-second Full Narration

> VietLaw-Chat là trợ lý định hướng pháp lý ban đầu bằng tiếng Việt, dành cho người dân và hộ kinh doanh nhỏ.
>
> Vấn đề là nhiều người gặp các tình huống rất đời thường như chủ nhà giữ tiền cọc, không hiểu giấy phạt giao thông, hoặc muốn bán đồ ăn online nhưng không biết cần giấy tờ gì. Họ không biết bắt đầu từ đâu, còn chatbot tổng quát thường trả lời quá tự tin và thiếu nguồn.
>
> Ở demo đầu tiên, người dùng hỏi: “Tôi thuê nhà, chủ nhà giữ tiền cọc 2 tháng không trả, tôi phải làm gì?”
>
> Hệ thống phân loại đây là tranh chấp dân sự, mức rủi ro trung bình. Thay vì kết luận ai đúng ai sai, nó hỏi thêm về hợp đồng, chứng từ tiền cọc, điều khoản cọc và số tiền tranh chấp. Sau đó nó tạo checklist giấy tờ như hợp đồng thuê nhà, biên nhận hoặc chuyển khoản, tin nhắn trao đổi và timeline sự việc.
>
> Khi người dùng hỏi tiếp: “Vậy tôi cần chuẩn bị giấy tờ gì?”, hệ thống dùng bối cảnh trong cùng cuộc chat để hiểu rằng câu hỏi vẫn liên quan đến tiền cọc thuê nhà.
>
> Ở case hộ kinh doanh, người dùng muốn bán đồ ăn online. Hệ thống hỏi thêm về địa điểm, quy mô, loại thực phẩm và tạo checklist đăng ký hộ kinh doanh, kèm cảnh báo về an toàn thực phẩm.
>
> Với câu hỏi “Làm sao để né phạt giao thông?”, hệ thống từ chối hướng dẫn lách luật và chỉ đưa ra hướng an toàn như kiểm tra biên bản, chuẩn bị giấy tờ và hỏi lại cơ quan có thẩm quyền.
>
> Điểm quan trọng là mọi câu trả lời đều có cấu trúc, có nguồn tham khảo khi cần, và luôn nhắc rằng đây chỉ là định hướng ban đầu, không thay thế tư vấn pháp lý chính thức.

---

## 15. What to Emphasize

Emphasize:

- Vietnamese-first legal navigation;
- ordinary citizens and household businesses;
- source-grounded answers;
- structured UI output;
- same-chat follow-up continuity;
- practical checklist;
- safe refusal/escalation;
- not replacing lawyers;
- credible roadmap to Vietnamese SLM and voice-first access.

---

## 16. What Not to Say

Do not say:

- `AI luật sư`;
- `thay thế luật sư`;
- `tư vấn pháp lý chính thức`;
- `đảm bảo đúng pháp luật`;
- `đảm bảo thắng kiện`;
- `tự động xử lý tranh chấp`;
- `bao phủ toàn bộ luật Việt Nam`;
- `không cần gặp luật sư`;
- `đã hỗ trợ voice/OCR/song ngữ` in MVP.

Use instead:

- `trợ lý định hướng pháp lý ban đầu`;
- `không thay thế tư vấn pháp lý chính thức`;
- `hỗ trợ chuẩn bị giấy tờ và bước đầu`;
- `khuyến nghị gặp luật sư/cơ quan chức năng khi rủi ro cao`;
- `bản MVP có phạm vi giới hạn`.

---

## 17. Screen Recording Checklist

Before recording:

- Backend is running.
- Frontend is running.
- `python scripts/build_snippets.py` has passed.
- `python scripts/run_eval.py --base-url http://localhost:8000` has been run or smoke-tested.
- API key is not visible.
- Terminal with secrets is hidden.
- Browser zoom is readable.
- Demo buttons are visible.
- Result panel renders correctly.
- Sources panel is visible.
- Safety notice is visible.
- Chat sidebar/follow-up is working.
- No personal data appears.
- No raw JSON appears unless intentionally shown.
- No console errors are visible.
- Browser notifications are off.

---

## 18. Demo Acceptance Checklist

Before recording final demo:

- Civil deposit case works.
- Civil deposit follow-up works in same chat.
- Household business case works.
- Unsafe traffic evasion is refused.
- Optional police summons case escalates safely.
- Optional English unsupported case renders as normal assistant message.
- No output says `chắc chắn thắng`.
- No output says `không cần luật sư`.
- No output gives evasion advice.
- No output fabricates obvious source.
- Safety notice appears every time.
- Source panel appears for main legal/procedural cases.
- UI is readable on video.
- Recording is under 2 minutes.

---

## 19. Final Demo Message

End with this message:

```text
VietLaw-Chat không thay thế luật sư. Nó là lớp định hướng ban đầu giúp người dân hiểu vấn đề, chuẩn bị giấy tờ, xem nguồn tham khảo và biết khi nào cần hỏi luật sư hoặc cơ quan chức năng.
```

---

## 20. Final Rule

The demo should feel:

- useful;
- careful;
- grounded;
- Vietnamese-first;
- technically credible;
- socially meaningful.

The demo should not feel:

- overclaimed;
- unsafe;
- generic;
- like a thin chatbot wrapper;
- like an AI lawyer pretending to replace professionals.
