"""FastAPI application: approved questions, practice sessions,
review queue. Only APPROVED questions are student-facing.

Learning-layer endpoints (session state machine, statistics, review items,
educational loop) live in src/learning/*; the routes here are thin wrappers
that translate HTTP into those functions and never re-implement their rules.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.api.dashboard_pages import HOME, LEARN, MOCKS, PARENT, PROGRESS
from src.api.practice_page import PRACTICE_HTML

from src.core.database import (
    CanonicalQuestion, QuestionReviewStatus, get_engine, get_session_factory,
    init_db,
)

DB_URL = os.environ.get("PLUS_DATABASE_URL", "sqlite:///./elevenplus.db")
_engine = get_engine(DB_URL)
_Session = get_session_factory(_engine)
init_db(_engine)


def get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


# Reviewer authorisation boundary.
# -------------------------------
# The application has no user/identity model yet (student routes take a bare
# ``student_id``). Reviewer operations change persisted state and can publish
# a question to students, so they MUST be gated server-side, not just hidden in
# the UI. The smallest correct boundary is a shared reviewer token supplied in
# the ``X-Reviewer-Token`` header and compared (constant-time) against the
# ``PLUS_REVIEWER_TOKEN`` environment variable.
#
# Fail-closed: when the token is not configured, reviewer MUTATIONS are locked
# (503) rather than left open. Read-only reviewer endpoints stay available so
# the workbench can render. This is a thin boundary pending a real auth system;
# it is never the sole protection for student data (answers are never sent to
# students regardless of this guard).
REVIEWER_TOKEN_ENV = "PLUS_REVIEWER_TOKEN"


def require_reviewer(x_reviewer_token: str | None = Header(default=None)):
    import hmac
    import os as _os
    expected = _os.environ.get(REVIEWER_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(
            503, "reviewer operations are locked: set PLUS_REVIEWER_TOKEN")
    if not x_reviewer_token or not hmac.compare_digest(
            x_reviewer_token, expected):
        raise HTTPException(403, "invalid or missing reviewer token")


app = FastAPI(title="11+ Platform API", version="0.1.0")


class AnswerIn(BaseModel):
    student_id: str
    session_id: str
    question_id: str
    chosen_answer: str
    time_taken_ms: int = 0
    action: str = "answer"
    hint_used: bool = False


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def home():
    return HOME


@app.get("/learn", response_class=HTMLResponse)
def learn():
    return LEARN


@app.get("/mocks", response_class=HTMLResponse)
def mocks():
    return MOCKS


@app.get("/progress", response_class=HTMLResponse)
def progress_page():
    return PROGRESS


@app.get("/parent", response_class=HTMLResponse)
def parent_page():
    return PARENT


@app.get("/practice", response_class=HTMLResponse)
def practice_page():
    return PRACTICE_HTML


@app.get("/api/questions")
def list_questions(subject: str | None = None, topic: str | None = None,
                   limit: int = 20, db: Session = Depends(get_db)):
    q = (db.query(CanonicalQuestion)
         .join(QuestionReviewStatus,
               QuestionReviewStatus.question_id == CanonicalQuestion.id)
         .filter(QuestionReviewStatus.status == "approved"))
    if subject:
        q = q.filter(CanonicalQuestion.subject == subject)
    if topic:
        q = q.filter(CanonicalQuestion.topic == topic)
    rows = q.limit(limit).all()
    # Student-facing: NEVER expose correct_answer here. Marking happens
    # server-side via the session answer route, which reads the verified
    # answer from the stored record. Exposing it here would let a client
    # trivially cheat.
    return [{"id": r.id, "subject": r.subject, "topic": r.topic,
             "question_type": r.question_type, "question_text": r.question_text,
             "options": r.options_json, "context": r.context} for r in rows]


@app.post("/api/sessions")
def create_session(student_id: str, session_type: str = "practice",
                   subject: str | None = None, topic: str | None = None,
                   limit: int = 20, planned_duration_seconds: int = 0,
                   from_review_queue: bool = False, seed: int = 42,
                   db: Session = Depends(get_db)):
    """Start a session through the explicit state machine.

    Backwards compatible: with only ``student_id`` supplied it behaves as
    before, but the question order is now frozen so the session can be resumed.
    """
    from src.learning.session import start_session
    try:
        s = start_session(
            db, student_id, session_type=session_type, subject=subject,
            topic=topic, limit=limit,
            planned_duration_seconds=planned_duration_seconds, seed=seed,
            from_review_queue=from_review_queue)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"session_id": s.id, "state": s.state,
            "session_type": s.session_type,
            "total": len(s.question_order)}


class SessionStartIn(BaseModel):
    student_id: str
    session_type: str = "practice"
    subject: str | None = None
    topic: str | None = None
    question_ids: list[str] = []
    limit: int = 20
    ordering: str = "canonical"
    seed: int = 42
    planned_duration_seconds: int = 0
    goals: dict = {}
    from_review_queue: bool = False


@app.post("/api/sessions/start")
def start_session_route(payload: SessionStartIn, db: Session = Depends(get_db)):
    """Body-based session start (frozen order, goals, review-queue support)."""
    from src.learning.session import start_session
    try:
        s = start_session(
            db, payload.student_id, session_type=payload.session_type,
            question_ids=payload.question_ids, subject=payload.subject,
            topic=payload.topic, limit=payload.limit,
            ordering=payload.ordering, seed=payload.seed,
            planned_duration_seconds=payload.planned_duration_seconds,
            goals=payload.goals, from_review_queue=payload.from_review_queue)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"session_id": s.id, "state": s.state,
            "total": len(s.question_order),
            "question_order": s.question_order}


@app.get("/api/sessions/{session_id}")
def get_session_state(session_id: str, db: Session = Depends(get_db)):
    """Resume payload: current question, index, progress, goals, activities."""
    from src.learning.session import session_state
    try:
        return session_state(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class SubmitIn(BaseModel):
    question_id: str = ""
    chosen_answer: str = ""
    time_taken_ms: int = 0
    hint_used: bool = False
    action: str = "answer"  # answer | skip | retry


@app.post("/api/sessions/{session_id}/answer")
def session_answer(session_id: str, payload: SubmitIn,
                   db: Session = Depends(get_db)):
    """ASSESS + EXPLAIN: record evidence, return feedback, schedule review."""
    from src.learning.session import submit_answer
    try:
        # Retries are re-attempts on a previously-answered question, so they
        # are not required to be the session's "current" question.
        enforce = payload.action != "retry"
        return submit_answer(db, session_id, payload.question_id,
                             payload.chosen_answer, payload.time_taken_ms,
                             hint_used=payload.hint_used, action=payload.action,
                             enforce_current=enforce)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/skip")
def session_skip(session_id: str, payload: SubmitIn | None = None,
                 db: Session = Depends(get_db)):
    """SKIP: stored as evidence, creates a review item, never counts as wrong."""
    from src.learning.session import skip_current
    question_id = (payload.question_id if payload and payload.question_id
                   else None)
    try:
        return skip_current(db, session_id,
                            payload.time_taken_ms if payload else 0,
                            question_id=question_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/retry")
def session_retry(session_id: str, db: Session = Depends(get_db)):
    """RETRY: allow a re-answer of the current question (hint returned)."""
    from src.learning.session import retry_current
    try:
        return retry_current(db, session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/complete")
def session_complete(session_id: str, db: Session = Depends(get_db)):
    """COMPLETE: results view, mastery refresh, new recommendations."""
    from src.learning.session import complete_session
    try:
        return complete_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/sessions/{session_id}/abandon")
def session_abandon(session_id: str, db: Session = Depends(get_db)):
    """ABANDON: close the session, keep all attempt evidence."""
    from src.learning.session import abandon_session
    try:
        return abandon_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/sessions/{session_id}/results")
def session_results_route(session_id: str, db: Session = Depends(get_db)):
    from src.learning.session import session_results
    try:
        return session_results(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/attempts")
def record_attempt(payload: AnswerIn, db: Session = Depends(get_db)):
    """Legacy evidence endpoint, kept for compatibility.

    Prefer ``POST /api/sessions/{id}/answer``. This path records evidence for
    a question that may not be the session's frozen current question, so it
    runs the same logic with ``enforce_current=False``. It never advances the
    session cursor and it still refuses non-approved questions.
    """
    from src.learning.session import get_session, submit_answer
    q = db.query(CanonicalQuestion).filter_by(id=payload.question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=q.id).first()
    if status is None or status.status != "approved":
        raise HTTPException(403, "question is not approved for practice")
    try:
        session = get_session(db, payload.session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    result = submit_answer(
        db, session.id, q.id, payload.chosen_answer,
        time_taken_ms=payload.time_taken_ms, hint_used=payload.hint_used,
        action=payload.action, enforce_current=False)
    return {"is_correct": result["is_correct"],
            "explanation": q.explanation,
            "feedback": result["feedback"],
            "review_item_id": result["review_item_id"]}


@app.get("/api/review-queue")
def review_queue(limit: int = 50, db: Session = Depends(get_db)):
    from src.pipeline.review import review_queue as rq
    rows = rq(db, limit)
    return [{"id": q.id, "subject": q.subject, "topic": q.topic,
             "text": q.question_text[:300], "status": s.status} for q, s in rows]


class ReviewIn(BaseModel):
    status: str  # approved | rejected
    reviewer: str = "api"
    reason: str = ""


@app.post("/api/review/{question_id}")
def review(question_id: str, payload: ReviewIn, db: Session = Depends(get_db),
           _reviewer: None = Depends(require_reviewer)):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved|rejected")
    from src.pipeline.review import ApprovalContractError, set_status
    try:
        set_status(db, question_id, payload.status, payload.reviewer,
                   payload.reason)
    except ApprovalContractError as exc:
        # The question exists but does not meet the trustworthy contract.
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True, "status": payload.status}


@app.get("/api/review/{question_id}")
def review_detail(question_id: str, db: Session = Depends(get_db)):
    """Reviewer workbench: the stored question, its provenance, verification
    states, extraction warnings and the precise unmet approval requirements."""
    from src.pipeline.review import approval_blockers, has_provenance
    from src.core.database import QuestionOccurrence, QuestionReviewEvent
    q = db.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    occs = db.query(QuestionOccurrence).filter_by(
        canonical_question_id=question_id).all()
    provenance = [{
        "document_id": o.document_id, "page_id": o.page_id,
        "question_number": o.question_number,
        "linked_answer": o.linked_answer,
        "extraction_confidence": o.extraction_confidence,
    } for o in occs]
    events = db.query(QuestionReviewEvent).filter_by(
        question_id=question_id).order_by(QuestionReviewEvent.created_at).all()
    return {
        "id": q.id, "subject": q.subject, "topic": q.topic,
        "question_type": q.question_type, "question_text": q.question_text,
        "options": q.options_json, "context": q.context,
        "correct_answer": q.correct_answer,
        "answer_status": q.answer_status,
        "explanation_status": q.explanation_status,
        "answer_evidence": q.answer_evidence,
        "explanation": q.explanation,
        "extraction_warnings": q.extraction_warnings_json or [],
        "review_status": (status.status if status else None),
        "reviewer": (status.reviewer if status else ""),
        "has_provenance": has_provenance(db, question_id),
        "provenance": provenance,
        "approval_blockers": approval_blockers(db, question_id),
        "review_history": [{
            "action": e.action, "reviewer": e.reviewer,
            "from_status": e.from_status, "to_status": e.to_status,
            "reason": e.reason, "created_at": e.created_at.isoformat(),
        } for e in events],
    }


class VerifyIn(BaseModel):
    reviewer: str = "api"
    evidence: str = ""


@app.post("/api/review/{question_id}/verify-answer")
def verify_answer_endpoint(question_id: str, payload: VerifyIn,
                           db: Session = Depends(get_db),
                           _reviewer: None = Depends(require_reviewer)):
    from src.pipeline.review import verify_answer
    try:
        verify_answer(db, question_id, payload.reviewer, payload.evidence)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "answer_status": "verified"}


@app.post("/api/review/{question_id}/verify-explanation")
def verify_explanation_endpoint(question_id: str, payload: VerifyIn,
                                db: Session = Depends(get_db),
                                _reviewer: None = Depends(require_reviewer)):
    from src.pipeline.review import verify_explanation
    try:
        verify_explanation(db, question_id, payload.reviewer, payload.evidence)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "explanation_status": "verified"}


class EditIn(BaseModel):
    reviewer: str = "api"
    question_text: str | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    options_json: list | None = None


@app.post("/api/review/{question_id}/edit")
def edit_endpoint(question_id: str, payload: EditIn,
                  db: Session = Depends(get_db),
                  _reviewer: None = Depends(require_reviewer)):
    from src.pipeline.review import edit_question
    try:
        edit_question(db, question_id, payload.reviewer,
                      question_text=payload.question_text,
                      correct_answer=payload.correct_answer,
                      explanation=payload.explanation,
                      options_json=payload.options_json)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}



@app.get("/api/progress/{student_id}")
def progress(student_id: str, db: Session = Depends(get_db)):
    """Progress view: mastery refresh, weak topics (existing shape) + extras."""
    from src.learning.review import review_summary
    from src.learning.weak_area import (
        open_recommendations, refresh_mastery, weak_skills, weak_topics,
    )
    refresh_mastery(db, student_id)
    weak = weak_topics(db, student_id)
    skills = weak_skills(db, student_id)
    return {
        "student_id": student_id,
        "weak_topics": [
            {"topic": w.topic_id, "accuracy": w.accuracy,
             "practiced": w.times_practiced} for w in weak],
        "weak_skills": [
            {"skill": s.skill_id, "topic": s.topic_id, "accuracy": s.accuracy,
             "practiced": s.times_practiced} for s in skills],
        "review": review_summary(db, student_id),
        "recommendations": open_recommendations(db, student_id),
    }


@app.get("/api/statistics/{student_id}")
def statistics_route(student_id: str, days: int = 14,
                     recent_window: int = 20,
                     db: Session = Depends(get_db)):
    """Deterministic learning statistics (subject/topic/skill/type/review)."""
    from src.learning.statistics import student_statistics
    from src.learning.weak_area import refresh_mastery
    refresh_mastery(db, student_id)
    return student_statistics(db, student_id, recent_window=recent_window,
                              days=days)


@app.get("/api/reviews/{student_id}")
def reviews_route(student_id: str, limit: int = 50,
                  db: Session = Depends(get_db)):
    """ReviewItem state for a student: due now, upcoming, per-state counts.

    Scheduling only - no FSRS. See src/learning/review.py.
    """
    from src.learning.review import due_review_items, review_summary
    due = due_review_items(db, student_id, limit=limit)
    summary = review_summary(db, student_id)
    return {
        "summary": summary,
        "due": [{"id": r.id, "source_type": r.source_type,
                 "source_id": r.source_id, "topic": r.topic_id,
                 "subject": r.subject, "state": r.state,
                 "due_at": r.due_at.isoformat() if r.due_at else "",
                 "due_reason": r.due_reason, "interval_days": r.interval_days,
                 "review_count": r.review_count,
                 "consecutive_correct": r.consecutive_correct} for r in due],
    }


@app.get("/api/recommendations/{student_id}")
def recommendations_route(student_id: str, refresh: bool = False,
                          db: Session = Depends(get_db)):
    """What the student should do next (deterministic, no LLM)."""
    from src.learning.weak_area import (
        open_recommendations, refresh_recommendations,
    )
    if refresh:
        return {"recommendations": refresh_recommendations(db, student_id)}
    return {"recommendations": open_recommendations(db, student_id)}


@app.get("/api/loop/{student_id}")
def loop_route(student_id: str, db: Session = Depends(get_db)):
    """The educational loop snapshot:
    LEARN -> PRACTISE -> ASSESS -> IDENTIFY ERROR -> EXPLAIN -> REVIEW ->
    RE-PRACTISE -> UPDATE MASTERY. Works without any LLM call.
    """
    from src.learning.loop import loop_snapshot
    from src.learning.weak_area import refresh_mastery
    # UPDATE MASTERY step: recompute from fresh evidence before reading
    refresh_mastery(db, student_id)
    return loop_snapshot(db, student_id)


@app.get("/api/system/statistics")
def system_statistics_route(limit: int = 50, db: Session = Depends(get_db)):
    """Content-health view: validation status counts, hardest questions.

    Item-discrimination figures are indicative only and reported as ``None``
    until enough students have answered.
    """
    from src.learning.statistics import system_statistics
    return system_statistics(db, limit=limit)


@app.get("/api/curriculum/{topic_id}")
def curriculum(topic_id: str, db: Session = Depends(get_db)):
    from src.core.database import (
        CurriculumCommonMistake, CurriculumLesson, CurriculumStrategy,
        CurriculumWorkedExample,
    )
    return {
        "lessons": [{"title": r.title, "content": r.content_markdown}
                    for r in db.query(CurriculumLesson).filter_by(topic_id=topic_id).all()],
        "strategies": [{"title": r.title, "content": r.content_markdown}
                       for r in db.query(CurriculumStrategy).filter_by(topic_id=topic_id).all()],
        "worked_examples": [{"title": r.title, "content": r.content_markdown}
                            for r in db.query(CurriculumWorkedExample).filter_by(topic_id=topic_id).all()],
        "common_mistakes": [{"mistake": r.mistake_text, "explanation": r.explanation_markdown}
                            for r in db.query(CurriculumCommonMistake).filter_by(topic_id=topic_id).all()],
    }


@app.get("/api/parent/{student_id}")
def parent_dashboard(student_id: str, db: Session = Depends(get_db)):
    from src.learning.parent_summary import parent_summary
    return parent_summary(db, student_id)


class ExamCreate(BaseModel):
    exam_board_id: str = "mixed"
    name: str = "Practice paper"
    region: str = ""


@app.post("/api/exams")
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    from src.core.database import AssessmentExam
    e = AssessmentExam(id=str(uuid.uuid4()), exam_board_id=payload.exam_board_id,
                       name=payload.name, region=payload.region)
    db.add(e)
    db.commit()
    return {"exam_id": e.id}


class AssembleIn(BaseModel):
    mode: str = "generated"  # generated | authentic
    sections: list[dict] = []
    document_id: str = ""
    seed: int = 42


@app.post("/api/exams/{exam_id}/assemble")
def assemble_exam(exam_id: str, payload: AssembleIn, db: Session = Depends(get_db)):
    from src.assessment.assembler import assemble_authentic, assemble_generated
    if payload.mode == "authentic":
        return assemble_authentic(db, exam_id, payload.document_id)
    return assemble_generated(db, exam_id, payload.sections, seed=payload.seed)


# ---------------- Knowledge / retrieval (read-only) ----------------
# Thin wrapper over the frozen ingestion foundation. Retrieval only ever
# *returns evidence* (filename + page + excerpt) for the given query; it never
# creates, promotes or approves questions/answers. If an index file is not
# configured or present, this returns HTTP 503 with a clear message so callers
# do not mistake "no index built yet" for "no evidence exists".

_KNOWLEDGE_INDEX_PATH = os.environ.get(
    "PLUS_KNOWLEDGE_INDEX", "data/knowledge/index.joblib"
)


class KnowledgeQuery(BaseModel):
    q: str
    k: int = 5


@app.post("/api/knowledge/search")
def knowledge_search(payload: KnowledgeQuery):
    from pathlib import Path

    from fastapi import HTTPException

    from src.knowledge.retriever import KnowledgeIndex
    path = Path(_KNOWLEDGE_INDEX_PATH)
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "knowledge index not built; run "
                "'python scripts/knowledge_cli.py index' first"
            ),
        )
    idx = KnowledgeIndex.load(path)
    hits = idx.search(payload.q, top_k=payload.k)
    return {
        "query": payload.q,
        "evidence": hits,
        "insufficient_evidence": len(hits) == 0,
    }

