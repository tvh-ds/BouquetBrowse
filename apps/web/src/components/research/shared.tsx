"use client";
import { useCallback, useEffect, useState } from "react";
import type { Locale } from "@/lib/types";

export interface PanelProps {
  lang: Locale;
  refresh: number;
  onChange?: () => void;
}
export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/v1/${path}`,
    body === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message ||
        "Operation failed. Reload current evidence and try again.",
    );
  return data;
}
export function useData<T>(path: string | null, refresh: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!path) return;
    let active = true;
    request<T>(path)
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error
              ? error.message
              : "Could not load this workspace.",
          );
      });
    return () => {
      active = false;
    };
  }, [path, refresh, revision]);
  const reload = useCallback(() => setRevision((n) => n + 1), []);
  return { data, error, reload };
}
export function useAction(onChange?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function perform(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      onChange?.();
      setNotice(message);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Operation failed.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, notice, perform };
}
export function Feedback({
  error,
  notice,
}: {
  error?: string;
  notice?: string;
}) {
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
    </>
  );
}
export function Loading({ error }: { error: string }) {
  return error ? (
    <Feedback error={error} />
  ) : (
    <p role="status">Loading workspace…</p>
  );
}
export function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 3,
  }).format(value / 1_000_000);
}
export function date(value: string | null) {
  return value
    ? new Date(value).toLocaleString(undefined, {
        timeZone: "Asia/Ho_Chi_Minh",
      })
    : "Unknown";
}
export function short(value: string) {
  return value.slice(0, 8);
}
export function lines(value: FormDataEntryValue | null) {
  return String(value || "")
    .split(/[,\n]/)
    .map((v) => v.trim())
    .filter(Boolean);
}
