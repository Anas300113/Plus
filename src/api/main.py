"""FastAPI application: approved questions, practice sessions,
review queue. Only APPROVED questions are student-facing."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningStudent,
    LearningStudySession, QuestionReviewStatus, get_engine,
    get_session_factory, init_db,
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


app = FastAPI(title="11+ Platform API", version="0.1.0")


class AnswerIn(BaseModel):
    student_id: str
    session_id: str
    question_id: str
    chosen_answer: str
    time_taken_ms: int = 0


@app.get("/api/health")
def health():
    return {"ok": True}


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
    return [{"id": r.id, "subject": r.subject, "topic": r.topic,
             "question_type": r.question_type, "question_text": r.question_text,
             "options": r.options_json, "context": r.context,
             "correct_answer": r.correct_answer} for r in rows]


@app.post("/api/sessions")
def create_session(student_id: str, session_type: str = "practice",
                   db: Session = Depends(get_db)):
    student = db.query(LearningStudent).filter_by(id=student_id).first()
    if student is None:
        student = LearningStudent(id=student_id, name=student_id)
        db.add(student)
        db.commit()
    s = LearningStudySession(id=str(uuid.uuid4()), student_id=student.id,
                             session_type=session_type)
    db.add(s)
    db.commit()
    return {"session_id": s.id}


@app.post("/api/attempts")
def record_attempt(payload: AnswerIn, db: Session = Depends(get_db)):
    q = db.query(CanonicalQuestion).filter_by(id=payload.question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=q.id).first()
    if status is None or status.status != "approved":
        raise HTTPException(403, "question is not approved for practice")
    correct = payload.chosen_answer.strip().upper() == q.correct_answer.strip().upper()
    db.add(LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=payload.student_id,
        session_id=payload.session_id, question_id=q.id,
        chosen_answer=payload.chosen_answer, is_correct=correct,
        time_taken_ms=payload.time_taken_ms))
    db.commit()
    return {"is_correct": correct, "explanation": q.explanation}


@app.get("/api/review-queue")
def review_queue(limit: int = 50, db: Session = Depends(get_db)):
    from src.pipeline.review import review_queue as rq
    rows = rq(db, limit)
    return [{"id": q.id, "subject": q.subject, "topic": q.topic,
             "text": q.question_text[:300], "status": s.status} for q, s in rows]


class ReviewIn(BaseModel):
    status: str  # approved | rejected
    reviewer: str = "api"


@app.post("/api/review/{question_id}")
def review(question_id: str, payload: ReviewIn, db: Session = Depends(get_db)):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved|rejected")
    from src.pipeline.review import set_status
    try:
        set_status(db, question_id, payload.status, payload.reviewer)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True, "status": payload.status}


@app.get("/api/progress/{student_id}")
def progress(student_id: str, db: Session = Depends(get_db)):
    from src.learning.weak_area import refresh_topic_mastery, weak_topics
    refresh_topic_mastery(db, student_id)
    weak = weak_topics(db, student_id)
    return {"weak_topics": [
        {"topic": w.topic_id, "accuracy": w.accuracy,
         "practiced": w.times_practiced} for w in weak]}
