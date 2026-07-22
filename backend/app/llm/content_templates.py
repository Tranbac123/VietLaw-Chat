"""Deterministic Vietnamese content for paths where the LLM is skipped or failed.

The LLM only drafts content for answer_with_guidance / ask_clarifying_questions.
Refusal, escalation, unsupported, and fallback content is templated here so unsafe
and high-risk responses are never LLM-authored (no tactical text can leak), and so
a failed LLM call still returns cautious, safe content.
"""
from app.nlp.patterns import PatternBank
from app.schemas import Decision, Domain, LLMContent

_CLARIFYING = {
    Domain.civil_dispute: [
        "Bạn có hợp đồng hoặc thỏa thuận bằng văn bản không?",
        "Có chứng từ chuyển khoản hoặc biên nhận không?",
        "Số tiền tranh chấp khoảng bao nhiêu?",
        "Sự việc xảy ra từ khi nào?",
    ],
    Domain.traffic: [
        "Bạn có thể nhập lại nội dung lỗi ghi trong biên bản không?",
        "Biên bản ghi thời gian, địa điểm và hành vi vi phạm như thế nào?",
        "Có tai nạn, thương tích hoặc thiệt hại tài sản không?",
        "Bạn muốn hiểu lỗi, chuẩn bị giấy tờ, hay hỏi cách khiếu nại?",
    ],
    Domain.household_business: [
        "Bạn bán tại nhà, thuê mặt bằng, hay chỉ bán trực tuyến?",
        "Bạn bán loại thực phẩm/hàng hóa gì?",
        "Quy mô bán hàng là nhỏ lẻ hay có nhân viên?",
        "Bạn bán trong một địa phương hay giao hàng liên tỉnh?",
    ],
    Domain.administrative: [
        "Bạn cần thực hiện thủ tục hành chính nào?",
        "Bạn đã có sẵn những giấy tờ gì?",
        "Bạn dự định nộp hồ sơ ở cơ quan nào?",
    ],
    Domain.high_risk: [
        "Bạn có giấy tờ, biên bản hoặc giấy mời liên quan không?",
        "Vụ việc xảy ra khi nào?",
        "Có ai bị thương hoặc bị đe dọa không?",
        "Bạn đã liên hệ luật sư hoặc cơ quan chức năng chưa?",
    ],
    Domain.unknown: [
        "Bạn có thể mô tả rõ hơn vụ việc không?",
        "Vụ việc xảy ra khi nào và ở đâu?",
        "Bạn có giấy tờ, biên bản, hợp đồng hoặc chứng từ liên quan không?",
    ],
}

_CHECKLIST = {
    Domain.civil_dispute: [
        "Hợp đồng hoặc thỏa thuận liên quan",
        "Chứng từ chuyển khoản hoặc biên nhận",
        "Tin nhắn/email trao đổi",
        "Quá trình xảy ra sự việc",
        "Thông tin bên liên quan",
    ],
    Domain.traffic: [
        "Biên bản hoặc giấy phạt",
        "Giấy phép lái xe",
        "Giấy đăng ký xe",
        "Bảo hiểm trách nhiệm dân sự nếu có liên quan",
        "Giấy tờ cá nhân cần thiết",
    ],
    Domain.household_business: [
        "Thông tin cá nhân chủ hộ",
        "Địa điểm kinh doanh",
        "Ngành nghề kinh doanh",
        "Loại hàng hóa/dịch vụ",
        "Giấy tờ liên quan an toàn thực phẩm nếu bán đồ ăn",
        "Thông tin cơ quan địa phương cần liên hệ",
    ],
    Domain.administrative: [
        "Giấy tờ cá nhân",
        "Hồ sơ/tài liệu liên quan đến thủ tục",
        "Thông tin cơ quan tiếp nhận hồ sơ",
    ],
    Domain.high_risk: [
        "Giấy mời/biên bản/tài liệu liên quan",
        "Giấy tờ cá nhân",
        "Quá trình xảy ra sự việc",
        "Danh sách người liên quan/nhân chứng nếu có",
        "Tài liệu/chứng cứ hợp pháp",
        "Câu hỏi cần hỏi luật sư",
    ],
    Domain.unknown: [
        "Giấy tờ hoặc tài liệu liên quan",
        "Quá trình xảy ra sự việc",
        "Tin nhắn/email/chứng từ nếu có",
    ],
}

_NEXT_STEPS_DEFAULT = [
    "Tập hợp giấy tờ và bằng chứng liên quan.",
    "Ghi lại quá trình xảy ra sự việc.",
    "Nếu cần, trao đổi bằng văn bản với bên liên quan.",
    "Nếu vụ việc quan trọng hoặc số tiền lớn, nên tham khảo luật sư hoặc cơ quan chức năng.",
]

_NEXT_STEPS_HIGH_RISK = [
    "Chuẩn bị giấy tờ liên quan và ghi lại timeline sự việc.",
    "Liên hệ luật sư hoặc cơ quan chức năng để được hướng dẫn chính thức.",
    "Không tự ý làm điều trái luật, không che giấu hoặc làm giả chứng cứ.",
]


def template_questions(domain: Domain) -> list[str]:
    return list(_CLARIFYING.get(domain, _CLARIFYING[Domain.unknown]))


def template_checklist(domain: Domain) -> list[str]:
    return list(_CHECKLIST.get(domain, _CHECKLIST[Domain.unknown]))


def template_next_steps(domain: Domain) -> list[str]:
    return list(_NEXT_STEPS_HIGH_RISK if domain == Domain.high_risk else _NEXT_STEPS_DEFAULT)


def refusal_content(unsafe, bank: PatternBank) -> LLMContent:
    summary = bank.safe_replacement_phrases.get("unsafe_refusal", "Tôi không thể hỗ trợ yêu cầu này.")
    return LLMContent(
        summary=summary,
        clarifying_questions=[],
        checklist=template_checklist(Domain.high_risk),
        next_steps=_NEXT_STEPS_HIGH_RISK,
        used_source_ids=[],
    )


def escalation_content(domain: Domain, bank: PatternBank) -> LLMContent:
    summary = bank.safe_replacement_phrases.get(
        "high_risk_escalation", "Vụ việc này có rủi ro pháp lý cao.")
    return LLMContent(
        summary=summary,
        clarifying_questions=template_questions(Domain.high_risk),
        checklist=template_checklist(Domain.high_risk),
        next_steps=_NEXT_STEPS_HIGH_RISK,
        used_source_ids=[],
    )


def unsupported_content(bank: PatternBank, reason: str = "non_legal") -> LLMContent:
    if reason == "language":
        return LLMContent(
            summary=("Bản MVP hiện chỉ hỗ trợ câu hỏi pháp lý bằng tiếng Việt. "
                     "Tính năng song ngữ Anh-Việt sẽ được xem xét ở phiên bản nâng cấp."),
            clarifying_questions=[],
            checklist=[],
            next_steps=["Vui lòng nhập câu hỏi pháp lý bằng tiếng Việt để bản MVP có thể phân tích."],
            used_source_ids=[],
        )
    return LLMContent(
        summary=bank.safe_replacement_phrases.get(
            "unsupported", "Câu hỏi này nằm ngoài phạm vi bản demo."),
        clarifying_questions=[],
        checklist=[],
        next_steps=[],
        used_source_ids=[],
    )


def fallback_content(domain: Domain, bank: PatternBank) -> LLMContent:
    return LLMContent(
        summary=("Hiện hệ thống chưa đủ thông tin hoặc chưa xử lý được nội dung trả lời. "
                 "Tôi có thể giúp bạn xác định thông tin cần chuẩn bị trước."),
        clarifying_questions=template_questions(domain),
        checklist=template_checklist(domain),
        next_steps=[
            "Không nên dựa vào phản hồi này như tư vấn pháp lý chính thức.",
            "Nếu vụ việc quan trọng, hãy tham khảo luật sư hoặc cơ quan chức năng.",
        ],
        used_source_ids=[],
    )
