"""Student ownership-boundary regression tests (P1-13).

Reproduce the concrete defect: every per-student route takes a bare
``student_id`` (path or body) and no endpoint verified the caller owns the
requested resource. Before the fix, ANY caller who knew another student's id
could read that student's progress / reviews / loop / parent dashboard, resume
their session, or submit answers into their session -- an ownership hole, not
just a privacy nicety.

The boundary is opt-in strict mode (``PLUS_REQUIRE_STUDENT_IDENTITY``): when
enabled a caller must present ``X-Student-Id`` and it must equal the OWNING
student id (for session routes the owner is read from the stored session, not
the URL). When disabled the API behaves exactly as before, so the stateless
demo UI and existing frozen tests keep working. These tests assert BOTH the
protected behaviour (flag on) and the unchanged behaviour (flag off), and they
drive the real persistence + TestClient path, never a mock.
"""
from __future__ import annotations

import uuid

import pytest

httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src.core.database import (  # noqa: E402
    CanonicalQuestion, QuestionReviewStatus, get_engine,
    get_session_factory, init_db,
)
import src.api.main as api_main  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A client bound to a fresh DB with one approved question."""
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text="2+2?", correct_answer="B",
        explanation="Because 2+2=4.",
        options_json=[{"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}])
    s.add(q)
    s.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    s.commit()
    qid = q.id
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app), qid


def _strict(monkeypatch):
    monkeypatch.setenv("PLUS_REQUIRE_STUDENT_IDENTITY", "1")


# ---- per-student GET endpoints ------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/progress/s1",
    "/api/statistics/s1",
    "/api/reviews/s1",
    "/api/recommendations/s1",
    "/api/loop/s1",
    "/api/parent/s1",
])
def test_cross_student_read_is_blocked(env, monkeypatch, path):
    """A caller cannot read student s1's data by supplying s1 in the URL:
    under strict identity an attacker's X-Student-Id must be rejected."""
    c, _ = env
    _strict(monkeypatch)
    r = c.get(path, headers={"X-Student-Id": "attacker"})
    assert r.status_code == 403, path
    r = c.get(path)
    assert r.status_code == 401, path
    r = c.get(path, headers={"X-Student-Id": "s1"})
    assert r.status_code == 200, path


@pytest.mark.parametrize("path", [
    "/api/progress/s1",
    "/api/reviews/s1",
    "/api/parent/s1",
])
def test_default_off_preserves_previous_behaviour(env, monkeypatch, path):
    """With the flag OFF (default) the endpoint works with no header, so the
    frozen suite and the stateless demo UI are unaffected."""
    c, _ = env
    monkeypatch.delenv("PLUS_REQUIRE_STUDENT_IDENTITY", raising=False)
    r = c.get(path)
    assert r.status_code == 200, path


# ---- session-scoped endpoints -------------------------------------------

def test_cannot_read_or_act_on_another_students_session(env, monkeypatch):
    """Resume/results/answer/complete/abandon must not let one student touch
    another's session, even knowing its id."""
    c, qid = env
    _strict(monkeypatch)
    sid = c.post("/api/sessions/start", headers={"X-Student-Id": "s1"},
                 json={"student_id": "s1"}).json()["session_id"]
    assert c.get(f"/api/sessions/{sid}",
                 headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.get(f"/api/sessions/{sid}/results",
                 headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.post(f"/api/sessions/{sid}/answer",
                  headers={"X-Student-Id": "attacker"},
                  json={"question_id": qid, "chosen_answer": "B"}
                  ).status_code == 403
    assert c.post(f"/api/sessions/{sid}/complete",
                  headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.post(f"/api/sessions/{sid}/abandon",
                  headers={"X-Student-Id": "attacker"}).status_code == 403
    assert c.get(f"/api/sessions/{sid}",
                 headers={"X-Student-Id": "s1"}).status_code == 200


def test_attempts_endpoint_requires_matching_identity(env, monkeypatch):
    """Legacy POST /api/attempts must also refuse a mismatched X-Student-Id."""
    c, qid = env
    _strict(monkeypatch)
    sid = c.post("/api/sessions/start", headers={"X-Student-Id": "s1"},
                 json={"student_id": "s1"}).json()["session_id"]
    r = c.post("/api/attempts", headers={"X-Student-Id": "attacker"},
               json={"student_id": "s1", "session_id": sid,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 403
    r = c.post("/api/attempts", headers={"X-Student-Id": "s1"},
               json={"student_id": "s1", "session_id": sid,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 200 and r.json()["is_correct"] is True

