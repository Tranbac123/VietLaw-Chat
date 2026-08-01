from __future__ import annotations

from pathlib import Path

import pytest

from backend_lite.app.storage_readiness import (
    ProductionStorageError,
    _decode_mountinfo_path,
    _is_mount_point,
    validate_persistent_storage,
)


def _mountinfo_with(mount_point: str) -> str:
    return (
        "36 35 98:0 / / rw,relatime shared:1 - ext4 /dev/root rw\n"
        f"37 35 98:1 / {mount_point} rw,relatime shared:2 - ext4 /dev/sdb1 rw\n"
    )


def test_development_default_unchanged_even_when_path_unset(tmp_path: Path):
    default_path = tmp_path / "data" / "vietlaw_chat.sqlite3"
    status = validate_persistent_storage(app_env="development", db_path=default_path)
    assert status.ready is True
    assert status.reason is None


def test_test_env_also_bypasses_production_checks(tmp_path: Path):
    status = validate_persistent_storage(app_env="test", db_path=tmp_path / "x.sqlite3")
    assert status.ready is True


def test_production_rejects_relative_path():
    status = validate_persistent_storage(
        app_env="production", db_path=Path("data/file.sqlite3")
    )
    assert status.ready is False
    assert "absolute" in status.reason


def test_production_rejects_path_outside_data(tmp_path: Path):
    status = validate_persistent_storage(
        app_env="production",
        db_path=Path("/app/data/vietlaw_chat.sqlite3"),
        persistent_root=tmp_path / "data",
    )
    assert status.ready is False
    assert "must resolve beneath" in status.reason


def test_production_rejects_tmp_path(tmp_path: Path):
    status = validate_persistent_storage(
        app_env="production",
        db_path=Path("/tmp/vietlaw_chat.sqlite3"),
        persistent_root=tmp_path / "data",
    )
    assert status.ready is False
    assert "must resolve beneath" in status.reason


def test_production_rejects_traversal_outside_root(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    status = validate_persistent_storage(
        app_env="production",
        db_path=root / ".." / "app" / "file.sqlite3",
        persistent_root=root,
    )
    assert status.ready is False
    assert "must resolve beneath" in status.reason


def test_production_rejects_data_dir_that_exists_but_is_not_mounted(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    status = validate_persistent_storage(
        app_env="production",
        db_path=root / "vietlaw_chat.sqlite3",
        persistent_root=root,
        mountinfo_reader=lambda: _mountinfo_with("/some/other/mount"),
    )
    assert status.ready is False
    assert "not a mounted filesystem" in status.reason


def test_production_accepts_mounted_writable_data(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    status = validate_persistent_storage(
        app_env="production",
        db_path=root / "vietlaw_chat.sqlite3",
        persistent_root=root,
        mountinfo_reader=lambda: _mountinfo_with(str(root)),
    )
    assert status.ready is True
    assert status.reason is None


def test_production_rejects_read_only_mounted_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "data"
    root.mkdir()
    import os as os_module

    real_access = os_module.access

    def fake_access(path, mode):
        if Path(path) == root and mode == os_module.W_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os_module, "access", fake_access)
    status = validate_persistent_storage(
        app_env="production",
        db_path=root / "vietlaw_chat.sqlite3",
        persistent_root=root,
        mountinfo_reader=lambda: _mountinfo_with(str(root)),
    )
    assert status.ready is False
    assert "not writable" in status.reason


def test_production_rejects_when_mountinfo_unreadable(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()

    def raise_oserror() -> str:
        raise OSError("no such file")

    status = validate_persistent_storage(
        app_env="production",
        db_path=root / "vietlaw_chat.sqlite3",
        persistent_root=root,
        mountinfo_reader=raise_oserror,
    )
    assert status.ready is False
    assert "cannot verify" in status.reason


def test_production_storage_error_message_carries_reason():
    error = ProductionStorageError("some reason")
    assert str(error) == "some reason"


# =============================================================================
# Deployment Correction Round 2 (LOW-01): mountinfo escape decoding.
# =============================================================================


def test_decode_mountinfo_path_handles_all_four_escapes():
    assert _decode_mountinfo_path(r"\040") == " "
    assert _decode_mountinfo_path(r"\011") == "\t"
    assert _decode_mountinfo_path(r"\012") == "\n"
    assert _decode_mountinfo_path(r"\134") == "\\"
    assert _decode_mountinfo_path(r"/data\040with\040space") == "/data with space"


def test_decode_mountinfo_path_leaves_unrecognized_escape_literal():
    # No exception -- an undecodable sequence just fails a later equality
    # comparison, which is already fail-closed for this module.
    assert _decode_mountinfo_path(r"/data\999") == r"/data\999"


def test_decode_mountinfo_path_handles_trailing_backslash_without_crashing():
    assert _decode_mountinfo_path("/data\\") == "/data\\"


def test_is_mount_point_accepts_exact_data_mount(tmp_path: Path):
    root = tmp_path / "data"
    assert _is_mount_point(root, _mountinfo_with(str(root)))


def test_is_mount_point_rejects_nested_mount_alone(tmp_path: Path):
    root = tmp_path / "data"
    nested = root / "nested"
    assert not _is_mount_point(root, _mountinfo_with(str(nested)))


def test_is_mount_point_parses_escaped_space_in_real_mount_path(tmp_path: Path):
    root_with_space = tmp_path / "data with space"
    escaped = str(root_with_space).replace(" ", r"\040")
    mountinfo_text = (
        "36 35 98:0 / / rw,relatime shared:1 - ext4 /dev/root rw\n"
        f"37 35 98:1 / {escaped} rw,relatime shared:2 - ext4 /dev/sdb1 rw\n"
    )
    assert _is_mount_point(root_with_space, mountinfo_text)


def test_is_mount_point_fails_closed_on_malformed_mountinfo(tmp_path: Path):
    root = tmp_path / "data"
    malformed_text = "this is not a valid mountinfo line at all\nneither is this\n"
    assert not _is_mount_point(root, malformed_text)


def test_validate_persistent_storage_accepts_mount_path_with_escaped_space(tmp_path: Path):
    root_with_space = tmp_path / "data with space"
    root_with_space.mkdir()
    escaped = str(root_with_space).replace(" ", r"\040")
    mountinfo_text = f"37 35 98:1 / {escaped} rw,relatime shared:2 - ext4 /dev/sdb1 rw\n"

    status = validate_persistent_storage(
        app_env="production",
        db_path=root_with_space / "vietlaw_chat.sqlite3",
        persistent_root=root_with_space,
        mountinfo_reader=lambda: mountinfo_text,
    )
    assert status.ready is True
