import Link from "next/link";
import type { Comparison, Locale, Price } from "@/lib/types";
import { date, money } from "@/lib/i18n";
export function Benchmark({ data, lang }: { data: Comparison; lang: Locale }) {
  const s = data.summary;
  const vi = lang === "vi";
  return (
    <section className="benchmark">
      <div className="benchmark-heading">
        <h2>{vi ? "Một góc nhìn về giá" : "A little price perspective"}</h2>
        <span
          className={`status-label ${s.status === "qualified" ? "good" : ""}`}
        >
          {s.status === "limited"
            ? vi
              ? "Mẫu còn nhỏ"
              : "Limited sample"
            : s.status === "qualified"
              ? vi
                ? "Đủ điều kiện so sánh"
                : "Qualified comparison"
              : vi
                ? "Chưa đủ bằng chứng"
                : "Insufficient evidence"}
        </span>
      </div>
      {s.median !== null ? (
        <>
          <p className="benchmark-main">
            {vi ? "Giá trung vị từ" : "Median advertised price across"}{" "}
            <strong>
              {s.seller_count} {vi ? "người bán khác" : "other sellers"}
            </strong>
            <span>{money(s.median)}</span>
          </p>
          <div className="benchmark-range">
            <div>
              <small>{vi ? "Khoảng giá" : "Price range"}</small>
              <strong>
                {money(s.min || 0)} – {money(s.max || 0)}
              </strong>
            </div>
            <div>
              <small>{vi ? "So với trung vị" : "Relative to median"}</small>
              <strong>
                {s.relative_difference !== null
                  ? `${s.relative_difference >= 0 ? "+" : ""}${(s.relative_difference * 100).toFixed(1)}%`
                  : "—"}
              </strong>
            </div>
            {s.percentile !== null && (
              <div>
                <small>{vi ? "Phân vị trong mẫu" : "Sample percentile"}</small>
                <strong>{s.percentile.toFixed(0)}%</strong>
              </div>
            )}
          </div>
        </>
      ) : (
        <p>
          {vi
            ? "Cần ít nhất 5 người bán khác có cấu hình và giá đủ rõ ràng trước khi hiển thị giá trung vị."
            : "At least five other sellers with sufficiently supported configurations and prices are needed to show a median."}
        </p>
      )}
      {s.target_issues.length > 0 && (
        <ul className="issue-list">
          {s.target_issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      <p className="fine-print">
        {vi
          ? `Một cấu hình phù hợp nhất cho mỗi người bán. Quảng cáo trong ${s.window_days} ngày; không bao gồm phí giao hàng. Không phải mẫu đại diện toàn thị trường Hà Nội.`
          : `One closest qualified configuration per seller. Advertisements within ${s.window_days} days; delivery excluded. This is not a representative Hanoi market estimate.`}
      </p>
      {s.is_demo && (
        <p className="demo-note">
          {vi
            ? "Số liệu minh họa hư cấu; không phải giá thị trường."
            : "Fictional demonstration statistics, not market prices."}
        </p>
      )}
    </section>
  );
}
export function Distribution({
  data,
  lang,
}: {
  data: Comparison;
  lang: Locale;
}) {
  const values = data.items
    .map((item) => ({
      name: item.seller.name,
      price: item.price?.amount_min || 0,
      id: item.id,
    }))
    .sort((a, b) => a.price - b.price);
  const max = Math.max(1, ...values.map((v) => v.price));
  return (
    <div className="distribution">
      <h3>
        {lang === "vi"
          ? "Các quảng cáo trong nhóm"
          : "Advertisements in this cohort"}
      </h3>
      {values.length ? (
        values.map((value) => (
          <div className="distribution-row" key={value.id}>
            <Link href={`/bouquets/${value.id}`}>{value.name}</Link>
            <div className="distribution-track">
              <span style={{ width: `${(value.price / max) * 100}%` }} />
            </div>
            <strong>{money(value.price)}</strong>
          </div>
        ))
      ) : (
        <p className="muted">
          {lang === "vi"
            ? "Chưa có cấu hình đủ điều kiện."
            : "No qualified configurations yet."}
        </p>
      )}
    </div>
  );
}
export function PriceHistory({
  items,
  lang,
  isDemo,
}: {
  items: Price[];
  lang: Locale;
  isDemo: boolean;
}) {
  const exact = items.filter(
    (p) =>
      p.amount_min === p.amount_max && ["exact", "promotion"].includes(p.kind),
  );
  const min = Math.min(...exact.map((p) => p.amount_min));
  const max = Math.max(...exact.map((p) => p.amount_min));
  const points = exact.map((p, i) => ({
    x: 30 + (i / Math.max(1, exact.length - 1)) * 540,
    y: 155 - ((p.amount_min - min) / Math.max(100000, max - min)) * 105,
    p,
  }));
  return (
    <section className="history">
      <h2>
        {lang === "vi" ? "Giá đã được quảng cáo" : "Advertised price history"}
      </h2>
      {exact.length > 1 ? (
        <>
          <svg
            viewBox="0 0 600 200"
            role="img"
            aria-label={
              lang === "vi"
                ? "Biểu đồ lịch sử giá quảng cáo"
                : "Advertised price observation chart"
            }
          >
            <path d="M30 175H570" stroke="var(--line)" />
            <polyline
              points={points.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="var(--ink)"
              strokeWidth="2"
            />
            {points.map(({ x, y, p }) => (
              <g key={p.id}>
                <circle cx={x} cy={y} r="4" fill="var(--ink)">
                  <title>
                    {date(p.advertised_at, lang)}: {money(p.amount_min)}
                  </title>
                </circle>
                <text x={x} y="195" textAnchor="middle">
                  {date(p.advertised_at, lang)}
                </text>
                <text x={x} y={y - 12} textAnchor="middle">
                  {Math.round(p.amount_min / 1000)}k
                </text>
              </g>
            ))}
          </svg>
          <details>
            <summary>
              {lang === "vi"
                ? "Xem các quan sát nguồn"
                : "View source observations"}
            </summary>
            <table>
              <thead>
                <tr>
                  <th>{lang === "vi" ? "Ngày quảng cáo" : "Advertised"}</th>
                  <th>{lang === "vi" ? "Giá" : "Price"}</th>
                  <th>{lang === "vi" ? "Bằng chứng" : "Evidence"}</th>
                </tr>
              </thead>
              <tbody>
                {exact.map((p) => (
                  <tr key={p.id}>
                    <td>{date(p.advertised_at, lang)}</td>
                    <td>{money(p.amount_min, p.currency)}</td>
                    <td>{String(p.evidence.quote || "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      ) : (
        <p className="muted">
          {lang === "vi"
            ? "Cần thêm các quan sát giá theo thời gian."
            : "More price observations over time are needed."}
        </p>
      )}
      {isDemo && (
        <p className="fine-print">
          {lang === "vi"
            ? "Lịch sử minh họa hư cấu."
            : "Fictional demonstration history."}
        </p>
      )}
    </section>
  );
}
