"""Runtime configuration.

Defaults are chosen so that `git clone && make install && make seed && make dev`
works with no API keys and no external services (ADR-0002, ADR-0005).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    """Project content root in source and container layouts."""
    here = Path(__file__).resolve()
    candidates = (here.parent, *here.parents)

    for candidate in candidates:
        if (candidate / "knowledge").is_dir() and (candidate / "fixtures").is_dir():
            return candidate
        if (candidate / "docker-compose.yml").is_file():
            return candidate

    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file():
            return candidate

    return here.parent


def _first_existing(*candidates: Path) -> Path:
    """Pick the first directory that exists.

    The API runs from two very different layouts: the source tree during
    `make dev`, and `/app` inside the container where `knowledge/` and
    `fixtures/` are bind-mounted. Falling back rather than hard-coding keeps
    one settings object valid in both.
    """
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_repo_root() / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Demo posture -----------------------------------------------------
    # Gates the seeded operators and the SYNTHETIC DEMO banner. A real
    # deployment sets this false, which disables password-free demo login.
    demo_mode: bool = True

    # --- Storage ----------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./data/eoc.db"

    # --- Model access (optional; see ADR-0005) ----------------------------
    llm_provider: Literal["none", "openai", "anthropic"] = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    embedding_provider: Literal["none", "openai"] = "none"

    # --- Local auth -------------------------------------------------------
    # Blank means "generate a random secret at import time", which is correct
    # for a demo: tokens do not survive a restart and none are ever valid
    # anywhere else.
    demo_jwt_secret: str = ""
    token_ttl_seconds: int = 60 * 60 * 12

    # --- HTTP -------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Content roots ----------------------------------------------------
    knowledge_dir: Path = Field(
        default_factory=lambda: _first_existing(
            _repo_root() / "knowledge", Path("/app/knowledge"), Path("knowledge")
        )
    )
    fixtures_dir: Path = Field(
        default_factory=lambda: _first_existing(
            _repo_root() / "fixtures", Path("/app/fixtures"), Path("fixtures")
        )
    )

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """Database URL with relative SQLite paths pinned to the repo root.

        A bare `sqlite:///./data/eoc.db` resolves against the process working
        directory, so `make seed` (run from apps/api) and `make reset` (run
        from the repo root) would quietly use two different files. Absolute
        paths and non-SQLite URLs pass through untouched.
        """
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return self.database_url

        raw = self.database_url[len(prefix) :]
        if not raw.startswith("./") and not raw.startswith("../"):
            return self.database_url  # already absolute (e.g. //// in Docker)

        target = (_repo_root() / raw).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{target.as_posix()}"

    @property
    def llm_enabled(self) -> bool:
        """True only when a provider AND a key are present.

        Checked in one place so the agent layer degrades to fixture mode by
        omission rather than by every call site remembering to check.
        """
        return self.llm_provider != "none" and bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
