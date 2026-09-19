# 11+ Preparation Platform

Production-quality UK 11+ preparation platform: Maths, English,
Verbal Reasoning, Non-Verbal Reasoning.

## Architecture rule

SOURCE MATERIAL, CANONICAL EDUCATIONAL CONTENT, STUDENT PERFORMANCE
and AI-GENERATED CONTENT are separate database table groups
(`source_*`, `canonical_*` + `curriculum_*` + `assessment_*`,
`learning_*`, `ai_*`). They are never collapsed into one table.

## Quickstart

```powershell
pip install -r requirements.txt  # or: pip install pydantic pydantic-settings sqlalchemy alembic fastapi "uvicorn[standard]" python-multipart pyyaml pypdf pdfplumber python-pptx Pillow numpy jsonschema pytest
$env:PYTHONPATH='.'
python scripts/build_fixtures.py
python scripts/seed_taxonomy.py --db sqlite:///./elevenplus.db
python scripts/spike_extract.py --source-root data/fixtures/spike --repo-name spike --batch spike-001 --db sqlite:///./elevenplus.db
python scripts/review_cli.py --db sqlite:///./elevenplus.db --list
$env:PLUS_DATABASE_URL='sqlite:///./elevenplus.db'
python -m uvicorn src.api.main:app --port 8000
```

API: `GET /api/health`, `GET /api/questions`, `POST /api/sessions`,
`POST /api/attempts`, `GET /api/progress/{student_id}`,
`GET /api/review-queue`, `POST /api/review/{question_id}`.

Only `approved` questions are student-facing.

## Tests

```powershell
$env:PYTHONPATH='.'
python -m pytest tests/
```

## Reference repos

Architecture inspiration only; content provenance and rights are
tracked per source. External schemas never leak: adapters
(`src/source/adapters/`) transform to the canonical model.
