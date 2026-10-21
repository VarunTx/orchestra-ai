import { allowedOrigin } from "@/lib/origin";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { API_URL as API } from "@/lib/server-config";
async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  // Explicit allowlist: new resource APIs must be added deliberately.
  const allowed = new Set([
    "workflows",
    "executions",
    "infrastructure",
    "schedules",
    "dashboard",
    "projects",
    "environments",
    "clusters",
    "services",
    "deployments",
    "incidents",
    "alerts",
    "notifications",
    "connectors",
    "audit",
    "settings",
    "work",
    "releases",
  ]);
  if (!allowed.has(path[0]))
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  if (req.method !== "GET" && !allowedOrigin(req))
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const token = (await cookies()).get("cp_session")?.value;
  if (!token)
    return NextResponse.json(
      { detail: "Sign in to your control plane" },
      { status: 401 },
    );
  try {
    const response = await fetch(
      `${API}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`,
      {
        method: req.method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: req.method === "GET" ? undefined : await req.text(),
        signal: AbortSignal.timeout(45000),
        cache: "no-store",
      },
    );
    const body = await response.text();
    return new NextResponse(response.status === 204 ? null : body, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Control-plane API unavailable" },
      { status: 503 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PATCH,
  proxy as DELETE,
  proxy as PUT,
};
