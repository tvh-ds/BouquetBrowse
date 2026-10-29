import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import type { Digest } from "@/lib/digests";

export default async function Digests() {
  const [lang, data] = await Promise.all([
    locale(),
    api<{ items: Digest[] }>("/v1/digests"),
  ]);
  const vi = lang === "vi";
  return (
    <main id="main" className="page-width standard-page">
      <div className="page-heading">
        <h1>{vi ? "Nhật ký những bó hoa." : "The bouquet journal."}</h1>
        <p>
          {vi
            ? "Những thay đổi đã ghi nhận, theo ngày Hà Nội. Mỗi bản tin giữ rõ phạm vi thu thập và nguồn thông tin."
            : "Observed changes by Hanoi calendar date, with collection coverage and original sources."}
        </p>
      </div>
      {!data.items.length ? (
        <section className="empty-state">
          <h2>{vi ? "Chưa có bản tin." : "No digests yet."}</h2>
          <p>
            {vi
              ? "Bản tin xuất hiện sau khi một ngày thu thập kết thúc. Không có dữ liệu thu thập trực tiếp nào được mô phỏng ở đây."
              : "A digest appears after a collection day closes. No live collection is simulated here."}
          </p>
          <Link className="button outline" href="/search">
            {vi ? "Khám phá bó hoa" : "Explore bouquets"}
          </Link>
        </section>
      ) : (
        <ol className="change-list">
          {data.items.map((item) => (
            <li key={item.date}>
              <div>
                <h2>
                  <Link href={`/digests/${item.date}`}>{item.date}</Link>
                </h2>
                <p>
                  {item.partial
                    ? vi
                      ? "Thu thập một phần"
                      : "Partial collection"
                    : vi
                      ? "Ngày thu thập đã kết thúc"
                      : "Collection day closed"}
                </p>
                <p className="muted">
                  {item.coverage.completed || 0}/{item.coverage.scheduled || 5}{" "}
                  {vi ? "lượt đã hoàn tất" : "runs completed"}
                </p>
              </div>
              <Link className="button outline" href={`/digests/${item.date}`}>
                {vi ? "Đọc bản tin" : "Read digest"}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
