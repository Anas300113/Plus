"""Bulk import reference banks through adapters.
Each file becomes a SourceDocument (rights=licensed, MIT); each
record becomes a CanonicalQuestion + QuestionOccurrence + review row
(status=validation_required). Fingerprint dedup is global."""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from src.canonical.validators import validate_canonical_question
from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, get_engine, get_session_factory, init_db,
)
from src.core.hashing import content_fingerprint, sha256_file
from src.core.logging import get_logger
from src.source.adapters.prep_adapter import PrepAdapter
from src.source.adapters.tutor_adapter import TutorAdapter

log = get_logger("import_reference")


def _doc_for(session, repo_name: str, repo_url: str, path: Path, batch: str):
    sha = sha256_file(path)
    doc = (session.query(SourceDocument)
           .filter_by(repo_name=repo_name, source_path=path.name).first())
    if doc is None:
        doc = SourceDocument(id=str(uuid.uuid4()), repo_name=repo_name,
                             repo_url=repo_url, source_path=path.name,
                             file_sha256=sha, file_size=path.stat().st_size,
                             file_type="json", rights_status="licensed",
                             rights_note="MIT-licensed reference bank",
                             ingestion_batch=batch)
        session.add(doc)
        session.commit()
    return doc


def import_file(session, path: Path, adapter, repo_name: str, repo_url: str,
                batch: str) -> dict:
    doc = _doc_for(session, repo_name, repo_url, path, batch)
    records = json.loads(path.read_text(encoding="utf-8"))
    stats = {"total": len(records), "imported": 0, "invalid": 0, "dupes": 0}
    for ext in records:
        canon = adapter.to_canonical(ext)
        result = validate_canonical_question(canon)
        if not result.passed:
            stats["invalid"] += 1
            continue
        fp = content_fingerprint(canon.get("question_text", ""),
                                 canon.get("correct_answer", ""))
        if session.query(CanonicalQuestion).filter_by(fingerprint=fp).first():
            stats["dupes"] += 1
            continue
        q = CanonicalQuestion(
            id=str(uuid.uuid4()), subject=canon["subject"],
            topic=canon.get("topic", "general"),
            subtopic=canon.get("subtopic", ""),
            question_type=canon.get("question_type", "mcq"),
            difficulty=canon.get("difficulty"),
            question_text=canon.get("question_text", ""),
            context=canon.get("context", ""),
            correct_answer=canon.get("correct_answer", ""),
            options_json=canon.get("options_json"),
            explanation=canon.get("explanation", ""),
            worked_solution=canon.get("worked_solution", ""),
            hint=canon.get("hint", ""),
            exam_board=canon.get("exam_board", ""),
            region=canon.get("region", ""),
            fingerprint=fp)
        session.add(q)
        session.flush()
        session.add(QuestionOccurrence(
            id=str(uuid.uuid4()), canonical_question_id=q.id,
            document_id=doc.id, page_id=doc.id,
            question_number=canon.get("source_question_id", ""),
            extraction_run=batch, extraction_version="adapter-0.1.0",
            extraction_confidence=0.8))
        session.add(QuestionReviewStatus(
            question_id=q.id, status="validation_required",
            source=f"adapter:{repo_name}", confidence=0.8))
        stats["imported"] += 1
    session.commit()
    log.info("imported %s: %s", path.name, stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Import reference banks via adapters")
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--tutor-json", default=None)
    ap.add_argument("--prep-dir", default=None)
    ap.add_argument("--batch", default="ref-001")
    args = ap.parse_args()
    engine = get_engine(args.db)
    init_db(engine)
    session = get_session_factory(engine)()
    total = {}
    if args.tutor_json:
        total["tutor"] = import_file(
            session, Path(args.tutor_json), TutorAdapter(),
            "11plus-tutor", "https://github.com/jhammant/11plus-tutor", args.batch)
    if args.prep_dir:
        prep_stats = {}
        for p in sorted(Path(args.prep_dir).glob("*.json")):
            prep_stats[p.name] = import_file(
                session, p, PrepAdapter(), "11plus-prep",
                "https://github.com/SahirVhora/11plus-prep", args.batch)
        total["prep"] = prep_stats
    print(total)


if __name__ == "__main__":
    main()
