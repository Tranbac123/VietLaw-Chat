"""Small owner-approved deterministic MVP domain policy."""

from __future__ import annotations

from .analysis_state import DomainAssessment, ResolvedContext

_RULES = (
    ("domain.high_risk.v1", "high_risk", ("triệu tập", "khởi tố", "tử vong", "phá hủy chứng cứ", "làm giả", "né công an", "đe dọa con nợ")),
    ("domain.traffic.v1", "traffic", ("giao thông", "tai nạn", "phạt nguội", "bằng lái")),
    ("domain.household_business.v1", "household_business", ("hộ kinh doanh", "đăng ký kinh doanh")),
    ("domain.administrative.v1", "administrative", ("quyết định hành chính", "thủ tục hành chính", "khiếu nại")),
    ("domain.civil.v1", "civil_dispute", ("đặt cọc", "hợp đồng", "tranh chấp", "chủ nhà", "con nợ", " khoản nợ")),
)
_UNSUPPORTED = ("nấu ăn", "lập trình", "thời tiết", "bóng đá", "du lịch")


def classify_domain(normalized_question: str, context: ResolvedContext) -> DomainAssessment:
    folded = normalized_question.casefold()
    if any(term in folded for term in _UNSUPPORTED):
        return DomainAssessment("unknown", "unsupported", False, ("domain.unsupported.v1",))
    for rule_id, domain, terms in _RULES:
        if any(term in folded for term in terms):
            insufficient = len(folded) < 24 or "không rõ" in folded or "tư vấn giúp" == folded
            return DomainAssessment(domain, "supported", not insufficient, (rule_id,))  # type: ignore[arg-type]
    prior_domains = [fact.value for fact in context.supporting_facts if fact.key == "domain"]
    if prior_domains and len(folded.split()) <= 5 and not context.conflicts:
        candidate = prior_domains[0]
        if candidate in {"civil_dispute", "traffic", "household_business", "administrative"}:
            return DomainAssessment(candidate, "supported", False, ("domain.prior_context.v1",))  # type: ignore[arg-type]
    return DomainAssessment("unknown", "ambiguous", False, ("domain.ambiguous.v1",))


__all__ = ["classify_domain"]
