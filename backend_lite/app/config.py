from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .env_loader import load_local_env


REPO_ROOT = Path(__file__).resolve().parents[2]


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
