"""Parent dashboard aggregation: practice completed, subject/topic
performance, recent activity, weak areas, next steps. Deterministic
queries only; no psychological claims."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningTopicMastery,
)


def parent_summary(session: Session, student_id: str) -> dict:
    attempts = session.query(LearningQuestionAttempt).filter_by(
        student_id=student_id).all()
    qids = {a.question_id for a in attempts}
    questions = {q.id: q for q in session.query(CanonicalQuestion)
                 .filter(CanonicalQuestion.id.in_(qids)).all()} if qids else {}
    by_subject: dict[str, dict] = {}
    for a in attempts:
        q = questions.get(a.question_id)
        if q is None:
            continue
        b = by_subject.setdefault(q.subject, {"attempted": 0, "correct": 0})
        b["attempted"] += 1
        b["correct"] += 1 if a.is_correct else 0
    mastery = session.query(LearningTopicMastery).filter_by(
        student_id=student_id).all()
    weak = [{"topic": m.topic_id, "accuracy": m.accuracy,
             "practiced": m.times_practiced}
            for m in sorted(mastery, key=lambda m: m.accuracy)
            if m.times_practiced >= 3 and m.accuracy < 0.6]
    recent = [{"question_id": a.question_id, "correct": a.is_correct,
               "at": a.created_at.isoformat() if a.created_at else ""}
              for a in attempts[-10:]]
    return {
        "practice_completed": len(attempts),
        "subject_performance": by_subject,
        "weak_areas": weak,
        "recent_activity": recent,
        "recommended_next_steps": [
            f"Practice {w['topic']} ({round(w['accuracy'] * 100)}% accuracy)"
            for w in weak[:3]],
    }
