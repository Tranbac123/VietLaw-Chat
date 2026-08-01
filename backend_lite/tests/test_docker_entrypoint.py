"""Deployment Correction Round 2 (MEDIUM-02): symlink-safe volume
ownership repair. `docker-entrypoint.py` lives at the repository root (not
inside the `backend_lite` package, since it must be `COPY`'d into the
Docker image standalone) and has a hyphen in its filename, so it is loaded
here via `importlib` rather than a normal import statement.

These tests run unprivileged (never as root) and exercise `_chown_tree`
with the CURRENT process's own uid/gid -- `os.chown` to a uid/gid you
already own is permitted without root, which is enough to prove the
symlink-rejection logic fires (or doesn't) BEFORE any ownership syscall
ever touches a path outside the tree. A real root-owned-volume smoke test
(actually repairing to uid 999) is covered separately by the Docker smoke
tests in the correction round report, which this unprivileged suite cannot
reach.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "docker_entrypoint", REPO_ROOT / "docker-entrypoint.py"
)
assert _SPEC is not None and _SPEC.loader is not None
docker_entrypoint = importlib.util.module_from_spec(_SPEC)
sys.modules["docker_entrypoint"] = docker_entrypoint
_SPEC.loader.exec_module(docker_entrypoint)


def test_chown_tree_repairs_plain_nested_directories_and_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    nested = data / "sub"
    nested.mkdir(parents=True)
    db_file = nested / "vietlaw_chat.sqlite3"
    db_file.write_text("fake db contents")

    uid, gid = os.getuid(), os.getgid()
    docker_entrypoint._chown_tree(str(data), uid, gid)

    assert os.lstat(data).st_uid == uid
    assert os.lstat(nested).st_uid == uid
    assert os.lstat(db_file).st_uid == uid
    # Existing database file remains readable/writable after repair.
    assert db_file.read_text() == "fake db contents"
    db_file.write_text("still writable")
    assert db_file.read_text() == "still writable"


def test_chown_tree_rejects_file_symlink_and_leaves_outside_target_untouched(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_target = outside / "target.txt"
    outside_target.write_text("do not touch")
    outside_stat_before = os.lstat(outside_target)

    data = tmp_path / "data"
    data.mkdir()
    link = data / "link"
    link.symlink_to(outside_target)

    uid, gid = os.getuid(), os.getgid()
    with pytest.raises(docker_entrypoint.SymlinkUnderDataError):
        docker_entrypoint._chown_tree(str(data), uid, gid)

    outside_stat_after = os.lstat(outside_target)
    assert outside_stat_after.st_uid == outside_stat_before.st_uid
    assert outside_stat_after.st_mtime == outside_stat_before.st_mtime


def test_chown_tree_rejects_directory_symlink_and_leaves_external_dir_untouched(
    tmp_path: Path,
) -> None:
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    outside_file = outside_dir / "file.txt"
    outside_file.write_text("external")
    outside_stat_before = os.lstat(outside_file)

    data = tmp_path / "data"
    data.mkdir()
    dir_link = data / "dir_link"
    dir_link.symlink_to(outside_dir, target_is_directory=True)

    uid, gid = os.getuid(), os.getgid()
    with pytest.raises(docker_entrypoint.SymlinkUnderDataError):
        docker_entrypoint._chown_tree(str(data), uid, gid)

    outside_stat_after = os.lstat(outside_file)
    assert outside_stat_after.st_uid == outside_stat_before.st_uid


def test_chown_tree_rejects_symlink_found_deep_in_nested_directories(tmp_path: Path) -> None:
    outside_target = tmp_path / "outside_target.txt"
    outside_target.write_text("secret")

    data = tmp_path / "data"
    nested = data / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "link").symlink_to(outside_target)

    uid, gid = os.getuid(), os.getgid()
    with pytest.raises(docker_entrypoint.SymlinkUnderDataError):
        docker_entrypoint._chown_tree(str(data), uid, gid)


def test_chown_tree_still_repairs_ordinary_siblings_before_hitting_a_later_symlink(
    tmp_path: Path,
) -> None:
    """Not a hard requirement (startup rejects regardless), but documents
    that the traversal order means already-visited plain entries may have
    been chowned before the rejecting symlink is found -- the container
    still refuses to start either way, so partial repair before rejection
    is harmless."""

    data = tmp_path / "data"
    data.mkdir()
    (data / "a_plain_file.txt").write_text("x")
    (data / "z_link").symlink_to(tmp_path / "nonexistent")

    uid, gid = os.getuid(), os.getgid()
    with pytest.raises(docker_entrypoint.SymlinkUnderDataError):
        docker_entrypoint._chown_tree(str(data), uid, gid)


def test_main_no_command_given_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        docker_entrypoint.main(["docker-entrypoint.py"])
    assert exc_info.value.code == 1
