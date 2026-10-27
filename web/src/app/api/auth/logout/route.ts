import { verifyMutation } from "@/lib/auth";
import { authenticated, handleApiError, json } from "@/lib/api-server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    return json({ signedOut: true });
  } catch (error) {
    return handleApiError(error, "We couldn’t sign you out just now. Please try again.");
  }
}
