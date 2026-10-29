import Link from "next/link";
import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import { date, label, words } from "@/lib/i18n";
import type { Comparison, Detail, Listing, Price } from "@/lib/types";
import { BouquetGrid, BouquetImage, PriceLabel } from "@/components/catalog";
import { CompareButton } from "@/components/controls";
import { Benchmark, PriceHistory } from "@/components/benchmark";
import { Icon } from "@/components/icons";
import { Composition, EvidenceState } from "@/components/evidence-state";
export default async function Bouquet({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [lang, listing, neighbors, compared, history] = await Promise.all([
    locale(),
    api<Detail>(`/v1/listings/${id}`),
    api<{ items: Listing[] }>(`/v1/listings/${id}/similar?limit=4`),
    api<Comparison>(`/v1/listings/${id}/comparison`),
    api<{ items: Price[]; is_demo: boolean }>(
      `/v1/listings/${id}/price-history`,
    ),
  ]);
  const w = words[lang];
  const title =
    lang === "en" && typeof listing.attributes.title_en === "string"
      ? listing.attributes.title_en
      : listing.title;
  return (
    <main id="main" className="page-width standard-page">
      <Link className="back-link" href="/search">
        ← {w.back}
      </Link>
      <div className="detail-layout">
        <div className="detail-photo">
          <BouquetImage listing={listing} priority />
        </div>
        <section className="detail-copy">
          <Link
            className="seller-caption"
            href={`/sellers/${listing.seller.id}`}
          >
            {listing.seller.name} · {listing.seller.district}
          </Link>
          <h1>{title}</h1>
          <p className="detail-intro">
            {lang === "vi"
              ? listing.description
              : `${label(listing.primary_flower, lang)} · ${label(listing.arrangement, lang)}. ${listing.color ? label(listing.color, lang) + ". " : ""}Contact the seller to confirm the advertised details.`}
          </p>
          <PriceLabel listing={listing} lang={lang} />
          <EvidenceState listing={listing} lang={lang} />
          <Composition listing={listing} lang={lang} />
          <p className="fine-print">
            {lang === "vi" ? "Đăng" : "Posted"}{" "}
            {date(listing.published_at, lang)} ·{" "}
            {lang === "vi" ? "Kiểm tra gần nhất" : "Last checked"}{" "}
            {date(listing.last_checked_at, lang)}
          </p>
          <p className="availability">
            <span className="status-dot" />
            {w.askAvailability}
          </p>
          <div className="detail-actions">
            {listing.source_url ? (
              <a
                className="button primary"
                href={listing.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {w.viewSeller}
                <Icon name="external" />
              </a>
            ) : (
              <span className="button muted-button">
                {lang === "vi" ? "Người bán minh họa" : "Demonstration seller"}
              </span>
            )}
            <CompareButton id={id} lang={lang} />
          </div>
          <h2>{w.details}</h2>
          <dl className="attribute-list">
            {[
              [w.flower, label(listing.primary_flower, lang)],
              [w.color, label(listing.color, lang)],
              [
                lang === "vi" ? "Kiểu cắm" : "Arrangement",
                label(listing.arrangement, lang),
              ],
              [
                lang === "vi" ? "Số cành được nêu" : "Stated stems",
                listing.stem_count?.toString() || "—",
              ],
              [
                lang === "vi" ? "Chuẩn bị được nêu" : "Stated preparation",
                listing.availability.lead_days
                  ? `${listing.availability.lead_days} ${lang === "vi" ? "ngày" : "days"}`
                  : "—",
              ],
              [
                lang === "vi" ? "Phong cách" : "Style",
                label(listing.style, lang),
              ],
            ].map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="review-note">
            <Icon name="check" />
            {listing.attributes.extraction_reviewed
              ? w.reviewed
              : lang === "vi"
                ? "Trích xuất chưa được duyệt"
                : "Extraction not reviewed"}
            .{" "}
            {lang === "vi"
              ? "Không phải xác nhận tồn kho."
              : "This does not confirm inventory."}
          </p>
        </section>
      </div>
      <div className="evidence-layout">
        <Benchmark data={compared} lang={lang} />
        <PriceHistory
          items={history.items}
          lang={lang}
          isDemo={history.is_demo}
        />
      </div>
      <section className="source-section">
        <h2>{w.source}</h2>
        <p className="muted">
          {lang === "vi"
            ? "Thông tin gốc được lưu riêng với mô tả do hệ thống tạo."
            : "Original seller information is kept separate from generated descriptions."}
        </p>
        {listing.sources.map((source, index) => (
          <details key={source.version_id} open={index === 0}>
            <summary>
              {source.platform} · {date(source.published_at, lang)}{" "}
              {listing.is_demo
                ? `· ${lang === "vi" ? "Minh họa" : "Demo"}`
                : ""}
            </summary>
            <blockquote>
              {source.caption ||
                (lang === "vi"
                  ? "Nội dung nguồn đã hết thời hạn lưu."
                  : "Source content retention has expired.")}
            </blockquote>
            {source.url && (
              <a
                className="underlined-link"
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {w.viewSeller}
                <Icon name="external" />
              </a>
            )}
          </details>
        ))}
        <details>
          <summary>
            {lang === "vi"
              ? "Nguồn gốc các thuộc tính"
              : "Field-level provenance"}
          </summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Origin</th>
                  <th>Confidence</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {listing.assertions.map((a) => (
                  <tr key={a.id}>
                    <td>{a.field}</td>
                    <td>{String(a.value.value ?? "Unknown")}</td>
                    <td>{a.status}</td>
                    <td>{a.calibrated_confidence ?? "Not calibrated"}</td>
                    <td>{a.review_state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <section className="related-section">
        <div className="section-heading">
          <div>
            <h2>{w.similar}</h2>
            <p>{w.similarNote}</p>
          </div>
        </div>
        <BouquetGrid items={neighbors.items} lang={lang} />
      </section>
    </main>
  );
}
