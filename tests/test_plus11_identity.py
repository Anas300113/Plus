"""Security and learning-flow tests for verified Supabase Auth identities."""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from src.api import main as api_main
from src.api import supabase_identity
from src.api.main import app
from src.api.plus11 import get_db
from src.core.database import (
    CanonicalQuestion,
    LearningQuestionAttempt,
    LearningStudent,
    QuestionReviewStatus,
    get_engine,
    get_session_factory,
    init_db,
)

SUPABASE_URL = "https://test-project.supabase.co"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_DEFAULT_SUBJECT = "11111111-1111-4111-8111-111111111111"


def _token(subject: str | None = None, *, issuer: str = f"{SUPABASE_URL}/auth/v1", expires: int | None = None, name: str = "Sam") -> str:
    now = int(time.time())
    claims = {
        "sub": subject or str(uuid.uuid4()),
        "iss": issuer,
        "aud": "authenticated",
        "role": "authenticated",
        "user_metadata": {"display_name": name},
        "iat": now,
        "exp": expires if expires is not None else now + 300,
    }
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """Bind endpoints and an isolated fake JWKS verifier to a fresh SQLite DB."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setattr(
        supabase_identity,
        "_jwks_client",
        lambda _url: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=_PUBLIC_KEY)),
    )
    engine = get_engine(f"sqlite:///{tmp_path / 'supabase-auth-test.sqlite'}")
    init_db(engine)
    monkeypatch.setattr(api_main, "_engine", engine)
    session_factory = get_session_factory(engine)

    def isolated_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _headers(subject: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(subject or _DEFAULT_SUBJECT)}"}


def test_readiness_checks_database_and_required_schema(api):
    client, _ = api
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def _approved_question(session_factory) -> str:
    question_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(CanonicalQuestion(
            id=question_id,
            subject="maths",
            topic="maths-arithmetic",
            question_type="mcq",
            question_text="What is 2 + 2?",
            correct_answer="B",
            explanation="Two pairs make four.",
            options_json=[{"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}],
        ))
        db.add(QuestionReviewStatus(question_id=question_id, status="approved"))
        db.commit()
    finally:
        db.close()
    return question_id


def test_identity_requires_valid_signature_expiry_and_issuer(api):
    client, _ = api
    assert client.get("/api/me/profile").status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": f"Bearer {_token(expires=int(time.time()) - 30)}"}).status_code == 401
    assert client.get("/api/me/profile", headers={"Authorization": f"Bearer {_token(issuer='https://another-project.supabase.co/auth/v1')}"}).status_code == 401


def test_profile_uses_verified_supabase_subject_and_never_returns_token(api):
    client, session_factory = api
    subject = str(uuid.uuid4())
    first = client.get("/api/me/profile", headers=_headers(subject))
    second = client.get("/api/me/profile", headers=_headers(subject))
    assert first.status_code == second.status_code == 200
    assert first.json()["student_id"] == subject
    assert first.json()["student_id"] == second.json()["student_id"]
    assert "user_metadata" not in first.json()
    assert "Bearer " not in first.text
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 0
    finally:
        db.close()


def test_profile_update_creates_the_learner_only_on_a_mutation(api):
    client, session_factory = api
    read = client.get("/api/me/profile", headers=_headers())
    assert read.status_code == 200
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 0
    finally:
        db.close()

    changed = client.patch(
        "/api/me/profile", headers=_headers(), json={"display_name": "Sam Learner"},
    )
    assert changed.status_code == 200
    assert changed.json()["display_name"] == "Sam Learner"
    db = session_factory()
    try:
        assert db.query(LearningStudent).count() == 1
    finally:
        db.close()


def test_catalog_includes_only_approved_content_and_never_answer_keys(api):
    client, session_factory = api
    approved_id = _approved_question(session_factory)
    db = session_factory()
    pending_id = str(uuid.uuid4())
    try:
        db.add(CanonicalQuestion(
            id=pending_id, subject="english", topic="unreviewed", question_type="mcq",
            question_text="Pending question?", correct_answer="A", explanation="Private.",
            options_json=[{"letter": "A", "text": "One"}],
        ))
        db.add(QuestionReviewStatus(question_id=pending_id, status="pending"))
        db.commit()
    finally:
        db.close()

    response = client.get("/api/me/catalog", headers=_headers())
    assert response.status_code == 200
    payload = response.json()
    assert [subject["id"] for subject in payload["subjects"]] == ["maths"]
    assert payload["subjects"][0]["topics"][0]["approved_question_count"] == 1
    assert approved_id not in response.text
    assert "correct_answer" not in response.text
    assert "explanation" not in response.text
    assert "Pending question" not in response.text


def test_practice_hides_answers_until_check_and_enforces_session_ownership(api):
    client, session_factory = api
    question_id = _approved_question(session_factory)
    start_body = {
        "subject_id": "maths",
        "topic_id": "maths-arithmetic",
        "idempotency_key": str(uuid.uuid4()),
    }
    first = client.post("/api/me/practice/sessions", headers=_headers(), json=start_body)
    duplicate = client.post("/api/me/practice/sessions", headers=_headers(), json=start_body)
    assert first.status_code == duplicate.status_code == 200
    session = first.json()
    assert session["session_id"] == duplicate.json()["session_id"]
    question = session["current_question"]
    assert question["id"] == question_id
    assert "correct_answer" not in question
    assert "explanation" not in question
    assert "answer" not in question

    other_learner = client.get(
        f"/api/me/practice/sessions/{session['session_id']}",
        headers=_headers(str(uuid.uuid4())),
    )
    assert other_learner.status_code == 404

    event_id = str(uuid.uuid4())
    answer_body = {
        "question_id": question_id,
        "chosen_answer": "B",
        "idempotency_key": event_id,
        "time_taken_ms": 12_000,
        "hint_used": False,
        "action": "answer",
    }
    checked = client.post(
        f"/api/me/practice/sessions/{session['session_id']}/answers",
        headers=_headers(), json=answer_body,
    )
    repeated = client.post(
        f"/api/me/practice/sessions/{session['session_id']}/answers",
        headers=_headers(), json=answer_body,
    )
    assert checked.status_code == repeated.status_code == 200
    assert checked.json()["is_correct"] is True
    assert checked.json()["explanation"] == "Two pairs make four."
    assert repeated.json()["is_correct"] is True
    db = session_factory()
    try:
        assert db.query(LearningQuestionAttempt).count() == 1
    finally:
        db.close()
