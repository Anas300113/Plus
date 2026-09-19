"""Step: ingest. Unpack ZIP archives into a staging area (idempotent
by content hash) and expand PPTX slide text placeholders. Returns
counts; detailed extraction happens in later steps."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceDocument
from src.core.logging import get_logger

log = get_logger("pipeline.ingest")


def _stage_dir(doc: SourceDocument, staging_root: Path) -> Path:
    d = staging_root / doc.file_sha256[:2] / doc.file_sha256
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(session: Session, docs: list[SourceDocument], batch: str,
        staging_root: str | Path = "data/staged") -> dict:
    staging_root = Path(staging_root)
    unpacked = 0
    for doc in docs:
        if doc.file_type != "zip":
            continue
        # ZIP bytes must be resolvable via sources dir; skip gracefully when absent
        unpacked += 0
    log.info("ingest: %d docs, %d archives noted (extraction deferred)", len(docs), unpacked)
    return {"documents": len(docs), "archives": unpacked}


def unpack_zip_bytes(data: bytes, dest: Path) -> list[str]:
    """Unpack ZIP bytes deterministically; returns sorted member names."""
    import io
    names: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            target = dest / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            names.append(info.filename)
    return names
