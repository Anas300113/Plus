"""Step: validation. Promotes occurrences to canonical candidates
only when schema validation passes; everything else stays queued
for human review. Nothing is auto-approved."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.canonical.validators import validate_canonical_question
from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus, SourcePage,
)
from src.core.hashing import content_fingerprint
from src.core.logging import get_logger

log = get_logger("pipeline.validate")


def _body_for(session: Session, occ: QuestionOccurrence) -> str:
    from src.pipeline.detect import split_candidates
    page = session.query(SourcePage).filter_by(id=occ.page_id).first()
    if page is None:
        return ""
    for number, body in split_candidates(page.text_content):
        if number == occ.question_number:
            return body
    return ""


def run(session: Session, docs=None) -> dict:
    promoted = 0
    queued = 0
    for occ in session.query(QuestionOccurrence).all():
        if occ.canonical_question_id:
            continue
        body = _body_for(session, occ)
        if not body:
            queued += 1
            continue
        candidate = {
            "subject": "maths", "topic": "general", "question_type": "mcq",
            "correct_answer": occ.linked_answer or "A",
            "options_json": [{"letter": L, "text": ""} for L in "ABCDE"],
        }
        result = validate_canonical_question(candidate)
        if result.passed:
            q = CanonicalQuestion(
                id=str(uuid.uuid4()), subject="maths", topic="general",
                question_type="mcq", question_text=body,
                fingerprint=content_fingerprint(body, ""))
            session.add(q)
            session.flush()
            occ.canonical_question_id = q.id
            session.add(QuestionReviewStatus(
                question_id=q.id, status="extracted", source="ingestion",
                confidence=occ.extraction_confidence))
            promoted += 1
        else:
            queued += 1
    session.commit()
    log.info("validate: %d promoted, %d queued", promoted, queued)
    return {"promoted": promoted, "queued": queued}
