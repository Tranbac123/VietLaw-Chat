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


def split_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ValueError("list must use inline form: [item_one, item_two]")

    inner = value[1:-1].strip()
    if not inner:
        return []

    items: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escape = False

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
            elif quote == ch:
                quote = None
            else:
                buf.append(ch)
            continue
        if ch == "," and quote is None:
            item = parse_scalar("".join(buf).strip())
            if item:
                items.append(item)
            buf = []
            continue
        buf.append(ch)

    if quote is not None:
        raise ValueError("unterminated quote in list")

    item = parse_scalar("".join(buf).strip())
    if item:
        items.append(item)
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
