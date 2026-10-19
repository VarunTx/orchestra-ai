import { API_URL } from "@/lib/server-config";
import { allowedOrigin } from "@/lib/origin";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
export async function POST(req: NextRequest) {
  if (!allowedOrigin(req))
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  try {
    const { token } = await req.json();
    if (typeof token !== "string" || token.length < 32 || token.length > 256)
      return NextResponse.json(
        { detail: "Enter a valid control-plane token" },
        { status: 401 },
      );
    const response = await fetch(`${API_URL}/api/session`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok)
      return NextResponse.json(
        {
          detail:
            response.status === 401
              ? "Invalid control-plane token"
              : "API unavailable",
        },
        { status: response.status },
      );
    (await cookies()).set("cp_session", token, {
      httpOnly: true,
      sameSite: "strict",
      secure:
        process.env.COOKIE_SECURE === "true" ||
        req.nextUrl.protocol === "https:",
      path: "/",
      maxAge: 28800,
    });
    return NextResponse.json({ authenticated: true });
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
  (await cookies()).delete("cp_session");
  return NextResponse.json({ authenticated: false });
}
