from __future__ import annotations

from pathlib import Path

import pytest

from backend_lite.app.config import Settings
from backend_lite.app.dependencies import build_container
from backend_lite.app.storage_readiness import ProductionStorageError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173,http://localhost:5173",
    )
    values.update(overrides)
    return Settings(**values)


def test_build_container_fails_closed_in_production_with_default_path(tmp_path: Path):
    settings = _settings(tmp_path, app_env="production")
    with pytest.raises(ProductionStorageError):
        build_container(settings)
    # Deployment Correction Round 1 (HIGH-01): validation must run before any
    # store's ensure_schema() call, so no SQLite file is created on the
    # rejected path.
    assert not settings.chat_db_path.exists()


def test_build_container_fails_closed_when_path_outside_data(tmp_path: Path):
    settings = _settings(tmp_path, app_env="production", chat_db_path=Path("/tmp/vietlaw_chat.sqlite3"))
    with pytest.raises(ProductionStorageError):
        build_container(settings)


def test_build_container_succeeds_in_development_with_project_relative_default(tmp_path: Path):
    settings = _settings(tmp_path, app_env="development")
    container = build_container(settings)
    assert container.chat_store.ready is True


def test_build_container_succeeds_in_production_with_mounted_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "data"
    root.mkdir()
    db_path = root / "vietlaw_chat.sqlite3"
    settings = _settings(tmp_path, app_env="production", chat_db_path=db_path)

    from backend_lite.app import dependencies as dependencies_module
    from backend_lite.app.storage_readiness import validate_persistent_storage

    mountinfo_text = f"37 35 98:1 / {root} rw,relatime shared:2 - ext4 /dev/sdb1 rw\n"

    def fake_validate(*, app_env, db_path):
        return validate_persistent_storage(
            app_env=app_env,
            db_path=db_path,
            persistent_root=root,
            mountinfo_reader=lambda: mountinfo_text,
        )

    monkeypatch.setattr(dependencies_module, "validate_persistent_storage", fake_validate)

    container = build_container(settings)
    assert container.chat_store.ready is True
    assert db_path.exists()
