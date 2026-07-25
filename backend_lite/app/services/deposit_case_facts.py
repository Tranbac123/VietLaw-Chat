from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .input_normalizer import InputNormalizer

FollowUpIntent = Literal["action_request", "risk_concern", "fact_update", "general_follow_up"]

_AMOUNT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*tr(?:ieu)?\b")

_WRITTEN_AGREEMENT_PHRASES = ("giay viet tay", "giay dat coc")
_SIGNATURE_PHRASES = ("chu ky",)
_SIGNATURE_NEGATIONS = ("khong co chu ky", "chua co chu ky", "khong ky")
_PAYMENT_PROOF_PHRASES = ("bien nhan", "chung tu chuyen khoan")
_BANK_TRANSFER_PHRASES = ("chuyen khoan",)
_CASH_PHRASES = ("dua tien mat", "tien mat")
_NOT_DELIVERED_PHRASES = ("khong giao nha", "chua giao nha", "khong nhan duoc nha")
_REFUND_REFUSED_PHRASES = ("khong tra coc", "khong hoan lai", "khong hoan tra", "khong tra lai tien")

_ACTION_REQUEST_PHRASES = ("nen lam gi", "phai lam sao", "buoc tiep theo")
_RISK_CONCERN_PHRASES = ("so bi quyt", "mat tien khong", "lay lai duoc tien", "co mat tien khong")

# Priority order matches section 4 rule 5: signature, payment proof, refund terms, timeline.
QUESTION_PRIORITY: tuple[tuple[str, str], ...] = (
    ("signature", "Giấy đặt cọc/thoả thuận đó đã có chữ ký của hai bên chưa?"),
    ("payment_proof", "Bạn có chứng từ chuyển khoản hoặc biên nhận tiền cọc không?"),
    ("refund_terms", "Thoả thuận có ghi điều khoản hoàn trả hoặc mất cọc khi vi phạm không?"),
    ("timeline", "Sự việc (đặt cọc, thời hạn giao nhà, yêu cầu hoàn cọc) diễn ra theo mốc thời gian nào?"),
)


@dataclass(eq=True)
class DepositCaseFacts:
    deposit_amount_millions: float | None = None
    has_written_agreement: bool = False
    has_signature: bool = False
    has_payment_proof: bool = False
    payment_method: Literal["bank_transfer", "cash"] | None = None
    property_not_delivered: bool = False
    refund_refused: bool = False
    refund_terms_known: bool = False
    timeline_known: bool = False

    def merge(self, other: "DepositCaseFacts") -> "DepositCaseFacts":
        return DepositCaseFacts(
            deposit_amount_millions=(
                other.deposit_amount_millions
                if other.deposit_amount_millions is not None
                else self.deposit_amount_millions
            ),
            has_written_agreement=self.has_written_agreement or other.has_written_agreement,
            has_signature=self.has_signature or other.has_signature,
            has_payment_proof=self.has_payment_proof or other.has_payment_proof,
            payment_method=other.payment_method or self.payment_method,
            property_not_delivered=self.property_not_delivered or other.property_not_delivered,
            refund_refused=self.refund_refused or other.refund_refused,
            refund_terms_known=self.refund_terms_known or other.refund_terms_known,
            timeline_known=self.timeline_known or other.timeline_known,
        )

    def known_question_ids(self) -> set[str]:
        known: set[str] = set()
        if self.has_signature:
            known.add("signature")
        if self.has_payment_proof:
            known.add("payment_proof")
        if self.refund_terms_known:
            known.add("refund_terms")
        if self.timeline_known:
            known.add("timeline")
        return known

    def is_empty(self) -> bool:
        return self == DepositCaseFacts()


def _has_phrase_without_negation(
    text: str, phrases: tuple[str, ...], negations: tuple[str, ...] = ()
) -> bool:
    for phrase in phrases:
        if phrase in text:
            if any(negation in text for negation in negations):
                continue
            return True
    return False


def extract_facts_from_text(text: str, normalizer: InputNormalizer) -> DepositCaseFacts:
    """Deterministic bounded fact extraction for the S1/S2 deposit demo.

    Not a general NLP model: matches only the fixed phrase set required by the task.
    """
    if not text:
        return DepositCaseFacts()
    _, accentless = normalizer.normalize(text)
    facts = DepositCaseFacts()

    amount_match = _AMOUNT_PATTERN.search(accentless)
    if amount_match:
        try:
            facts.deposit_amount_millions = float(amount_match.group(1).replace(",", "."))
        except ValueError:
            facts.deposit_amount_millions = None

    if any(phrase in accentless for phrase in _WRITTEN_AGREEMENT_PHRASES):
        facts.has_written_agreement = True

    if _has_phrase_without_negation(accentless, _SIGNATURE_PHRASES, _SIGNATURE_NEGATIONS):
        facts.has_signature = True

    if any(phrase in accentless for phrase in _PAYMENT_PROOF_PHRASES):
        facts.has_payment_proof = True

    if any(phrase in accentless for phrase in _BANK_TRANSFER_PHRASES):
        facts.payment_method = "bank_transfer"
        facts.has_payment_proof = True
    elif any(phrase in accentless for phrase in _CASH_PHRASES):
        facts.payment_method = "cash"

    if any(phrase in accentless for phrase in _NOT_DELIVERED_PHRASES):
        facts.property_not_delivered = True

    if any(phrase in accentless for phrase in _REFUND_REFUSED_PHRASES):
        facts.refund_refused = True

    return facts


def extract_facts(texts: list[str], normalizer: InputNormalizer) -> DepositCaseFacts:
    facts = DepositCaseFacts()
    for text in texts:
        facts = facts.merge(extract_facts_from_text(text, normalizer))
    return facts


def classify_follow_up_intent(
    current_text: str, message_facts: DepositCaseFacts, normalizer: InputNormalizer
) -> FollowUpIntent:
    _, accentless = normalizer.normalize(current_text)
    if any(phrase in accentless for phrase in _ACTION_REQUEST_PHRASES):
        return "action_request"
    if any(phrase in accentless for phrase in _RISK_CONCERN_PHRASES):
        return "risk_concern"
    if not message_facts.is_empty():
        return "fact_update"
    return "general_follow_up"


def select_clarifying_questions(
    facts: DepositCaseFacts,
    already_asked: set[str],
    max_questions: int = 2,
) -> list[tuple[str, str]]:
    known = facts.known_question_ids()
    selected: list[tuple[str, str]] = []
    for question_id, question_text in QUESTION_PRIORITY:
        if question_id in known or question_id in already_asked:
            continue
        selected.append((question_id, question_text))
        if len(selected) >= max_questions:
            break
    return selected


def format_deposit_amount(facts: DepositCaseFacts) -> str | None:
    if facts.deposit_amount_millions is None:
        return None
    value = facts.deposit_amount_millions
    if value == int(value):
        return f"{int(value)} triệu đồng"
    return f"{value:g} triệu đồng"


def known_facts_summary_fragments(facts: DepositCaseFacts) -> list[str]:
    fragments: list[str] = []
    amount = format_deposit_amount(facts)
    if amount:
        fragments.append(f"khoản đặt cọc {amount}")
    if facts.has_written_agreement:
        fragments.append("có giấy đặt cọc/giấy viết tay")
    if facts.property_not_delivered:
        fragments.append("nhà chưa được bàn giao")
    if facts.refund_refused:
        fragments.append("chủ nhà chưa hoàn lại tiền cọc")
    if facts.has_signature:
        fragments.append("giấy tờ đã có chữ ký hai bên")
    if facts.payment_method == "bank_transfer":
        fragments.append("tiền cọc chuyển khoản")
    elif facts.payment_method == "cash":
        fragments.append("tiền cọc đưa tiền mặt")
    return fragments
