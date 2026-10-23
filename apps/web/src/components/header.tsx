import Link from "next/link";
import { session } from "@/lib/api";
import { words } from "@/lib/i18n";
import type { Locale } from "@/lib/types";
import { LocaleSwitch, Logout } from "./controls";
import { Icon } from "./icons";
export async function Header({ lang }: { lang: Locale }) {
  const user = await session();
  const w = words[lang];
  return (
    <>
      <header className="site-header">
        <div className="header-inner">
          <Link href="/" className="brand" aria-label="BouquetBrowse home">
            <span className="brand-mark">
              <Icon name="leaf" />
            </span>
            <span>
              Bouquet<span className="brand-light">Browse</span>
            </span>
          </Link>
          <nav aria-label="Main navigation">
            {user && (
              <>
                <Link href="/">{w.discover}</Link>
                <Link href="/compare">{w.compare}</Link>
                <Link href="/analytics">{w.analytics}</Link>
                {["admin", "reviewer"].includes(user.role) && (
                  <Link href="/admin">{w.admin}</Link>
                )}
              </>
            )}
          </nav>
          <div className="header-actions">
            <span className="location">
              <Icon name="pin" />
              Hà Nội
            </span>
            <LocaleSwitch lang={lang} />
            {user && <Logout lang={lang} />}
          </div>
        </div>
      </header>
      {user && (
        <div className="research-strip">
          <span className="status-dot" />
          {user.mode === "demo"
            ? w.demo
            : lang === "vi"
              ? "Nghiên cứu riêng tư · Chỉ dành cho người được mời"
              : "Private research · Invited participants only"}
        </div>
      )}
    </>
  );
}
