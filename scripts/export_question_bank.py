"""Export a large normalized JSONL question dataset.

Canonical questions retain their reviewed fields. Unpromoted dump occurrences
are exported as review records with status ``discovered`` or
``validation_required``; they are not silently treated as approved content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceAsset, SourceDocument, SourcePage, get_engine, get_session_factory,
    init_db,
)
from src.pipeline.detect import split_candidates
from scripts.import_11_dump import _subject, _topic

SCHEMA_VERSION = "1.1.0"


def _options(options: list | None) -> list[dict]:
    return [{"id": str(o.get("letter") or o.get("id") or ""),
             "text": str(o.get("text") or "")}
            for o in (options or []) if isinstance(o, dict)]


def _body(page: SourcePage | None, number: str) -> str:
    if not page:
        return ""
    for n, text in split_candidates(page.text_content or ""):
        if n == number:
            return text
    return (page.text_content or "").strip()


def _assets(session, document_id: str, page_id: str | None) -> list[dict]:
    return [{"asset_id": a.id, "storage_path": a.storage_path,
             "mime_type": a.mime_type}
            for a in session.query(SourceAsset).filter_by(
                document_id=document_id, page_id=page_id).all()]


def _record(session, occ: QuestionOccurrence, q: CanonicalQuestion | None,
            doc: SourceDocument, page: SourcePage | None,
            review: QuestionReviewStatus | None) -> dict:
    if q is not None:
        subject = q.subject_id or q.subject
        topic = q.topic_id or q.topic
        skill = q.skill_id or ((q.skill_ids or [None])[0])
        prompt = q.prompt_json or {"text": q.question_text or "",
                                   "instructions": q.instructions or "",
                                   "context": q.context or ""}
        options = _options(q.options_json)
        answer_value = q.correct_answer or ""
        answer_type = ((q.answer_json or {}).get("type")
                       if q.answer_json else
                       ("single_choice" if options else "text"))
        explanation_text = q.explanation or q.worked_solution or ""
        status = q.validation_status or (review.status if review else "validation_required")
        difficulty = q.difficulty
        assets = q.assets_json if q.assets_json is not None else _assets(session, doc.id, occ.page_id)
        answer_verified = q.answer_status == "verified"
        explanation_verified = q.explanation_status == "verified"
    else:
        subject = _subject(doc.source_path) or "maths"
        topic = _topic(subject, doc.source_path) or None
        skill = None
        body = _body(page, occ.question_number)
        prompt = {"text": body}
        options = _options(occ.options_json)
        answer_value = occ.linked_answer or ""
        answer_type = "single_choice" if options else "unknown"
        explanation_text = ""
        status = review.status if review else "discovered"
        difficulty = None
        assets = _assets(session, doc.id, occ.page_id)
        answer_verified = False
        explanation_verified = False
    return {
        "schema_version": SCHEMA_VERSION,
        "id": q.id if q is not None else f"dump-occurrence-{occ.id}",
        "subject_id": subject,
        "topic_id": topic,
        "skill_id": skill,
        "question_type": q.question_type if q is not None else ("mcq" if options else "unknown_custom"),
        "prompt": prompt,
        "options": options,
        "answer": {"type": answer_type, "value": answer_value},
        "explanation": {"text": explanation_text,
                        "verified": explanation_verified},
        "difficulty": difficulty,
        "assets": assets,
        "provenance": {
            "source_id": doc.id, "source_path": doc.source_path,
            "page": page.page_number if page else None,
            "source_question_id": occ.question_number,
            "licence": doc.rights_status,
        },
        "validation": {
            "status": status, "answer_verified": answer_verified,
            "explanation_verified": explanation_verified,
        },
    }


def export(db_url: str, output: Path) -> dict:
    engine = get_engine(db_url)
    init_db(engine)
    session = get_session_factory(engine)()
    try:
        docs = {d.id: d for d in session.query(SourceDocument).all()}
        pages = {p.id: p for p in session.query(SourcePage).all()}
        questions = {q.id: q for q in session.query(CanonicalQuestion).all()}
        reviews = {r.question_id: r for r in session.query(QuestionReviewStatus).all()}
        lines: list[str] = []
        seen: set[str] = set()
        for occ in session.query(QuestionOccurrence).order_by(QuestionOccurrence.id):
            doc = docs.get(occ.document_id)
            if doc is None:
                continue
            q = questions.get(occ.canonical_question_id) if occ.canonical_question_id else None
            record = _record(session, occ, q, doc, pages.get(occ.page_id),
                             reviews.get(q.id) if q else None)
            if record["id"] in seen:
                continue
            seen.add(record["id"])
            lines.append(json.dumps(record, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":")))
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = ("\n".join(lines) + "\n") if lines else ""
        output.write_text(payload, encoding="utf-8")
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        manifest = {"schema_version": SCHEMA_VERSION, "record_count": len(lines),
                    "sha256": digest, "approved": sum('"status":"approved"' in line for line in lines),
                    "reference_only_or_pending": len(lines) - sum('"status":"approved"' in line for line in lines)}
        output.with_suffix(output.suffix + ".manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="sqlite:///./elevenplus.db")
    parser.add_argument("--out", default="data/exports/question-bank.jsonl")
    args = parser.parse_args()
    print(export(args.db, Path(args.out)))


if __name__ == "__main__":
    main()
