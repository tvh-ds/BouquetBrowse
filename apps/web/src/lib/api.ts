import "server-only";
import { cookies } from "next/headers";
import { redirect, notFound } from "next/navigation";
const base = process.env.API_URL || "http://127.0.0.1:8000";
export async function api<T>(path: string): Promise<T> {
  const jar = await cookies();
  const response = await fetch(base + path, {
    headers: {
      Authorization: `Bearer ${jar.get("bb_access")?.value || ""}`,
      "X-Bouquet-Proxy":
        process.env.INTERNAL_API_TOKEN || "localhost-proxy-demo-token",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (response.status === 401) redirect("/login");
  if (response.status === 404) notFound();
  if (response.status === 403)
    throw new Error("This account does not have access to this operation.");
  if (!response.ok)
    throw new Error(
      `The catalog is unavailable (${response.status}). Please try again.`,
    );
  return response.json();
}
export async function session() {
  const token = (await cookies()).get("bb_access")?.value;
  if (!token) return null;
  const response = await fetch(base + "/v1/session", {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Bouquet-Proxy":
        process.env.INTERNAL_API_TOKEN || "localhost-proxy-demo-token",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  return response.ok
    ? (response.json() as Promise<import("./types").Session>)
    : null;
}
