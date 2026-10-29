import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { startWeeklyPlan } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { idempotency_key?: unknown } | null;
    if (!body || typeof body.idempotency_key !== "string" || !/^[0-9a-f-]{36}$/i.test(body.idempotency_key)) {
      return jsonError("This learning plan request is invalid.", 400, "invalid_weekly_plan_request");
    }
    return json(await startWeeklyPlan(auth.result.token, body.idempotency_key), 201);
  } catch (error) {
    return handleApiError(error, "We couldn’t start today’s test. Please try again.");
  }
}
