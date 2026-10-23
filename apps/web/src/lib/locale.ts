import "server-only";
import { cookies } from "next/headers";
import type { Locale } from "./types";
export async function locale(): Promise<Locale> {
  return (await cookies()).get("bb_locale")?.value === "en" ? "en" : "vi";
}
