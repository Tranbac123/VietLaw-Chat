"""Load the repository-local dotenv file for backend_lite configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def repository_root() -> Path:
    """Return this checkout's root without consulting the current directory."""

    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=None)
def load_local_env(env_path: Path | None = None) -> bool:
    """Load this repository's ``.env`` once without overriding process values.

    ``env_path`` exists solely to let tests supply an isolated temporary dotenv
    file. Production callers use only the repository-root ``.env``.
    """

    resolved_path = env_path if env_path is not None else repository_root() / ".env"
    if not resolved_path.is_file():
        return False
    load_dotenv(resolved_path, override=False)
    return True
