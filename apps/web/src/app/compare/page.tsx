import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import { label, words } from "@/lib/i18n";
import type { Comparison, Detail } from "@/lib/types";
import { BouquetImage, PriceLabel } from "@/components/catalog";
import { CompareButton } from "@/components/controls";
import { Benchmark, Distribution } from "@/components/benchmark";
export default async function Compare({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string }>;
}) {
  const { ids: input } = await searchParams;
  const ids = [
    ...new Set(
      (input || "").split(",").filter((id) => /^[a-f0-9-]{36}$/i.test(id)),
    ),
  ].slice(0, 4);
  const lang = await locale();
  const vi = lang === "vi";
  if (!ids.length)
    return (
      <main id="main" className="page-width standard-page empty-state">
        <h1>
          {vi
            ? "Đặt những lựa chọn cạnh nhau."
            : "A little side-by-side perspective."}
        </h1>
        <p>
          {vi
            ? "Chọn tối đa bốn bó hoa bằng nút + trong bộ sưu tập, sau đó mở khay so sánh bên dưới."
            : "Choose up to four bouquets with the + button in the catalog, then open the comparison tray below."}
        </p>
        <Link href="/search" className="button primary">
          {words[lang].browse}
        </Link>
      </main>
    );
  const listings = await Promise.all(
    ids.map((id) => api<Detail>(`/v1/listings/${id}`)),
  );
  const compared = await api<Comparison>(`/v1/listings/${ids[0]}/comparison`);
  return (
    <main id="main" className="page-width standard-page">
      <div className="page-heading">
        <h1>{vi ? "So sánh có cơ sở." : "Compare with a little clarity."}</h1>
        <p>
          {vi
            ? "Đẹp tương tự chưa chắc là sản phẩm tương đương. Xem cả cấu hình và bằng chứng giá."
            : "Looking alike does not make two bouquets equivalent. Compare the configuration and the price evidence."}
        </p>
      </div>
      <div className="comparison-grid">
        {listings.map((l) => (
          <article className="comparison-column" key={l.id}>
            <Link className="comparison-photo" href={`/bouquets/${l.id}`}>
              <BouquetImage listing={l} />
            </Link>
            <Link className="seller-caption" href={`/sellers/${l.seller.id}`}>
              {l.seller.name}
            </Link>
            <h2>
              <Link href={`/bouquets/${l.id}`}>
                {lang === "en" && typeof l.attributes.title_en === "string"
                  ? l.attributes.title_en
                  : l.title}
              </Link>
            </h2>
            <PriceLabel listing={l} lang={lang} />
            <dl className="attribute-list">
              {[
                [words[lang].flower, label(l.primary_flower, lang)],
                [words[lang].color, label(l.color, lang)],
                [
                  vi ? "Số cành được nêu" : "Stated stems",
                  l.stem_count?.toString() || "—",
                ],
                [
                  vi ? "Chuẩn bị" : "Preparation",
                  l.availability.lead_days
                    ? `${l.availability.lead_days} ${vi ? "ngày" : "days"}`
                    : "—",
                ],
                [
                  vi ? "Tình trạng" : "Availability",
                  vi ? "Hỏi người bán" : "Ask seller",
                ],
              ].map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <CompareButton id={l.id} lang={lang} comparisonIds={ids} />
          </article>
        ))}
      </div>
      <div className="evidence-layout">
        <Benchmark data={compared} lang={lang} />
        <Distribution data={compared} lang={lang} />
      </div>
      <p className="fine-print">
        {vi
          ? "Nhóm tham khảo được tính cho bó hoa đầu tiên, độc lập với những sản phẩm bạn chọn thủ công."
          : "The reference cohort is calculated for the first bouquet, independently of your manually selected products."}
      </p>
    </main>
  );
}
