"""Database connection configuration regression tests."""
from __future__ import annotations

import pytest

from src.core.config import ProductionConfigurationError, validate_production_environment
from src.core.database import get_engine


def test_postgres_preserves_supabase_sslmode(monkeypatch):
    monkeypatch.delenv("PLUS_DB_SSLMODE", raising=False)
    monkeypatch.delenv("SUPABASE_DB_SSLROOTCERT", raising=False)
    engine = get_engine(
        "postgresql://user:password@db.example.supabase.co:5432/postgres?sslmode=require"
    )
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.query["sslmode"] == "require"
    finally:
        engine.dispose()


def test_postgres_can_opt_into_certificate_verification(monkeypatch, tmp_path):
    ca = tmp_path / "supabase-ca.crt"
    ca.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PLUS_DB_SSLMODE", "verify-full")
    monkeypatch.setenv("SUPABASE_DB_SSLROOTCERT", str(ca))
    engine = get_engine("postgresql://user:password@db.example.supabase.co:5432/postgres")
    try:
        assert engine.url.query["sslmode"] == "verify-full"
        assert engine.url.query["sslrootcert"] == str(ca)
    finally:
        engine.dispose()


def test_postgres_rejects_unsafe_or_unknown_sslmode(monkeypatch):
    monkeypatch.setenv("PLUS_DB_SSLMODE", "disable")
    with pytest.raises(ValueError, match="PLUS_DB_SSLMODE"):
        get_engine("postgresql://user:password@db.example.supabase.co:5432/postgres")


def _production_env() -> dict[str, str]:
    return {
        "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example",
        "SUPABASE_URL": "https://example.supabase.co",
        "DATABASE_URL": "postgresql://user:password@db.example.supabase.co:5432/postgres",
        "PLUS11_AUTH_ALLOWED_ORIGINS": "https://plus.example.com",
        "PLUS_REAL_STUDENT_DATA": "1",
        "PLUS_REQUIRE_STUDENT_IDENTITY": "1",
        "PLUS_DB_SSLMODE": "require",
        "PLUS_RUN_MIGRATIONS": "0",
    }


def test_production_environment_accepts_safe_baseline():
    validate_production_environment(_production_env())


def test_production_environment_rejects_sqlite_and_insecure_origin():
    env = _production_env()
    env["DATABASE_URL"] = "sqlite:///./elevenplus.db"
    with pytest.raises(ProductionConfigurationError, match="PostgreSQL"):
        validate_production_environment(env)
    env = _production_env()
    env["PLUS11_AUTH_ALLOWED_ORIGINS"] = "http://localhost:3000"
    with pytest.raises(ProductionConfigurationError, match="HTTPS"):
        validate_production_environment(env)


def test_production_environment_requires_ca_for_verified_tls():
    env = _production_env()
    env["PLUS_DB_SSLMODE"] = "verify-full"
    with pytest.raises(ProductionConfigurationError, match="SUPABASE_DB_SSLROOTCERT"):
        validate_production_environment(env)
