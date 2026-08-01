#!/usr/bin/env python3
"""
Build VietLaw-Chat legal snippets from Markdown authoring files.

Default workflow from repo root:
  python scripts/build_snippets.py

Input:
  data/snippets_md/**/*.md

Authoring rule:
  ## Plain summary is required for MVP compiler validation, even though the RAG spec describes it as recommended for human authoring. This keeps runtime JSON stable.

Output:
  data/legal_snippets.json

Runtime rule:
  Backend/RAG must read data/legal_snippets.json only. Markdown is authoring input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Repo root on sys.path so the build can reuse the production host-allowlist
# validator instead of duplicating its logic here (see `import_root` below).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend_lite.app.services.official_source_hosts import (  # noqa: E402
    is_trusted_official_host,
)

#: Civil Code (91/2015/QH13) snippets: the only IDs subject to the exact-host
#: and document-number checks below. Traffic/business snippets cite other,
#: already-verified government hosts and are untouched by this validation.
OFFICIAL_SOURCE_BOUNDED_IDS = {
    "civil_deposit_001",
    "civil_contract_001",
    "civil_contract_002",
}

CIVIL_CODE_DOCUMENT_NUMBER = "91/2015/QH13"

#: MODE_2D correction (M-02): the exact, independently-verified legal identity
#: for every snippet on the article-citation allowlist. `civil_contract_001`/
#: `civil_contract_002` are deliberately absent -- no verified article number
#: exists for them yet, so they are left without article-level metadata
#: rather than assigning an unverified one (see the migration report). Adding
#: a new bounded snippet later means adding its own verified entry here, not
#: widening a generic non-empty check.
ARTICLE_LEVEL_CITATION_IDENTITY: dict[str, dict[str, Any]] = {
    "civil_deposit_001": {
        "document_title": "Bộ luật Dân sự 2015",
        "article_number": "328",
        "article_title": "Đặt cọc",
        "clause_numbers": [1, 2],
    },
}
ARTICLE_LEVEL_CITATION_IDS = set(ARTICLE_LEVEL_CITATION_IDENTITY)

ALLOWED_DOMAINS = {
    "civil_dispute",
    "traffic",
    "household_business",
    "administrative",
    "high_risk",
    "unknown",
}

ALLOWED_SOURCE_TYPES = {
    "official_source",
    "procedure",
    "legal_snippet",
    "curated_note",
    "safety_policy",
    "demo_only",
}

ALLOWED_STATUSES = {
    "active",
    "needs_review",
    "demo_only",
    "deprecated",
}

REQUIRED_FRONTMATTER_FIELDS = {
    "id",
    "domain",
    "source_name",
    "source_type",
    "status",
    "tags",
    "last_checked",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class SnippetBuildError(Exception):
    """Raised for a clear, user-fixable snippet authoring error."""


def parse_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _tokenize_inline_list(value: str, *, keep_empty: bool = False) -> list[tuple[str, bool]]:
    """Split an inline `[item_one, item_two]` list into (raw_text, was_quoted)
    pairs. Shared by `split_inline_list` (general fields) and
    `parse_clause_numbers_strict` (M-02B: the one field that needs to know
    whether each token was quoted, without changing general-field behavior).

    ``keep_empty`` defaults to `False`, which preserves the exact original
    behavior every caller other than `parse_clause_numbers_strict` relies on
    (a stray/duplicate/leading/trailing comma silently produces one fewer
    item). `parse_clause_numbers_strict` passes `keep_empty=True` so it can
    see and reject an empty segment itself (M-03: the trailing-comma
    finding) -- `split_inline_list`'s call site is unchanged and therefore so
    is its behavior.
    """

    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ValueError("list must use inline form: [item_one, item_two]")

    inner = value[1:-1].strip()
    if not inner:
        return []

    tokens: list[tuple[str, bool]] = []
    buf: list[str] = []
    quote: str | None = None
    was_quoted = False
    escape = False

    def _flush(raw: str) -> None:
        raw = raw.strip()
        if raw or keep_empty:
            tokens.append((raw, was_quoted))

    for ch in inner:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\" and quote:
            escape = True
            continue
        if ch in {"'", '"'}:
            if quote is None:
                quote = ch
                was_quoted = True
            elif quote == ch:
                quote = None
            else:
                buf.append(ch)
            continue
        if ch == "," and quote is None:
            _flush("".join(buf))
            buf = []
            was_quoted = False
            continue
        buf.append(ch)

    if quote is not None:
        raise ValueError("unterminated quote in list")

    _flush("".join(buf))
    return tokens


def split_inline_list(value: str) -> list[str]:
    """General shared inline-list parser (tags, risk_notes, ...).

    Every item is always a plain string, regardless of whether it was quoted
    in the authoring source -- restored to this original semantics in M-02B
    after round 2 accidentally made this SHARED parser type-aware, which
    changed unrelated fields' acceptance of unquoted `true`/`false`/numbers.
    Only `clause_numbers` needs typed items; see `parse_clause_numbers_strict`.
    """

    return [parse_scalar(raw) for raw, _ in _tokenize_inline_list(value)]


_BARE_INT_RE = re.compile(r"^-?[0-9]+$")
_BARE_FLOAT_RE = re.compile(r"^-?[0-9]+\.[0-9]+$")


def parse_clause_numbers_strict(value: str) -> list[Any]:
    """Field-specific strict parser for `clause_numbers` only (M-02B/M-03).

    Distinguishes quoted from unquoted tokens using the same raw-text
    tokenizer as the general list parser, but types ONLY here: an unquoted
    whole number becomes a real `int`, an unquoted `true`/`false` becomes a
    real `bool`, an unquoted decimal becomes a real `float`, and every
    quoted token stays a `str` -- so `require_positive_int_list` can reject
    anything that is not a genuine `int` without ever coercing a string
    through `int(str(item))`. General fields (tags, risk_notes, ...) are
    never routed through this function and keep their original string-only
    behavior via `split_inline_list`.

    Unlike the shared parser (which silently drops an empty segment from a
    stray comma), this field's exact accepted grammar admits only genuine
    items separated by single commas: `[1, 2]` is accepted; a leading,
    trailing, or doubled comma -- which produces an empty segment -- is
    rejected outright (M-03), never silently discarded.
    """

    items: list[Any] = []
    for raw, was_quoted in _tokenize_inline_list(value, keep_empty=True):
        if not was_quoted and raw == "":
            raise ValueError(
                "clause_numbers must not contain an empty item -- check for "
                "a leading, trailing, or doubled comma"
            )
        if was_quoted:
            items.append(raw)
            continue
        if raw == "true":
            items.append(True)
        elif raw == "false":
            items.append(False)
        elif _BARE_INT_RE.match(raw):
            items.append(int(raw))
        elif _BARE_FLOAT_RE.match(raw):
            items.append(float(raw))
        else:
            items.append(raw)
    return items


def parse_frontmatter(frontmatter: str, path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}

    for line_no, raw_line in enumerate(frontmatter.splitlines(), start=2):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise SnippetBuildError(f"{path}:{line_no}: invalid frontmatter line: {raw_line!r}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise SnippetBuildError(f"{path}:{line_no}: empty frontmatter key")
        if key in data:
            raise SnippetBuildError(f"{path}:{line_no}: duplicate frontmatter key: {key}")

        try:
            if value.startswith("["):
                # M-02B: only `clause_numbers` is routed through the typed
                # parser; every other inline-list field keeps the general
                # string-only parser unchanged.
                if key == "clause_numbers":
                    data[key] = parse_clause_numbers_strict(value)
                else:
                    data[key] = split_inline_list(value)
            else:
                data[key] = parse_scalar(value)
        except ValueError as exc:
            raise SnippetBuildError(f"{path}:{line_no}: invalid value for {key}: {exc}") from exc

    return data


def section_map(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}

    for idx, match in enumerate(matches):
        name = match.group(1).strip().lower()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        sections[name] = body[start:end].strip()

    return sections


def require_text(value: Any, path: Path, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnippetBuildError(f"{path}: missing or empty field: {field}")
    return value.strip()


def require_list(value: Any, path: Path, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SnippetBuildError(f"{path}: field must be a list: {field}")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SnippetBuildError(f"{path}: field {field} contains an empty/non-string item")
        cleaned.append(item.strip())
    if field == "tags" and not cleaned:
        raise SnippetBuildError(f"{path}: tags must contain at least one value")
    return cleaned


def validate_official_source_metadata(snippet_id: str, meta: dict[str, Any], path: Path) -> None:
    """Enforce the exact-host allowlist and document number for the bounded
    Civil Code IDs. Fails the build deterministically -- this is a hard
    compile error, not a warning, so a deceptive or unauthorized URL can
    never reach `data/legal_snippets.json`.

    Scoped to `OFFICIAL_SOURCE_BOUNDED_IDS` only: traffic/business snippets
    cite other already-verified government hosts and must not be rejected by
    this check.
    """

    if snippet_id not in OFFICIAL_SOURCE_BOUNDED_IDS:
        return

    for field in ("source_url", "official_backup_url", "official_tertiary_url"):
        url = str(meta.get(field, "")).strip()
        if not url:
            raise SnippetBuildError(
                f"{path}: {snippet_id} requires a non-empty {field} for the "
                "official-source migration"
            )
        if not is_trusted_official_host(url):
            raise SnippetBuildError(
                f"{path}: {snippet_id}.{field} {url!r} is not an exact allowed "
                "official host (https + congbao.chinhphu.vn / vanban.chinhphu.vn "
                "/ vbpl.vn only)"
            )

    document_number = str(meta.get("official_document_number", "")).strip()
    if document_number != CIVIL_CODE_DOCUMENT_NUMBER:
        raise SnippetBuildError(
            f"{path}: {snippet_id}.official_document_number must be exactly "
            f"{CIVIL_CODE_DOCUMENT_NUMBER!r}, got {document_number!r}"
        )


def require_positive_int_list(value: Any, path: Path, field: str) -> list[int]:
    """Require every item to already be a genuine Python `int` as produced by
    the parser (M-02, round 2) -- never coerced via `int(str(item))`, which
    would silently accept a quoted numeric string. `bool` is explicitly
    excluded even though it subclasses `int` in Python, so an unquoted
    `true`/`false` is rejected rather than read as `1`/`0`.
    """

    if not isinstance(value, list) or not value:
        raise SnippetBuildError(f"{path}: field must be a non-empty list: {field}")
    cleaned: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise SnippetBuildError(
                f"{path}: field {field} contains a non-integer item (must be an "
                f"unquoted whole number, not a string/float/boolean): {item!r}"
            )
        if item <= 0:
            raise SnippetBuildError(f"{path}: field {field} contains a non-positive item: {item!r}")
        cleaned.append(item)
    if len(cleaned) != len(set(cleaned)):
        raise SnippetBuildError(f"{path}: field {field} contains duplicate clause numbers")
    return cleaned


#: The exact frontmatter keys that carry article-level identity. Authoring
#: any of these on a snippet outside the allowlist is a build error, not a
#: silently-discarded no-op (MODE_2D correction M-02).
_ARTICLE_LEVEL_KEYS = ("document_title", "article_number", "article_title", "clause_numbers")


def validate_article_level_citation_metadata(
    snippet_id: str, meta: dict[str, Any], path: Path
) -> dict[str, Any]:
    """Bounded article-level legal-citation metadata (MODE_2D), corrected to
    an exact-identity gate in round 1 (M-02).

    Scoped to `ARTICLE_LEVEL_CITATION_IDENTITY` only. For every other
    snippet, authoring ANY article-level key is now a hard build error
    (previously it was silently discarded, which is exactly the gap the
    independent review found: authoring article-level metadata on the wrong
    snippet must fail loudly, not vanish quietly). For the one bounded
    snippet, every field must match its independently-verified value
    EXACTLY -- not merely be non-empty -- so a typo'd article/clause/
    document title can never reach a rendered legal citation.
    """

    if snippet_id not in ARTICLE_LEVEL_CITATION_IDS:
        authored = [key for key in _ARTICLE_LEVEL_KEYS if key in meta]
        if authored:
            raise SnippetBuildError(
                f"{path}: {snippet_id} is not on the approved article-citation "
                f"allowlist but authors article-level field(s): {', '.join(authored)}"
            )
        return {}

    expected = ARTICLE_LEVEL_CITATION_IDENTITY[snippet_id]

    document_title = require_text(meta.get("document_title", ""), path, "document_title")
    article_number = require_text(meta.get("article_number", ""), path, "article_number")
    article_title = require_text(meta.get("article_title", ""), path, "article_title")
    clause_numbers = require_positive_int_list(meta.get("clause_numbers", []), path, "clause_numbers")

    if document_title != expected["document_title"]:
        raise SnippetBuildError(
            f"{path}: {snippet_id}.document_title must be exactly "
            f"{expected['document_title']!r}, got {document_title!r}"
        )
    if article_number != expected["article_number"]:
        raise SnippetBuildError(
            f"{path}: {snippet_id}.article_number must be exactly "
            f"{expected['article_number']!r}, got {article_number!r}"
        )
    if article_title != expected["article_title"]:
        raise SnippetBuildError(
            f"{path}: {snippet_id}.article_title must be exactly "
            f"{expected['article_title']!r}, got {article_title!r}"
        )
    if clause_numbers != sorted(clause_numbers):
        raise SnippetBuildError(
            f"{path}: {snippet_id}.clause_numbers must be sorted ascending, got {clause_numbers!r}"
        )
    if clause_numbers != expected["clause_numbers"]:
        raise SnippetBuildError(
            f"{path}: {snippet_id}.clause_numbers must be exactly "
            f"{expected['clause_numbers']!r}, got {clause_numbers!r}"
        )

    # document_number is already validated exactly equal to
    # CIVIL_CODE_DOCUMENT_NUMBER by validate_official_source_metadata for this
    # same bounded ID -- reused here rather than re-authored under a second
    # frontmatter key that could silently drift from the validated one.
    document_number = str(meta.get("official_document_number", "")).strip()

    return {
        "document_title": document_title,
        "document_number": document_number,
        "article_number": article_number,
        "article_title": article_title,
        "clause_numbers": clause_numbers,
    }


def parse_snippet(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise SnippetBuildError(f"{path}: file must start with YAML-like frontmatter delimited by ---")

    frontmatter, body = match.groups()
    meta = parse_frontmatter(frontmatter, path)

    missing = sorted(REQUIRED_FRONTMATTER_FIELDS - meta.keys())
    if missing:
        raise SnippetBuildError(f"{path}: missing required frontmatter field(s): {', '.join(missing)}")

    h1 = H1_RE.search(body)
    if not h1:
        raise SnippetBuildError(f"{path}: missing H1 title, e.g. '# Đặt cọc...' ")

    sections = section_map(body)
    if "text" not in sections:
        raise SnippetBuildError(f"{path}: missing required section: ## Text")
    if "plain summary" not in sections:
        raise SnippetBuildError(f"{path}: missing recommended/required MVP section: ## Plain summary")

    domain = require_text(meta["domain"], path, "domain")
    source_type = require_text(meta["source_type"], path, "source_type")
    status = require_text(meta["status"], path, "status")
    last_checked = require_text(meta["last_checked"], path, "last_checked")

    if domain not in ALLOWED_DOMAINS:
        raise SnippetBuildError(f"{path}: invalid domain {domain!r}; allowed: {sorted(ALLOWED_DOMAINS)}")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise SnippetBuildError(
            f"{path}: invalid source_type {source_type!r}; allowed: {sorted(ALLOWED_SOURCE_TYPES)}"
        )
    if status not in ALLOWED_STATUSES:
        raise SnippetBuildError(f"{path}: invalid status {status!r}; allowed: {sorted(ALLOWED_STATUSES)}")
    if not DATE_RE.match(last_checked):
        raise SnippetBuildError(f"{path}: last_checked must use YYYY-MM-DD, got {last_checked!r}")

    snippet = {
        "id": require_text(meta["id"], path, "id"),
        "domain": domain,
        "title": h1.group(1).strip(),
        "source_name": require_text(meta["source_name"], path, "source_name"),
        "source_url": str(meta.get("source_url", "")).strip(),
        "source_type": source_type,
        "status": status,
        "text": sections["text"].strip(),
        "plain_language_summary": sections["plain summary"].strip(),
        "tags": require_list(meta["tags"], path, "tags"),
        "risk_notes": require_list(meta.get("risk_notes", []), path, "risk_notes"),
        "last_checked": last_checked,
    }

    if not snippet["text"]:
        raise SnippetBuildError(f"{path}: ## Text must not be empty")
    if not snippet["plain_language_summary"]:
        raise SnippetBuildError(f"{path}: ## Plain summary must not be empty")

    validate_official_source_metadata(snippet["id"], meta, path)
    snippet.update(validate_article_level_citation_metadata(snippet["id"], meta, path))

    return snippet


def build(input_dir: Path, output_file: Path) -> list[dict[str, Any]]:
    markdown_files = sorted(input_dir.rglob("*.md"))
    markdown_files = [p for p in markdown_files if p.name.lower() != "readme.md"]
    if not markdown_files:
        raise SnippetBuildError(f"No snippet Markdown files found in {input_dir}")

    snippets = [parse_snippet(path) for path in markdown_files]

    seen: dict[str, Path] = {}
    for snippet, path in zip(snippets, markdown_files):
        snippet_id = snippet["id"]
        if snippet_id in seen:
            raise SnippetBuildError(f"{path}: duplicate snippet id {snippet_id!r}; first seen in {seen[snippet_id]}")
        seen[snippet_id] = path

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(snippets, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snippets


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Compile VietLaw-Chat snippet Markdown files to JSON.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=repo_root / "data" / "snippets_md",
        help="Directory containing snippet .md files. Default: data/snippets_md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "data" / "legal_snippets.json",
        help="Output JSON file. Default: data/legal_snippets.json",
    )
    args = parser.parse_args()

    try:
        snippets = build(args.input_dir, args.output)
    except SnippetBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Built {len(snippets)} snippets → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
