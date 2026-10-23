import { NextRequest, NextResponse } from "next/server";
import { validOrigin } from "@/lib/request-origin";
const base = process.env.API_URL || "http://127.0.0.1:8000";
function localDemo(request: NextRequest) {
  if (
    process.env.APP_MODE !== "pilot" &&
    !["localhost", "127.0.0.1", "[::1]"].includes(request.nextUrl.hostname)
  )
    return false;
  return true;
}
async function handle(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  if (!localDemo(request))
    return NextResponse.json(
      { error: { message: "Demo mode is available only on localhost." } },
      { status: 403 },
    );
  const path = (await params).path.join("/");
  if (
    !/^(v1\/[a-zA-Z0-9_\-/]+|auth\/(login|refresh|logout|config))$/.test(path)
  )
    return new NextResponse(null, { status: 404 });
  if (request.method !== "GET") {
    if (!validOrigin(request)) return new NextResponse(null, { status: 403 });
    if (!request.headers.get("content-type")?.startsWith("application/json"))
      return NextResponse.json(
        { error: { message: "Use application/json." } },
        { status: 415 },
      );
  }
  if (path === "auth/logout") {
    const result = NextResponse.json({ ok: true });
    result.cookies.delete("bb_access");
    result.cookies.delete("bb_refresh");
    return result;
  }
  const headers: Record<string, string> = {
    "X-Bouquet-Proxy":
      process.env.INTERNAL_API_TOKEN || "localhost-proxy-demo-token",
    Authorization: `Bearer ${request.cookies.get("bb_access")?.value || ""}`,
    "Content-Type": "application/json",
  };
  const idempotency = request.headers.get("idempotency-key");
  if (idempotency) headers["Idempotency-Key"] = idempotency;
  let body: ArrayBuffer | undefined;
  if (request.method !== "GET") {
    body = await request.arrayBuffer();
    if (body.byteLength > 5 * 1024 * 1024)
      return NextResponse.json(
        { error: { message: "Import exceeds 5 MB." } },
        { status: 413 },
      );
  }
  if (path === "auth/refresh") {
    const refresh = request.cookies.get("bb_refresh")?.value;
    if (!refresh)
      return NextResponse.json(
        { error: { message: "Sign in again." } },
        { status: 401 },
      );
    body = new TextEncoder().encode(JSON.stringify({ refresh_token: refresh }))
      .buffer as ArrayBuffer;
  }
  try {
    const response = await fetch(`${base}/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(45000),
    });
    if ((path === "auth/login" || path === "auth/refresh") && response.ok) {
      const data = await response.json();
      const result = NextResponse.json({ ok: true });
      const opts = {
        httpOnly: true,
        secure: process.env.APP_MODE === "pilot",
        sameSite: "lax" as const,
        path: "/",
      };
      result.cookies.set("bb_access", data.access_token, {
        ...opts,
        maxAge: data.expires_in || 3600,
      });
      if (data.refresh_token)
        result.cookies.set("bb_refresh", data.refresh_token, {
          ...opts,
          maxAge: 86400 * 7,
        });
      return result;
    }
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "api_unavailable",
          message: "The catalog service is unavailable. Please try again.",
        },
      },
      { status: 503 },
    );
  }
}
export const GET = handle;
export const POST = handle;
