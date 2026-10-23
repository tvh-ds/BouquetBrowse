"use client";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { Locale } from "@/lib/types";
import { words } from "@/lib/i18n";
import { Icon } from "./icons";

function subscribe(callback: () => void) {
  window.addEventListener("bb-compare", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("bb-compare", callback);
    window.removeEventListener("storage", callback);
  };
}
function snapshot() {
  try {
    return localStorage.getItem("bb-compare") || "[]";
  } catch {
    return "[]";
  }
}
function useSelection() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => "[]");
  let ids: string[] = [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed))
      ids = parsed
        .filter((id): id is string => typeof id === "string")
        .slice(0, 4);
  } catch {}
  return ids;
}
function save(ids: string[]) {
  try {
    localStorage.setItem("bb-compare", JSON.stringify(ids));
    window.dispatchEvent(new Event("bb-compare"));
  } catch {}
}
export function CompareButton({
  id,
  lang = "vi",
  compact = false,
  comparisonIds,
}: {
  id: string;
  lang?: Locale;
  compact?: boolean;
  comparisonIds?: string[];
}) {
  const ids = useSelection();
  const router = useRouter();
  const selected = (comparisonIds || ids).includes(id);
  const [message, setMessage] = useState("");
  return (
    <span className="compare-control">
      <button
        type="button"
        className={
          compact
            ? `icon-button card-compare ${selected ? "selected" : ""}`
            : `button ${selected ? "secondary" : "outline"}`
        }
        aria-label={
          selected ? words[lang].removeCompare : words[lang].addCompare
        }
        aria-pressed={selected}
        onClick={() => {
          if (selected) {
            const next = (comparisonIds || ids).filter((i) => i !== id);
            save(next);
            if (comparisonIds)
              router.replace(`/compare?ids=${next.join(",")}`, {
                scroll: false,
              });
            setMessage("");
          } else if (ids.length < 4) {
            save([...ids, id]);
            setMessage("");
          } else {
            setMessage(
              lang === "vi"
                ? "Chọn tối đa 4 bó hoa."
                : "Compare up to four bouquets.",
            );
          }
        }}
      >
        <Icon name={selected ? "check" : "plus"} />
        {!compact &&
          (selected ? words[lang].removeCompare : words[lang].addCompare)}
      </button>
      {message && (
        <span role="status" className="selection-message">
          {message}
        </span>
      )}
    </span>
  );
}
export function CompareTray({ lang }: { lang: Locale }) {
  const ids = useSelection();
  const router = useRouter();
  const pathname = usePathname();
  if (!ids.length) return null;
  return (
    <aside className="compare-tray" aria-label={words[lang].compare}>
      <div>
        <strong>{ids.length}/4</strong>{" "}
        <span>{lang === "vi" ? "bó hoa đã chọn" : "bouquets selected"}</span>
      </div>
      <Link className="button primary" href={`/compare?ids=${ids.join(",")}`}>
        {words[lang].compare}
        <Icon name="arrow" />
      </Link>
      <button
        className="icon-button"
        type="button"
        aria-label={words[lang].clear}
        onClick={() => {
          save([]);
          if (pathname === "/compare") router.replace("/compare");
        }}
      >
        <Icon name="close" />
      </button>
    </aside>
  );
}
export function LocaleSwitch({ lang }: { lang: Locale }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="locale-button"
      type="button"
      disabled={busy}
      aria-label={
        lang === "vi" ? "Switch to English" : "Chuyển sang tiếng Việt"
      }
      onClick={async () => {
        setBusy(true);
        try {
          await fetch("/api/locale", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lang: lang === "vi" ? "en" : "vi" }),
          });
          router.refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      {lang === "vi" ? "EN" : "VI"}
    </button>
  );
}
export function Logout({ lang }: { lang: Locale }) {
  const router = useRouter();
  return (
    <button
      className="text-button"
      type="button"
      onClick={async () => {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        save([]);
        router.push("/login");
        router.refresh();
      }}
    >
      {words[lang].signOut}
    </button>
  );
}
