# Attribution — 11plus-prep reference material

The files in this directory are **verbatim, unmodified copies** from the
upstream repository, retained for structural reference only (regional
metadata mapping and staged-learning-plan concept mapping). They are not
wired into any Plus runtime code path.

- Source repository: https://github.com/SahirVhora/11plus-prep
- Source commit: `d970c16614c95140dc946bd3f8f320aeef4a69f3` (audited 2026-10-12)
- Licence: MIT License, Copyright (c) 2026 Sahir Vhora (full text: `LICENSE`)
- Files:
  - `regions.ts` — regional configuration metadata (exam boards, subjects,
    registration/test periods, school lists, tips)
  - `staged-learning-plan.md` — five-stage learning progression document

Important caveats carried over from the source and audit:

- Regional information (registration windows, test formats, school lists)
  is **indicative, undated source-supplied metadata**, not confirmed current
  admissions policy. It must be re-verified against official sources before
  being shown to families.
- The `regions.ts` configuration declares a `london` question bank that does
  NOT exist upstream (`src/data/questions/london.json` is missing at the
  audited commit). London coverage must not be claimed.
- The 75% threshold and session durations in the staged plan are **attributed
  source recommendations**, not validated educational rules.
