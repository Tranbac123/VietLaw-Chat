"""Bounded pre-deploy hardening: `Dockerfile.backend`'s shell-form `CMD`
must expand `${PORT}` as exactly one shell word.

Unquoted, a value like `PORT="8000 --reload"` would be word-split by `sh`
into two separate argv entries, letting `--reload` be interpreted as a
second Uvicorn argument; quoted, the same value is passed to `--port` as a
single (invalid) string, which Uvicorn itself rejects, failing startup
closed rather than silently enabling the dev reloader.

Review finding LOW-01 (first pass): the static/source-text assertions
below prove the Dockerfile is WRITTEN with the quoted form, but not that
`sh` actually WORD-SPLITS it as intended -- a typo elsewhere in the
quoting could still pass a text match. `test_cmd_keeps_malformed_port_as_
single_argument` below is behavioral: it runs the real extracted CMD
string through an actual `sh -c`, substituting `uvicorn` for a stub that
reports its argv, so the test observes real shell word-splitting behavior
rather than pattern-matching source text. This does not require Docker --
only `sh` and Python, both already required to run this suite at all.

Review finding LOW-01 (second pass): `_cmd_shell_command` used to extract
the command via `re.search`, which returns only the FIRST `CMD` match in
the file. Docker itself uses only the LAST `CMD` instruction as an
image's effective command -- so if a later, unsafe `CMD` were ever added
(accidentally, or by a future edit above this one), `re.search` would
keep validating the earlier, now-DEAD instruction and stay green while
the image actually ran something else entirely. `_all_cmd_instructions`
now collects every `CMD` match and `_cmd_shell_command` asserts there is
exactly one, so a second CMD instruction fails this test outright instead
of being silently ignored.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _dockerfile_text() -> str:
    return (REPO_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")


def _cmd_instructions_in(dockerfile_text: str) -> list[str]:
    """Every `CMD [...]` instruction's raw JSON-array text, in file order.

    Docker uses only the LAST `CMD` instruction as the image's effective
    command; every earlier one is dead. Collecting all of them (instead of
    `re.search`'s first match) lets `_cmd_shell_command` assert there is
    exactly one, so a second CMD -- which would silently override this
    test's target in the real image -- fails the test instead of being
    ignored. Takes the Dockerfile text as a parameter (rather than reading
    the file itself) so the "exactly one" guard can be exercised directly
    against a synthetic multi-CMD Dockerfile in a test, without needing to
    actually edit `Dockerfile.backend` to prove it fires.
    """

    return [
        match.group(1) for match in re.finditer(r"^CMD\s+(\[.*\])\s*$", dockerfile_text, re.MULTILINE)
    ]


def _cmd_shell_command() -> str:
    """The actual shell command string Docker would run for the image's
    single effective `CMD` instruction.

    Parses the JSON-array `CMD` instruction the same way Docker itself does
    (`sh -c "<command>"`), rather than pattern-matching the Dockerfile's raw
    (JSON-escaped) text directly -- so this test asserts on the real
    argument Uvicorn would receive, immune to how the quoting happens to be
    escaped in the source file.
    """

    cmd_instructions = _cmd_instructions_in(_dockerfile_text())
    assert len(cmd_instructions) == 1, (
        "Dockerfile.backend must have exactly ONE CMD instruction -- Docker "
        "uses only the LAST one as the image's effective command, so any "
        f"additional CMD would silently override the one this suite validates; "
        f"found {len(cmd_instructions)}: {cmd_instructions!r}"
    )
    argv = json.loads(cmd_instructions[0])
    assert argv[:2] == ["sh", "-c"], "CMD must stay shell-form (sh -c ...)"
    return argv[2]


def test_effective_cmd_guard_fires_on_a_synthetic_multi_cmd_dockerfile() -> None:
    """Self-check: proves the "exactly one CMD" assertion in
    `_cmd_shell_command` actually fires, without editing the real
    `Dockerfile.backend` to do it. A synthetic Dockerfile text with two CMD
    instructions -- an unsafe (unquoted) one followed by the real safe one
    -- must be detected as having 2 instructions, mirroring the exact
    review scenario: a later CMD silently overriding an earlier, validated
    one.
    """

    synthetic_dockerfile = (
        'CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT}"]\n'
        'CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \\"${PORT}\\""]\n'
    )
    cmd_instructions = _cmd_instructions_in(synthetic_dockerfile)
    assert len(cmd_instructions) == 2, (
        "self-check failed: the synthetic Dockerfile has 2 CMD instructions, "
        f"but the helper found {len(cmd_instructions)}: {cmd_instructions!r}"
    )


def test_cmd_quotes_port_expansion() -> None:
    command = _cmd_shell_command()
    assert '--port "${PORT}"' in command
    assert "--port ${PORT}" not in command


def test_cmd_is_still_shell_form_with_exec() -> None:
    # Must stay `exec uvicorn ...` (so Uvicorn becomes PID 1's replacement
    # process image and receives signals directly) -- this task only
    # changes the quoting, not the exec contract.
    command = _cmd_shell_command()
    assert command.startswith("exec uvicorn backend_lite.app.main:app --host 0.0.0.0 --port")


def _run_with_stubbed_uvicorn(tmp_path: Path, command: str, port_value: str) -> list[str]:
    """Run `command` under a real `sh -c`, with `uvicorn` on `PATH`
    resolving to a stub that reports its argv (one entry per line) instead
    of the real Uvicorn. Returns the argv the shell actually handed it.
    """

    stub = tmp_path / "uvicorn"
    stub.write_text('#!/bin/sh\nfor a in "$@"; do printf \'%s\\n\' "$a"; done\n', encoding="utf-8")
    stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    env["PORT"] = port_value

    result = subprocess.run(
        ["sh", "-c", command],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return result.stdout.splitlines()


def test_cmd_keeps_malformed_port_as_single_argument(tmp_path: Path) -> None:
    command = _cmd_shell_command()
    argv = _run_with_stubbed_uvicorn(tmp_path, command, "8000 --reload")

    assert "8000 --reload" in argv, (
        "expected the malformed PORT value to reach Uvicorn as a single "
        f"argv entry (which Uvicorn itself then rejects); got argv={argv!r}"
    )
    assert "--reload" not in argv, (
        "the shell word-split PORT into a separate --reload argument -- "
        f"this is the exact regression the quoting guards against; argv={argv!r}"
    )


def test_cmd_passes_a_normal_port_through_unchanged(tmp_path: Path) -> None:
    command = _cmd_shell_command()
    argv = _run_with_stubbed_uvicorn(tmp_path, command, "8000")
    assert argv[-1] == "8000"


@pytest.mark.parametrize(
    "unquoted_command",
    [
        # A hand-built UNQUOTED variant of the exact same command, used only
        # to prove the harness itself actually observes real shell
        # word-splitting (rather than passing vacuously regardless of
        # quoting) -- not a claim about what Dockerfile.backend contains.
        "exec uvicorn backend_lite.app.main:app --host 0.0.0.0 --port ${PORT}",
    ],
)
def test_harness_detects_word_splitting_in_the_unquoted_form(
    tmp_path: Path, unquoted_command: str
) -> None:
    argv = _run_with_stubbed_uvicorn(tmp_path, unquoted_command, "8000 --reload")
    assert argv[-2:] == ["8000", "--reload"], (
        "self-check failed: the unquoted form should word-split PORT into "
        f"two argv entries, proving the harness observes real shell "
        f"behavior; got argv={argv!r}"
    )
