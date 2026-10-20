import { API_URL } from "@/lib/server-config";
import { allowedOrigin } from "@/lib/origin";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const COOKIE = "cp_session";

function secureCookie(req: NextRequest) {
  return process.env.COOKIE_SECURE === "true" || req.nextUrl.protocol === "https:";
}

/** Exchange the owner password (or master API token) for an opaque server-side session. */
export async function POST(req: NextRequest) {
  if (!allowedOrigin(req))
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  let credential: unknown;
  try {
    ({ credential } = await req.json());
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  if (typeof credential !== "string" || credential.length < 8 || credential.length > 500)
    return NextResponse.json(
      { detail: "Enter your owner password or API token" },
      { status: 401 },
    );
  try {
    const response = await fetch(`${API_URL}/api/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
      signal: AbortSignal.timeout(10000),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok)
      return NextResponse.json(
        {
          detail:
            response.status === 401
              ? "Invalid password or API token"
              : response.status === 429
                ? "Too many attempts. Wait a minute and retry."
                : "API unavailable",
        },
        { status: response.status },
      );
    (await cookies()).set(COOKIE, String(payload.session_token), {
      httpOnly: true,
      sameSite: "strict",
      secure: secureCookie(req),
      path: "/",
      maxAge: 60 * 60 * 8,
    });
    return NextResponse.json({ authenticated: true, method: payload.method });
  } catch {
    return NextResponse.json(
      { detail: "Unable to connect to the API" },
      { status: 503 },
    );
  }
}

export async function DELETE(req: NextRequest) {
  if (!allowedOrigin(req))
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const token = (await cookies()).get(COOKIE)?.value;
  if (token) {
    await fetch(`${API_URL}/api/session`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    }).catch(() => undefined);
  }
  (await cookies()).delete(COOKIE);
  return NextResponse.json({ authenticated: false });
}

/** Confirm the HTTP-only session is still valid server-side. */
export async function GET() {
  // Safe method: no Origin header is sent by browsers on same-origin GET.
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token)
    return NextResponse.json({ authenticated: false }, { status: 401 });
  try {
    const response = await fetch(`${API_URL}/api/session`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });
    if (!response.ok) {
      (await cookies()).delete(COOKIE);
      return NextResponse.json({ authenticated: false }, { status: 401 });
    }
    return NextResponse.json({ authenticated: true });
  } catch {
    return NextResponse.json({ detail: "API unavailable" }, { status: 503 });
  }
}
