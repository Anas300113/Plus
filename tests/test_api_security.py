"""Security regressions for administrative API boundaries and input limits."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.core.database import (
    CanonicalQuestion,
    QuestionReviewStatus,
    get_engine,
    get_session_factory,
    init_db,
)
import src.api.main as api_main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("PLUS_REVIEWER_TOKEN", raising=False)
    engine = get_engine(f"sqlite:///{tmp_path / 'security.db'}")
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    question = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text="2+2?", correct_answer="B",
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
    )
    session.add(question)
    session.add(QuestionReviewStatus(question_id=question.id, status="approved"))
    session.commit()
    session.close()
    monkeypatch.setattr(api_main, "_Session", session_factory)
    return TestClient(api_main.app)


def test_exam_mutations_fail_closed_without_reviewer_token(client):
    response = client.post("/api/exams", json={"name": "Untrusted"})
    assert response.status_code == 503


def test_exam_mutations_reject_invalid_reviewer_token(client, monkeypatch):
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "correct-token")
    response = client.post(
        "/api/exams", json={"name": "Untrusted"},
        headers={"X-Reviewer-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_internal_statistics_requires_reviewer_token(client, monkeypatch):
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "correct-token")
    assert client.get("/api/system/statistics").status_code == 403
    response = client.get(
        "/api/system/statistics",
        headers={"X-Reviewer-Token": "correct-token"},
    )
    assert response.status_code == 200


def test_public_inputs_are_bounded(client):
    assert client.get("/api/questions", params={"limit": 101}).status_code == 422
    assert client.get("/api/questions", params={"limit": 0}).status_code == 422
    response = client.post(
        "/api/knowledge/search",
        json={"q": "x" * 1001, "k": 5},
    )
    # Auth is evaluated before loading the index, but malformed bodies are
    # rejected by Pydantic at the request boundary.
    assert response.status_code == 422
