"""VietLaw Public Beta V0: the trust-level contract.

Every answer the legal-fallback vertical produces (curated traffic, official
web search, or general guidance) is labelled with exactly one of three trust
levels. This module is the single source of truth for the Vietnamese label
and explanation text, so the backend and any future surface (frontend,
evaluation, logs) can never disagree about what a level means.

Bounded and additive: this module does not modify `contracts/fast_demo.py`
or any MODE_2D behavior. The existing rental-deposit flow does not currently
render a trust badge, and this module does not require it to.
"""

from __future__ import annotations

from enum import Enum


class TrustLevel(str, Enum):
    """How the answer's legal support was established."""

    #: Answered entirely from the repository's own curated, human-verified
    #: data (the existing rental-deposit pack, or the new curated traffic
    #: pack). The strongest guarantee this system can give.
    CURATED_VERIFIED = "curated_verified"
    #: Answered after retrieving and inspecting a specific official
    #: Vietnamese government/legal-publication source at query time, which
    #: passed the deterministic evidence-sufficiency gate.
    OFFICIAL_SOURCE_SEARCH = "official_source_search"
    #: No curated rule matched and no official source cleared the evidence
    #: gate. Only safe, non-specific procedural guidance is given -- no
    #: article, clause, penalty, deadline, or legal conclusion is asserted.
    GENERAL_GUIDANCE = "general_guidance"


#: Required Vietnamese labels (task §4). Exact strings -- do not reword.
TRUST_LABELS: dict[TrustLevel, str] = {
    TrustLevel.CURATED_VERIFIED: "Đã kiểm chứng trong dữ liệu VietLaw",
    TrustLevel.OFFICIAL_SOURCE_SEARCH: "Tra cứu từ nguồn pháp luật chính thức",
    TrustLevel.GENERAL_GUIDANCE: "Hướng dẫn chung, chưa đủ căn cứ kết luận",
}

#: One-sentence Vietnamese explanation, shown in the frontend's expandable
#: tooltip. Deliberately does not repeat implementation vocabulary (no
#: "orchestrator", "fallback", "provider", "flag").
TRUST_EXPLANATIONS: dict[TrustLevel, str] = {
    TrustLevel.CURATED_VERIFIED: (
        "Nội dung này đã được đội ngũ VietLaw kiểm tra và xác minh trước, dựa trên văn bản "
        "pháp luật chính thức."
    ),
    TrustLevel.OFFICIAL_SOURCE_SEARCH: (
        "Nội dung này được tra cứu từ nguồn pháp luật chính thức của cơ quan nhà nước tại "
        "thời điểm bạn hỏi. Bạn nên đối chiếu lại với văn bản gốc trước khi sử dụng cho mục "
        "đích quan trọng."
    ),
    TrustLevel.GENERAL_GUIDANCE: (
        "Hệ thống chưa tìm đủ căn cứ pháp lý chính thức để kết luận cho trường hợp này. "
        "Đây chỉ là hướng dẫn chung, không thay thế tư vấn pháp lý chuyên nghiệp."
    ),
}


class EvidenceOutcome(str, Enum):
    """Deterministic outcome of the evidence-sufficiency gate (task §6.4)."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


#: Only SUFFICIENT may ever produce OFFICIAL_SOURCE_SEARCH. Every other
#: evidence outcome must fall through to GENERAL_GUIDANCE -- this mapping is
#: the single place that invariant is expressed, so a caller cannot
#: accidentally special-case a fourth outcome into a trust level.
EVIDENCE_OUTCOME_TRUST_LEVEL: dict[EvidenceOutcome, TrustLevel] = {
    EvidenceOutcome.SUFFICIENT: TrustLevel.OFFICIAL_SOURCE_SEARCH,
    EvidenceOutcome.INSUFFICIENT: TrustLevel.GENERAL_GUIDANCE,
    EvidenceOutcome.CONFLICTING: TrustLevel.GENERAL_GUIDANCE,
    EvidenceOutcome.UNAVAILABLE: TrustLevel.GENERAL_GUIDANCE,
}


def trust_label(level: TrustLevel) -> str:
    return TRUST_LABELS[level]


def trust_explanation(level: TrustLevel) -> str:
    return TRUST_EXPLANATIONS[level]


__all__ = [
    "EVIDENCE_OUTCOME_TRUST_LEVEL",
    "TRUST_EXPLANATIONS",
    "TRUST_LABELS",
    "EvidenceOutcome",
    "TrustLevel",
    "trust_explanation",
    "trust_label",
]
