"""In-memory keyword RAG.

Two-bucket scoring (the point of the whole design): content_score decides
RELEVANCE, boost_score only re-ranks already-relevant candidates. Content comes
from tag/phrase matches on the raw folded query plus distinctive-token overlap on
title/summary/text — generic follow-up words ("giấy tờ", "chuẩn bị") are stoplisted
so a bare follow-up retrieves nothing until same-chat context adds real terms.
"""
from dataclasses import dataclass, field
from typing import Optional, Union

from app.errors import RetrievalError
from app.input_normalizer import NormalizedText, strip_accents
from app.schemas import Decision, Domain

RETRIEVAL_STRATEGY = "in_memory_keyword_v1"

_REQUIRED = ("id", "domain", "title", "source_name", "source_type", "status", "text",
             "tags", "last_checked")

# Generic / function / follow-up tokens that must not create relevance on their own.
_STOP = frozenset({
    "toi", "ban", "minh", "co", "la", "va", "cua", "cho", "gi", "the", "nao",
    "phai", "lam", "sao", "vay", "roi", "nay", "cai", "mot", "nhung", "que",
    "khi", "nhu", "da", "se", "thi", "ma", "de", "voi", "cung", "cac", "khong",
    "tra", "can", "chuan", "bi", "giay", "to", "muon", "biet", "hoi", "xin",
    "giup", "chi", "cong", "viec", "hom", "duoc", "them", "rat", "chua", "moi",
    "tinh", "huong", "truong", "cao", "khac", "nhat",  # generic; avoid non-legal collisions
})


def _tokens(text: str) -> set[str]:
    return {t for t in strip_accents(text.lower()).split() if len(t) >= 3 and t not in _STOP}


@dataclass
class Snippet:
    id: str
    domain: str
    title: str
    source_name: str
    source_url: Optional[str]
    source_type: str
    status: str
    text: str
    plain_language_summary: Optional[str]
    tags: list[str]
    risk_notes: list[str]
    last_checked: str


@dataclass
class RetrievedSource:
    snippet: Snippet
    score: float

    def __getattr__(self, name):  # passthrough to snippet fields
        return getattr(self.snippet, name)


@dataclass
class RetrievalResult:
    sources: list[RetrievedSource] = field(default_factory=list)
    allowed_source_ids: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    has_sources: bool = False
    retrieval_strategy: str = RETRIEVAL_STRATEGY


def _to_snippet(d: dict) -> Snippet:
    missing = [k for k in _REQUIRED if not d.get(k)]
    if missing:
        raise RetrievalError(f"snippet {d.get('id', '?')} missing fields: {missing}")
    return Snippet(
        id=d["id"], domain=d["domain"], title=d["title"], source_name=d["source_name"],
        source_url=d.get("source_url") or None, source_type=d["source_type"],
        status=d["status"], text=d["text"],
        plain_language_summary=d.get("plain_language_summary") or None,
        tags=list(d.get("tags", [])), risk_notes=list(d.get("risk_notes", [])),
        last_checked=d["last_checked"],
    )


def load_snippets(path: str) -> list[Snippet]:
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise RetrievalError(f"cannot load legal snippets: {e}") from e
    if not isinstance(data, list):
        raise RetrievalError("legal_snippets.json must be a JSON list")
    return [_to_snippet(d) for d in data]


class _Indexed:
    """Precomputed folded matching surface for one snippet."""
    __slots__ = ("snip", "tag_phrases", "tag_tokens", "title", "summary", "text", "name")

    def __init__(self, snip: Snippet):
        self.snip = snip
        self.tag_phrases = [strip_accents(t.replace("_", " ").lower()) for t in snip.tags]
        self.tag_tokens = [_tokens(t.replace("_", " ")) for t in snip.tags]
        self.title = _tokens(snip.title)
        self.summary = _tokens(snip.plain_language_summary or "")
        self.text = _tokens(snip.text)
        self.name = _tokens(snip.source_name)


class Retriever:
    def __init__(self, snippets: list[Union[Snippet, dict]],
                 min_content_score: int = 2, top_k: int = 3, max_absolute: int = 5):
        self.snippets = [s if isinstance(s, Snippet) else _to_snippet(s) for s in snippets]
        self._index = [_Indexed(s) for s in self.snippets]
        self.min_content_score = min_content_score
        self.top_k = top_k
        self.max_absolute = max_absolute

    def retrieve(self, norm: NormalizedText, domain: Domain, decision: Decision,
                 detected_topic: Optional[str] = None, context_terms: str = "",
                 top_k: Optional[int] = None) -> RetrievalResult:
        query_ai = " ".join(filter(None, [
            norm.accent_insensitive, strip_accents(context_terms.lower()),
            detected_topic or "",
        ]))
        distinctive = _tokens(query_ai)
        unsafe_or_high = domain == Domain.high_risk or decision == Decision.refuse_unsafe_request

        scored: list[tuple[float, float, RetrievedSource]] = []
        for idx in self._index:
            if idx.snip.status == "deprecated":
                continue
            # High-risk/unsafe: only safety/high-risk snippets, never normal how-to.
            if unsafe_or_high and idx.snip.domain != Domain.high_risk.value:
                continue
            content = self._content_score(idx, query_ai, distinctive)
            if content < self.min_content_score:
                continue
            boost = self._boost_score(idx.snip, domain, unsafe_or_high)
            total = content + boost
            scored.append((total, content, RetrievedSource(idx.snip, round(total, 2))))

        scored.sort(key=lambda t: (-t[0], t[2].id))
        k = min(top_k or self.top_k, self.max_absolute)
        chosen = [rs for _, _, rs in scored[:k]]
        return RetrievalResult(
            sources=chosen, allowed_source_ids=[s.id for s in chosen],
            retrieval_count=len(chosen), has_sources=bool(chosen),
        )

    def _content_score(self, idx: _Indexed, query_ai: str, distinctive: set[str]) -> float:
        tag_score = 0.0
        for phrase, toks in zip(idx.tag_phrases, idx.tag_tokens):
            if phrase and phrase in query_ai:
                tag_score += 3
            elif toks & distinctive:
                tag_score += 1
        title_score = 2.0 if idx.title & distinctive else 0.0

        # Primary signal (tag or title) is required; summary/text/source_name only
        # augment an already-relevant snippet. Prevents a lone shared generic token
        # in body text from making an unrelated snippet look relevant.
        primary = tag_score + title_score
        if primary == 0:
            return 0.0

        score = primary
        if idx.summary & distinctive:
            score += 1.5
        if idx.text & distinctive:
            score += 1
        if idx.name & distinctive:
            score += 0.5
        return score

    def _boost_score(self, snip: Snippet, domain: Domain, unsafe_or_high: bool) -> float:
        boost = 3.0 if snip.domain == domain.value else -2.0
        boost += {"active": 2.0, "needs_review": 0.5, "demo_only": -1.0}.get(snip.status, 0.0)
        if snip.source_type in ("official_source", "procedure"):
            boost += 1.0
        if unsafe_or_high and snip.source_type == "safety_policy":
            boost += 1.0
        return boost
