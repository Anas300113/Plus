"""Application settings (Pydantic)."""
from __future__ import annotations

from pathlib import Path
import os
from urllib.parse import urlparse

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLUS_")

    database_url: str = Field(default="sqlite:///./elevenplus.db")
    assets_dir: Path = Field(default=Path("./data/assets"))
    sources_dir: Path = Field(default=Path("./data/sources"))
    fixtures_dir: Path = Field(default=Path("./data/fixtures"))
    pipeline_version: str = Field(default="0.1.0")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        app = data.get("app", {})
        db = data.get("database", {})
        storage = data.get("storage", {})
        pipeline = data.get("pipeline", {})
        return cls(
            database_url=db.get("url", "sqlite:///./elevenplus.db"),
            assets_dir=Path(storage.get("assets_dir", "./data/assets")),
            sources_dir=Path(storage.get("sources_dir", "./data/sources")),
            fixtures_dir=Path(storage.get("fixtures_dir", "./data/fixtures")),
            pipeline_version=str(pipeline.get("version", "0.1.0")),
        )


class ProductionConfigurationError(ValueError):
    """Raised when a production deployment is missing a safe runtime setting."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_production_environment(environ: dict[str, str] | None = None) -> None:
    """Fail closed before starting a real-data deployment.

    This validates configuration only; it never attempts a network connection
    or prints secret values. Database connectivity and schema are checked by
    the migration command and ``/api/ready``.
    """
    env = os.environ if environ is None else environ
    required = (
        "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_URL", "DATABASE_URL", "PLUS11_AUTH_ALLOWED_ORIGINS",
    )
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise ProductionConfigurationError(
            "Missing required production environment variable(s): " + ", ".join(missing))

    db = urlparse(env["DATABASE_URL"])
    if db.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ProductionConfigurationError("Production DATABASE_URL must use PostgreSQL.")
    project_hosts = []
    for name in ("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"):
        parsed = urlparse(env[name])
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ProductionConfigurationError(f"{name} must be an HTTPS Supabase project origin.")
        project_hosts.append(parsed.netloc)
    if project_hosts[0] != project_hosts[1]:
        raise ProductionConfigurationError("SUPABASE_URL and NEXT_PUBLIC_SUPABASE_URL must reference the same project.")
    origins = [item.strip() for item in env["PLUS11_AUTH_ALLOWED_ORIGINS"].split(",") if item.strip()]
    if not origins:
        raise ProductionConfigurationError("PLUS11_AUTH_ALLOWED_ORIGINS must contain a production HTTPS origin.")
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ProductionConfigurationError("Production auth origins must be HTTPS origins without paths.")
    if not _truthy(env.get("PLUS_REAL_STUDENT_DATA")) or not _truthy(env.get("PLUS_REQUIRE_STUDENT_IDENTITY")):
        raise ProductionConfigurationError(
            "PLUS_REAL_STUDENT_DATA and PLUS_REQUIRE_STUDENT_IDENTITY must both be enabled in production.")
    sslmode = env.get("PLUS_DB_SSLMODE", "require").strip().lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ProductionConfigurationError("PLUS_DB_SSLMODE must be require, verify-ca, or verify-full.")
    if sslmode in {"verify-ca", "verify-full"} and not env.get("SUPABASE_DB_SSLROOTCERT", "").strip():
        raise ProductionConfigurationError(
            "SUPABASE_DB_SSLROOTCERT is required when PLUS_DB_SSLMODE is verify-ca or verify-full.")
    migration_flag = env.get("PLUS_RUN_MIGRATIONS", "0").strip()
    if migration_flag not in {"0", "1"}:
        raise ProductionConfigurationError("PLUS_RUN_MIGRATIONS must be 0 or 1.")


def load_taxonomy(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_exams(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
