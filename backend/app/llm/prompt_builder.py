"""Prompt builder.

Assembles a grounded, content-only prompt. The LLM may output ONLY the 5 content
fields and may reference sources solely via used_source_ids from allowed ids. It is
explicitly told NOT to emit backend-owned fields (domain/risk/decision/sources/etc).
"""
from app.rag.rag_retriever import RetrievedSource
from app.schemas import Decision, Domain, RiskLevel

_SYSTEM = (
    "Bạn là VietLaw-Chat, trợ lý định hướng pháp lý ban đầu bằng tiếng Việt. "
    "Bạn KHÔNG phải luật sư và không thay thế tư vấn pháp lý chính thức. Bạn giúp người "
    "dùng hiểu loại vấn đề, xác định thông tin còn thiếu, chuẩn bị giấy tờ, gợi ý bước "
    "tiếp theo an toàn và biết khi nào nên gặp luật sư/cơ quan chức năng.\n\n"
    "Quy tắc:\n"
    "- Trả lời bằng tiếng Việt.\n"
    "- Không đảm bảo kết quả pháp lý, không nói chắc chắn thắng/thua.\n"
    "- Không hướng dẫn hành vi trái luật, né tránh, che giấu, hoặc làm giả.\n"
    "- Không bịa nguồn, số điều luật, tên cơ quan hay URL.\n"
    "- Chỉ dùng các nguồn đã truy xuất bên dưới cho nhận định pháp lý/thủ tục.\n"
    "- Nếu nguồn không đủ, nói rõ mức độ nguồn còn hạn chế và tránh kết luận mạnh.\n"
    "- Chỉ trả về JSON theo schema content-only bên dưới."
)

_SCHEMA = (
    "Các trường JSON bắt buộc (chỉ những trường này):\n"
    "{\n"
    '  "summary": "tóm tắt ngắn bằng tiếng Việt, thận trọng, không phán quyết pháp lý",\n'
    '  "clarifying_questions": ["câu hỏi 1", "câu hỏi 2"],\n'
    '  "checklist": ["mục 1", "mục 2"],\n'
    '  "next_steps": ["bước 1", "bước 2"],\n'
    '  "used_source_ids": ["chỉ id nằm trong danh sách allowed_source_ids"]\n'
    "}\n"
    "Không xuất domain, risk_level, decision, sources, safety_notice, confidence, "
    "metadata hay bất kỳ id/chat_id nào. Chỉ JSON, không thêm văn bản ngoài JSON."
)


def _format_sources(sources: list[RetrievedSource]) -> str:
    if not sources:
        return "Hiện chưa có nguồn phù hợp được truy xuất cho câu hỏi này."
    lines = []
    for i, s in enumerate(sources, 1):
        lines.append(
            f"Source {i}:\n"
            f"id: {s.id}\n"
            f"title: {s.title}\n"
            f"source_name: {s.source_name}\n"
            f"source_type: {s.source_type}\n"
            f"status: {s.status}\n"
            f"text: {s.text}\n"
            f"plain_summary: {s.plain_language_summary or ''}"
        )
    return "\n\n".join(lines)


def build_prompt(question: str, context_summary: str, domain: Domain, risk_level: RiskLevel,
                 decision: Decision, sources: list[RetrievedSource],
                 allowed_source_ids: list[str]) -> str:
    return "\n\n".join([
        _SYSTEM,
        f"Ngữ cảnh trong cùng cuộc trò chuyện:\n{context_summary or '(không có)'}",
        f"Câu hỏi mới nhất của người dùng:\n{question}",
        ("Ngữ cảnh phân loại từ backend:\n"
         f"- predicted_domain: {domain.value}\n"
         f"- predicted_risk_level: {risk_level.value}\n"
         f"- decision_hint: {decision.value}"),
        f"Nguồn đã truy xuất:\n{_format_sources(sources)}",
        f"Allowed retrieved source ids:\n{allowed_source_ids}",
        _SCHEMA,
    ])
