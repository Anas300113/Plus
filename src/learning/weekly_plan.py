"""Deterministic weekly 11+ learning plan.

Mon-Thu teach one subject each day. Friday is a balanced 40-question check
when possible, or a weak-topic repair test when the learner has a measured gap.
Only approved questions are selectable for a learner session.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, CurriculumCommonMistake, CurriculumLesson,
    CurriculumStrategy, CurriculumWorkedExample, QuestionReviewStatus,
)
from src.learning.queries import approved_question_ids
from src.learning.statistics import student_statistics

DAY_SUBJECTS = {0: "maths", 1: "english", 2: "non_verbal_reasoning", 3: "verbal_reasoning"}
SUBJECT_LABELS = {
    "maths": "Maths", "english": "English",
    "non_verbal_reasoning": "NVR", "verbal_reasoning": "VR",
}


def _slug_subject(value: str) -> str:
    return value.replace("_", "-")


def _humanise(value: str) -> str:
    return " ".join(word.capitalize() for word in (value or "").replace("_", "-").split("-"))


def _topic_options(db: Session, subject: str) -> list[tuple[str, int]]:
    rows = (db.query(CanonicalQuestion.topic, func.count(CanonicalQuestion.id))
            .join(QuestionReviewStatus, QuestionReviewStatus.question_id == CanonicalQuestion.id)
            .filter(CanonicalQuestion.subject == subject,
                    QuestionReviewStatus.status == "approved")
            .group_by(CanonicalQuestion.topic).order_by(CanonicalQuestion.topic).all())
    return [(topic, int(count)) for topic, count in rows]


def _lesson(db: Session, topic_id: str | None) -> dict:
    if not topic_id or topic_id == "general":
        return {"topic_id": topic_id or "", "title": "Quick concept overview",
                "overview": "Read the question carefully, identify the rule being tested, and work one step at a time.",
                "strategy": "Underline the important information, try a method, then check that your answer is sensible.",
                "worked_example": "Use the first question as a worked example: explain why the correct answer follows from the rule.",
                "common_mistakes": []}
    lesson = db.query(CurriculumLesson).filter_by(topic_id=topic_id).order_by(CurriculumLesson.display_order).first()
    strategy = db.query(CurriculumStrategy).filter_by(topic_id=topic_id).order_by(CurriculumStrategy.display_order).first()
    example = db.query(CurriculumWorkedExample).filter_by(topic_id=topic_id).first()
    mistakes = db.query(CurriculumCommonMistake).filter_by(topic_id=topic_id).limit(3).all()
    return {
        "topic_id": topic_id,
        "title": lesson.title if lesson else _humanise(topic_id),
        "overview": lesson.content_markdown if lesson else "Learn the core rule, then apply it to a simple example before attempting the test.",
        "strategy": strategy.content_markdown if strategy else "Identify the rule, apply it carefully, and check your result.",
        "worked_example": example.content_markdown if example else "Work through the first question slowly and explain each step.",
        "common_mistakes": [m.explanation_markdown or m.mistake_text for m in mistakes],
    }


def _weak_topic(db: Session, student_id: str, subject: str | None = None) -> tuple[str, str, float] | None:
    weak = student_statistics(db, student_id, days=30).get("weak_topics", [])
    for row in weak:
        topic = row.get("topic", "")
        q = (db.query(CanonicalQuestion).filter_by(topic=topic)
             .join(QuestionReviewStatus, QuestionReviewStatus.question_id == CanonicalQuestion.id)
             .filter(QuestionReviewStatus.status == "approved").first())
        if q and (subject is None or q.subject == subject):
            return q.subject, topic, float(row.get("accuracy", 0.0))
    return None


def weekly_plan(db: Session, student_id: str, on_date: date | None = None) -> dict:
    day = on_date or date.today()
    weekday = day.weekday()
    if weekday in DAY_SUBJECTS:
        subject = DAY_SUBJECTS[weekday]
        choices = _topic_options(db, subject)
        weak = _weak_topic(db, student_id, subject)
        if weak:
            _, topic, accuracy = weak
            selection_reason = "weak_topic"
        elif choices:
            topic = choices[day.isocalendar().week % len(choices)][0]
            accuracy = None
            selection_reason = "curriculum_rotation"
        else:
            topic, accuracy, selection_reason = "", None, "no_approved_topic"
        topic_count = sum(n for t, n in choices if t == topic) if topic else 0
        subject_count = sum(n for _, n in choices)
        # The lesson remains topic-specific, but do not ship a one-question
        # test while a new bank is still growing. Use a same-subject set until
        # that topic has at least ten reviewed items.
        if topic_count < 10 and subject_count:
            requested, count, mode = min(10, subject_count), min(10, subject_count), "subject_review"
        else:
            requested, count, mode = 15, min(15, topic_count), "subject_topic"
        subject_ids = [subject]
    else:
        weak = _weak_topic(db, student_id)
        if weak:
            subject, topic, accuracy = weak
            topic_count = len(approved_question_ids(db, subject=subject, topic=topic, limit=15))
            subject_count = sum(n for _, n in _topic_options(db, subject))
            requested, count, mode = (min(15, subject_count), min(15, subject_count), "weak_topic_repair") if topic_count < 10 else (15, topic_count, "weak_topic_repair")
            selection_reason, subject_ids = "weak_topic", [subject]
        else:
            topic, accuracy, mode, selection_reason = "", None, "combined", "weekly_review"
            requested, subject_ids = 40, list(DAY_SUBJECTS.values())
            count = sum(len(approved_question_ids(db, subject=s, limit=10)) for s in subject_ids)
    return {
        "date": day.isoformat(), "weekday": day.strftime("%A"),
        "subject_id": _slug_subject(subject) if weekday in DAY_SUBJECTS or mode == "weak_topic_repair" else "combined",
        "subject": SUBJECT_LABELS.get(subject, "Combined") if weekday in DAY_SUBJECTS or mode == "weak_topic_repair" else "Combined",
        "topic_id": topic, "topic": _humanise(topic) if topic else "All subjects",
        "mode": mode, "selection_reason": selection_reason,
        "requested_questions": requested, "available_questions": count,
        "question_count": count, "weak_accuracy": accuracy,
        "subject_ids": [_slug_subject(s) for s in subject_ids],
        "lesson": _lesson(db, topic),
        "ready": count > 0,
    }


def question_ids_for_plan(db: Session, plan: dict) -> list[str]:
    if plan["mode"] == "combined":
        ids: list[str] = []
        for subject in DAY_SUBJECTS.values():
            ids.extend(approved_question_ids(db, subject=subject, limit=10))
        return ids
    raw_subject = plan["subject_id"].replace("-", "_")
    if plan["mode"] == "subject_review":
        return approved_question_ids(db, subject=raw_subject, limit=plan["question_count"])
    topic_ids = approved_question_ids(db, subject=raw_subject, topic=plan["topic_id"], limit=plan["question_count"])
    if plan["mode"] == "weak_topic_repair" and len(topic_ids) < min(10, plan["question_count"]):
        return approved_question_ids(db, subject=raw_subject, limit=plan["question_count"])
    return topic_ids
