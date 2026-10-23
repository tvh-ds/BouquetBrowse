import type { Metadata } from "next";
import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource/be-vietnam-pro/700.css";
import "@fontsource/bodoni-moda/500.css";
import "@fontsource/bodoni-moda/500-italic.css";
import "./globals.css";
import { locale } from "@/lib/locale";
import { words } from "@/lib/i18n";
import { Header } from "@/components/header";
import { CompareTray } from "@/components/controls";
export const metadata: Metadata = {
  title: {
    default: "BouquetBrowse · Finding your flowers",
    template: "%s · BouquetBrowse",
  },
  description:
    "Discover Hanoi bouquets and evidence-qualified advertised-price comparisons.",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const lang = await locale();
  return (
    <html lang={lang}>
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <Header lang={lang} />
        {children}
        <footer className="site-footer">
          <div>
            <span className="footer-brand">BouquetBrowse</span>
            <p>{words[lang].footer}</p>
          </div>
          <p>
            {words[lang].footerNote}
            <br />
            <span>Hà Nội, Việt Nam · Research pilot</span>
          </p>
        </footer>
        <CompareTray lang={lang} />
      </body>
    </html>
  );
}
