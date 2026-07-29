"""Official-source migration: exact-host allowlist and curated-data integrity.

Bounded to the Civil Code (91/2015/QH13) migration. This module's allowlist is
intentionally narrow -- it is not applied to every legal snippet in the pack,
since traffic/business snippets cite other verified government hosts outside
this set (see `is_trusted_official_host`'s own docstring). Zero provider calls.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.services.official_source_hosts import (
    OFFICIAL_SOURCE_HOSTS,
    is_trusted_official_host,
)
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

import scripts.build_snippets as build_snippets  # noqa: E402  (repo root added to sys.path by that module)

REPO_ROOT = Path(__file__).resolve().parents[3]
SNIPPETS_PATH = REPO_ROOT / "data" / "legal_snippets.json"
SNIPPETS_MD_DIR = REPO_ROOT / "data" / "snippets_md" / "civil_dispute"

CIVIL_CODE_SNIPPET_IDS = {"civil_deposit_001", "civil_contract_001", "civil_contract_002"}
LEGACY_BROKEN_URL = "https://vbpl.moj.gov.vn/tuyenquang/Pages/vbpq-toanvan.aspx?ItemID=95942&Keyword="
PRIMARY_URL = "https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm"
BACKUP_URL = "https://vanban.chinhphu.vn/default.aspx?docid=183188&pageid=27160"
CIVIL_CODE_DOCUMENT_NUMBER = "91/2015/QH13"
INCORRECT_DOCUMENT_NUMBER = "92/2015/QH13"


# ---------------------------------------------------------------------------
# Exact-host allowlist
# ---------------------------------------------------------------------------

def test_exact_official_hosts_accepted() -> None:
    assert is_trusted_official_host(
        "https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm"
    )
    assert is_trusted_official_host(
        "https://vanban.chinhphu.vn/default.aspx?docid=183188&pageid=27160"
    )
    assert is_trusted_official_host(
        "https://vbpl.vn/van-ban/chi-tiet/bo-luat-dan-su-so-91-2015-qh13--95942"
    )


def test_allowlist_is_exactly_three_hosts() -> None:
    assert OFFICIAL_SOURCE_HOSTS == {
        "congbao.chinhphu.vn",
        "vanban.chinhphu.vn",
        "vbpl.vn",
    }


def test_http_scheme_rejected() -> None:
    assert not is_trusted_official_host("http://congbao.chinhphu.vn/x")


def test_deceptive_subdomain_rejected() -> None:
    assert not is_trusted_official_host("https://evil.congbao.chinhphu.vn.example.com/x")


def test_suffix_trick_rejected() -> None:
    assert not is_trusted_official_host("https://congbao.chinhphu.vn.evil.example/x")


def test_embedded_credentials_rejected() -> None:
    assert not is_trusted_official_host("https://user@congbao.chinhphu.vn/x")


def test_broad_gov_vn_rejected() -> None:
    assert not is_trusted_official_host("https://example.gov.vn/x")


def test_bare_chinhphu_vn_rejected() -> None:
    # Not one of the three verified subdomains -- exact match only, no
    # "*.chinhphu.vn" wildcard trust.
    assert not is_trusted_official_host("https://chinhphu.vn/x")


def test_legacy_broken_url_rejected() -> None:
    assert not is_trusted_official_host(LEGACY_BROKEN_URL)


def test_non_string_and_empty_inputs_rejected() -> None:
    assert not is_trusted_official_host(None)
    assert not is_trusted_official_host("")
    assert not is_trusted_official_host("   ")
    assert not is_trusted_official_host("not a url")


# ---------------------------------------------------------------------------
# Curated Civil Code data now uses a trusted host (data-integrity, not just
# unit-level regex correctness)
# ---------------------------------------------------------------------------

def _load_snippets() -> list[dict]:
    return json.loads(SNIPPETS_PATH.read_text(encoding="utf-8"))


def test_civil_code_entries_use_a_trusted_official_host() -> None:
    snippets = _load_snippets()
    checked = {s["id"] for s in snippets if s["id"] in CIVIL_CODE_SNIPPET_IDS}
    assert checked == CIVIL_CODE_SNIPPET_IDS

    for snippet in snippets:
        if snippet["id"] in CIVIL_CODE_SNIPPET_IDS:
            assert is_trusted_official_host(snippet["source_url"]), snippet["id"]


def test_legacy_broken_url_absent_from_active_source_data() -> None:
    snippets = _load_snippets()
    for snippet in snippets:
        assert snippet.get("source_url") != LEGACY_BROKEN_URL


def test_civil_code_primary_url_is_congbao() -> None:
    snippets = _load_snippets()
    for snippet in snippets:
        if snippet["id"] in CIVIL_CODE_SNIPPET_IDS:
            assert snippet["source_url"] == PRIMARY_URL


# ---------------------------------------------------------------------------
# Document identity
# ---------------------------------------------------------------------------

def test_document_number_91_present_in_primary_url_slug() -> None:
    assert "91-2015-qh13" in PRIMARY_URL.lower()


def test_incorrect_document_number_92_absent_from_active_source_data() -> None:
    raw = SNIPPETS_PATH.read_text(encoding="utf-8")
    assert INCORRECT_DOCUMENT_NUMBER not in raw
    assert INCORRECT_DOCUMENT_NUMBER.replace("/", "-").lower() not in raw.lower()


# ---------------------------------------------------------------------------
# Backup/tertiary URL recorded in the authoring registry (not the runtime API)
# ---------------------------------------------------------------------------

def test_official_backup_url_recorded_in_authoring_metadata() -> None:
    md_files = [
        SNIPPETS_MD_DIR / "001_civil_deposit_001.md",
        SNIPPETS_MD_DIR / "002_civil_contract_001.md",
        SNIPPETS_MD_DIR / "003_civil_contract_002.md",
    ]
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        assert f'official_backup_url: "{BACKUP_URL}"' in text
        assert is_trusted_official_host(BACKUP_URL)


def test_backup_url_not_exposed_via_runtime_schema() -> None:
    # The backup lives only in the authoring registry; the API-facing
    # SourceObject schema (extra="forbid") never carries a second URL field,
    # so no unrelated schema migration was needed for this documentation.
    snippets = _load_snippets()
    for snippet in snippets:
        if snippet["id"] in CIVIL_CODE_SNIPPET_IDS:
            assert "official_backup_url" not in snippet
            assert "official_tertiary_url" not in snippet


# ---------------------------------------------------------------------------
# End-to-end: the rental-deposit fixture renders the new primary URL
# ---------------------------------------------------------------------------

def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _plan(**overrides) -> str:
    payload = {
        "response_kind": "legal",
        "response_mode": "acknowledge",
        "summary": "Đã ghi nhận thông tin của bạn.",
        "analysis": None,
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "draft": None,
        "known_facts_summary": [],
        "uncertainty_notice": None,
        "fact_updates": [],
        "selected_source_ids": ["civil_deposit_001"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_rental_deposit_fixture_renders_new_primary_url_end_to_end(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    container = app.state.container
    fake = FakeLLMClient(responses=[_plan()])
    store = FastDemoStateStore(settings.chat_db_path)
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(
            enabled=True, model="claude-test-model", api_key="test-key",
            timeout_s=30.0, max_output_tokens=2048, temperature=0.0,
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            json={
                "session_id": "s1",
                "question": "tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc",
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()

    urls = [source["url"] for source in body["sources"]]
    assert PRIMARY_URL in urls
    assert LEGACY_BROKEN_URL not in urls
    assert fake.calls == 1


# ---------------------------------------------------------------------------
# Build-time enforcement: the exact-host + document-number check is wired
# into the Markdown->JSON build, not merely unit-tested in isolation.
# ---------------------------------------------------------------------------

SNIPPETS_MD_ROOT = REPO_ROOT / "data" / "snippets_md"


def _copy_snippets_md(tmp_path: Path) -> Path:
    dest = tmp_path / "snippets_md"
    shutil.copytree(SNIPPETS_MD_ROOT, dest)
    return dest


def test_real_authoring_data_passes_build_validation(tmp_path: Path) -> None:
    """The actual committed .md files must already satisfy every check."""
    output = tmp_path / "legal_snippets.json"
    snippets = build_snippets.build(SNIPPETS_MD_ROOT, output)
    ids = {s["id"] for s in snippets}
    assert CIVIL_CODE_SNIPPET_IDS <= ids

    # Traffic/business snippets, outside the bounded set, are untouched by
    # this validation and still build with their own (different) hosts.
    traffic = next(s for s in snippets if s["id"] == "traffic_law_001")
    assert "chinhphu.vn" in traffic["source_url"]
    assert not is_trusted_official_host(traffic["source_url"])  # correctly outside the allowlist


def test_build_fails_on_deceptive_civil_code_host(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    target = root / "civil_dispute" / "001_civil_deposit_001.md"
    text = target.read_text(encoding="utf-8")
    text = text.replace(PRIMARY_URL, "https://congbao.chinhphu.vn.evil.example/x")
    target.write_text(text, encoding="utf-8")

    with pytest.raises(build_snippets.SnippetBuildError, match="not an exact allowed official host"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_build_fails_on_http_civil_code_url(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    target = root / "civil_dispute" / "001_civil_deposit_001.md"
    text = target.read_text(encoding="utf-8").replace("https://congbao", "http://congbao")
    target.write_text(text, encoding="utf-8")

    with pytest.raises(build_snippets.SnippetBuildError, match="not an exact allowed official host"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_build_fails_on_wrong_document_number(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    target = root / "civil_dispute" / "001_civil_deposit_001.md"
    text = target.read_text(encoding="utf-8").replace(
        'official_document_number: "91/2015/QH13"',
        'official_document_number: "92/2015/QH13"',
    )
    target.write_text(text, encoding="utf-8")

    with pytest.raises(build_snippets.SnippetBuildError, match="official_document_number"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_build_fails_on_missing_backup_url(tmp_path: Path) -> None:
    root = _copy_snippets_md(tmp_path)
    target = root / "civil_dispute" / "001_civil_deposit_001.md"
    lines = [
        line for line in target.read_text(encoding="utf-8").splitlines()
        if not line.startswith("official_backup_url")
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(build_snippets.SnippetBuildError, match="official_backup_url"):
        build_snippets.build(root, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()


def test_build_validation_scoped_to_bounded_civil_code_ids_only(tmp_path: Path) -> None:
    """A deceptive host on an unrelated (non-bounded) snippet must not be rejected
    by this migration's check -- traffic/business source handling is untouched."""
    root = _copy_snippets_md(tmp_path)
    target = root / "traffic" / "007_traffic_law_001.md"
    text = target.read_text(encoding="utf-8")
    assert "source_url:" in text
    # Same deceptive-suffix shape that fails for a bounded Civil Code ID above.
    text = re_sub_first_url(text, "https://chinhphu.vn.evil.example/x")
    target.write_text(text, encoding="utf-8")

    # Must build successfully: this ID is outside OFFICIAL_SOURCE_BOUNDED_IDS.
    snippets = build_snippets.build(root, tmp_path / "out.json")
    traffic = next(s for s in snippets if s["id"] == "traffic_law_001")
    assert traffic["source_url"] == "https://chinhphu.vn.evil.example/x"


def re_sub_first_url(text: str, new_url: str) -> str:
    return re.sub(r'(source_url:\s*")[^"]*(")', rf"\g<1>{new_url}\g<2>", text, count=1)
