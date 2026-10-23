import type { NextRequest } from "next/server";

export function validOrigin(request: NextRequest) {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  if (!origin) return true;
  if (process.env.APP_MODE === "pilot")
    return origin === process.env.PUBLIC_ORIGIN;
  // Next normalizes loopback URLs to localhost internally. Check the browser's
  // original Host, constrained to loopback, rather than that normalized URL.
  const host = request.headers.get("host");
  return (
    !!host &&
    /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host) &&
    origin === `http://${host}`
  );
}
