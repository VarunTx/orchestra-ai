import type { NextRequest } from "next/server";
// Pin the public origin explicitly: Next standalone normalizes nextUrl to its bind host.
// Never trust arbitrary forwarded headers for CSRF decisions.
export function allowedOrigin(req: NextRequest) {
  const configured =
    process.env.APP_ORIGINS ||
    process.env.RENDER_EXTERNAL_URL ||
    (process.env.DEPLOYMENT_ENVIRONMENT === "hosted"
      ? ""
      : "http://localhost:3000,http://127.0.0.1:3000");
  return configured
    .split(",")
    .map((s) => s.trim())
    .includes(req.headers.get("origin") || "");
}
