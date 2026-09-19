"""API tests via FastAPI TestClient (needs httpx installed)."""
from __future__ import annotations

import uuid

import pytest

httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from src.core.database import (
    CanonicalQuestion, QuestionReviewStatus, get_engine,
    get_session_factory, init_db,
)
import src.api.main as api_main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "api.db"
    url = f"sqlite:///{db_file}"
    engine = get_engine(url)
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    s.add(q)
    s.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    s.commit()
    qid = q.id
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    c = TestClient(api_main.app)
    return c, qid


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json() == {"ok": True}


def test_questions_only_approved(client):
    c, qid = client
    rows = c.get("/api/questions").json()
    assert [r["id"] for r in rows] == [qid]


def test_attempt_flow(client):
    c, qid = client
    sid = c.post("/api/sessions", params={"student_id": "s1"}).json()["session_id"]
    r = c.post("/api/attempts", json={"student_id": "s1", "session_id": sid,
                                      "question_id": qid, "chosen_answer": "B"})
    assert r.json()["is_correct"] is True
    prog = c.get("/api/progress/s1").json()
    assert "weak_topics" in prog


def test_practice_page_served(client):
    c, _ = client
    r = c.get("/practice")
    assert r.status_code == 200 and "11+ Practice" in r.text


def test_dashboard_pages_served(client):
    c, _ = client
    for path, marker in [("/", "11+ Preparation Platform"),
                         ("/learn", "Learn"), ("/mocks", "Mock Exams"),
                         ("/progress", "Progress"), ("/parent", "Parent dashboard")]:
        r = c.get(path)
        assert r.status_code == 200 and marker in r.text, path


def test_curriculum_and_parent_endpoints(client):
    c, _ = client
    assert c.get("/api/curriculum/maths-fractions").status_code == 200
    assert "practice_completed" in c.get("/api/parent/s1").json()


def test_exam_assemble_endpoint(client):
    c, qid = client
    exam = c.post("/api/exams", json={"name": "E"}).json()
    out = c.post(f"/api/exams/{exam['exam_id']}/assemble",
                 json={"mode": "generated",
                       "sections": [{"subject": "maths", "count": 5}]}).json()
    assert out["questions"] == [qid]
