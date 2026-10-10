# 11+ Preparation Platform

Production-quality UK 11+ preparation platform: Maths, English,
Verbal Reasoning, Non-Verbal Reasoning.

## Architecture rule

SOURCE MATERIAL, CANONICAL EDUCATIONAL CONTENT, STUDENT PERFORMANCE
and AI-GENERATED CONTENT are separate database table groups
(`source_*`, `canonical_*` + `curriculum_*` + `assessment_*`,
`learning_*`, `ai_*`). They are never collapsed into one table.

Data flow: **source → canonical → curriculum → assessment → learning → AI**.
Each layer owns its tables and never reaches across layers.

## Learning layer (Phase 6)

The learning layer (`src/learning/*`) provides deterministic,
evidence-based learning mechanics — no AI required on the critical path.

### Session state machine (`src/learning/session.py`)
- `SessionState`: planned → started → in_progress ↔ reviewing → complete | abandoned
- `SessionType`: learn | practice | review | mock | diagnostic | catch_up
- Explicit transitions enforced via `SESSION_TRANSITIONS`
- `start_session`, `submit_answer`, `skip_current`, `retry_current`,
  `complete_session`, `abandon_session`
- Question order frozen at start so sessions can be resumed exactly
- Explanation served from stored canonical content (`queries.explain_question`),
  not an LLM
- Unapproved questions excluded from sessions

### ReviewItem scheduling (`src/learning/review.py`)
- `LearningReviewItem`: what to review and when — scheduling state only,
  separate from mastery aggregates and evidence
- Deterministic interval ladder: 1 → 3 → 7 → 14 → 30 days, capped
- Reset on wrong answer; FSRS deliberately absent
- Due queue excludes rejected (non-approved) questions
- `suspend_review_item` for removals
- Idempotent `ensure_review_item` via unique constraint on
  (student_id, source_type, source_id)

### Statistics & mastery (`src/learning/statistics.py`, `src/learning/weak_area.py`)
- `attempt_totals`: skips excluded from accuracy by design
- `student_statistics`: by_subject, by_topic, by_skill, by_question_type,
  by_difficulty, recent window, practice_volume, topic_mastery,
  skill_mastery, weak_topics, weak_skills, review summary, mock_results
- `refresh_topic_mastery` / `refresh_skill_mastery` / `refresh_mastery`:
  deterministic aggregates from `LearningQuestionAttempt` rows
- `repeated_mistakes`, `question_performance` (error_rate, discrimination_index
  as None until enough students), `system_statistics` (content health)
- `filter_weak_topics` pure function

### Educational loop (`src/learning/loop.py`)
- LEARN → PRACTISE → ASSESS → IDENTIFY ERROR → EXPLAIN → REVIEW →
  RE-PRACTISE → UPDATE MASTERY
- `loop_snapshot` assembles all steps from stored content + evidence
- `AI_REQUIRED_FOR_LOOP = False` — AI augments, never drives the loop

### Models (`src/core/database.py`)
- `LearningStudySession` — session_type, state, planned/actual duration,
  goals_json, recommended_activities_json, question_order_json (frozen for
  resume), current_index, skipped_ids_json, accuracy
- `LearningQuestionAttempt` — evidence: what the student actually did
- `LearningReviewItem` — scheduling: what to review and when
- `LearningTopicMastery` / `LearningSkillMastery` — learning state aggregates
- `LearningRecommendation` — what-to-do-next
- `LearningStudent` — student hub

### Migration framework (`src/core/migrations.py`)
- `ensure_schema`: `create_all` + additive `ALTER` for missing columns +
  backfill indexes
- `schema_migrations` table records applied IDs; idempotent re-runs
- `server_default` on every new column so existing SQLite DBs survive
  without wipe

## API

### Legacy (backwards compatible)
- `GET /api/health`
- `GET /api/questions` — approved questions only
- `POST /api/sessions` — create session (now goes through state machine)
- `POST /api/attempts` — legacy attempt endpoint (tolerant `enforce_current`)

### Session state machine
- `POST /api/sessions` — create session (query-param form)
- `POST /api/sessions/start` — create session (body form, full control)
- `POST /api/sessions/{session_id}/answer`
- `POST /api/sessions/{session_id}/skip`
- `POST /api/sessions/{session_id}/retry`
- `POST /api/sessions/{session_id}/complete`
- `POST /api/sessions/{session_id}/abandon`

### Learning endpoints
- `GET /api/reviews/{student_id}` — due review items + review summary
- `GET /api/recommendations/{student_id}` — open recommendations
  (optionally refresh)
- `GET /api/loop/{student_id}` — educational loop snapshot
- `GET /api/system/statistics` — content-health view
- `GET /api/progress/{student_id}` — existing progress endpoint extended
- `GET /api/parent/{student_id}` — parent dashboard

Only `approved` questions are student-facing.

## Quickstart

```powershell
pip install -r requirements.txt  # or: pip install pydantic pydantic-settings sqlalchemy alembic fastapi "uvicorn[standard]" python-multipart pyyaml pypdf pdfplumber python-pptx Pillow numpy jsonschema pytest
$env:PYTHONPATH='.'
python scripts/build_fixtures.py
python scripts/seed_taxonomy.py --db sqlite:///./elevenplus.db
python scripts/spike_extract.py --source-root data/fixtures/spike --repo-name spike --batch spike-001 --db sqlite:///./elevenplus.db
$env:PLUS_DATABASE_URL='sqlite:///./elevenplus.db'
python -m uvicorn src.api.main:app --port 8000
```

## Knowledge engine & ingestion CLI (`scripts/knowledge_cli.py`)

Local, offline retrieval over the frozen ingestion foundation — no network,
no model downloads (TF-IDF + cosine similarity via `scikit-learn`, persisted
with `joblib`). Retrieval returns verifiable `filename` + `page` + excerpt
and never fabricates evidence.

```powershell
$env:PYTHONPATH='.'

# Discover + ingest a directory into the DB (idempotent, resumable). This is
# the CLI path that actually populates the DB; `index` only reads existing rows.
python scripts/knowledge_cli.py --db elevenplus.db ingest `
  --source "D:/11+ dump" --repo corpus --batch b1 --assets data/assets

# Build / rebuild the TF-IDF index from DB content (atomic replace).
python scripts/knowledge_cli.py --db elevenplus.db index --out data/knowledge/index.joblib

# Retrieve relevant passages with page-level citations.
python scripts/knowledge_cli.py --db elevenplus.db query `
  --index data/knowledge/index.joblib --q "opposite of generous" -k 3

# Verify index/DB consistency and rebuild if drifted.
python scripts/knowledge_cli.py --db elevenplus.db repair --index data/knowledge/index.joblib

# Reproducible, read-only content-readiness metrics from stored records.
python scripts/knowledge_cli.py --db elevenplus.db report
```

### OCR on scanned PDFs (Windows)
Tesseract may be installed but **not on PATH**. Point the pipeline at the
binary explicitly; otherwise scanned pages are skipped by design (distinct
from an extraction failure):

```powershell
$env:PLUS_TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Generated artefacts are excluded from Git: `data/assets/`, `data/knowledge/`,
`*.joblib`.

## Tests

```powershell
$env:PYTHONPATH='.'
python -m pytest tests/
```

**183 tests, all passing.**

Phase 6 (learning layer) — `test_learning_session.py` (18),
`test_review_items.py` (11), `test_statistics.py` (12),
`test_educational_loop.py` (11), `test_migrations.py` (8), plus extended
`test_api.py`.

Knowledge engine — `test_knowledge_engine.py` (chunking, TF-IDF retrieval,
page-level citations, insufficient-evidence behaviour, index/DB repair,
atomic replace) and `test_content_readiness.py` (CLI `ingest` bridge,
off-PATH OCR engine config, reproducible read-only report, provenance /
ordered-option checks).

Ingestion — `test_mcq_option_extraction.py`, `test_answer_linking.py`,
`test_ocr.py`, `test_ingestion_idempotency.py`, `test_provenance.py`,
`test_duplicate_detection.py`, and others.


## Reference repos

Architecture inspiration only; content provenance and rights are
tracked per source. External schemas never leak: adapters
(`src/source/adapters/`) transform to the canonical model.
