# ADR-002: Student identity and data ownership

- **Status:** Accepted (Phase 1 implemented; Phase 2 is the target design)
- **Date:** 2026-10-15
- **Gate:** Master Engineering Quality Gate — student identity / ownership (§6)

## Context

Student-scoped routes (`/api/progress/{id}`, `/api/parent/{id}`,
`/api/statistics/{id}`, `/api/reviews/{id}`, `/api/recommendations/{id}`,
`/api/loop/{id}`, `/api/attempts`, and the seven `/api/sessions/...` routes)
take a bare `student_id` (path, query, or body). There is **no user/identity
model** in the platform, so ownership was never enforced by default.

The existing guard (`PLUS_REQUIRE_STUDENT_IDENTITY`) requires an
`X-Student-Id` header equal to the owning student. This is explicitly **not
authentication**: the header is caller-supplied, so an attacker who knows or
guesses a victim's id echoes it in both header and URL and is served the
victim's data. The code (`src/api/main.py`) and the regression tests
(`tests/test_student_identity.py`) document this gap deliberately so it
cannot be mistaken for a verified boundary.

**Consequence:** with the platform holding real student data, anyone who knows
an id can read another student's progress, attempts, parent dashboard, and
learning record, and can plant sessions attributed to them. This is
release-blocking for real student data.

## Decision

We separate two concerns that were previously conflated:

1. **Immediate (Phase 1, implemented here): make the absence of authentication
   loud instead of silently insecure.** A new explicit switch,
   `PLUS_REAL_STUDENT_DATA`, declares "this deployment holds real student
   data." When set, every student-scoped route **fails closed with HTTP 503**
   — the same posture `require_reviewer()` already uses when
   `PLUS_REVIEWER_TOKEN` is unset — because no server-verified student
   identity exists yet. This does **not** implement authentication; it stops
   the platform from silently exposing real student data behind a spoofable
   header. Default (unset) preserves current behaviour for the stateless demo
   UI and the frozen test suite.

2. **Target (Phase 2, design only — do not rush-build): a real, server-verified
   student principal.** See below.

## Phase 2 target design (not yet implemented)

- **Issue an identity at a trust boundary.** A student obtains a credential
  only through an authenticated event (initial enrolment / login). The server
  issues a **signed session token** (JWT or server-side session id) whose
  payload carries the canonical `student_id`. Signing key lives server-side
  only.
- **Derive, never accept.** On each request the server resolves the principal
  from the verified token (signature + expiry checked) and uses *that*
  `student_id`. The `X-Student-Id` header and any caller-supplied id in
  path/body/query are **ignored for authorization** (they may remain for
  routing/display but never decide ownership).
- **Parent access** binds to a distinct parent principal mapped to its
  students server-side; a bare student id must never grant parent view.
- **Session cookie** (`HttpOnly`, `Secure`, `SameSite=Lax`) for the browser
  UI; **bearer token** for API clients. Both carry the same signed claim.
- **Migration:** existing rows are keyed by opaque `student_id` strings and are
  compatible; the mapping id → principal is created at first authenticated
  login. No destructive schema change. Until a student authenticates, their
  data is unreachable (fail-closed), which is the safe state.

## Consequences

- Real-data deployments cannot accidentally expose student data: they get a
  loud 503, not a silent cross-student leak.
- The demo/dev path is unchanged (flag off).
- The platform is **still not production-secure for real student data** until
  Phase 2 ships. Phase 1 removes the *silent* failure mode; it does not grant
  a security guarantee. The `..._is_NOT_prevented` tests remain as pinning of
  that residual gap and must be flipped to assert protection when Phase 2 lands.

## Alternatives considered

- **Flip `PLUS_REQUIRE_STUDENT_IDENTITY` on by default.** Rejected: it still
  compares a spoofable header to a spoofable id, so it adds friction without
  adding security, while breaking the demo UI.
- **Build full OIDC/login now.** Rejected for this gate: a rushed identity
  system is security theater and risks worse errors than an honest, documented
  gap. It is the right Phase 2, with proper review.
