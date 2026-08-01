"""VietLaw Public Beta V0: GENERAL_GUIDANCE mode (task §7).

Deterministic, template-based, and makes NO provider call. This is a
deliberate design choice, not a shortcut: the strongest possible guarantee
against an invented article number, clause, penalty, deadline, or legal
conclusion is a generator that has no path to produce free-form legal
prose at all. Every sentence below is backend-authored, bounded, and
identical for every invocation of a given `LegalIntentSignal` -- nothing
here is templated FROM model output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeneralGuidanceContent:
    summary: str
    checklist: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    uncertainty_notice: str = ""


#: The fixed opening line (task §7, item 6: "no legal conclusion has been
#: established"). Always the first sentence of `summary`.
_NO_CONCLUSION_NOTICE = (
    "Tôi chưa có đủ nguồn chính thức để kết luận chính xác về điều luật hoặc mức xử lý áp "
    "dụng cho trường hợp này."
)

_SAFE_EVIDENCE_STEPS = [
    "Giữ lại biên bản, quyết định xử phạt hoặc giấy tờ liên quan (bản gốc và ảnh chụp).",
    "Ghi lại thời gian, địa điểm và diễn biến sự việc trong khi còn nhớ rõ.",
    "Không ký vào bất kỳ giấy tờ nào bạn chưa đọc và hiểu rõ nội dung.",
]

_SAFE_PROCEDURAL_STEPS = [
    "Hỏi trực tiếp cơ quan hoặc cá nhân có thẩm quyền đã lập biên bản/ra quyết định để được "
    "giải thích căn cứ áp dụng cho trường hợp cụ thể của bạn.",
    "Nếu không đồng ý với quyết định, tìm hiểu quyền khiếu nại hoặc khởi kiện theo thủ tục "
    "hành chính hiện hành, trong thời hạn được ghi trên chính văn bản đó.",
]

_AUTHORITY_CATEGORIES = {
    "traffic": "cơ quan công an giao thông đã lập biên bản, hoặc một luật sư/trung tâm trợ giúp pháp lý",
    "labor": "phòng/sở lao động - thương binh và xã hội tại địa phương, hoặc một luật sư",
    "civil": "hòa giải viên cơ sở, hoặc một luật sư",
    "general": "cơ quan nhà nước có thẩm quyền liên quan trực tiếp đến vụ việc, hoặc một luật sư",
}


def build_general_guidance(
    *,
    issue_summary: str,
    clarifying_questions: list[str],
    authority_category: str = "general",
) -> GeneralGuidanceContent:
    """Build the required 6-part structure (task §7):

      1. what issue the user appears to be facing  -> `issue_summary`
      2. which facts need clarification             -> `clarifying_questions`
      3. safe documents/evidence to preserve         -> checklist (evidence)
      4. general procedural options                 -> checklist (procedure)
      5. appropriate authority/professional category -> checklist (authority)
      6. explicit no-conclusion statement            -> summary opening line

    `issue_summary` must itself already avoid inventing specifics (the
    caller -- `legal_fallback_orchestrator.py` -- builds it only from the
    user's own message and already-accepted facts, never from a model-
    generated legal conclusion).
    """

    authority = _AUTHORITY_CATEGORIES.get(authority_category, _AUTHORITY_CATEGORIES["general"])
    summary_parts = [_NO_CONCLUSION_NOTICE]
    if issue_summary.strip():
        summary_parts.append(issue_summary.strip())
    summary = " ".join(summary_parts)

    checklist = list(_SAFE_EVIDENCE_STEPS)
    next_steps = list(_SAFE_PROCEDURAL_STEPS) + [
        f"Bạn có thể liên hệ {authority} để được hướng dẫn cụ thể hơn cho trường hợp của mình."
    ]

    return GeneralGuidanceContent(
        summary=summary,
        checklist=checklist,
        next_steps=next_steps,
        uncertainty_notice=(
            "Đây là hướng dẫn chung, không phải kết luận pháp lý cho trường hợp cụ thể của bạn."
        ),
    )


__all__ = ["GeneralGuidanceContent", "build_general_guidance"]
