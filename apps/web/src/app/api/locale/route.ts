import { NextRequest, NextResponse } from "next/server";
import { validOrigin } from "@/lib/request-origin";
export async function POST(request: NextRequest) {
  if (!validOrigin(request)) return new NextResponse(null, { status: 403 });
  const { lang } = await request.json();
  if (!["vi", "en"].includes(lang))
    return new NextResponse(null, { status: 422 });
  const result = NextResponse.json({ ok: true });
  result.cookies.set("bb_locale", lang, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.APP_MODE === "pilot",
    path: "/",
    maxAge: 86400 * 365,
  });
  return result;
}
