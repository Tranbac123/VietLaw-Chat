"""Runtime configuration + the frozen safety-notice constant.

Env vars are provider-neutral (see .env.example). `resolved_provider` maps the
neutral config to a concrete LLM provider: anthropic or openai-compatible.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor default data paths to the repo root (backend/app/config.py -> repo).
# Keeps the server and tests independent of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# backend owns this exact text.
# The LLM must never generate or modify it.
SAFETY_NOTICE = (
    "Thông tin này chỉ mang tính định hướng ban đầu, không thay thế tư vấn "
    "pháp lý chính thức. Nếu vụ việc có tranh chấp lớn, rủi ro hình sự, "
    "quyền lợi quan trọng hoặc bạn không chắc nên làm gì, hãy tham khảo "
    "luật sư hoặc cơ quan chức năng."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # App
    app_env: str = "development"
    log_level: str = "info"
    frontend_origin: str = "http://localhost:5173"

    # LLM (provider-neutral). resolved_provider maps to a concrete provider.
    ai_provider: str = ""  # "anthropic" | "openai" | "" (infer from base_url)
    ai_api_key: str = ""
    ai_model_name: str = "api-model"
    ai_base_url: str = ""
    llm_timeout: float = 30.0
    llm_max_retries: int = 1

    # Data paths (default to repo-root data/; override via env with any path)
    chat_db_path: str = str(_REPO_ROOT / "data" / "vietlaw_chat.sqlite3")
    legal_snippets_path: str = str(_REPO_ROOT / "data" / "legal_snippets.json")
    unsafe_patterns_path: str = str(_REPO_ROOT / "data" / "unsafe_patterns.json")

    # RAG / context thresholds
    min_content_score: int = 2
    top_k: int = 3
    max_results_absolute: int = 5
    history_window: int = 10

    @property
    def resolved_provider(self) -> str:
        if self.ai_provider:
            return self.ai_provider
        return "openai" if self.ai_base_url else "anthropic"
