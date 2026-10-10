"""Trustworthy review/approval service.

Single authority for moving a canonical question toward the student-facing
bank. It enforces the Question Bank v1 contract:

* A question is NEVER approved merely because ``correct_answer`` is set.
* Approval requires: usable text, sufficient page-level provenance,
  question-type specific validity (MCQ: ordered, distinguishable options
  whose label maps unambiguously to the verified answer), a **verified**
  answer, and a **verified** explanation.
* Every status change and every edit is appended to ``QuestionReviewEvent``
  (reviewer, UTC timestamp, decision, reason). The review trail is never
  overwritten.

Editing a verified answer or explanation resets that field to ``candidate``
so a later edit can never silently keep a stale verification.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewEvent,
    QuestionReviewStatus,
)

REVIEWABLE = ("discovered", "extracted", "ai_reviewed", "validation_required")
APPROVED = "approved"
REJECTED = "rejected"
VERIFIED = "verified"
CANDIDATE = "candidate"
MISSING = "missing"


class ApprovalContractError(ValueError):
    """Raised when a requested approval violates the trustworthy-question
    contract (unmet requirements). Distinct from a missing-row ValueError so
    callers can map it to a 400 rather than a 404."""
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_event(session: Session, question_id: str, action: str,
               reviewer: str, from_status: str = "", to_status: str = "",
               reason: str = "") -> None:
    session.add(QuestionReviewEvent(
        id=str(uuid.uuid4()), question_id=question_id, action=action,
        reviewer=reviewer, from_status=from_status, to_status=to_status,
        reason=reason, created_at=_now()))


def review_queue(session: Session, limit: int = 50):
    return (
        session.query(CanonicalQuestion, QuestionReviewStatus)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(QuestionReviewStatus.status.in_(REVIEWABLE))
        .order_by(CanonicalQuestion.id)
        .limit(limit).all()
    )


# ---- contract checks -------------------------------------------------------


def _occurrences(session: Session, question_id: str):
    return (session.query(QuestionOccurrence)
            .filter_by(canonical_question_id=question_id).all())


def has_provenance(session: Session, question_id: str) -> bool:
    """True when at least one occurrence pins a document AND a page."""
    for occ in _occurrences(session, question_id):
        if occ.document_id and occ.page_id:
            return True
    return False


def _looks_mcq(question: CanonicalQuestion) -> bool:
    qt = (question.question_type or "").lower()
    return ("mcq" in qt or "multiple" in qt or "choice" in qt
            or bool(question.options_json))


def option_labels(question: CanonicalQuestion) -> list[str]:
    opts = question.options_json or []
    labels = []
    for opt in opts:
        if isinstance(opt, dict):
            # Extraction stores the label under "letter"; accept "label"/"key"
            # too so adapters with other keys still resolve.
            labels.append(str(opt.get("letter") or opt.get("label")
                               or opt.get("key") or "").strip())
        else:
            labels.append(str(opt).strip())
    return [l for l in labels if l]


def approval_blockers(session: Session, question_id: str) -> list[str]:
    """Unmet requirements that block approval. Empty list == eligible.

    A question is NEVER approved merely because ``correct_answer`` is set.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    blockers: list[str] = []
    if not (q.question_text or "").strip():
        blockers.append("question_text is empty")
    if not has_provenance(session, question_id):
        blockers.append("no occurrence with document+page provenance")
    if _looks_mcq(q):
        labels = option_labels(q)
        if len(labels) < 2:
            blockers.append("mcq requires at least two labelled options")
        if len(set(l.upper() for l in labels)) != len(labels):
            blockers.append("option labels are not distinguishable")
        ans = (q.correct_answer or "").strip()
        if not ans:
            blockers.append("mcq requires a correct_answer")
        elif labels and ans.upper() not in {l.upper() for l in labels}:
            blockers.append("correct_answer does not map to a valid option")
    if q.answer_status != VERIFIED:
        blockers.append(f"answer_status is '{q.answer_status}', not verified")
    if q.explanation_status != VERIFIED:
        blockers.append(
            f"explanation_status is '{q.explanation_status}', not verified")
    return blockers


# ---- mutation --------------------------------------------------------------


def set_status(session: Session, question_id: str, status: str,
               reviewer: str = "cli", reason: str = "") -> None:
    row = session.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    if row is None:
        raise ValueError(f"no review row for {question_id}")
    if status == APPROVED:
        blockers = approval_blockers(session, question_id)
        if blockers:
            raise ApprovalContractError(
                "cannot approve; unmet requirements: " + "; ".join(blockers))
    from_status = row.status
    row.status = status
    row.reviewer = reviewer
    row.decision = status
    row.reason = reason
    row.updated_at = _now()
    action = "approve" if status == APPROVED else (
        "reject" if status == REJECTED else "status")
    _log_event(session, question_id, action, reviewer,
               from_status=from_status, to_status=status, reason=reason)
    _log_event(session, question_id, action, reviewer,
               from_status=from_status, to_status=status, reason=reason)
    session.commit()


def verify_answer(session: Session, question_id: str, reviewer: str,
                  evidence: str = "") -> None:
    """Record that a human verified the answer against source evidence."""
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    if not (q.correct_answer or "").strip():
        raise ValueError(f"question {question_id} has no answer to verify")
    q.answer_status = VERIFIED
    if evidence:
        q.answer_evidence = evidence
    q.updated_at = _now()
    session.commit()
    _log_event(session, question_id, "verify_answer", reviewer,
               to_status=VERIFIED, reason=evidence)


def verify_explanation(session: Session, question_id: str, reviewer: str,
                       note: str = "") -> None:
    """Record that a human verified the explanation supports the answer."""
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    if not (q.explanation or "").strip():
        raise ValueError(f"question {question_id} has no explanation to verify")
    q.explanation_status = VERIFIED
    q.updated_at = _now()
    session.commit()
    _log_event(session, question_id, "verify_explanation", reviewer,
               to_status=VERIFIED, reason=note)


def edit_question(session: Session, question_id: str, reviewer: str,
                  question_text: str | None = None,
                  correct_answer: str | None = None,
                  explanation: str | None = None,
                  options_json: list | None = None) -> None:
    """Apply a reviewer edit while preserving the original extraction.

    Editing a verified answer or explanation (or the MCQ option set an
    answer maps to) RESETS that field to ``candidate`` so a stale
    ``verified`` can never survive an edit. The original pipeline-extracted
    text is preserved in the audit ``reason`` so nothing is destroyed.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    notes: list[str] = []
    if question_text is not None and question_text != q.question_text:
        notes.append(f"question_text was {q.question_text!r}")
        q.question_text = question_text
    if correct_answer is not None and correct_answer != q.correct_answer:
        notes.append(f"correct_answer was {q.correct_answer!r}")
        q.correct_answer = correct_answer
        if q.answer_status == VERIFIED:
            q.answer_status = CANDIDATE  # edit invalidates verification
    if explanation is not None and explanation != q.explanation:
        notes.append(f"explanation was {q.explanation!r}")
        q.explanation = explanation
        if q.explanation_status == VERIFIED:
            q.explanation_status = CANDIDATE
    if options_json is not None and options_json != q.options_json:
        notes.append(f"options_json was {q.options_json!r}")
        q.options_json = options_json
        if q.answer_status == VERIFIED:
            q.answer_status = CANDIDATE  # option->answer mapping may be stale
    q.updated_at = _now()
    session.commit()
    _log_event(session, question_id, "edit", reviewer,
               reason="; ".join(notes) if notes else "no-op")
    session.commit()
