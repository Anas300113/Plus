"""Ingestion pipeline orchestrator. Steps are deterministic,
idempotent, resumable and versioned. Each step records a
checkpoint on the PipelineRun row."""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import PipelineRun
from src.core.logging import get_logger
from src.pipeline import classify as classify_step
from src.pipeline import dedup as dedup_step
from src.pipeline import detect as detect_step
from src.pipeline import extract as extract_step
from src.pipeline import ingest as ingest_step
from src.pipeline import inventory as inventory_step
from src.pipeline import link as link_step
from src.pipeline import offices as offices_step
from src.pipeline import validate as validate_step
from src.source.inventory import inventory_directory

log = get_logger("pipeline")

STEPS = [
    "inventory", "ingest", "page_extract", "text_extract",
    "image_extract", "detect", "link", "classify",
    "dedup", "validate",
]


def run_pipeline(
    session: Session,
    source_root: str | Path,
    repo_name: str,
    batch: str,
    version: str = "0.1.0",
    resume_from: str | None = None,
) -> PipelineRun:
    run = PipelineRun(id=str(uuid.uuid4()), pipeline_version=version, status="running")
    session.add(run)
    session.commit()
    stats: dict = {}
    try:
        start = STEPS.index(resume_from) if resume_from in STEPS else 0
        docs = []
        if start <= 0:
            docs = inventory_directory(session, source_root, repo_name, batch=batch,
                                       version=version)
            stats["inventory"] = len(docs)
            run.checkpoint = "inventory"
            session.commit()
        for step in STEPS[1:]:
            if STEPS.index(step) < start:
                continue
            if step == "ingest":
                stats[step] = ingest_step.run(session, docs, batch)
            elif step == "page_extract":
                stats[step] = extract_step.run_page_extract(session, docs)
            elif step == "text_extract":
                stats[step] = extract_step.run_text_extract(session, docs, source_root)
                office = offices_step.run_office_extract(session, docs, source_root)
                stats[step] = {"pdf_pages": stats[step].get("pages", 0),
                               "office_pages": office.get("pages", 0)}
            elif step == "image_extract":
                stats[step] = extract_step.run_image_extract(session, docs, source_root)
            elif step == "detect":
                stats[step] = detect_step.run(session, docs)
            elif step == "link":
                stats[step] = link_step.run(session, docs)
            elif step == "classify":
                stats[step] = classify_step.run(session, docs)
            elif step == "dedup":
                stats[step] = dedup_step.run(session, docs)
            elif step == "validate":
                stats[step] = validate_step.run(session, docs)
            run.checkpoint = step
            session.commit()
        run.status = "completed"
        run.stats_json = stats
        session.commit()
    except Exception as exc:  # retryable: checkpoint preserved
        run.status = "failed"
        run.error_message = str(exc)
        session.commit()
        raise
    log.info("pipeline run %s completed: %s", run.id, stats)
    return run
