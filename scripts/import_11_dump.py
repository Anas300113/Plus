"""Import the 11-dump repository as a review-gated reference corpus.

This importer intentionally does not approve or publish copied questions. The
dump contains third-party PDFs and has no licence manifest. It inventories
files, extracts page text, preserves source provenance, detects question
occurrences, links same-document answer keys where possible, and promotes only
schema-valid candidates to ``validation_required``. A reviewer must confirm
rights, answer, explanation, topic, and quality before publication.
"""
from __future__ import annotations

import argparse
import re
import uuid
from pathlib import Path

from src.core.config import load_taxonomy
from src.core.database import (
    CanonicalQuestion, SourceDocument, QuestionOccurrence,
    QuestionReviewStatus, get_engine, get_session_factory, init_db,
)
from src.core.hashing import sha256_file
from src.pipeline import classify, detect, extract, link, validate
from src.source.inventory import classify_file

REPO_NAME = "11-dump"
REPO_URL = "https://github.com/Anas300113/11-dump"
COMMIT = "134922d"
BATCH = "11-dump-2026-10-29"

# Never treat an external dump as licensed merely because it is on GitHub.
REFERENCE_ONLY_NOTE = (
    "Imported from 11-dump without a licence or permission manifest. "
    "Reference-only until rights are verified by an authorised reviewer."
)


def inventory_dump(session, root: Path) -> list[SourceDocument]:
    docs: list[SourceDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = str(path.relative_to(root))
        sha = sha256_file(path)
        doc = session.query(SourceDocument).filter_by(
            repo_name=REPO_NAME, source_path=rel).first()
        if doc is None:
            doc = SourceDocument(
                id=str(uuid.uuid4()), repo_name=REPO_NAME,
                repo_url=REPO_URL, source_path=rel,
                rights_status="reference_only", rights_note=REFERENCE_ONLY_NOTE,
                ingestion_batch=BATCH, ingestion_version="1.0.0",
                commit_sha=COMMIT)
            session.add(doc)
        doc.file_sha256 = sha
        doc.file_size = path.stat().st_size
        doc.file_type = classify_file(path)
        doc.rights_status = "reference_only"
        doc.rights_note = REFERENCE_ONLY_NOTE
        docs.append(doc)
    session.commit()
    return docs


def _subject(path: str) -> str:
    text = path.lower()
    if "non-verbal" in text or "nonverbal" in text or "nvr" in text:
        return "non_verbal_reasoning"
    if "verbal" in text or re.search(r"(^|[/ ])vr([/ ._-]|$)", text):
        return "verbal_reasoning"
    if "english" in text or "comprehension" in text or "writing" in text:
        return "english"
    if "math" in text or "ks2" in text or "number" in text or "fraction" in text:
        return "maths"
    return ""


def _topic(subject: str, haystack: str) -> str:
    text = haystack.lower()
    rules = {
        "maths": [
            ("fraction", "maths-fractions"), ("percent", "maths-percentages"),
            ("ratio", "maths-ratio"), ("algebra", "maths-algebra"),
            ("sequence", "maths-sequences"), ("graph", "maths-graphs"),
            ("table", "maths-tables"), ("geometry", "maths-geometry"),
            ("angle", "maths-geometry"), ("time", "maths-time"),
            ("money", "maths-money"), ("number", "maths-number"),
            ("whole-number", "maths-number"), ("arithmetic", "maths-arithmetic"),
        ],
        "english": [
            ("comprehension", "eng-comprehension"), ("grammar", "eng-grammar"),
            ("punctuation", "eng-punctuation"), ("spelling", "eng-spelling"),
            ("vocabulary", "eng-vocabulary"), ("cloze", "eng-cloze"),
            ("creative", "eng-creative-writing"), ("technical", "eng-technical-english"),
        ],
        "verbal_reasoning": [
            ("anagram", "vr-word-construction"), ("alphabetical", "vr-letter-sequences"),
            ("sequence", "vr-letter-sequences"), ("hidden", "vr-hidden-words"),
            ("code", "vr-codes"), ("synonym", "vr-synonyms"),
            ("antonym", "vr-antonyms"), ("analogy", "vr-analogies"),
            ("classification", "vr-classification"), ("odd-one", "vr-odd-one-out"),
        ],
        "non_verbal_reasoning": [
            ("matrix", "nvr-matrices"), ("sequence", "nvr-shape-sequences"),
            ("rotation", "nvr-rotations"), ("reflect", "nvr-reflections"),
            ("fold", "nvr-paper-folding"), ("cube", "nvr-cube-nets"),
            ("analogy", "nvr-analogies"), ("odd", "nvr-odd-one-out"),
        ],
    }
    for needle, topic in rules.get(subject, []):
        if needle in text:
            return topic
    return ""


def apply_subject_suggestions(session) -> int:
    docs = {d.id: d for d in session.query(SourceDocument).filter_by(repo_name=REPO_NAME)}
    changed = 0
    for occ in session.query(QuestionOccurrence).all():
        if not occ.canonical_question_id:
            continue
        doc = docs.get(occ.document_id)
        q = session.get(CanonicalQuestion, occ.canonical_question_id)
        if not doc or not q:
            continue
        subject = _subject(doc.source_path)
        if subject and q.subject != subject:
            q.subject = subject
            changed += 1
        if subject and q.subject_id != subject:
            q.subject_id = subject
            changed += 1
        # Use source naming only for automatic topic suggestions. Extracted
        # worksheet text contains many layout words such as "table" and
        # "time" that are not reliable evidence of the question skill.
        topic = _topic(subject, doc.source_path)
        status = session.get(QuestionReviewStatus, q.id)
        if status and status.status == "validation_required" and not topic:
            if q.topic != "general":
                q.topic = "general"
                changed += 1
        if topic and q.topic != topic:
            q.topic = topic
            q.topic_id = topic
            changed += 1
        elif not topic and status and status.status == "validation_required":
            if q.topic_id is not None:
                q.topic_id = None
                changed += 1
        # Never let the generic validator's placeholder answer/explanation look
        # publishable. The occurrence remains useful evidence for reviewers.
        if status:
            if q.validation_status != status.status:
                q.validation_status = status.status
                changed += 1
            status.status = "validation_required"
            status.source = REPO_NAME
            status.reason = REFERENCE_ONLY_NOTE
            status.reviewer = ""
    session.commit()
    return changed


def run(db_url: str, root: Path, reclassify_only: bool = False) -> dict:
    engine = get_engine(db_url)
    init_db(engine)
    session = get_session_factory(engine)()
    try:
        docs = inventory_dump(session, root)
        pdf_docs = [d for d in docs if d.file_type == "pdf"]
        if reclassify_only:
            changed = apply_subject_suggestions(session)
            return {"files": len(docs), "reclassified": changed,
                    "note": REFERENCE_ONLY_NOTE}
        extract.run_page_extract(session, pdf_docs, root)
        extract.run_text_extract(session, pdf_docs, root)
        detect_stats = detect.run(session, pdf_docs, version="1.0.0", batch=BATCH)
        link_stats = link.run(session, pdf_docs)
        classify_stats = classify.run(session, pdf_docs)
        validate_stats = validate.run(session, pdf_docs)
        changed = apply_subject_suggestions(session)
        return {
            "files": len(docs), "pdfs": len(pdf_docs),
            "detect": detect_stats, "link": link_stats,
            "classify": classify_stats, "validate": validate_stats,
            "subject_suggestions_applied": changed,
            "note": REFERENCE_ONLY_NOTE,
        }
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", default="/home/ubuntu/11-dump")
    parser.add_argument("--db", default="sqlite:///./elevenplus.db")
    parser.add_argument("--reclassify-only", action="store_true")
    args = parser.parse_args()
    print(run(args.db, Path(args.dump).resolve(), args.reclassify_only))


if __name__ == "__main__":
    main()
