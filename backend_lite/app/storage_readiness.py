"""VietLaw Limited Demo Deployment Correction Round 1 (HIGH-01): production
persistent-storage validation.

`Settings.chat_db_path` previously accepted ANY path with no distinction
between development and production -- an unset or misconfigured
`CHAT_DB_PATH` in a production deployment silently wrote SQLite state into
the container's own writable overlay filesystem (`/app/data/...`), which
looks perfectly healthy right up until the container is replaced, at
which point every chat, message, and per-chat traffic/fast-demo state is
gone. `validate_persistent_storage` is the single, bounded, injectable-
clock-free (this one needs an injectable FILE reader instead, for the same
reason) check that closes this: in production, it requires an absolute
`CHAT_DB_PATH` that resolves to a descendant of an ACTUALLY MOUNTED `/data`
filesystem, verified via `/proc/self/mountinfo` -- not merely
`Path.exists()`/`Path.is_dir()`/`os.access(..., W_OK)`, none of which can
tell a real bind-mounted volume apart from an ordinary directory the
container image (or a prior `mkdir`) happened to create in its own
writable layer.

Development and test configurations are entirely unaffected: this
function returns "ready" immediately whenever `app_env != "production"`,
preserving every existing project-relative default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: Where Railway (per this deployment's configuration) mounts the
#: persistent volume. Kept as a default parameter (not a hardcoded
#: constant used directly), so a test can point this at a different path
#: without needing an actual mount at `/data`.
DEFAULT_PERSISTENT_ROOT = Path("/data")

_MOUNTINFO_PATH = Path("/proc/self/mountinfo")


@dataclass(frozen=True)
class PersistentStorageStatus:
    """Result of `validate_persistent_storage`. `reason` is always `None`
    when `ready` is `True`, and always a short, non-sensitive (no raw
    filesystem layout beyond the paths the operator themselves configured)
    explanation when `False` -- safe to surface in a log line, never
    intended for an HTTP response body (see `routes_health.py`, which
    reports only booleans, never this dataclass's `reason` text, to an
    external caller)."""

    ready: bool
    reason: str | None = None


def read_mountinfo() -> str:
    """The real, non-injected mount-table reader: `/proc/self/mountinfo`
    (Linux-only -- absent on macOS, which is fine, since this is only ever
    consulted when `app_env == "production"`, and local development never
    sets that). Raises `OSError` on any platform without this pseudo-file;
    callers treat that as "cannot prove a mount, so fail closed," never as
    "assume mounted.\""""

    return _MOUNTINFO_PATH.read_text(encoding="utf-8")


def _is_descendant(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


#: Deployment Correction Round 2 (LOW-01): the four octal escape sequences
#: the Linux kernel actually uses when emitting `/proc/self/mountinfo`
#: (`fs/proc_namespace.c::show_mountinfo` escapes space, tab, newline, and
#: backslash itself in every path field, via `mangle()`) -- any raw
#: occurrence of these bytes in a real mount path would otherwise corrupt
#: the whitespace-separated field format, so the kernel always encodes
#: them this way. This is not a general filesystem-path escape scheme,
#: only mountinfo's specific four.
_MOUNTINFO_ESCAPES: dict[str, str] = {
    "040": " ",
    "011": "\t",
    "012": "\n",
    "134": "\\",
}


def _decode_mountinfo_path(raw: str) -> str:
    """Decodes `\\040`/`\\011`/`\\012`/`\\134` octal escapes in a single
    mountinfo path field. Any other backslash sequence (a malformed or
    unrecognized escape) is left as a literal backslash rather than raising
    -- this function only ever feeds a subsequent EQUALITY comparison
    against a known-literal target (see `_is_mount_point`), so an
    undecodable sequence simply fails to match, which is already the
    correct fail-closed outcome for this module."""

    decoded: list[str] = []
    i = 0
    length = len(raw)
    while i < length:
        char = raw[i]
        if char == "\\" and i + 4 <= length and raw[i + 1 : i + 4] in _MOUNTINFO_ESCAPES:
            decoded.append(_MOUNTINFO_ESCAPES[raw[i + 1 : i + 4]])
            i += 4
        else:
            decoded.append(char)
            i += 1
    return "".join(decoded)


def _is_mount_point(root: Path, mountinfo_text: str) -> bool:
    """Bounded parsing of `/proc/self/mountinfo`'s well-documented
    whitespace-separated format (`man 5 proc_pid_mountinfo`): field index 4
    (0-indexed, i.e. the 5th space-separated field) is the mount point.
    Only that one field is ever inspected -- this is not a general
    mountinfo parser. The field is escape-decoded (see
    `_decode_mountinfo_path`) before comparison, since the kernel encodes
    space/tab/newline/backslash in every path field it emits -- a real
    mount path containing one of these bytes (e.g. `/data with space`)
    would otherwise never compare equal to the literal target and would be
    (incorrectly) treated as unmounted. `/data` itself never contains any
    of these bytes, so this fix does not change behavior for the actual
    production mount path -- it only fixes the general case."""

    target = str(root)
    for line in mountinfo_text.splitlines():
        fields = line.split(" ")
        if len(fields) > 4 and _decode_mountinfo_path(fields[4]) == target:
            return True
    return False


def validate_persistent_storage(
    *,
    app_env: str,
    db_path: Path,
    persistent_root: Path = DEFAULT_PERSISTENT_ROOT,
    mountinfo_reader: Callable[[], str] = read_mountinfo,
) -> PersistentStorageStatus:
    """The single place production-vs-development persistence policy is
    decided. Development/test (`app_env != "production"`) always returns
    `ready=True` immediately -- the existing local, project-relative
    default is untouched by this function entirely.

    Production requires, in order (the first failing condition is the one
    reported):

      1. `db_path` is absolute (Settings' own field validator already
         guarantees this for anything that went through it, but this
         function accepts a bare `Path` too, for direct unit testing).
      2. The RESOLVED `db_path` is a descendant of the RESOLVED
         `persistent_root` -- this single check is what actually rejects
         an unset `CHAT_DB_PATH` (whose default resolves under the image's
         own working directory, never under `/data`), a `/tmp/...` path, a
         `/app/data/...` path, and a `/data/../app/...` traversal attempt,
         all via the exact same comparison, after `Path.resolve()` has
         already collapsed `..` segments.
      3. `persistent_root` is an ACTUAL mount point per
         `/proc/self/mountinfo` -- not merely an existing writable
         directory, which an image's own `mkdir` or a stale container
         layer could produce just as easily as a real Railway volume
         attachment.
      4. `persistent_root` exists, is a directory, and is writable by this
         process.
    """

    if app_env.strip().lower() != "production":
        return PersistentStorageStatus(ready=True)

    if not db_path.is_absolute():
        return PersistentStorageStatus(
            ready=False, reason="CHAT_DB_PATH must be an absolute path in production"
        )

    resolved_db_path = db_path.resolve()
    resolved_root = persistent_root.resolve()

    if not _is_descendant(resolved_db_path, resolved_root):
        return PersistentStorageStatus(
            ready=False,
            reason=f"CHAT_DB_PATH must resolve beneath {resolved_root} in production",
        )

    try:
        mountinfo_text = mountinfo_reader()
    except OSError:
        return PersistentStorageStatus(
            ready=False,
            reason=f"cannot verify {resolved_root} is a mounted filesystem (mountinfo unreadable)",
        )

    if not _is_mount_point(resolved_root, mountinfo_text):
        return PersistentStorageStatus(
            ready=False, reason=f"{resolved_root} is not a mounted filesystem"
        )

    if not resolved_root.is_dir():
        return PersistentStorageStatus(
            ready=False, reason=f"{resolved_root} does not exist or is not a directory"
        )

    if not os.access(resolved_root, os.W_OK):
        return PersistentStorageStatus(ready=False, reason=f"{resolved_root} is not writable")

    return PersistentStorageStatus(ready=True)


class ProductionStorageError(RuntimeError):
    """Raised by `dependencies.py::build_container` when production
    persistent-storage validation fails -- BEFORE any store class is
    constructed or any `ensure_schema()` call runs, so no SQLite file is
    ever created on ephemeral storage. Uncaught, this fails application
    startup entirely (the task's preferred outcome: "prefer failing
    application startup before any SQLite file is created")."""


__all__ = [
    "DEFAULT_PERSISTENT_ROOT",
    "PersistentStorageStatus",
    "ProductionStorageError",
    "read_mountinfo",
    "validate_persistent_storage",
]
