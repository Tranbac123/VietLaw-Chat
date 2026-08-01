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

from ..contracts.fast_demo import FastDemoFacts, FastDemoState
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


# MVP safety decision: automatic clause-level selection is disabled (see
# `resolve_deposit_applicable_clause`), so exactly one general, conditional,
# article-level relevance note is used for every response -- never a
# clause-2-confirmed variant. Fixed text, never model-generated. It explains
# what Điều 328 concerns and explicitly conditions any further consequence
# on verified facts and the agreement; it never states that Khoản 2 applies,
# never promises a guaranteed recovery or automatic entitlement to double
# the deposit, and never states a specific compensation amount.
_DEPOSIT_RELEVANCE_ARTICLE_LEVEL_ONLY = (
    "Quy định này liên quan vì khoản đặt cọc được dùng để bảo đảm việc giao kết "
    "hoặc thực hiện hợp đồng thuê nhà. Hậu quả cụ thể còn phụ thuộc thỏa thuận đặt "
    "cọc, nội dung hợp đồng và các tình tiết đã được xác minh cụ thể trong từng vụ "
    "việc; văn bản đầy đủ của Điều 328 nêu rõ các trường hợp và hệ quả tương ứng."
)


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
        self, pack: list[PackEntry], selected_ids: list[str], facts: FastDemoFacts | None = None
    ) -> list[SourceObject]:
        """Intersect model-selected IDs with the exact pack it was given.

        Anything else -- an invented ID, a real ID that was not in this pack --
        is dropped. Only displayable authority types reach the UI.

        ``facts`` (optional, defaults to no non-performance signal) is this
        turn's already-validated state facts, passed through to the
        deposit-authority citation attachment (MODE_2D) -- never stored on
        this pack instance, which is a shared wiring-time singleton and must
        stay free of any per-request state. MVP safety decision: the source
        retains its curated `clause_numbers` as document metadata only; the
        MVP resolver never automatically selects a clause from these facts,
        so the deposit-authority citation always renders at article level
        (Điều 328) only, regardless of what `facts` contains.
        """

        resolved_facts = facts if facts is not None else FastDemoFacts()
        allowed = {entry.id: entry for entry in pack}
        resolved: list[SourceObject] = []
        for source_id in selected_ids:
            entry = allowed.get(source_id)
            if entry is None or not entry.displayable:
                continue
            source = entry.source
            if source.id == DEPOSIT_AUTHORITY_ID:
                # Article-level citation (MODE_2D), attached here, backend-
                # side -- never from the model's own text. MVP safety
                # decision: `attach_deposit_citation_metadata` never
                # automatically selects a clause; the source always renders
                # at Điều 328 only. See `resolve_deposit_applicable_clause`
                # for the current (unconditional `None`) behavior.
                source = attach_deposit_citation_metadata(source, resolved_facts)
            if source not in resolved:
                resolved.append(source)
        return resolved


def resolve_deposit_applicable_clause(
    facts: FastDemoFacts, clause_numbers: list[int] | None = None
) -> int | None:
    """MVP safety decision: automatic clause-level selection from free-form
    language is disabled. Article-level citation remains enabled.

    Correction rounds 1 through 6 progressively narrowed the conditions
    under which free-form Vietnamese text could resolve
    `receiving_party_nonperformance_status == "confirmed"` and therefore
    select Khoản 2 Điều 328 -- first from a legally overbroad rule, then
    through a series of context guards, actor-binding schemes, and finally a
    conservative positive-event grammar. Independent verification kept
    finding narrow adversarial inputs that still confirmed unsafely. Rather
    than continuing to patch inference (round 7 of the same problem), the
    product decision for this MVP is to stop deriving a structured legal
    consequence from free-form language altogether: this resolver now
    unconditionally returns `None`, regardless of `facts`, of
    `clause_numbers`, or of any upstream inference result.

    The complete curated Điều 328 article remains fully available and is
    still rendered; only the automatic Khoản-2 selection is disabled.
    `receiving_party_nonperformance_status` may still be computed and
    persisted for future work, but it has zero authority here:

        NONPERFORMANCE_FACT_MAY_EXIST=yes
        NONPERFORMANCE_FACT_CONTROLS_APPLICABLE_CLAUSE=no

    `clause_numbers` is still accepted as a parameter (not removed, so the
    call sites and the runtime membership invariant in
    `attach_deposit_citation_metadata` are unaffected) but is intentionally
    unused: no fact state or curated clause list can make this function
    return anything but `None`.
    """

    return None


def attach_deposit_citation_metadata(source: SourceObject, facts: FastDemoFacts) -> SourceObject:
    """Backend-resolved citation precision for the deposit-authority source only.

    `applicable_clause` and `relevance_note` are never model output: both are
    computed here from already-validated `FastDemoState` facts and a single
    fixed, general, conditional relevance text, so an "applicable clause"
    can never be invented by the model or parsed from its prose. A no-op for
    every other source, including the two other bounded Civil Code IDs,
    which carry no article-level metadata in this task.

    MVP safety decision: `resolve_deposit_applicable_clause` always returns
    `None` now (see its docstring), so `clause` below is always `None` and
    the relevance note is always the single article-level-only text. The
    runtime membership invariant below is kept as defense in depth even
    though it is currently never exercised -- if a future change to the
    resolver ever disagrees with the source's own curated `clause_numbers`,
    this still fails closed to no-clause rather than rendering an uncurated
    one.
    """

    if source.id != DEPOSIT_AUTHORITY_ID or not source.article_number:
        return source

    clause = resolve_deposit_applicable_clause(facts, source.clause_numbers)

    if clause is not None and clause not in source.clause_numbers:
        clause = None

    return source.model_copy(
        update={"applicable_clause": clause, "relevance_note": _DEPOSIT_RELEVANCE_ARTICLE_LEVEL_ONLY}
    )


__all__ = [
    "DEPOSIT_AUTHORITY_ID",
    "DISPLAYABLE_SOURCE_TYPES",
    "FastDemoSourcePack",
    "NO_SOURCE_ID",
    "PackEntry",
    "RENTAL_CHECKLIST_ID",
    "attach_deposit_citation_metadata",
    "resolve_deposit_applicable_clause",
]
