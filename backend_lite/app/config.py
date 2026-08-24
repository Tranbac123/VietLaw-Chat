from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .env_loader import load_local_env


REPO_ROOT = Path(__file__).resolve().parents[2]

#: The only values `APP_ENV` may resolve to. `storage_readiness.py`'s
#: production/non-production branch, and `main.py`'s CORS-wildcard guard,
#: both key off this same three-way distinction -- an explicit typo
#: (`prod`, `staging`, ...) must never silently fall into the
#: non-production branch and skip those checks, so it is rejected here
#: rather than accepted and misinterpreted.
_ALLOWED_APP_ENVS = frozenset({"development", "test", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "info"
    backend_mode: str = "lite"
    chat_db_path: Path = REPO_ROOT / "data" / "vietlaw_chat.sqlite3"
    legal_snippets_path: Path = REPO_ROOT / "data" / "legal_snippets.json"
    unsafe_patterns_path: Path = REPO_ROOT / "data" / "unsafe_patterns.json"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    rag_top_k: int = 3
    context_message_limit: int = 8

    def __init__(self, **values: object) -> None:
        load_local_env()
        super().__init__(**values)

    @field_validator("chat_db_path", "legal_snippets_path", "unsafe_patterns_path", mode="before")
    @classmethod
    def resolve_path(cls, value: object) -> Path:
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else (Path.cwd() / path).resolve()

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        """Fail closed on an unrecognized `APP_ENV`, case/whitespace aside.

        An explicit typo like `prod` previously fell into the SAME
        `app_env != "production"` branch as a genuine non-production
        environment everywhere this field is read (the persistent-storage
        guard, the CORS-wildcard guard), silently skipping every
        production-only safeguard instead of surfacing the misconfiguration.
        Normalizing a RECOGNIZED value's case/whitespace (e.g. `
        PRODUCTION `) is not the same as normalizing an unrecognized one
        (`prod` is never coerced into `production`) -- that would hide the
        same class of misconfiguration this validator exists to catch.
        """

        normalized = value.strip().lower()
        if normalized not in _ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV must be one of {sorted(_ALLOWED_APP_ENVS)} (got {value!r})"
            )
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
