import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import type { Digest } from "@/lib/digests";
import { ChangeList } from "@/components/change-list";

export default async function DailyDigest({
  params,
}: {
  params: Promise<{ day: string }>;
}) {
  const { day } = await params;
  const [lang, digest] = await Promise.all([
    locale(),
    api<Digest>(`/v1/digests/${encodeURIComponent(day)}`),
  ]);
  return (
    <main id="main" className="page-width standard-page">
      <Link className="back-link" href="/digests">
        ← {lang === "vi" ? "Nhật ký" : "Journal"}
      </Link>
      <div className="page-heading">
        <h1>{digest.date}</h1>
        <p>
          {digest.partial
            ? lang === "vi"
              ? "Bản tin một phần — không bao gồm thời gian máy tính ngủ hoặc nguồn không truy cập được."
              : "Partial digest — sleeping-computer periods and unavailable sources were not collected."
            : lang === "vi"
              ? "Những thay đổi đã ghi nhận trong ngày."
              : "Observed changes from this collection day."}
        </p>
        <p className="fine-print">
          {digest.coverage.completed || 0}/{digest.coverage.scheduled || 5}{" "}
          {lang === "vi"
            ? "lượt hoàn tất · Múi giờ Hà Nội"
            : "runs completed · Hanoi time"}
        </p>
      </div>
      <ChangeList items={digest.items} lang={lang} />
    </main>
  );
}
