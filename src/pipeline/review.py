"""Review queue helpers: list items needing human review, approve
or reject them. Approval is the only path to student-facing data."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import CanonicalQuestion, QuestionReviewStatus

REVIEWABLE = ("extracted", "ai_reviewed", "validation_required")


def review_queue(session: Session, limit: int = 50):
    return (
        session.query(CanonicalQuestion, QuestionReviewStatus)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(QuestionReviewStatus.status.in_(REVIEWABLE))
        .limit(limit).all()
    )


def set_status(session: Session, question_id: str, status: str,
               reviewer: str = "cli") -> None:
    row = session.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    if row is None:
        raise ValueError(f"no review row for {question_id}")
    row.status = status
    session.commit()
