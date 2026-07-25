"""FAST DEMO V2 prompt construction.

Bounded context only: current message, last 8-12 same-chat messages, current
authoritative state, the selected source pack, the slot allowlist, and the
rules. Never another chat, never credentials, never the whole corpus.

The state-authority rule is stated explicitly and the Current Demo State is
placed AFTER the history, so the most recent and most authoritative block is
the last thing the model reads. This is what stops a corrected 15,000,000 from
being dragged back to 20,000,000 by the still-visible history.
"""

from __future__ import annotations

import json

from ..contracts.fast_demo import ALLOWED_SLOTS, FastDemoState
from ..schemas.chat import ChatMessage
from .fast_demo_source_pack import PackEntry

MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 700

SYSTEM_PROMPT = """Bạn là trợ lý pháp lý VietLaw-Chat trong một bản demo giới hạn về TIỀN CỌC THUÊ NHÀ tại Việt Nam.

NGUYÊN TẮC THẨM QUYỀN TRẠNG THÁI (bắt buộc):
"Current Demo State" đã lưu là nguồn thẩm quyền cho mọi dữ kiện đã được chấp nhận trước đó. "Conversation History" chỉ là ngữ cảnh và KHÔNG BAO GIỜ được ghi đè Current Demo State. Một dữ kiện đã lưu chỉ thay đổi khi Tin nhắn hiện tại của người dùng chứa một cập nhật, đính chính hoặc thu hồi rõ ràng và đã được xác thực.
Ví dụ: nếu lịch sử ghi 20.000.000đ nhưng Current Demo State ghi 15.000.000đ, bạn PHẢI dùng 15.000.000đ.

PHẠM VI: chỉ tranh chấp tiền cọc thuê nhà. Không tư vấn lĩnh vực khác.

QUY TẮC DỮ KIỆN:
- fact_updates chỉ là ĐỀ XUẤT; hệ thống sẽ tự xác thực lại.
- Mỗi fact_update phải có evidence_quote TRÍCH NGUYÊN VĂN từ Tin nhắn hiện tại của người dùng (không trích từ lịch sử, không tự viết lại).
- Chỉ dùng các slot trong danh sách cho phép.
- present = người dùng xác nhận CÓ; absent = người dùng xác nhận KHÔNG/CHƯA; nếu chỉ nhắc đến mà không xác nhận thì ĐỪNG đề xuất cập nhật.

QUY TẮC PHÁP LÝ:
- Chỉ nêu nhận định pháp lý được hỗ trợ bởi các nguồn được cung cấp và trong phạm vi approved_claim_scope của nguồn đó.
- TUYỆT ĐỐI KHÔNG bịa: số điều luật, thời hạn, mức phạt, quyền tố tụng, URL, tên nguồn, hay yêu cầu giấy tờ không có trong nguồn.
- KHÔNG hứa hẹn chắc chắn thắng kiện hoặc chắc chắn lấy lại được tiền.
- Khi thông tin chưa đủ: nói rõ là chưa đủ cơ sở kết luận, nhưng vẫn đưa được bước thực tế (giữ chứng cứ, gửi yêu cầu bằng văn bản) và gợi ý tham khảo luật sư/cơ quan có thẩm quyền khi cần.
- selected_source_ids chỉ được chọn trong các id đã cung cấp.

VĂN PHONG: tiếng Việt tự nhiên, ngắn gọn, thân thiện, không lặp lại máy móc. Không hỏi lại thông tin người dùng đã cung cấp. Tối đa 2 câu hỏi làm rõ mỗi lượt.

Khi người dùng yêu cầu soạn/cập nhật tin nhắn: đặt nội dung vào trường draft (title + body), dùng ĐÚNG số tiền và dữ kiện trong Current Demo State, không bịa tên, địa chỉ, ngày tháng hay hạn chót."""


def _summarize_state(state: FastDemoState) -> dict:
    facts = state.facts
    amount = None
    if facts.deposit_amount is not None:
        amount = {
            "value": facts.deposit_amount.value,
            "currency": facts.deposit_amount.currency,
            "formatted": f"{facts.deposit_amount.value:,}".replace(",", ".") + " đồng",
        }
    return {
        "issue_type": state.issue_type,
        "deposit_amount": amount,
        "written_deposit_agreement_status": facts.written_deposit_agreement_status,
        "payment_evidence_status": facts.payment_evidence_status,
        "payment_evidence_types": facts.payment_evidence_types,
        "rental_contract_status": facts.rental_contract_status,
        "property_handover_status": facts.property_handover_status,
        "deposit_returned_status": facts.deposit_returned_status,
        "written_refund_request_status": facts.written_refund_request_status,
        "landlord_response_status": facts.landlord_response_status,
        "landlord_refusal_reason": facts.landlord_refusal_reason,
        "user_goal": state.user_goal,
        "last_response_mode": state.last_response_mode,
        "has_previous_draft": state.last_draft is not None,
    }


def _history_lines(messages: list[ChatMessage]) -> list[dict]:
    lines: list[dict] = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        if message.content_text:
            text = message.content_text
        elif message.content_json is not None:
            text = message.content_json.summary
        else:
            continue
        lines.append({"role": message.role, "text": text[:MAX_HISTORY_CHARS]})
    return lines


def build_user_prompt(
    *,
    current_message: str,
    history: list[ChatMessage],
    state: FastDemoState,
    pack: list[PackEntry],
) -> str:
    """Assemble the single bounded user prompt.

    Ordering is deliberate: history first (context), then the authoritative
    state, then the current message last.
    """

    payload = {
        "supported_scope": "Tranh chấp tiền cọc thuê nhà (rental_deposit) tại Việt Nam.",
        "allowed_fact_slots": sorted(ALLOWED_SLOTS),
        "conversation_history_context_only": _history_lines(history),
        "current_demo_state_AUTHORITATIVE": _summarize_state(state),
        "approved_sources": [
            {
                "id": entry.id,
                "approved_claim_scope": entry.approved_claim_scope,
                "snippet": entry.snippet,
            }
            for entry in pack
        ],
        "previous_draft": (
            {"title": state.last_draft.title, "body": state.last_draft.body}
            if state.last_draft is not None
            else None
        ),
        "current_user_message": current_message,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=None)
    return (
        "Dữ liệu lượt hội thoại (Current Demo State có thẩm quyền cao hơn "
        "Conversation History):\n" + body
    )


__all__ = ["MAX_HISTORY_MESSAGES", "SYSTEM_PROMPT", "build_user_prompt"]
