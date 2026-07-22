"""Citation guard.

Authoritative check that used_source_ids in retrieved. Any invented/out-of-set id
is removed; the removal is reported so metadata + confidence can reflect it.
"""
from typing import Optional

from app.schemas import LLMContent


def apply(content: LLMContent, retrieved_source_ids: list[str]) -> tuple[LLMContent, Optional[str]]:
    retrieved = set(retrieved_source_ids)
    valid = [i for i in content.used_source_ids if i in retrieved]
    removed = [i for i in content.used_source_ids if i not in retrieved]
    if not removed:
        return content, None
    cleaned = content.model_copy(update={"used_source_ids": valid})
    return cleaned, f"removed invalid source ids: {removed}"
