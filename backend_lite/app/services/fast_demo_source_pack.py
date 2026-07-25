"""FAST DEMO V2 deterministic bounded source pack.

No embeddings, no vector search, no reranking, no new corpus. A small fixed
registry over the EXISTING owner-approved snippets, selected by response
intent and known facts, capped at three.

Each pack entry carries an ``approved_claim_scope``: a valid source ID does not
authorize claims beyond it. The backend owns all displayed source metadata; the
model only ever returns IDs, which are then intersected with the pack.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts.fast_demo import FastDemoState
from ..schemas.content import SourceObject

DEPOSIT_AUTHORITY_ID = "civil_deposit_001"
RENTAL_CHECKLIST_ID = "civil_rental_001"
CONTRACT_EFFECT_ID = "civil_contract_002"
NO_SOURCE_ID = "general_no_source_001"

# Source types that may be shown in the UI source panel. Curated notes and
# safety policies are useful model context but are not citable authorities,
# so they never render as a "source".
DISPLAYABLE_SOURCE_TYPES = frozenset({"official_source", "legal_snippet", "procedure"})

_CLAIM_SCOPE: dict[str, list[str]] = {
    DEPOSIT_AUTHORITY_ID: [
        "Định nghĩa đặt cọc và mục đích bảo đảm giao kết/thực hiện hợp đồng.",
        "Khi tranh chấp tiền cọc cần xem thỏa thuận đặt cọc và điều kiện hoàn trả/mất cọc.",
        "Không kết luận bên nào đúng khi chưa có đủ thông tin.",
    ],
    RENTAL_CHECKLIST_ID: [
        "Danh mục chứng cứ nên chuẩn bị khi tranh chấp thuê nhà hoặc tiền cọc.",
        "Không phải căn cứ pháp lý; chỉ là hướng dẫn thực hành chuẩn bị hồ sơ.",
    ],
    CONTRACT_EFFECT_ID: [
        "Hợp đồng giao kết hợp pháp có hiệu lực và các bên phải thực hiện cam kết.",
        "Không suy ra chế tài hay mức phạt cụ thể.",
    ],
    NO_SOURCE_ID: [
        "Khi chưa có nguồn phù hợp thì chỉ trả lời thận trọng và gợi ý kiểm tra thêm.",
    ],
}


@dataclass(frozen=True)
class PackEntry:
    id: str
    approved_claim_scope: list[str]
    snippet: str
    source: SourceObject

    @property
    def displayable(self) -> bool:
        return self.source.source_type in DISPLAYABLE_SOURCE_TYPES


class FastDemoSourcePack:
    """Fixed registry built once at wiring time from the approved snippet store."""

    def __init__(self, entries: dict[str, PackEntry]) -> None:
        self._entries = entries

    @classmethod
    def from_snippets(cls, snippets) -> "FastDemoSourcePack":
        entries: dict[str, PackEntry] = {}
        for snippet in snippets:
            if snippet.id not in _CLAIM_SCOPE:
                continue
            entries[snippet.id] = PackEntry(
                id=snippet.id,
                approved_claim_scope=list(_CLAIM_SCOPE[snippet.id]),
                snippet=snippet.text,
                source=snippet.as_source(),
            )
        return cls(entries)

    @property
    def available_ids(self) -> list[str]:
        return sorted(self._entries)

    def select(self, state: FastDemoState, message_cue: str) -> list[PackEntry]:
        """Bounded deterministic selection: at most three, fixed priority."""

        chosen: list[str] = []

        # The deposit authority is always relevant once a deposit matter exists.
        chosen.append(DEPOSIT_AUTHORITY_ID)

        wants_evidence = any(
            cue in message_cue
            for cue in ("bang chung", "chung cu", "giay to", "chuan bi", "ho so", "checklist")
        )
        facts = state.facts
        missing_paperwork = (
            facts.written_deposit_agreement_status == "absent"
            or facts.rental_contract_status == "absent"
        )
        if wants_evidence or missing_paperwork:
            chosen.append(RENTAL_CHECKLIST_ID)

        if facts.rental_contract_status == "present":
            chosen.append(CONTRACT_EFFECT_ID)

        entries: list[PackEntry] = []
        for source_id in chosen:
            entry = self._entries.get(source_id)
            if entry is not None and entry not in entries:
                entries.append(entry)
            if len(entries) >= 3:
                break
        return entries

    def resolve_selected(
        self, pack: list[PackEntry], selected_ids: list[str]
    ) -> list[SourceObject]:
        """Intersect model-selected IDs with the exact pack it was given.

        Anything else -- an invented ID, a real ID that was not in this pack --
        is dropped. Only displayable authority types reach the UI.
        """

        allowed = {entry.id: entry for entry in pack}
        resolved: list[SourceObject] = []
        for source_id in selected_ids:
            entry = allowed.get(source_id)
            if entry is None or not entry.displayable:
                continue
            if entry.source not in resolved:
                resolved.append(entry.source)
        return resolved


__all__ = [
    "DEPOSIT_AUTHORITY_ID",
    "DISPLAYABLE_SOURCE_TYPES",
    "FastDemoSourcePack",
    "NO_SOURCE_ID",
    "PackEntry",
    "RENTAL_CHECKLIST_ID",
]
