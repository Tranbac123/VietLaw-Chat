"""Parse LLM output into the content whitelist.

Only summary/clarifying_questions/checklist/next_steps/used_source_ids survive.
Everything else the LLM emits (sources, domain, safety_notice, metadata, ...) is
ignored. If parsing fails or summary is unusable, return cautious fallback content
and flag it (metadata.llm_parse_error → success 200 upstream, not an error).
"""
import json
import re

from app.content_templates import fallback_content
from app.patterns import PatternBank
from app.schemas import Domain, LLMContent

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _load_json(raw: str):
    for candidate in (raw, _extract(raw)):
        if candidate is None:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _extract(raw: str):
    m = _FENCE.search(raw)
    if m:
        return m.group(1)
    m = _OBJECT.search(raw)
    return m.group(0) if m else None


def _str_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()]


def parse_content_or_fallback(
    raw: str, retrieved_source_ids: list[str], domain: Domain, bank: PatternBank
) -> tuple[LLMContent, bool]:
    obj = _load_json(raw or "")
    if obj is None:
        return fallback_content(domain, bank), True

    summary = obj.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""
    if not summary:
        return fallback_content(domain, bank), True

    retrieved = set(retrieved_source_ids)
    used = [i for i in _str_list(obj.get("used_source_ids")) if i in retrieved]

    return LLMContent(
        summary=summary,
        clarifying_questions=_str_list(obj.get("clarifying_questions")),
        checklist=_str_list(obj.get("checklist")),
        next_steps=_str_list(obj.get("next_steps")),
        used_source_ids=used,
    ), False
