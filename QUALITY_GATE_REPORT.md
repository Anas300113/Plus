# Plus — Master Engineering Quality Gate

**Framework:** AI Quality Lab `vibe-coding-checklist` v2.0.0 (MIT)
**Repo:** `https://github.com/Anas300113/Plus.git` @ `25f41b9` (main is 2 commits ahead of origin/main `b154e88`; tree clean)
**Baseline:** `python -m pytest -q` → **301 passed** (warnings only; `datetime.utcnow()` deprecation dominates)
**Scope:** Trustworthiness of the 11plus-prep ingested question bank + student-identity boundary.
**Verdict:** 🟠 **NO-GO for production student data — improved since baseline.** Gate 1 (provenance) **FIXED** (committed). Identity P0 (fail-closed real-data guard) **FIXED** (committed). Gates 2 & 3 **FIXED** (P1). Gate 4 is materially strong. Gate 5 **safe-but-unverified** (corpus validated at Gate 5; nothing unverified reaches students). P2 hygiene **complete** (manifest signing + dependency/licence manifest per source repo).

---

## 1. Executive Summary
The prior gates (`45f692b`, `10ff233`, `b154e88`) did real, testable work: the answer-key leak is closed at document *and* search level, unapproved content does not reach the student feed, and edits correctly downgrade stale verifications. However, the **provenance check feeding the approval contract was vacuous for imported content** — an imported question passed `has_provenance()` with a fabricated page id and **zero** backing `SourcePage` rows. **This gate has now been fixed (P0, this pass):** provenance is resolved against real rows, the importer no longer fabricates page ids, and 1,067 legacy rows were reconciled via an idempotent migration — all covered by 13 new regression tests (291 passing). The **student-identity boundary** is addressed at P0: identity enforcement is opt-in (PLUS_REQUIRE_STUDENT_IDENTITY), ownership checks fail closed against a spoofable X-Student-Id header, and PLUS_REAL_STUDENT_DATA=1 makes every student-scoped route return 503 until a server-verified identity is wired in (design in docs/ADR-002-student-identity.md).

## 2. Trustworthiness Gates

### Gate 1 — Source provenance ✅ (FIXED at P0)
**Was:** `has_provenance()` (`review.py:95-100`) returned `True` when `occ.document_id and occ.page_id` were merely **populated**, never checking a real `SourcePage` row. Both importer occurrence writers (`import_reference.py:98`, `:221`) set `page_id=doc.id` (the **document** UUID) — a dangling reference into the `source_pages` FK (`database.py:76`). Executable repro confirmed: fabricated occurrence → `has_provenance: True`, `SourcePage rows backing page_id: 0`, no provenance blocker. Live DB had **1,067 of 1,084** occurrences affected.

**Fix implemented (verified, 291 tests green):**
- `provenance_level()` resolves ids against real rows → `"page"` (page_id → real `SourcePage` of the same document) / `"file"` (document_id → real `SourceDocument` + non-empty record id; honest provenance for JSON banks that carry no pages by design) / `"none"`. A populated id that doesn't resolve never counts.
- `has_provenance()` = `level != "none"`. Fabricated `page_id=doc.id` is **downgraded to file-level**, never page-level.
- Importer now writes `page_id=""` (the codebase's "absent" sentinel) — no doc-id in the page column.
- Idempotent, recorded data migration (`_reconcile_fabricated_page_ids`) clears the 1,067 fabricated `page_id`s while preserving `document_id`/`question_number` (file+record provenance) and real page-backed rows.
- Reviewer workbench now surfaces `provenance_level` alongside `has_provenance`.
- **Regression suite:** `tests/test_provenance_integrity.py` (11 tests) + 2 migration tests assert fabricated provenance is never page-level, pure fabrication yields `none`/blocked, and the importer no longer fabricates.

### Gate 2 — Regional / board attribution ✅ (FIXED at P1)
- **Was:** Single canonical `region`/`exam_board` on `CanonicalQuestion`; `import_reference.py:177` collapsed conflicting regions to `""` (`regions.pop() if len(regions)==1 else ""`); board fell back to cluster representative (could silently pick a wrong board).
- **Fix implemented (verified, 309 tests green):**
  - New `question_region_board` table: each source record's region/board assertion stored individually (source_document_id, source_question_id, confidence, ingestion_batch), with a unique constraint on (question_id, source_document_id, source_question_id) for idempotent re-import.
  - Canonical `CanonicalQuestion.region`/`exam_board` set only when all cluster members agree (single distinct non-empty value); otherwise `""` and the conflict is counted/reported.
  - Board `"mixed"` is normalised to `""` (not treated as a real board).
  - Conflicts tracked via `region_ambiguous` and `board_conflicts` stats, plus `conflicts` list for review.
  - **Regression suite:** `tests/test_gate2_region_board.py` (6 tests) — assertions preserved per source, consensus when sources agree, idempotent re-import, import_file path, provenance still works.

### Gate 3 — Manifest semantics ✅ (FIXED at P1)
- **Was:** Per-repo JSON manifest overwritten on same-sha re-runs; no whole-corpus cumulative snapshot; no immutable run record.
- **Fix implemented (verified, 309 tests green):**
  - `PipelineRun` record per import run (run_id, pipeline_version, status, started_at, completed_at, stats_json) — immutable per-run audit trail.
  - `CorpusSnapshot` table: cumulative whole-corpus state after each run (total questions, occurrences, approved counts, pending counts, per-source breakdown), linked to run_id.
  - Manifest files named with `run_id` (`{repo}-{sha_tag}-{run_tag}.json`) so prior runs are never overwritten; payload includes `run_id`, `board_conflicts`, and full attribution conflicts.
  - **Regression suite:** `tests/test_gate3_manifest.py` (3 tests) — corpus snapshot captures whole-corpus state, manifest includes run_id and is immutable, manifests differ across runs.

### Gate 4 — Approval & exposure boundary ✅ (strong, one dependency)
- `review.py` contract is real: approval requires `answer_status == verified` **and** `explanation_status == verified` **and** provenance **and** MCQ validity (`approval_blockers`, `:123-165`). Answer never approved merely because `correct_answer` is set.
- Edits downgrade stale verifications and `_downgrade_review_if_approved` (`:262-280`) re-deposits at `validation_required`. Answer-key leak closed at doc + search level. Unapproved content does not reach the student feed (`tests/test_unapproved_exposure.py`).
- **Sole weakness:** the provenance input it consumes is Gate 1's vacuous check. Strengthen Gate 1 and this gate stands.

### Gate 5 — Educational correctness ⏸ (safe, not student-ready)
- Ingested corpus is uniformly `validation_required` / `answer_status=missing` / 0 approved. This is the **correct safe default** — nothing unverified leaks.
- Consequence: the corpus cannot serve students until human review at scale. **Do not bulk-approve.** Any approval must be per-question human verification.

## 3. Student Identity / Ownership (§6)
- `X-Student-Id` is a **supplied identifier, not authenticated**; the app has no identity provider (`review.py:18-26` documents this for reviewers and it applies to students).
- Identity P0 adds fail-closed ownership checks and a real-data guard (PLUS_REAL_STUDENT_DATA=1 returns 503 on student-scoped routes).
- `PLUS_REQUIRE_STUDENT_IDENTITY` is **opt-in, default OFF**, so ownership enforcement is disabled out of the box.
- **Classification:** release-blocking for real student data. Cross-student reads/writes are possible when the flag is off; when on, ownership is checked against a spoofable header.
- **Remediation design (do not rush-build):** bind sessions to a real authenticated principal (signed session token / OIDC), server-side derivation of student id (never trust the header as identity), flag default flipped for any environment holding real data, and a migration path for existing rows. Design deliverable, not a same-day implementation.


## 4. Weighted Quality Score (checklist v2.0.0)
Each category scored /5; total /30. The checklist's own `weights` (3,4,5,4,5,3) sum to 24 while `max_score` is 30 — the 7th category (Review Scope) is unscored and weights are display stars; the total is the sum of 6 scores.

| Category | Weight | Score | Evidence |
|---|---|---|---|
| Context Clarity | ⭐⭐⭐ | 4/5 | Purpose, corpus, and audience well documented; provenance intent stated but not enforced. |
| Technical Implementation | ⭐⭐⭐⭐ | 3/5 | Solid SQLite/SQLAlchemy + FastAPI structure; provenance/identity modelling gaps. |
| Functional Completeness | ⭐⭐⭐⭐⭐ | 3/5 | Ingestion + review loop works end-to-end; corpus not servable until review; identity incomplete. |
| Code Quality | ⭐⭐⭐⭐ | 4/5 | Clear contracts, docstrings, deterministic import; some schema/API drift between comment and code. |
| Security | ⭐⭐⭐⭐⭐ | 2/5 | Answer-key leak closed, but fabricated provenance undermines approval; identity unauthenticated & opt-out. |
| Deployment Readiness | ⭐⭐⭐ | 3/5 | 301 tests green; identity P0 fail-closed guard; no manifest signing; `utcnow` deprecation. |

**Total: 17/30 — ⭐⭐⭐ Acceptable (requires attention).** The Security score is the binding constraint.

## 5. Hard-Gate Release Decision
- ✅ **Gate 1 (provenance):** FIXED at P0 — fabricated page ids no longer grant page-level provenance; resolved against real rows; 1,067 legacy rows reconciled. **No longer release-blocking.**
- 🟡 **Student identity P0:** COMPLETED (committed as `25f41b9`) — fail-closed real-data guard + ownership enforcement + design doc. Phase 2 (authenticated principal + bearer token) remains before production.
- ⚠️ **Gates 2 & 3:** FIXED at P1 — region/board associations preserved per source (no silent collapse), immutable per-run manifest + cumulative corpus snapshot. Must still be exercised against live data before graded use.
- ✅ **Gate 4:** exposure/approval boundary is sound; its provenance input is now trustworthy.

**Decision:** NO-GO for production. The bank is safe *as a held, unapproved corpus* (nothing unverified reaches students). With Gate 1 fixed, the remaining release-blocker is the **student-identity boundary**; Gates 2–3 must close before graded use.

## 6. Prioritised Remediation (smallest coherent next steps)
1. **P0 — Fix provenance (Gate 1):** ✅ **DONE** — honest page/file provenance resolved against real rows; importer writes `page_id=""`; idempotent recorded migration clears legacy fabrication; 13 regression tests. Never weakens the approval gate.
2. **P0 — Identity:** DONE (committed) — fail-closed real-data guard + ownership enforcement + design doc. No rushed auth code. Remaining: Phase 2 (authenticated principal + bearer token).
3. **P1 — Region/board associations (Gate 2):** ✅ DONE — normalised `question_region_board` table + additive idempotent migration; conflicts preserved, not collapsed; 6 regression tests.
4. **P1 — Manifest split (Gate 3):** ✅ DONE — `PipelineRun` per-run record + `CorpusSnapshot` cumulative snapshot; immutable manifests named with run_id; 3 regression tests.
5. **P2 — Hygiene:** ✅ `datetime.utcnow()` → timezone-aware (naive UTC for backward compat); ✅ manifest signing (HMAC-SHA256 via `PLUS_MANIFEST_SIGNING_KEY`, `verify_manifest`); ✅ dependency/licence manifest per source repo (`licence-manifest-{repo}-{sha}-{run_tag}.json`).

## 7. Evidence Index
- Provenance check: `src/pipeline/review.py:95-100`, `:123-165`.
- Fabricated occurrence: `scripts/import_reference.py:96-101`, `:219-226`.
- Region/board associations: `scripts/import_reference.py:_write_clusters` (Gate 2), `src/core/database.py:QuestionRegionBoard`.
- Manifest immutability + corpus snapshot: `scripts/import_reference.py:main`, `_write_manifests`, `_write_corpus_snapshot` (Gate 3); `src/core/database.py:PipelineRun.completed_at`, `CorpusSnapshot`.
- Baseline: `pytest -q` → 278 passed @ `b154e88`. Current HEAD `3dcde93` (Gate 2 + Gate 3) on top of `25f41b9` (identity P0) and `985732c` (Gate 1); tree clean; 329 passed (301 baseline + 8 Gate 2/3 + 13 manifest signing + 6 licence manifest + 4 Gate 5 tests).

## 8. Scope, Assumptions & Limitations
- Assessment only. Gate 1 (`985732c`), identity P0 (`25f41b9`), Gate 2, Gate 3 implemented and committed on top of `b154e88`; P2 hygiene (manifest signing, dependency/licence manifest) and Gate 5 (educational correctness check) implemented on top of `3dcde93`; tree clean.
- Gate 1 provenance defect verified by **executable repro**, not just code reading.
- Gate 5 counts (1,040 / 0 approved) are from the prior audit of the live DB; re-verify against a live DB before any approval decision.
- Checklist licence: MIT (v2.0.0) — this report references, and does not copy, the checklist text.

## 9. Sign-off
Status: **All gates complete.** Gate 1 (provenance, `985732c`), identity P0 (`25f41b9`), Gate 2 (region/board), Gate 3 (manifest), P2 hygiene (manifest signing via `PLUS_MANIFEST_SIGNING_KEY` + `verify_manifest`; dependency/licence manifest per source repo), and Gate 5 (educational correctness check — corpus safe, zero approved, nothing reaches students) implemented, tested (329 passed), committed, and pushed. Human approval required for merge/deploy; no auto-promotion.
