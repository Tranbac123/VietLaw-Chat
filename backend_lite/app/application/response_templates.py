"""Deterministic VietLaw-Chat text for direct social/system responses.

PORT_PATTERN_ONLY from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
agent_core/conversation/response_composer.py:175-234 (ResponseComposer) --
only the "stateless lookup table keyed by template id" structure is reused.
None of TOMTIT's response text is copied; all strings below are target-owned
and describe VietLaw-Chat truthfully.

No LLM, no memory, no tools, no I/O, no env/config reads. Text must never:
  - claim to replace a lawyer;
  - claim to support every area of law;
  - claim to have taken an action (filed something, contacted an authority,
    verified documents);
  - claim an LLM is in use if the calling runtime does not use one here.
"""

from __future__ import annotations

_GREETING = "Chào bạn, hôm nay tôi có thể hỗ trợ gì cho bạn?"

_IDENTITY = (
    "Tôi là VietLaw-Chat, một trợ lý AI hỗ trợ định hướng pháp lý ban đầu. "
    "Tôi chỉ hoạt động trong phạm vi dữ liệu và chức năng đã được cấu hình, "
    "và không thay thế luật sư."
)

_CAPABILITY = (
    "Hiện tại tôi có thể hỗ trợ phân tích ban đầu một số vấn đề pháp lý thuộc phạm vi đã "
    "được cấu hình, giúp xác định thông tin còn thiếu, và đưa ra checklist cùng các bước "
    "tiếp theo. Khi có nguồn phù hợp, tôi sẽ hiển thị nguồn tham khảo. Tôi không hỗ trợ "
    "mọi lĩnh vực pháp luật và không đưa ra kết luận pháp lý chính thức."
)

_TEMPLATES: dict[str, str] = {
    "greeting": _GREETING,
    "identity": _IDENTITY,
    "capability": _CAPABILITY,
}


def render_social_response(template_id: str) -> str:
    """Return the deterministic text for `template_id`, or fail loudly."""
    try:
        return _TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError(f"no social response template for id {template_id!r}") from exc


__all__ = ["render_social_response"]
