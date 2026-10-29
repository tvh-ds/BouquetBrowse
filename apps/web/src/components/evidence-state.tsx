import { label } from "@/lib/i18n";
import type { Listing, Locale } from "@/lib/types";

export function EvidenceState({
  listing,
  lang,
}: {
  listing: Listing;
  lang: Locale;
}) {
  const vi = lang === "vi";
  return (
    <div className="evidence-status">
      {listing.source_state && listing.source_state !== "accessible" && (
        <p>
          {vi
            ? "Nguồn hiện không truy cập được. Đây không phải xác nhận đã hết hàng."
            : "The source is currently unavailable. This does not mean sold out."}
        </p>
      )}
      {listing.updating && (
        <p role="status">
          {vi
            ? "Đang cập nhật — đang hiển thị phiên bản hoàn tất gần nhất."
            : "Updating — showing the last completed revision."}
        </p>
      )}
      {listing.state === "provisional" && (
        <p>
          {vi
            ? "Thông tin tạm thời · Chưa đủ điều kiện so sánh giá chuẩn."
            : "Provisional listing · Excluded from qualified price benchmarks."}
        </p>
      )}
      {listing.capture_complete === false && (
        <p>
          {vi
            ? "Đã thu thập một phần hội thoại; có thể còn câu trả lời khác."
            : "Partial conversation capture; more replies may exist."}
        </p>
      )}
      {listing.offer_type === "recreation_quote" && (
        <p>
          {vi
            ? "Báo giá làm theo mẫu. Ảnh tham khảo không phải sản phẩm đã hoàn thành của người bán."
            : "Made-to-order quotation. Reference imagery is not the seller’s completed work."}
        </p>
      )}
    </div>
  );
}

export function Composition({
  listing,
  lang,
  compact = false,
}: {
  listing: Listing;
  lang: Locale;
  compact?: boolean;
}) {
  if (!listing.composition.length) return null;
  const components = listing.composition.filter(
    (component, index, all) =>
      all.findIndex(
        (c) => c.flower === component.flower && c.status === component.status,
      ) === index,
  );
  return (
    <ul
      className={compact ? "composition-inline" : "composition-list"}
      aria-label={lang === "vi" ? "Thành phần hoa" : "Flower composition"}
    >
      {components.map((component, index) => {
        const tentative =
          (component.status !== "stated" &&
            !component.supported &&
            !["accepted", "corrected"].includes(component.review_state)) ||
          component.alternatives.length > 0 ||
          component.status === "conflict";
        return (
          <li key={`${component.flower}-${index}`}>
            <span>
              {label(component.flower, lang)}
              {component.stated_count ? ` · ${component.stated_count}` : ""}
            </span>
            {tentative && (
              <small>
                {lang === "vi" ? "Chưa chắc chắn" : "Tentative"}
                {component.alternatives.length
                  ? `: ${component.alternatives.map((f) => label(f, lang)).join(" / ")}`
                  : ""}
              </small>
            )}
            {!compact && (
              <small>
                {component.status === "stated"
                  ? lang === "vi"
                    ? "Người bán nêu"
                    : "Seller-stated"
                  : lang === "vi"
                    ? "Nhận diện từ ảnh"
                    : "Visual observation"}
              </small>
            )}
          </li>
        );
      })}
    </ul>
  );
}
