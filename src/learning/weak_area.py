"""Deterministic transparent weak-area + recommendation engine.
v1: accuracy by subject/topic/question-type only."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningRecommendation,
    LearningTopicMastery,
)
import uuid


def refresh_topic_mastery(session: Session, student_id: str) -> int:
    attempts = session.query(LearningQuestionAttempt).filter_by(
        student_id=student_id).all()
    if not attempts:
        return 0
    qids = {a.question_id for a in attempts}
    questions = {q.id: q for q in session.query(CanonicalQuestion)
                 .filter(CanonicalQuestion.id.in_(qids)).all()}
    buckets: dict[str, dict] = {}
    for a in attempts:
        q = questions.get(a.question_id)
        if q is None:
            continue
        b = buckets.setdefault(q.topic, {"n": 0, "c": 0})
        b["n"] += 1
        b["c"] += 1 if a.is_correct else 0
    for topic, b in buckets.items():
        row = session.query(LearningTopicMastery).filter_by(
            student_id=student_id, topic_id=topic).first()
        if row is None:
            row = LearningTopicMastery(student_id=student_id, topic_id=topic)
            session.add(row)
        row.accuracy = (b["c"] / b["n"]) if b["n"] else 0.0
        row.times_practiced = b["n"]
        row.times_correct = b["c"]
    session.commit()
    return len(buckets)


def weak_topics(session: Session, student_id: str,
                threshold: float = 0.6, min_attempts: int = 3) -> list:
    return (session.query(LearningTopicMastery)
            .filter_by(student_id=student_id)
            .filter(LearningTopicMastery.times_practiced >= min_attempts,
                    LearningTopicMastery.accuracy < threshold)
            .order_by(LearningTopicMastery.accuracy).all())


def recommend(session: Session, student_id: str, limit: int = 10):
    weak = weak_topics(session, student_id)
    if not weak:
        return None
    topics = [w.topic_id for w in weak]
    questions = (session.query(CanonicalQuestion)
                 .filter(CanonicalQuestion.topic.in_(topics))
                 .limit(limit).all())
    rec = LearningRecommendation(
        id=str(uuid.uuid4()), student_id=student_id,
        reason="weak_topic",
        question_ids_json=[q.id for q in questions])
    session.add(rec)
    session.commit()
    return rec
