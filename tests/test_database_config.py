"""Database connection configuration regression tests."""
from __future__ import annotations

import pytest

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
