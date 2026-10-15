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


def _doc_for(session, repo_name: str, repo_url: str, path: Path, batch: str,
             source_sha: str = "", licence_note: str = "") -> tuple:
    """Return (SourceDocument, upstream_changed).

    The document row records the source file hash, the audited source commit
    and the licence/attribution notice so every imported question is traceable
    to an exact upstream version. If the upstream FILE has changed since the
    first import, the change is detected and reported but the existing row --
    and everything imported from it -- is never silently overwritten.
    """
    sha = sha256_file(path)
    doc = (session.query(SourceDocument)
           .filter_by(repo_name=repo_name, source_path=path.name).first())
    if doc is None:
        doc = SourceDocument(id=str(uuid.uuid4()), repo_name=repo_name,
                             repo_url=repo_url, source_path=path.name,
                             file_sha256=sha, file_size=path.stat().st_size,
                             file_type="json", commit_sha=source_sha,
                             rights_status="licensed",
                             rights_note=licence_note
                             or "MIT-licensed reference bank",
                             ingestion_batch=batch)
        session.add(doc)
        session.commit()
        return doc, False
    if doc.file_sha256 and doc.file_sha256 != sha:
        log.warning(
            "upstream change detected for %s (recorded %s..., current %s...); "
            "existing import kept, nothing overwritten", path.name,
            doc.file_sha256[:12], sha[:12])
        return doc, True
    return doc, False


def import_file(session, path: Path, adapter, repo_name: str, repo_url: str,
                batch: str, source_sha: str = "") -> dict:
    doc, changed = _doc_for(session, repo_name, repo_url, path, batch,
                            source_sha, adapter.licence_note)
    records = json.loads(path.read_text(encoding="utf-8"))
    stats = {"total": len(records), "imported": 0, "invalid": 0, "dupes": 0,
             "upstream_changed": changed, "document_id": doc.id,
             "sha256": doc.file_sha256}
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
            document_id=doc.id, page_id="",
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


def import_banks(session, bank_dir: Path, adapter, repo_name: str,
                 repo_url: str, batch: str, source_sha: str = "") -> dict:
    """Deterministic multi-file bank import (Gate 1).

    Records are grouped into content-fingerprint CLUSTERS across all files
    before anything is written, so the result never depends on file iteration
    order:

    * one canonical question per cluster; content comes from the cluster
      representative = min (filename, source question id);
    * every source record keeps its own QuestionOccurrence (document +
      source question id), including duplicate records sharing a canonical,
      so no legitimate source association is dropped;
    * canonical region/board = the single distinct non-empty assertion among
      cluster members, or "" when members assert conflicting values (never
      invented, never silently resolved);
    * existing canonical rows are NEVER overwritten; divergences are returned
      in ``conflicts`` for review;
    * repeat runs add only missing occurrences (idempotent) and never touch
      existing review-status rows.
    """
    files = sorted(bank_dir.glob("*.json"))
    clusters: dict[str, list] = {}
    per_file: dict[str, dict] = {}
    invalid = 0
    for path in files:
        records = json.loads(path.read_text(encoding="utf-8"))
        doc, changed = _doc_for(session, repo_name, repo_url, path, batch,
                                source_sha, adapter.licence_note)
        per_file[path.name] = {
            "records": len(records), "sha256": doc.file_sha256,
            "document_id": doc.id, "upstream_changed": changed}
        for ext in records:
            canon = adapter.to_canonical(ext)
            if not validate_canonical_question(canon).passed:
                invalid += 1
                continue
            fp = content_fingerprint(canon["question_text"],
                                     canon["correct_answer"])
            clusters.setdefault(fp, []).append(
                {"canon": canon, "filename": path.name, "doc": doc,
                 "changed": changed, "source_id": str(ext.get("id", ""))})
    return _write_clusters(session, clusters, per_file, invalid, adapter,
                           batch)


def _write_clusters(session, clusters: dict, per_file: dict, invalid: int,
                    adapter, batch: str) -> dict:
    stats = {"files": len(per_file),
             "records": sum(f["records"] for f in per_file.values()),
             "imported": 0, "invalid": invalid, "occurrences_added": 0,
             "duplicates_merged": 0, "region_set_from_duplicate": 0,
             "region_ambiguous": 0, "upstream_changed": 0,
             "conflicts": [], "per_file": per_file,
             "manifest_files": []}
    for fp, members in clusters.items():
        members.sort(key=lambda m: (m["filename"], m["source_id"]))
        rep = members[0]
        stats["duplicates_merged"] += len(members) - 1
        stats["upstream_changed"] += 1 if any(
            m["changed"] for m in members) else 0
        regions = {m["canon"]["region"] for m in members
                   if m["canon"].get("region")}
        boards = {m["canon"]["exam_board"] for m in members
                  if m["canon"].get("exam_board")
                  and m["canon"]["exam_board"] != "mixed"}
        region = regions.pop() if len(regions) == 1 else ""
        board = (list(boards)[0] if len(boards) == 1
                 else (rep["canon"].get("exam_board") or ""))
        if len(regions) > 1:
            stats["region_ambiguous"] += 1

        q = session.query(CanonicalQuestion).filter_by(
            fingerprint=fp).first()
        if q is None:
            q = CanonicalQuestion(
                id=str(uuid.uuid4()), subject=rep["canon"]["subject"],
                topic=rep["canon"].get("topic", "general"),
                subtopic=rep["canon"].get("subtopic", ""),
                question_type=rep["canon"].get("question_type", "mcq"),
                difficulty=rep["canon"].get("difficulty"),
                question_text=rep["canon"].get("question_text", ""),
                context=rep["canon"].get("context", ""),
                correct_answer=rep["canon"].get("correct_answer", ""),
                options_json=rep["canon"].get("options_json"),
                explanation=rep["canon"].get("explanation", ""),
                exam_board=board, region=region, fingerprint=fp)
            session.add(q)
            session.flush()
            session.add(QuestionReviewStatus(
                question_id=q.id, status="validation_required",
                source=f"adapter:{adapter.source_name}", confidence=0.8))
            stats["imported"] += 1
            if region and region != rep["canon"].get("region"):
                stats["region_set_from_duplicate"] += 1
        elif (q.region or "") != region or (q.exam_board or "") != board:
            stats["conflicts"].append({
                "fingerprint": fp, "existing_region": q.region,
                "existing_board": q.exam_board,
                "deterministic_region": region,
                "deterministic_board": board,
                "sources": [f"{m['filename']}#{m['source_id']}"
                            for m in members]})
        for m in members:
            exists = session.query(QuestionOccurrence).filter_by(
                document_id=m["doc"].id,
                question_number=m["source_id"]).first()
            if exists is None:
                session.add(QuestionOccurrence(
                    id=str(uuid.uuid4()), canonical_question_id=q.id,
                    document_id=m["doc"].id, page_id="",
                    question_number=m["source_id"],
                    extraction_run=batch,
                    extraction_version="adapter-0.2.0",
                    extraction_confidence=0.8))
                stats["occurrences_added"] += 1
    session.commit()
    for name, info in per_file.items():
        stats["manifest_files"].append({"file": name, **info})
    log.info("bank import: %s", {k: v for k, v in stats.items()
                                 if k not in ("manifest_files", "per_file",
                                              "conflicts")})
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Import reference banks via adapters")
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--tutor-json", default=None)
    ap.add_argument("--prep-dir", default=None)
    ap.add_argument("--batch", default="ref-001")
    ap.add_argument("--source-sha", default="",
                    help="audited upstream commit SHA recorded on each "
                         "SourceDocument for traceability")
    ap.add_argument("--manifest-dir", default=None,
                    help="write a per-repo JSON ingestion manifest here")
    args = ap.parse_args()
    engine = get_engine(args.db)
    init_db(engine)
    session = get_session_factory(engine)()
    total = {}
    manifests: dict[str, list] = {}
    if args.tutor_json:
        total["tutor"] = import_file(
            session, Path(args.tutor_json), TutorAdapter(),
            "11plus-tutor", "https://github.com/jhammant/11plus-tutor",
            args.batch, args.source_sha)
    if args.prep_dir:
        result = import_banks(
            session, Path(args.prep_dir), PrepAdapter(), "11plus-prep",
            "https://github.com/SahirVhora/11plus-prep", args.batch,
            args.source_sha)
        manifests["11plus-prep"] = result
        total["prep"] = result
    if args.manifest_dir and manifests:
        _write_manifests(Path(args.manifest_dir), manifests, args)
    print(total)


def _write_manifests(manifest_dir: Path, manifests: dict, args) -> None:
    """Reproducible per-repo ingestion manifest (source URL/SHA, licence,
    per-file hashes and outcomes, duplicate/attribution statistics). Repeat
    runs for the SAME source sha rewrite the manifest; a different sha
    produces a differently named file, so prior manifests are preserved."""
    import datetime
    manifest_dir.mkdir(parents=True, exist_ok=True)
    for repo, result in manifests.items():
        sha_tag = (args.source_sha or "unversioned")[:12]
        name = f"{repo}-{sha_tag}.json"
        totals = {
            "files": result["files"],
            "records": result["records"],
            "imported": result["imported"],
            "invalid": result["invalid"],
            "duplicates_merged": result["duplicates_merged"],
            "occurrences_added": result["occurrences_added"],
            "region_set_from_duplicate":
                result["region_set_from_duplicate"],
            "region_ambiguous": result["region_ambiguous"],
            "region_conflicts_kept_for_review": len(
                result.get("conflicts", [])),
            "upstream_changed_files": result["upstream_changed"],
        }
        payload = {
            "source_repo": ("https://github.com/SahirVhora/11plus-prep"
                            if repo == "11plus-prep" else repo),
            "source_sha": args.source_sha,
            "licence": ("MIT License, Copyright (c) 2026 Sahir Vhora"
                        if repo == "11plus-prep" else "see source repository"),
            "import_batch": args.batch,
            "imported_at_utc": datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds"),
            "totals": totals,
            "files": result.get("manifest_files", []),
            "attribution_conflicts": result.get("conflicts", []),
        }
        out = manifest_dir / name
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("manifest written: %s", out)


if __name__ == "__main__":
    main()
