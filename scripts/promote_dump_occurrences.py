"""Promote extracted dump occurrences into canonical, review-gated records.

This never approves content. It creates a canonical record when a usable prompt
was extracted, preserving missing answers and incomplete options explicitly.
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, SourcePage, get_engine, get_session_factory, init_db,
)
from src.core.hashing import content_fingerprint
from src.pipeline.detect import split_candidates
from scripts.import_11_dump import _subject, _topic


def body_for(page: SourcePage | None, number: str) -> str:
    if page is None:
        return ""
    for n, body in split_candidates(page.text_content or ""):
        if n == number:
            return body.strip()
    return ""


def promote(db_url: str) -> dict:
    engine = get_engine(db_url)
    init_db(engine)
    session = get_session_factory(engine)()
    created = updated = skipped = 0
    try:
        docs = {d.id: d for d in session.query(SourceDocument).filter_by(repo_name="11-dump")}
        for occ in session.query(QuestionOccurrence).order_by(QuestionOccurrence.id):
            doc = docs.get(occ.document_id)
            if doc is None:
                continue
            page = session.get(SourcePage, occ.page_id) if occ.page_id else None
            body = body_for(page, occ.question_number)
            if not body:
                skipped += 1
                continue
            options = [
                {"letter": str(o.get("letter") or o.get("id") or "").upper(),
                 "text": str(o.get("text") or "")}
                for o in (occ.options_json or []) if isinstance(o, dict)
            ]
            options = [o for o in options if o["letter"]]
            subject = _subject(doc.source_path) or "maths"
            topic = _topic(subject, doc.source_path) or "general"
            qtype = "mcq" if len(options) >= 2 and any(o["text"] for o in options) else "unknown_custom"
            answer = occ.linked_answer or ""
            answer_status = "candidate" if answer else "missing"
            q = (session.get(CanonicalQuestion, occ.canonical_question_id)
                 if occ.canonical_question_id else None)
            if q is None:
                q = CanonicalQuestion(
                    id=str(uuid.uuid4()), schema_version="1.1.0",
                    subject=subject, subject_id=subject, topic=topic,
                    topic_id=topic if topic != "general" else None,
                    skill_id=None, subtopic="",
                    question_type=qtype, difficulty=None,
                    skill_ids=[], question_text=body,
                    prompt_json={"text": body}, instructions="", context="",
                    correct_answer=answer,
                    answer_json={"type": "single_choice" if qtype == "mcq" else "unknown",
                                 "value": answer},
                    options_json=options or None, explanation="",
                    explanation_status="missing", answer_status=answer_status,
                    assets_json=[], source_id=doc.id,
                    validation_status="validation_required",
                    fingerprint=content_fingerprint(body, answer),
                )
                session.add(q)
                session.flush()
                occ.canonical_question_id = q.id
                session.add(QuestionReviewStatus(
                    question_id=q.id, status="validation_required",
                    source="dump-promotion", confidence=occ.extraction_confidence,
                ))
                created += 1
            else:
                # A second linker pass may discover an answer after the first
                # validation pass. Update only unapproved reference records.
                if q.validation_status != "approved" and answer and q.correct_answer != answer:
                    q.correct_answer = answer
                    q.answer_json = {"type": "single_choice" if q.question_type == "mcq" else "unknown",
                                     "value": answer}
                    q.answer_status = "candidate"
                    updated += 1
        session.commit()
        return {"created": created, "updated": updated, "skipped_without_prompt": skipped}
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="sqlite:///./elevenplus.db")
    args = parser.parse_args()
    print(promote(args.db))


if __name__ == "__main__":
    main()
