# Real-Corpus Validation Report — 11+ Ingestion Pipeline (new sample)

> **⚠️ HISTORICAL SNAPSHOT — SUPERSEDED.** This report records a validation
> run against code SHA `09141eb`. Both blockers named in §15
> ("NOT READY — BLOCKERS REMAIN") have since been **fixed and verified**:
>
> 1. **MCQ option extraction** — only structurally-supported, contiguous
>    option sets are now promoted; malformed/shuffled/gapped/sub-part runs are
>    rejected to review (fixed in `87b14d0`).
> 2. **NVR false answer links** — answer-linking is now document-scoped with
>    explicit key evidence only; `11NVRPaper2.pdf` false links = 0 (also
>    `87b14d0`).
>
> The ingestion/content foundation was then **frozen** (`87b14d0`), and a
> local, provenance-preserving knowledge engine (retrieval + content-readiness
> report) was added on top (`46ee376`, `708c1ea`). The current readiness state
> is documented in `README.md`. Treat §1–§15 below strictly as the historical
> baseline for that SHA, not the current status.

## 1. Run identity


| field | value |
|---|---|
| code SHA (HEAD) | `09141ebafa1b2e292750092479bd46991a88ff3e` |
| code changes since prior spike | `ocr.py`, `extract.py`, `ingest.py`, `detect.py` (see section 14) |
| corpus root | `C:\Users\ADMIN\AppData\Local\Temp\plus-validation\corpus` |
| corpus files (full repo) | 596 |
| corpus root sha256 | `7da4239e9d332cda3b9937b319b5d89c03ac68b65c5e997fd771a3a9a670457a` |
| sample dir | `sample_corpus` (21 distinct source files) |
| started_at (run #1) | 2026-09-21T17:05:01.288Z |
| finished_at (run #1) | 2026-09-21T17:06:30.856Z |
| pipeline version | validate-1.0.0 |
| OCR engine / version | tesseract / **5.4.0.20240606** |

## 2. Exact selected file list (21 source files; 2 ZIP + 1 PPTX inflate to 27 docs)

All 21 source files are new vs the prior 23-file spike except where the corpus has no alternative:
- `11NVRPaper2.pdf` (only NVR file not already exhausted by the prior list)
- `11_Sample_ maths_exam_questions.pptx` (the corpus's only .pptx)

All files SHA-256 verified (0 hash mismatches). Full list:

| category | size | rel | sha12 |
|---|---|---|---|
| native_text_pdf | 5.31MB | Maths_2.pdf | 527fe2e1e7d7 |
| native_text_pdf | 5.45MB | English_2.pdf | 5a3a538941c8 |
| mixed_image_heavy | 2.80MB | 9+ Maths Sample Paper 2D.pdf | 66194a7e2e23 |
| mixed_image_heavy | 1.26MB | 9+ Sample papers 2013 2.pdf | bb2d435192c7 |
| native_text_pdf | 5.33MB | English_3.pdf | 18b126e5baf9 |
| native_text_pdf | 9.50MB | Maths_P9.pdf | e0251ee4346c |
| native_text_pdf | 4.99MB | English_AS4-6.pdf | e30ab8c134eb |
| native_text_pdf | 3.70MB | 11ComprehensionPracticePaper.pdf | 8ba2063d87c8 |
| native_text_pdf | 3.29MB | 11MathsPracticePaper2.pdf | b138c52a1627 |
| native_text_pdf | 4.48MB | Maths_3.pdf | 313590481b83 |
| answer_key | 0.07MB | csse 2008 MATHS marking scheme.pdf | 27dbc07fcb3c |
| answer_key | 0.21MB | CGP11+EnglishAnswerSheet.pdf | 14f42a1fec7c |
| scanned_pdf | 0.44MB | 2008 intake maths.pdf | 68bf217275eb |
| scanned_pdf | 0.30MB | 2008 intake English.pdf | ef909d50e0a7 |
| scanned_pdf | 4.03MB | 11VerbalReasoning.pdf | aad4efbc714a |
| scanned_pdf | 4.27MB | 11VerbalPaper2.pdf | 0aa5c90b7ab2 |
| scanned_pdf | 0.45MB | CSSE_Maths_2007.pdf | 6c415c4f2fe1 |
| scanned_pdf | 0.52MB | CSSE_English_2007.pdf | 060a09cad3c8 |
| scanned_pdf | 0.07MB | CSSE_Maths_2008_Ans.pdf | 27dbc07fcb3c |
| nvr | 4.69MB | 11NVRPaper2.pdf | fd92d4b24eb7 |
| pptx | 0.45MB | 11_Sample_ maths_exam_questions.pptx | 9c73c21ea21e |
| zip | 20.07MB | susan daughtrey vr techniques.zip | 43a9b5573fe1 |
| zip | 1.49MB | core-skills-booster-worksheets-pack-2-2.zip | a839a953dd8d |

## 3. Corpus composition (sample)

by category: `{native_text_pdf:8, mixed_image_heavy:2, answer_key:2, scanned_pdf:7, nvr:1, pptx:1, zip:2}` = 21 files / 83.2 MB. Covers native-text PDFs, scanned/image-only PDFs, mixed/image-heavy PDFs, Maths, English, VR, NVR, question papers, answer sheets, marking schemes, PPTX, ZIP, worksheets.

## 4. Stage-by-stage pipeline counts

Full `STEPS`: inventory → ingest → page_extract → text_extract → image_extract → ocr → vision → detect → link → classify → dedup → validate → approve.

`run #1 stats`:
```
{"inventory":23,"ingest":{"documents":23,"archives":2,"files_unpacked":4},
 "page_extract":{"documents":23,"pages":170},"text_extract":{"pdf_pages":170,"office_pages":5},
 "image_extract":{"assets":440},"ocr":{"ocred":33,"skipped":141},
 "detect":{"candidates":319},"link":{"linked":283,"answer_keys":32},
 "classify":{"classified":246},"dedup":{"questions":0,"duplicates":0},
 "validate":{"promoted":69,"queued":250},"approve":{"ready_for_review":69}}
```

Table counts (run #1): documents 27, pages 175, assets 440, occurrences 319, canonical 69, review_rows 69, approved 0. Reconciliation: 170 pdf_pages + 5 pptx office_pages = 175 pages. 21 source docs + 2 zip (archives) + 4 unpacked nested PDFs = 27 documents.

## 5. OCR measurements

| metric | value |
|---|---|
| pages_total | 175 |
| pages_native (>=40 native chars) | 141 |
| pages_ocr_required (<40 native chars) | 34 |
| pages_ocr_attempted | 34 |
| pages_ocr_success (>=40 ocr chars) | 33 |
| pages_ocr_partial (1..39 ocr chars) | 0 |
| pages_ocr_empty (0 ocr chars) | 1 |
| pages_ocr_required_not_run | 0 |
| skipped | 141 |
| engine | tesseract |
| version | 5.4.0.20240606 |

### is_scanned_page (40-char) heuristic — real effect on this sample
- Scanned/image-only pages classified as ocr_required and actually OCR'd: **34 / 34 → 0 missed**.
- Native pages incorrectly sent to OCR: **0** (ocr_attempted == ocr_required == 34 exactly; the 141 native pages were left untouched).
- Empty/near-empty OCR result: **1** (9+ Maths Sample Paper 2D.pdf p2 — a cover/blank page).

### Real scanned pages where OCR produced usable text (native_chars==0, real ocr_version recorded)
- `CSSE_English_2007.pdf` p2 — 5744 ocr chars — usable. Sample: *"2 @ CHES ... Section C ... Use full sentences in your answers"* (OCR is character-correct but low-quality on this degraded English scan).
- `CSSE_English_2007.pdf` p4 — 2950 chars. Sample: *"Section B q. There are twelve spelling mistakes ... Write out the numbers 1-12"*.
- `CSSE_English_2007.pdf` p6 — 1360 chars. Sample: *"Candidates must not tick more boxes than they are instructed to."*
- `Maths_3.pdf` p2 — 1712 chars — **clean**: *"GL Assessment's Practice Papers give you and your child everything you need to prepare for the English test. Written by our own test experts..."*
- `English_3.pdf` p2 — 1479 chars — **clean**: *"GL Assessment's Practice Papers ... the English test. Written by our own test experts..."*
- `9+ Maths Sample Paper 2D.pdf` p5 — 500 chars — **clean MCQ**: *"21. i cm a. What is the area of shape A? cm b. Now draw another square... perimeter of 16 cm."*
- `9+ Maths Sample Paper 2D.pdf` p11 — 125 chars — *"...20. Here is aclock. a. What time is it? ... until this clock shows 7.30?"*
- `9+ Maths Sample Paper 2D.pdf` p17 — 88 chars — *"28. Work out the area of each shape. a. Rectangle Answer: cm b. Triangle Answer: cm"*

These 8 are genuinely usable OCR results from real scans.

### Native text_content unchanged
`text_extract` populates `SourcePage.text_content` directly from the PDF text stream; OCR only ever writes `SourcePage.ocr_text`/`ocr_used`/`ocr_engine`/`ocr_version` and never touches `text_content`. Verified: native-text docs (e.g. `11MathsPracticePaper2.pdf`, 9567 native chars over 12 pages) retain their full native content; scan PDFs have `native_chars=0` (or header-only ~10 chars on covers) while their `ocr_text` carries the extracted words.

## 7. NVR / image preservation (SourceDocument → SourcePage → SourceAsset → QuestionOccurrence → CanonicalQuestion)

| metric | value |
|---|---|
| SourceAsset rows | 440 |
| asset files present on disk | 440 |
| asset files missing | 0 |
| asset bytes on disk | ~87.1 MB |

Representative asset rows (one per page where applicable):
- `11NVRPaper2.pdf` — 10 pages, **72 assets**, native headers only (7881 chars).
- `9+ Maths Sample Paper 2D.pdf` — 22 pages, **22 assets** (OCR-derived; 1 page OCR-empty).
- `9+ Sample papers 2013 2.pdf` — 16 pages, 10 assets.

`_store_image_asset` is now idempotent on `(sha256, page_id)`; the same embedded image recurring on two pages keeps **one row per page** (page provenance preserved) while the on-disk bytes are shared (verified by unit test + 440 assets / 440 files, 0 missing).

## 8. Answer-link measurements (do NOT infer answers)

| metric | value |
|---|---|
| MCQ candidates (QuestionOccurrence) | 319 |
| occurrences with extracted options | 35 (11%) |
| of which options_json is a real non-empty list | 35 |
| occurrences with options_json = JSON `null` | 284 (89%) |
| occurrences with options_json = `[]` | 0 |
| option sets with >=4 options | 15 |
| occurrences with answer evidence (linked_answer != '') | 283 |
| occurrences without answer evidence | 36 |
| canonical questions promoted | 69 |
| of which retain REAL parsed options | 6 (9%) |
| of which use placeholder options / null | 63 (91%) |
| validation schema "failures" | 0 (validate is promote-or-queue) |
| human-review items queued | 250 |
| approvals | 0 (auto-approve disabled in settings.yaml) |

### Option-count distribution (35 occurrences with real options)
`{2:15, 3:5, 4:3, 5:8, 7:1, 8:1, 12:1, 13:1}`

### Representative real option sets (different formats)
1. 12-option (PPTX, q from `11_Sample_ maths_exam_questions.pptx`): `["A: Write down the length of one side of the square playground.", "B: Find the perimeter of the square.\n..."]
2. 3-option (9+ Sample papers 2013 2, native): A/B/C lettered.
3. 5-option lettered (9+ Maths Sample Paper 2D p5).
4. **Malformed** — 7-option set with shuffled labels: `[{A:"B)"},{C:"A)"},{B:"C)"},{A:"B)"},{C:"A)"},{B:"C)"},{...}]` — option letters out of order. Real ambiguous/malformed set produced by the heuristic on noisy OCR/native text.
5. 2-option (mixed number + word problems).

## 9. Deduplication measurements

| metric | value |
|---|---|
| raw candidates (occurrences) | 319 |
| duplicate groups (fingerprint collisions) | 0 |
| duplicate occurrences | 0 |
| canonical questions (after validate promotion) | 69 |

dedup.py fingerprints each CanonicalQuestion on (question_text, correct_answer) and reports collisions. It found 0 collisions on this sample — validate's canonicalization already collapsed 319 occurrences into 69 distinct questions (each occurrence carries a canonical_question_id). Representative inspected groups: none — there are no duplicate groups to collapse; legitimate variants across documents (e.g. different 9+ maths papers) were NOT incorrectly merged into a single canonical question (69 distinct canonical IDs; 0 collisions confirms no over-collapse).

## 10. End-to-end provenance measurements

| metric | value |
|---|---|
| CanonicalQuestion rows | 69 |
| Canonical questions with full chain SourceDocument->SourcePage->QuestionOccurrence->CanonicalQuestion AND non-null options | 6 |
| Canonical questions with the document->page->occurrence link intact | 69 (all) |
| Canonical questions MISSING occurrence/provenance link | 0 |
| asset files on disk / asset rows | 440 / 440 |

Provenance chain is intact for 100% of the 69 promoted canonical questions (0 missing). The residual gap is content completeness (91% of canonical lack real options), not link integrity.

## 11. First-run vs second-run idempotency (SAME populated DB, validate.py run --tag new2)

| table | before (new2) | after (new2) | delta |
|---|---|---|---|
| documents | 27 | 27 | 0 |
| pages | 175 | 175 | 0 |
| assets | 440 | 440 | 0 |
| occurrences | 319 | 319 | 0 |
| canonical | 69 | 69 | 0 |
| review_rows | 69 | 69 | 0 |
| approved | 0 | 0 | 0 |

new1.after == new2.before == new2.after for EVERY measured table -> idempotent: the second run created zero unintended duplicates. (Source DB validation_new.db, asset dir assets_new, staged dir staged_new.)

## 12. Full test-suite result

python -m pytest --tb=short -q -p no:warnings -> 138 passed, 0 failed. (includes the 5 new idempotency/ocr/mcq/dedup regression tests in tests/test_ocr.py + tests/test_page_extraction.py + tests/test_source_discovery.py.)

## 13. Material failures / limitations observed

1. Option-extraction weakness (BLOCKER for core use case). 284/319 candidates (89%) get options_json=null; only 6/69 canonical (9%) keep real options. Pre-existing (extract_options heuristic), not a regression. Mitigated only by validate's placeholder A-E fallback, so MCQs lack usable option lists. Affects grading/utility of the core product.
2. Malformed option sets. e.g. 9+ Sample papers 2013 2.pdf produced a 7-option set with shuffled labels and garbage text.
3. NVR false answer links. 11NVRPaper2.pdf reports 16 linked answers despite having no answer key; number-based linker produces coincidental matches.
4. 1 empty OCR page (9+ Maths Sample Paper 2D.pdf p2, cover). Not lost — page retained, ocr_text="".
5. CSSE English scans OCR to readable-but-low-fidelity text (e.g. CSSE_English_2007.pdf glyphs render as SSSSSSS...) — usable for keyword/matching but not clean copy. Expected for degraded 2005-era scans.
6. dedup.duplicate=0 is uninformative on this sample because validate canonicalization already de-aliased by canonical_question_id; dedup's fingerprint pass finds no additional exact collisions. It does NOT cross-check questions lacking options (correct_answer defaults to "A"), so duplicate coverage is partial — a latent risk if many option-less questions share bodies.

## 14. Code changes made during this validation (final, live on HEAD)

(Already applied and unit-tested.)
- src/pipeline/ocr.py: _tesseract_version(); ocr_page sets ocr_used=True on attempt and records real engine/version; run_ocr records actual version.
- src/pipeline/extract.py: pymupdf image extraction (info["image"], not info["bytes"]); idempotent per (sha256, page_id) with session.flush() before dedup check; commits at end; skips re-writing existing asset files.
- src/pipeline/detect.py: native text first, OCR text fallback for scanned pages.
- src/pipeline/ingest.py: idempotent zip unpacking (session.flush() + (repo_name, source_path) exists-check), real per-file sha256, session.commit(), correct archives count.
- tests/test_ocr.py: 5 new regression tests (image extract idempotency, same-image across pages provenance, zip ingest idempotency, OCRtext fallback detection, ocr engine/version recording).

## 15. Readiness decision

NOT READY — BLOCKERS REMAIN

Rationale (factual): the pipeline is safe and idempotent — second run produced identical counts across all tables, assets are 100% on disk (440/440), provenance chain is intact (69/69 canonical), and no phantom/duplicate rows were created. OCR on real scans is functional (33/34 success, real usable text captured). However the platform's core deliverable — MCQ questions WITH usable options — is materially broken on real 11+ material: 89% of detected questions have no parsed options (284/319 null; 63/69 canonical carry placeholder/no options), and the answer linker emits spurious answer links on NVR material. Scaling would ingest large volumes of option-less / mis-linked questions that downstream grading/scheduling cannot use. Recommended before scale-up: (a) improve extract_options (better lettered-option regex + OCR-denoising), add regression; (b) gate answer-linking to documents that are actually answer keys (suppress NVR/number-coincidence links). These are targeted fixes, not an architecture redesign.