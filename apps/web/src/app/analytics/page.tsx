import { api } from "@/lib/api";
import { locale } from "@/lib/locale";
import type { Comparison, Listing } from "@/lib/types";
import { Benchmark, Distribution } from "@/components/benchmark";
interface Analytics {
  catalog_count: number;
  seller_count: number;
  eligible_count: number;
  is_demo: boolean;
  targets: { id: string; title: string; seller: string }[];
  selected: Listing | null;
  comparison: Comparison | null;
  historical_note: string;
}
export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ listing_id?: string }>;
}) {
  const { listing_id } = await searchParams;
  const [lang, data] = await Promise.all([
    locale(),
    api<Analytics>(
      `/v1/analytics/cohorts${listing_id ? `?listing_id=${encodeURIComponent(listing_id)}` : ""}`,
    ),
  ]);
  const vi = lang === "vi";
  return (
    <main id="main" className="page-width standard-page">
      <div className="page-heading">
        <h1>
          {vi
            ? "Hiểu giá, từ những gì có thật."
            : "Price perspective, grounded in evidence."}
        </h1>
        <p>
          {vi
            ? "So sánh các quảng cáo đủ tương đồng, từng người bán một."
            : "Compare sufficiently similar advertisements, one independent seller at a time."}
        </p>
      </div>
      {data.is_demo && (
        <p className="demo-note">
          {vi
            ? "Toàn bộ số liệu dưới đây là minh họa hư cấu, không phải thống kê thị trường Hà Nội."
            : "All figures below are fictional demonstration data, not Hanoi market statistics."}
        </p>
      )}
      <dl className="coverage-row">
        <div>
          <dt>{vi ? "Trong bộ sưu tập" : "Indexed listings"}</dt>
          <dd>{data.catalog_count}</dd>
        </div>
        <div>
          <dt>{vi ? "Người bán" : "Independent sellers"}</dt>
          <dd>{data.seller_count}</dd>
        </div>
        <div>
          <dt>
            {vi
              ? "Có bằng chứng cấu hình & giá"
              : "Configuration & price evidence"}
          </dt>
          <dd>{data.eligible_count}</dd>
        </div>
      </dl>
      <form className="analytics-selector" action="/analytics">
        <label htmlFor="cohort-target">
          {vi ? "Chọn bó hoa tham chiếu" : "Choose a reference bouquet"}
        </label>
        <div>
          <select
            id="cohort-target"
            name="listing_id"
            defaultValue={data.selected?.id || ""}
          >
            {data.targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} · {t.seller}
              </option>
            ))}
          </select>
          <button className="button primary" type="submit">
            {vi ? "Xem nhóm so sánh" : "View cohort"}
          </button>
        </div>
      </form>
      {data.comparison ? (
        <div className="evidence-layout">
          <Benchmark data={data.comparison} lang={lang} />
          <Distribution data={data.comparison} lang={lang} />
        </div>
      ) : (
        <p>
          {vi
            ? "Chưa có đủ bằng chứng để tạo nhóm so sánh."
            : "There is not enough evidence to build a comparison cohort."}
        </p>
      )}
      <section className="methodology">
        <h2>
          {vi
            ? "Những con số này nói lên điều gì?"
            : "What do these numbers mean?"}
        </h2>
        <p>
          {vi
            ? "Chỉ dùng giá được nêu rõ, cùng loại hoa, màu chính, kiểu bó và số cành tương đương (±20%). Mỗi người bán chỉ đóng góp một cấu hình. Ngân sách tìm kiếm không làm thay đổi nhóm tham khảo."
            : "Only explicit prices with matching flowers, primary color, arrangement, and comparable stated stem counts (±20%) qualify. Each seller contributes one configuration. Search budgets do not change the reference cohort."}
        </p>
        <p>
          {vi
            ? "Dưới 5 người bán: không hiển thị trung vị. Từ 5–9: mẫu còn nhỏ. Phân vị chỉ xuất hiện từ 10 người bán. Hoạt động đăng bài không phải số đơn hàng hay tồn kho."
            : "Below five sellers, the median is suppressed. Five to nine is a limited sample. Percentiles require ten sellers. Posting activity is not sales or inventory."}
        </p>
        <p className="fine-print">
          {vi
            ? "Xu hướng theo mùa cần dữ liệu thật theo thời gian; chưa hiển thị kết luận khi thiếu độ phủ."
            : data.historical_note}
        </p>
      </section>
    </main>
  );
}
