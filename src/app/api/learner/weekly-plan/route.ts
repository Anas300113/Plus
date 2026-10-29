import { authenticated, handleApiError, json } from "@/lib/api-server";
import { getWeeklyPlan } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    return json(await getWeeklyPlan(auth.result.token));
  } catch (error) {
    return handleApiError(error, "We couldn’t load today’s learning plan. Please try again.");
  }
}
