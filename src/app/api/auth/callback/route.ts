import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedPublicOrigin } from "@/lib/auth";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const origin = url.origin;
  if (!isAllowedPublicOrigin(origin)) {
    return new Response("This callback origin is not allowed.", { status: 403 });
  }

  const code = url.searchParams.get("code");
  const destination = new URL("/account", origin);
  if (code && code.length <= 4096) {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    destination.searchParams.set("auth", error ? "error" : "success");
  } else {
    destination.searchParams.set("auth", "error");
  }

  const response = NextResponse.redirect(destination, { status: 303 });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
