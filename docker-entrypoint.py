#!/usr/bin/env python3
"""VietLaw Limited Demo Deployment Correction Round 1 (HIGH-02): container
entrypoint that repairs Railway volume ownership, then drops privileges
before starting the application process.

Railway mounts a persistent volume ROOT-OWNED, regardless of which user the
image itself declares with `USER` -- switching to a non-root user at BUILD
time (the previous `Dockerfile.backend` contract) leaves the container with
no opportunity, at RUN time, to fix ownership of a freshly attached
root-owned volume before the application tries to write to it. This script
is why `Dockerfile.backend` no longer has a `USER` directive: the image
must start as root so this entrypoint can inspect and, if needed, `chown`
`/data`, and only THEN exec the real application as the unprivileged
`vietlaw` user.

Deliberately implemented with only the Python standard library (`os`,
`pwd`, `grp`, `stat`, `sys`) already present in the `python:3.11-slim` base
image -- no `gosu`/`su-exec` binary to install, verify a checksum for, or
trust from a third-party apt/download source. `os.execvp` (not
`subprocess`) replaces this process's own image with the target command,
so the application becomes PID 1 and receives signals (e.g. Railway's
restart/stop) directly, exactly as it would running as the sole process in
the container.

If this process is NOT running as root (e.g. someone already set a
non-root `USER` or runs this image under `docker run --user`), ownership
repair is skipped entirely and the target command is exec'd as-is --
identical to the pre-correction image's behavior in that case.

Deployment Correction Round 2 (MEDIUM-02): the previous `os.walk()` +
`os.chown()` traversal FOLLOWED symlinks -- `os.chown()`'s default
`follow_symlinks=True` means a file symlink under `/data` pointing outside
it (`/data/link -> /outside/target`) had its TARGET's ownership changed,
not the link itself: a concrete, demonstrated ownership escape outside the
volume. For this limited demo, the chosen contract is not "skip symlinks"
(which would leave an attacker- or misconfiguration-planted symlink
silently unrepaired and give no operator signal) but "any symlink anywhere
under `/data` fails startup closed" -- the volume is expected to hold only
plain directories and regular files (the SQLite database and nothing
else), so a symlink's mere presence is itself unexpected and worth halting
on. Traversal uses `os.scandir()` (which reports each entry's type without
an extra syscall on most platforms) and every entry is re-verified with
`os.lstat`-equivalent, no-follow semantics (`entry.stat(follow_symlinks=
False)`) IMMEDIATELY before its own `os.chown(..., follow_symlinks=False)`
call, narrowing (never eliminating -- no unprivileged traversal of a
mutable filesystem can fully eliminate a TOCTOU race) the window between
"this looked safe" and "this got chowned" to the single syscall gap
between the check and the change.
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
import sys

_APP_USER = "vietlaw"
_APP_GROUP = "vietlaw"
_DATA_DIR = "/data"


class SymlinkUnderDataError(RuntimeError):
    """Raised the moment ANY symlink (file or directory) is found anywhere
    under `/data`. Deliberately not narrowed to "symlink pointing outside
    `/data`" -- detecting that distinction reliably (resolving the link
    target and checking it against the volume root) is itself susceptible
    to the same kind of race this module is trying to avoid, and a
    symlink's mere presence on a volume that is expected to hold only the
    SQLite database and plain directories is already an unexpected,
    startup-worthy condition on its own."""


def _chown_path(path: str, uid: int, gid: int) -> None:
    """Re-checks `path` with no-follow (`lstat`) semantics immediately
    before chowning it, also with no-follow semantics
    (`follow_symlinks=False`) -- so even in the event of a symlink swapped
    in between the check and this call, the symlink itself (never a target
    outside `/data`) is the only thing `os.chown` could ever act on."""

    entry_stat = os.lstat(path)
    if stat.S_ISLNK(entry_stat.st_mode):
        raise SymlinkUnderDataError(path)
    os.chown(path, uid, gid, follow_symlinks=False)


def _chown_tree(root: str, uid: int, gid: int) -> None:
    """Ownership repair only -- deliberately narrower than `chmod -R 777`,
    which the task explicitly forbids: this changes WHO owns the volume's
    files, never WHAT permissions they carry, so an operator's own
    permission bits on pre-existing files are preserved.

    Never follows a directory symlink into recursion (`os.scandir` yields
    the entry itself, not its target's contents, unless explicitly
    followed -- this function never does), and raises
    `SymlinkUnderDataError` the instant either the root or any descendant
    entry turns out to be a symlink, before any further ownership change
    beneath it is attempted.
    """

    _chown_path(root, uid, gid)

    with os.scandir(root) as it:
        entries = list(it)
    for entry in entries:
        # Re-check every entry's type with no-follow semantics right here,
        # not trusting `entry.is_dir()`'s cached `d_type` from `scandir`,
        # since that cache could predate a race-induced swap.
        entry_lstat = os.lstat(entry.path)
        if stat.S_ISLNK(entry_lstat.st_mode):
            raise SymlinkUnderDataError(entry.path)
        os.chown(entry.path, uid, gid, follow_symlinks=False)
        if stat.S_ISDIR(entry_lstat.st_mode):
            _chown_tree(entry.path, uid, gid)


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("docker-entrypoint.py: no command given", file=sys.stderr)
        raise SystemExit(1)

    if os.geteuid() == 0:
        user = pwd.getpwnam(_APP_USER)
        group = grp.getgrnam(_APP_GROUP)
        uid, gid = user.pw_uid, group.gr_gid

        if os.path.lexists(_DATA_DIR) and stat.S_ISDIR(os.lstat(_DATA_DIR).st_mode):
            try:
                _chown_tree(_DATA_DIR, uid, gid)
            except SymlinkUnderDataError as error:
                print(
                    f"docker-entrypoint.py: rejecting startup -- symlink found under "
                    f"{_DATA_DIR}: {error}",
                    file=sys.stderr,
                )
                raise SystemExit(1) from error
            except OSError as error:
                # A read-only mounted volume (or any other ownership-repair
                # failure) must fail startup closed, with a clear message --
                # never a raw traceback, and never silently continuing as
                # root or against unrepaired ownership.
                print(
                    f"docker-entrypoint.py: cannot repair ownership of {_DATA_DIR}: {error}",
                    file=sys.stderr,
                )
                raise SystemExit(1) from error

        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    os.execvp(argv[1], argv[1:])


if __name__ == "__main__":
    main(sys.argv)
