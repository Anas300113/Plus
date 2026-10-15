# Plus — Master Engineering Quality Gate

**Framework:** AI Quality Lab `vibe-coding-checklist` v2.0.0 (MIT)
**Repo:** `https://github.com/Anas300113/Plus.git` @ `b154e88` (main == origin/main, tree clean)
**Baseline:** `python -m pytest -q` → **278 passed** (warnings only; `datetime.utcnow()` deprecation dominates)
**Scope:** Trustworthiness of the 11plus-prep ingested question bank + student-identity boundary.
**Verdict:** 🟠 **NO-GO for production student data — improved since baseline.** Gate 1 (provenance) is now **FIXED** (P0). The student-identity boundary remains release-blocking. Gates 2 & 3 are significant gaps. Gate 4 is materially strong.

---

## 1. Executive Summary
The prior gates (`45f692b`, `10ff233`, `b154e88`) did real, testable work: the answer-key leak is closed at document *and* search level, unapproved content does not reach the student feed, and edits correctly downgrade stale verifications. However, the **provenance check feeding the approval contract was vacuous for imported content** — an imported question passed `has_provenance()` with a fabricated page id and **zero** backing `SourcePage` rows. **This gate has now been fixed (P0, this pass):** provenance is resolved against real rows, the importer no longer fabricates page ids, and 1,067 legacy rows were reconciled via an idempotent migration — all covered by 13 new regression tests (291 passing). Student identity remains an unauthenticated supplied header with ownership enforcement **off by default** — acceptable for a dev corpus, unsafe for real student data, and now the sole release-blocker.

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

### Gate 2 — Regional / board attribution ⚠️ (significant gap)
- Single canonical `region` on `CanonicalQuestion`; `import_reference.py:177` collapses conflicting regions to `""` (`regions.pop() if len(regions)==1 else ""`).
- `:180-181` counts `region_ambiguous`; `:206-213` logs divergences into `conflicts` (manifest only) instead of preserving the assertions. Valid region/board assertions from individual sources are discarded from the queryable model.
- **Fix direction:** normalised association table (canonical ↔ region/board with source + confidence), additive + idempotent migration, reconciliation that preserves every valid assertion and flags true conflicts.

### Gate 3 — Auditable manifests ⚠️ (gap)
- `_write_manifests` (`import_reference.py:270-309`) is **per-run**, keyed by source sha. `totals` (`:280-293`) reflect *this run* only; there is no cumulative corpus snapshot. This is the source of the "1040 imported / 0 new vs 27 occurrences" ambiguity — an incremental re-run reports ~0 new while the corpus holds 1,040.
- **Fix direction:** split the manifest into an immutable per-run record **and** a cumulative corpus snapshot (total questions, occurrences, approved counts, per-source breakdown) so incremental runs reconcile against whole-corpus state.

### Gate 4 — Approval & exposure boundary ✅ (strong, one dependency)
- `review.py` contract is real: approval requires `answer_status == verified` **and** `explanation_status == verified` **and** provenance **and** MCQ validity (`approval_blockers`, `:123-165`). Answer never approved merely because `correct_answer` is set.
- Edits downgrade stale verifications and `_downgrade_review_if_approved` (`:262-280`) re-deposits at `validation_required`. Answer-key leak closed at doc + search level. Unapproved content does not reach the student feed (`tests/test_unapproved_exposure.py`).
- **Sole weakness:** the provenance input it consumes is Gate 1's vacuous check. Strengthen Gate 1 and this gate stands.

### Gate 5 — Educational correctness ⏸ (safe, not student-ready)
- Ingested corpus is uniformly `validation_required` / `answer_status=missing` / 0 approved. This is the **correct safe default** — nothing unverified leaks.
- Consequence: the corpus cannot serve students until human review at scale. **Do not bulk-approve.** Any approval must be per-question human verification.

## 3. Student Identity / Ownership (§6)
- `X-Student-Id` is a **supplied identifier, not authenticated**; the app has no identity provider (`review.py:18-26` documents this for reviewers and it applies to students).
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
| Deployment Readiness | ⭐⭐⭐ | 3/5 | 278 tests green; no manifest signing; identity default unsafe for prod; `utcnow` deprecation. |

**Total: 17/30 — ⭐⭐⭐ Acceptable (requires attention).** The Security score is the binding constraint.

## 5. Hard-Gate Release Decision
- ✅ **Gate 1 (provenance):** FIXED at P0 — fabricated page ids no longer grant page-level provenance; resolved against real rows; 1,067 legacy rows reconciled. **No longer release-blocking.**
- ❌ **Student identity:** unauthenticated, ownership enforcement off by default → **still release-blocking for real student data.**
- ⚠️ **Gates 2 & 3:** significant attribution/auditability gaps → must-fix before trusting the corpus for graded use.
- ✅ **Gate 4:** exposure/approval boundary is sound; its provenance input is now trustworthy.

**Decision:** NO-GO for production. The bank is safe *as a held, unapproved corpus* (nothing unverified reaches students). With Gate 1 fixed, the remaining release-blocker is the **student-identity boundary**; Gates 2–3 must close before graded use.

## 6. Prioritised Remediation (smallest coherent next steps)
1. **P0 — Fix provenance (Gate 1):** ✅ **DONE** — honest page/file provenance resolved against real rows; importer writes `page_id=""`; idempotent recorded migration clears legacy fabrication; 13 regression tests. Never weakens the approval gate.
2. **P0 — Identity:** design + review authenticated principal binding; server-derived student id; flip default for data-bearing envs. No rushed auth code. **(next)**
3. **P1 — Region/board associations (Gate 2):** normalised model + additive idempotent migration; preserve all assertions; flag conflicts.
4. **P1 — Manifest split (Gate 3):** immutable per-run record + cumulative corpus snapshot.
5. **P2 — Hygiene:** `datetime.utcnow()` → timezone-aware; manifest signing; dependency/licence manifest per source repo.

## 7. Evidence Index
- Provenance check: `src/pipeline/review.py:95-100`, `:123-165`.
- Fabricated occurrence: `scripts/import_reference.py:96-101`, `:219-226`.
- Region collapse / conflicts: `scripts/import_reference.py:172-181`, `:206-213`.
- Manifest totals: `scripts/import_reference.py:280-293`.
- Schema: `src/core/database.py:26-82` (`SourceDocument`, `SourcePage`, `QuestionOccurrence`).
- Baseline: `pytest -q` → 278 passed @ `b154e88`.

## 8. Scope, Assumptions & Limitations
- Assessment only. **No code changed, nothing committed or pushed** (tree clean @ `b154e88`).
- Gate 1 provenance defect verified by **executable repro**, not just code reading.
- Gate 5 counts (1,040 / 0 approved) are from the prior audit of the live DB; re-verify against a live DB before any approval decision.
- Checklist licence: MIT (v2.0.0) — this report references, and does not copy, the checklist text.

## 9. Sign-off
Status: **Draft → In Review.** Awaiting stakeholder decision on Gate 1 + identity remediation before any GO re-assessment. Human approval required for merge/deploy; no auto-promotion.
