"""Verify Supabase Auth access tokens for account-backed learner routes.

Only a verified JWT subject is used as learner identity. Email and user
metadata are display-only and never determine authorization or ownership.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class LearnerIdentity:
    student_id: str
    display_name: str


def _supabase_url() -> str:
    value = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        raise ValueError("SUPABASE_URL must be the HTTPS project origin.")
    return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)


def get_current_learner(
    authorization: str | None = Header(default=None),
) -> LearnerIdentity:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in to access your learning.",
                            headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    if not token or len(token) > 8192:
        raise HTTPException(401, "The sign-in session is invalid.")

    try:
        project_url = _supabase_url()
        jwks_url = f"{project_url}/auth/v1/.well-known/jwks.json"
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{project_url}/auth/v1",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=5,
        )
    except (jwt.PyJWTError, ValueError, OSError):
        raise HTTPException(401, "Your sign-in session is invalid or expired.") from None
    except Exception:
        # Network/JWKS failures are unavailable auth infrastructure, not a
        # valid identity; fail closed without leaking provider details.
        raise HTTPException(503, "Account verification is temporarily unavailable.") from None

    subject = claims.get("sub")
    if (not isinstance(subject, str)
            or not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}", subject)
            or claims.get("role") != "authenticated"):
        raise HTTPException(401, "The sign-in session is not valid for Plus11.")

    metadata = claims.get("user_metadata")
    raw_name = metadata.get("display_name", metadata.get("full_name", "")) if isinstance(metadata, dict) else ""
    name = " ".join(raw_name.split())[:80] if isinstance(raw_name, str) else ""
    return LearnerIdentity(student_id=subject.lower(), display_name=name or "Learner")
