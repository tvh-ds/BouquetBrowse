import Link from "next/link";
import { date } from "@/lib/i18n";
import type { Locale } from "@/lib/types";
import type { Change } from "@/lib/digests";

export function ChangeList({ items, lang }: { items: Change[]; lang: Locale }) {
  const names: Record<string, [string, string]> = {
    new_offer: ["Bó hoa mới", "New bouquet offer"],
    advertised_price_update: [
      "Thông tin giá được cập nhật",
      "Advertised price updated",
    ],
    seller_update: ["Thông tin người bán", "Seller profile update"],
    source_access: ["Tình trạng nguồn thay đổi", "Source access changed"],
  };
  if (!items.length)
    return (
      <p className="muted">
        {lang === "vi"
          ? "Chưa có thay đổi phù hợp trong bản tin này."
          : "No eligible changes in this digest."}
      </p>
    );
  return (
    <ol className="change-list">
      {items.map((item) => (
        <li key={item.id}>
          <div>
            <h3>{names[item.kind]?.[lang === "vi" ? 0 : 1] || item.kind}</h3>
            <p className="fine-print">
              {lang === "vi" ? "Ghi nhận" : "Observed"}{" "}
              {date(item.observed_at, lang)}
              {item.advertised_at
                ? ` · ${lang === "vi" ? "Quảng cáo đăng" : "Advertised"} ${date(item.advertised_at, lang)}`
                : ""}
            </p>
          </div>
          <div className="change-actions">
            {item.listing_id && (
              <Link href={`/bouquets/${item.listing_id}`}>
                {lang === "vi" ? "Xem bó hoa" : "View bouquet"}
              </Link>
            )}
            {item.seller_id && (
              <Link href={`/sellers/${item.seller_id}`}>
                {lang === "vi" ? "Người bán" : "Seller"}
              </Link>
            )}
            {item.source_url && (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {lang === "vi" ? "Nguồn" : "Source"}
              </a>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
