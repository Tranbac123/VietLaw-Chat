"""DEMO A2 LITE — SCRIPTED rental_deposit scenario classifier + bounded extractor.

NOT a general Vietnamese grammar. Extraction runs ONLY after the scenario
classifier approves one of the deposit scenario families, and derives facts only
from a small set of owner-approved anchored patterns. Current message only; no
store, no episode selection, no prior-history extraction.

V4 complete-message closure (owner decision, see REMEDIATION_V4):
  - ``DEMO_CLASSIFICATION_MODE=complete_message_allowlist``;
  - a message activates a deposit scenario only if its ENTIRE
    eligibility-normalized text ``re.fullmatch``es one owner-approved template
    (start AND end anchored). A valid paid-deposit prefix followed by ANY
    unrelated residual clause ("... Tôi bị sa thải. Tôi nên làm gì?") no longer
    matches any template and is UNSUPPORTED -- the prior start-only ``search``
    anchor (which let cue detectors match anywhere in the remainder) is removed;
  - quoted, definitional, third-party, future ("sẽ"), planned ("dự định"),
    required ("phải"), negated ("chưa"), uncertain ("đoán"), or residual-bearing
    mentions never fullmatch a template, so they are UNSUPPORTED;
  - only the approved fixed fact clauses are captured; no general polarity grammar.

Every TextAnchor is built through ``create_validated_text_anchor`` against the NFC
original, so ``anchor.quote == nfc_original[anchor.start:anchor.end]``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..contracts.demo_llm import DemoScenario
from ..contracts.legal_facts import (
    Claimant,
    ExistenceValue,
    FactOpKind,
    MoneyAmount,
    PaymentEvidenceValue,
    TextAnchor,
    UnboundFactOperation,
    validate_text_anchor,
)

EXTRACTOR_VERSION = "demo_extractor.v4_scripted"

SUPPORTED_SLOTS: frozenset[str] = frozenset(
    {
        "deposit_amount",
        "written_agreement_exists",
        "payment_evidence_exists",
        "property_handed_over",
        "deposit_returned",
    }
)

# Amount unit tokens (NFC, accented + unaccented). Matched on the NFC original so
# offsets are exact for the anchor.
_AMOUNT = re.compile(
    r"(\d[\d.,]*)\s*(triệu|trieu|tr|đồng|dong|nghìn|nghin|ngàn|ngan)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Normalization for eligibility / scenario matching (NOT for anchor offsets)
# ---------------------------------------------------------------------------

_SEPARATORS = re.compile(r"[-_/\\()\[\]{}.·,;:!?\"'“”‘’]+")


def normalize_for_eligibility(text: str) -> str:
    """NFC -> lower -> strip Vietnamese accents -> separators to space -> collapse.

    Used only for safety and scenario matching. Never used for TextAnchor offsets
    (those use the NFC original). Normalizes obfuscations such as ``mã-tấu`` ->
    ``ma tau`` and ``example[.]com`` -> ``example com``.
    """

    nfc = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", nfc.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    stripped = stripped.replace("đ", "d")
    spaced = _SEPARATORS.sub(" ", stripped)
    return re.sub(r"\s+", " ", spaced).strip()


# ---------------------------------------------------------------------------
# Approved COMPLETE-MESSAGE templates (matched on the normalized eligibility
# text with re.fullmatch -- anchored at BOTH message start and message end).
# No arbitrary extra clause, before, between, or after the approved clauses, is
# permitted. Benign whitespace is already collapsed by normalize_for_eligibility.
# ---------------------------------------------------------------------------

# A generic amount token as it appears in normalized text: normalize_for_eligibility
# maps '.', ',', and other separators to spaces, so "20.000.000" -> "20 000 000".
_AMOUNT_TOKEN = r"\d[\d\s]*(?:trieu|tr|dong|nghin|ngan)"

_TEMPLATES: tuple[tuple[re.Pattern[str], DemoScenario], ...] = (
    # B. DEPOSIT_FACT_UPDATE
    (re.compile(rf"toi da dat coc {_AMOUNT_TOKEN}"), DemoScenario.DEPOSIT_FACT_UPDATE),
    (re.compile(rf"toi da dat coc {_AMOUNT_TOKEN} toi khong co giay dat coc nhung co sao ke chuyen khoan"),
     DemoScenario.DEPOSIT_FACT_UPDATE),
    (re.compile(rf"toi da dua {_AMOUNT_TOKEN} tien coc"), DemoScenario.DEPOSIT_FACT_UPDATE),
    (re.compile(rf"toi da dua {_AMOUNT_TOKEN} tien coc con hop dong ghi {_AMOUNT_TOKEN}"),
     DemoScenario.DEPOSIT_FACT_UPDATE),
    # C. DEPOSIT_LEGAL_GUIDANCE
    (re.compile(
        rf"toi da dat coc {_AMOUNT_TOKEN} khong co giay dat coc co sao ke chuyen khoan "
        rf"chua duoc ban giao nha va chu nha chua tra lai tien coc toi nen lam gi"
    ), DemoScenario.DEPOSIT_LEGAL_GUIDANCE),
    # D. DEPOSIT_DRAFT_REQUEST
    (re.compile(
        rf"toi da dat coc {_AMOUNT_TOKEN} nhung chu nha chua tra lai tien coc "
        rf"viet giup toi tin nhan yeu cau hoan tra tien coc"
    ), DemoScenario.DEPOSIT_DRAFT_REQUEST),
)

# Approved fixed fact clauses (normalized substrings) -> (slot, present?).
_FACT_CLAUSES: tuple[tuple[str, str, bool], ...] = (
    ("khong co giay dat coc", "written_agreement_exists", False),
    ("co sao ke chuyen khoan", "payment_evidence_exists", True),
    ("co sao ke", "payment_evidence_exists", True),
    ("chua duoc ban giao nha", "property_handed_over", False),
    ("chua ban giao nha", "property_handed_over", False),
    ("chua tra lai tien coc", "deposit_returned", False),
    ("chua tra tien coc", "deposit_returned", False),
    ("chua hoan coc", "deposit_returned", False),
)

# NFC-original regexes for anchoring each captured fact clause (accent-flexible).
_FACT_CLAUSE_ANCHORS: dict[str, tuple[re.Pattern[str], ...]] = {
    "written_agreement_exists": (re.compile(r"không\s+có\s+giấy\s+đặt\s+cọc", re.IGNORECASE),
                                 re.compile(r"khong\s+co\s+giay\s+dat\s+coc", re.IGNORECASE)),
    "payment_evidence_exists": (re.compile(r"sao\s+kê", re.IGNORECASE), re.compile(r"sao\s+ke", re.IGNORECASE)),
    "property_handed_over": (re.compile(r"chưa\s+(?:được\s+)?bàn\s+giao\s+nhà", re.IGNORECASE),
                             re.compile(r"chua\s+(?:duoc\s+)?ban\s+giao\s+nha", re.IGNORECASE)),
    "deposit_returned": (re.compile(r"chưa\s+(?:trả\s+lại|trả|hoàn)\s+(?:tiền\s+)?cọc", re.IGNORECASE),
                         re.compile(r"chua\s+(?:tra\s+lai|tra|hoan)\s+(?:tien\s+)?coc", re.IGNORECASE)),
}


@dataclass
class ExtractionResult:
    operations: list[UnboundFactOperation] = field(default_factory=list)
    conflict_slots: list[str] = field(default_factory=list)

    def has_facts(self) -> bool:
        return bool(self.operations)


def create_validated_text_anchor(nfc_original: str, start: int, end: int, message_id: str) -> TextAnchor:
    anchor = TextAnchor(
        message_id=message_id,
        start=start,
        end=end,
        quote=nfc_original[start:end],
        text_form="nfc_original",
    )
    return validate_text_anchor(anchor, nfc_original)


def classify_demo_scenario(nfc_original: str) -> DemoScenario:
    """Classify a message into an approved deposit scenario, or UNSUPPORTED.

    Complete-message allowlist (V4): the ENTIRE normalized message must
    ``fullmatch`` one owner-approved template. A valid paid-deposit prefix
    followed by ANY unrelated residual clause never matches (no start-only /
    ``search`` anchoring), so it is UNSUPPORTED. Greeting/social is handled by
    the router; this only recognizes the three deposit scenario families.
    """

    norm = normalize_for_eligibility(nfc_original)
    for pattern, scenario in _TEMPLATES:
        if pattern.fullmatch(norm):
            return scenario
    return DemoScenario.UNSUPPORTED


def _anchor_for(nfc_original: str, patterns: tuple[re.Pattern[str], ...], message_id: str) -> TextAnchor | None:
    for pattern in patterns:
        match = pattern.search(nfc_original)
        if match is not None:
            return create_validated_text_anchor(nfc_original, match.start(), match.end(), message_id)
    return None


def _op(slot: str, op: FactOpKind, anchor: TextAnchor, value, index: int) -> UnboundFactOperation:
    return UnboundFactOperation(
        op=op,
        slot_hint=slot,
        issue_type_hint="rental_deposit",
        claimed_status=None,
        value=value,
        claimant=Claimant.USER,
        anchor=anchor,
        extractor_version=EXTRACTOR_VERSION,
        confidence=0.95,
        op_index=index,
    )


def extract_scenario_facts(nfc_original: str, scenario: DemoScenario, message_id: str) -> ExtractionResult:
    """Extract bounded facts from an already-approved deposit scenario message."""

    if scenario not in (
        DemoScenario.DEPOSIT_FACT_UPDATE,
        DemoScenario.DEPOSIT_LEGAL_GUIDANCE,
        DemoScenario.DEPOSIT_DRAFT_REQUEST,
    ):
        return ExtractionResult()
    if nfc_original != unicodedata.normalize("NFC", nfc_original):
        raise ValueError("extractor input must be NFC-normalized original text")

    norm = normalize_for_eligibility(nfc_original)
    ops: list[UnboundFactOperation] = []
    index = 0

    # deposit_amount: the FIRST amount in the message (the paid-deposit anchor
    # guarantees the message begins with the actual paid amount).
    amount_match = _AMOUNT.search(nfc_original)
    if amount_match is not None:
        vnd = _parse_amount(amount_match.group(1), amount_match.group(2))
        if vnd is not None:
            anchor = create_validated_text_anchor(nfc_original, amount_match.start(), amount_match.end(), message_id)
            ops.append(_op("deposit_amount", FactOpKind.SET_VALUE, anchor,
                           MoneyAmount(amount_vnd=vnd, precision="exact", as_written=amount_match.group(0).strip()), index))
            index += 1

    # Approved fixed fact clauses only.
    seen: set[str] = set()
    for phrase, slot, present in _FACT_CLAUSES:
        if slot in seen or phrase not in norm:
            continue
        anchor = _anchor_for(nfc_original, _FACT_CLAUSE_ANCHORS.get(slot, ()), message_id)
        if anchor is None:
            continue  # fail closed if the original span cannot be located
        if present:
            value = PaymentEvidenceValue(method="bank_transfer", has_document=True) if slot == "payment_evidence_exists" else ExistenceValue()
            ops.append(_op(slot, FactOpKind.AFFIRM, anchor, value, index))
        else:
            ops.append(_op(slot, FactOpKind.NEGATE, anchor, None, index))
        index += 1
        seen.add(slot)

    return ExtractionResult(operations=ops)


def _parse_amount(number_raw: str, unit: str) -> int | None:
    unit_low = unit.lower()
    cleaned = number_raw.strip()
    if unit_low in {"đồng", "dong"}:
        digits = re.sub(r"[.,\s]", "", cleaned)
        return int(digits) if digits.isdigit() else None
    if unit_low in {"nghìn", "nghin", "ngàn", "ngan"}:
        base = _decimal(cleaned)
        return int(round(base * 1_000)) if base is not None else None
    base = _decimal(cleaned)
    return int(round(base * 1_000_000)) if base is not None else None


def _decimal(raw: str) -> float | None:
    token = raw.strip()
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    elif token.count(".") == 1 and len(token.split(".")[1]) != 3:
        pass
    else:
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


__all__ = [
    "EXTRACTOR_VERSION",
    "SUPPORTED_SLOTS",
    "ExtractionResult",
    "classify_demo_scenario",
    "create_validated_text_anchor",
    "extract_scenario_facts",
    "normalize_for_eligibility",
]
