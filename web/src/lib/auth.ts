import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import { AppError } from "@/lib/errors";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type LearnerSession = {
  userId: string;
  name: string;
};

function extraAllowedOrigins(): string[] {
  return (process.env.PLUS11_AUTH_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function isAllowedPublicOrigin(raw: string): boolean {
  let candidate: URL;
  try {
    candidate = new URL(raw);
  } catch {
    return false;
  }
  if (candidate.username || candidate.password || candidate.pathname !== "/" || candidate.search || candidate.hash) return false;
  const origin = candidate.origin;
  if (extraAllowedOrigins().some((allowed) => {
    try { return new URL(allowed).origin === origin && new URL(allowed).pathname === "/"; } catch { return false; }
  })) return candidate.protocol === "https:";
  const localHost = candidate.hostname === "localhost" || candidate.hostname === "127.0.0.1" || candidate.hostname === "[::1]";
  return localHost && candidate.protocol === "http:";
}

export function validatedRequestOrigin(request: Request): URL {
  const raw = request.headers.get("origin");
  if (!raw || !isAllowedPublicOrigin(raw)) throw new AppError("This request origin is not allowed.", 403, "invalid_origin");
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new AppError("Cross-site state changes are not allowed.", 403, "cross_site_request");
  return new URL(raw);
}

export async function getLearnerSession(_request: Request): Promise<{ session: LearnerSession; token: string } | null> {
  void _request;
  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } = await supabase.auth.getClaims();
  if (claimsError || !claimsData?.claims) return null;
  const claims = claimsData.claims;
  if (typeof claims.sub !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(claims.sub)) return null;
  if (claims.role !== "authenticated" || claims.aud !== "authenticated") return null;

  // Only read the access token after getClaims() has verified the cookie JWT.
  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  const session = sessionData.session;
  if (sessionError || !session || session.user.id !== claims.sub || !session.access_token) return null;
  const metadata = claims.user_metadata;
  const candidate = metadata && typeof metadata === "object" && "display_name" in metadata
    ? metadata.display_name
    : metadata && typeof metadata === "object" && "full_name" in metadata
      ? metadata.full_name
      : "Learner";
  const name = typeof candidate === "string" && candidate.trim() ? candidate.trim().slice(0, 80) : "Learner";
  return { session: { userId: claims.sub, name }, token: session.access_token };
}

export function csrfToken(sessionToken: string): string {
  return createHmac("sha256", sessionToken).update("plus11-csrf-v1").digest("base64url");
}

export function verifyMutation(request: Request, sessionToken: string): URL {
  const origin = validatedRequestOrigin(request);
  const supplied = request.headers.get("x-plus11-csrf");
  if (!supplied) throw new AppError("A valid request token is required. Refresh the page and try again.", 403, "csrf_required");
  const expectedBytes = Buffer.from(csrfToken(sessionToken));
  const suppliedBytes = Buffer.from(supplied);
  if (expectedBytes.length !== suppliedBytes.length || !timingSafeEqual(expectedBytes, suppliedBytes)) {
    throw new AppError("A valid request token is required. Refresh the page and try again.", 403, "csrf_invalid");
  }
  return origin;
}
