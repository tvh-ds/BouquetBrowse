"use client";
import { useCallback, useState } from "react";
import type { Detail, Locale } from "@/lib/types";
export interface Source {
  id: string;
  name: string;
  enabled: boolean;
  state: string;
  detail: string;
  last_success_at: string | null;
}
export interface Job {
  id: string;
  kind: string;
  state: string;
  attempts: number;
  last_error: string | null;
  created_at: string;
}
export interface Overview {
  published: number;
  pending_reviews: number;
  failed_jobs: number;
  model_spend_usd: number;
  model_budget_usd: number;
  recent_actions: {
    id: string;
    decision: string;
    reason: string;
    created_at: string;
  }[];
}
const sample = JSON.stringify(
  {
    posts: [
      {
        platform: "operator",
        platform_post_id: "pilot-example-001",
        username: "research.florist",
        seller_name: "Research Florist",
        seller_slug: "research-florist",
        district: "Ba Đình",
        city: "Hanoi",
        source_url: null,
        published_at: new Date().toISOString(),
        caption:
          "Bó hoa hồng màu hồng, 20 cành. Giá 650k. Đặt trước 2 ngày. Có giao hàng. Phí ship 30k.",
        media_urls: [],
        rights_confirmed: false,
      },
    ],
  },
  null,
  2,
);
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api${path}`,
    body !== undefined
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "Operation failed.");
  return data;
}
export interface StudioData {
  overview: Overview | null;
  sources: Source[];
  jobs: Job[];
  reviews: Detail[];
}
export function Studio({
  lang,
  role,
  initial,
}: {
  lang: Locale;
  role: string;
  initial: StudioData;
}) {
  const vi = lang === "vi";
  const isAdmin = role === "admin";
  const [tab, setTab] = useState(isAdmin ? "overview" : "reviews");
  const [overview, setOverview] = useState<Overview | null>(initial.overview);
  const [sources, setSources] = useState<Source[]>(initial.sources);
  const [jobs, setJobs] = useState<Job[]>(initial.jobs);
  const [reviews, setReviews] = useState<Detail[]>(initial.reviews);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState(sample);
  const [pageUrl, setPageUrl] = useState("");
  const [pageWarnings, setPageWarnings] = useState<string[]>([]);
  const load = useCallback(async () => {
    try {
      const result = await request<{ items: Detail[] }>("/v1/admin/reviews");
      setReviews(result.items);
      if (isAdmin) {
        const [o, s, j] = await Promise.all([
          request<Overview>("/v1/admin/overview"),
          request<{ items: Source[] }>("/v1/admin/sources"),
          request<{ items: Job[] }>("/v1/admin/jobs"),
        ]);
        setOverview(o);
        setSources(s.items);
        setJobs(j.items);
      }
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to load catalog operations.",
      );
    }
  }, [isAdmin]);
  async function perform(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await fn();
      setStatus(message);
      await load();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Operation failed.");
    } finally {
      setBusy(false);
    }
  }
  const tabs = isAdmin
    ? [
        ["overview", vi ? "Tổng quan" : "Overview"],
        ["imports", vi ? "Nhập dữ liệu" : "Import"],
        ["reviews", vi ? "Duyệt thông tin" : "Review"],
        ["jobs", vi ? "Tác vụ" : "Jobs"],
        ["sources", vi ? "Nguồn" : "Sources"],
        ["takedown", vi ? "Gỡ dữ liệu" : "Takedown"],
      ]
    : [["reviews", vi ? "Duyệt thông tin" : "Review"]];
  return (
    <>
      <div
        className="studio-tabs"
        role="tablist"
        aria-label="Catalog operations"
      >
        {tabs.map(([id, title]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            id={`tab-${id}`}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {title}
            {id === "reviews" ? ` (${reviews.length})` : ""}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {status && (
        <p role="status" className="operation-status">
          {status}
        </p>
      )}
      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        aria-busy={busy}
      >
        {tab === "overview" && overview && (
          <section className="studio-section">
            <dl className="studio-overview">
              <div>
                <span>{vi ? "Đã xuất bản" : "Published"}</span>
                <strong>{overview.published}</strong>
              </div>
              <div>
                <span>{vi ? "Chờ duyệt" : "Awaiting review"}</span>
                <strong>{overview.pending_reviews}</strong>
              </div>
              <div>
                <span>{vi ? "Tác vụ lỗi" : "Failed jobs"}</span>
                <strong>{overview.failed_jobs}</strong>
              </div>
              <div>
                <span>{vi ? "Ngân sách mô hình" : "Model budget"}</span>
                <strong>
                  ${overview.model_spend_usd.toFixed(2)} / $
                  {overview.model_budget_usd}
                </strong>
              </div>
            </dl>
            <h2>
              {vi
                ? "Một bộ sưu tập có thể kiểm chứng."
                : "A catalog you can trace."}
            </h2>
            <p className="studio-note">
              {vi
                ? "Nhập bài đăng, xử lý trong worker, duyệt bằng chứng và xuất bản. Mô hình không được tự xác nhận tồn kho hoặc tạo giá mới."
                : "Import posts, process them through the worker, review evidence, and publish. Models cannot confirm inventory or invent prices."}
            </p>
            <h3>{vi ? "Các thao tác gần đây" : "Recent actions"}</h3>
            <div className="studio-table">
              <table>
                <thead>
                  <tr>
                    <th>Decision</th>
                    <th>Reason</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.recent_actions.map((a) => (
                    <tr key={a.id}>
                      <td>{a.decision}</td>
                      <td>{a.reason}</td>
                      <td>{new Date(a.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {tab === "imports" && (
          <section className="studio-section">
            <h2>{vi ? "Đọc bài đăng công khai" : "Collect a public post"}</h2>
            <p className="studio-note">
              {vi
                ? "Dán URL của một bài đăng Threads hoặc Instagram. Đọc trang không cần token API; trang yêu cầu đăng nhập hoặc chặn truy cập sẽ báo lỗi. Kiểm tra chú thích, ảnh, ngày đăng, người bán và quyền sử dụng trước khi nhập."
                : "Paste an individual Threads or Instagram post URL. No API token is needed for public HTML; login walls and access restrictions produce an error. Verify caption, images, publication date, seller details, and permitted use before importing."}
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                setPageWarnings([]);
                setText("");
                void perform(
                  async () => {
                    const result = await request<{
                      draft: Record<string, unknown>;
                      warnings: string[];
                    }>("/v1/admin/pages/preview", { url: pageUrl });
                    setText(JSON.stringify({ posts: [result.draft] }, null, 2));
                    setPageWarnings(result.warnings);
                  },
                  vi
                    ? "Đã đọc trang. Bổ sung các trường còn thiếu trong bản nháp bên dưới trước khi nhập."
                    : "Page collected. Complete missing fields in the draft below before importing.",
                );
              }}
            >
              <label className="form-field" htmlFor="public-page-url">
                <span>{vi ? "URL bài đăng công khai" : "Public post URL"}</span>
                <input
                  id="public-page-url"
                  type="url"
                  required
                  maxLength={2048}
                  value={pageUrl}
                  onChange={(event) => setPageUrl(event.target.value)}
                  placeholder="https://www.threads.com/@seller/post/..."
                />
              </label>
              <div className="form-actions">
                <button
                  className="button secondary"
                  disabled={busy}
                  type="submit"
                >
                  {busy
                    ? vi
                      ? "Đang xử lý…"
                      : "Working…"
                    : vi
                      ? "Đọc trang & tạo bản nháp"
                      : "Collect page & draft"}
                </button>
              </div>
            </form>
            {pageWarnings.length > 0 && (
              <div role="status">
                <ul>
                  {pageWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
            <h2>
              {vi
                ? "Từ bài đăng đến dữ liệu có cấu trúc."
                : "From a post to a structured record."}
            </h2>
            <p className="studio-note">
              {vi
                ? "Dán JSON theo mẫu. Xác nhận quyền xử lý bằng rights_confirmed: true chỉ khi phù hợp. Bài nhập sẽ được worker xử lý và chờ duyệt; không tự xuất bản."
                : "Paste records using the sample schema. Set rights_confirmed: true only when appropriate. Imported posts are processed by the worker and queued for review, not automatically published."}
            </p>
            <label htmlFor="import-json" className="sr-only">
              Import JSON
            </label>
            <textarea
              id="import-json"
              className="import-editor"
              value={text}
              onChange={(event) => setText(event.target.value)}
              spellCheck={false}
            />
            <div className="form-actions">
              <button
                className="button primary"
                disabled={busy}
                onClick={() =>
                  void perform(
                    () => request("/v1/admin/imports", JSON.parse(text)),
                    vi
                      ? "Đã nhập. Worker sẽ xử lý; xem tab Tác vụ và Duyệt thông tin."
                      : "Imported. The worker will process this source; see Jobs and Review.",
                  )
                }
              >
                {vi ? "Nhập & đưa vào hàng đợi" : "Import & queue"}
              </button>
            </div>
          </section>
        )}
        {tab === "reviews" && (
          <section className="studio-section">
            <h2>
              {vi
                ? "Bằng chứng trước khi xuất bản."
                : "Evidence before publication."}
            </h2>
            <p className="studio-note">
              {vi
                ? "Duyệt thông tin trích xuất không đồng nghĩa với xác nhận tồn kho. Khi có nhiều giá, nhập đúng giá sản phẩm và trích dẫn khớp nguồn."
                : "Reviewing extraction does not verify stock. For multiple prices, provide the correct product price and a matching source quote."}
            </p>
            {reviews.length ? (
              reviews.map((listing) => (
                <article className="review-item" key={listing.id}>
                  <h3>
                    {listing.title} · {listing.seller.name}
                  </h3>
                  <blockquote>{listing.sources[0]?.caption}</blockquote>
                  <details>
                    <summary>
                      {vi
                        ? "Xem các trường được trích xuất"
                        : "Inspect extracted fields"}
                    </summary>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Value</th>
                            <th>Origin</th>
                          </tr>
                        </thead>
                        <tbody>
                          {listing.assertions.map((a) => (
                            <tr key={a.id}>
                              <td>{a.field}</td>
                              <td>{String(a.value.value ?? "Unknown")}</td>
                              <td>{a.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      const f = new FormData(event.currentTarget);
                      const button = (event.nativeEvent as SubmitEvent)
                        .submitter as HTMLButtonElement | null;
                      const body: Record<string, unknown> = {
                        decision: button?.value || "accept",
                        reason: String(f.get("reason")),
                      };
                      if (f.get("price")) {
                        body.price_minor = Number(f.get("price"));
                        body.price_evidence_quote = String(f.get("quote"));
                      }
                      void perform(
                        () =>
                          request(
                            `/v1/admin/reviews/${listing.id}/decision`,
                            body,
                          ),
                        vi
                          ? "Đã lưu quyết định duyệt."
                          : "Review decision saved.",
                      );
                    }}
                  >
                    <div className="form-grid">
                      <label className="form-field">
                        <span>
                          {vi
                            ? "Giá sửa lại (VND, không bắt buộc)"
                            : "Corrected price (VND, optional)"}
                        </span>
                        <input name="price" type="number" min="0" step="1" />
                      </label>
                      <label className="form-field">
                        <span>
                          {vi
                            ? "Trích dẫn khớp nguồn cho giá sửa"
                            : "Exact source quote for corrected price"}
                        </span>
                        <input name="quote" maxLength={1000} />
                      </label>
                    </div>
                    <label className="form-field">
                      <span>{vi ? "Lý do quyết định" : "Decision reason"}</span>
                      <input
                        name="reason"
                        required
                        minLength={3}
                        maxLength={1000}
                        placeholder={
                          vi
                            ? "Đã đối chiếu giá và cấu hình với nguồn…"
                            : "Checked price and configuration against source…"
                        }
                      />
                    </label>
                    <div className="form-actions">
                      <button
                        className="button primary"
                        type="submit"
                        name="decision"
                        value="accept"
                        disabled={busy}
                      >
                        {vi ? "Duyệt & xuất bản" : "Accept & publish"}
                      </button>
                      <button
                        className="button outline"
                        type="submit"
                        name="decision"
                        value="correct"
                        disabled={busy}
                      >
                        {vi ? "Lưu sửa & xuất bản" : "Correct & publish"}
                      </button>
                      <button
                        className="button outline"
                        type="submit"
                        name="decision"
                        value="reject"
                        disabled={busy}
                      >
                        {vi ? "Từ chối" : "Reject"}
                      </button>
                    </div>
                  </form>
                </article>
              ))
            ) : (
              <p className="operation-status">
                {vi
                  ? "Không có bản ghi chờ duyệt."
                  : "No records awaiting review."}
              </p>
            )}
          </section>
        )}
        {tab === "jobs" && (
          <section className="studio-section">
            <div className="section-heading">
              <h2>{vi ? "Tác vụ nền" : "Background work"}</h2>
              <button
                className="button outline"
                disabled={busy}
                onClick={() => void load()}
              >
                {vi ? "Làm mới" : "Refresh"}
              </button>
            </div>
            {jobs.length ? (
              <div className="studio-table">
                <table>
                  <thead>
                    <tr>
                      <th>Job</th>
                      <th>State</th>
                      <th>Attempts</th>
                      <th>Result / recovery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id}>
                        <td>
                          {j.kind}
                          <br />
                          <code>{j.id.slice(0, 8)}</code>
                        </td>
                        <td>
                          <span className="status-label">{j.state}</span>
                        </td>
                        <td>{j.attempts}</td>
                        <td>
                          {j.last_error}
                          {j.state === "failed" && (
                            <button
                              className="button outline"
                              disabled={busy}
                              onClick={() =>
                                void perform(
                                  () =>
                                    request(`/v1/admin/jobs/${j.id}/retry`, {}),
                                  "Job queued again.",
                                )
                              }
                            >
                              Retry
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">
                {vi
                  ? "Chưa có tác vụ. Nhập bài đăng để bắt đầu."
                  : "No jobs yet. Import a post to begin."}
              </p>
            )}
          </section>
        )}
        {tab === "sources" && (
          <section className="studio-section">
            <h2>
              {vi ? "Nguồn & khả năng truy cập" : "Sources & capabilities"}
            </h2>
            <p className="studio-note">
              {vi
                ? "Không có chế độ lấy dữ liệu bằng cách vượt hạn chế nền tảng. Nguồn chưa cấu hình luôn báo rõ, không thay bằng dữ liệu minh họa."
                : "Unavailable adapters report their actual capability state. They never bypass platform restrictions or substitute demo records."}
            </p>
            {sources.map((source) => (
              <div className="source-row" key={source.id}>
                <div>
                  <h3>{source.name}</h3>
                  <span
                    className={`status-label ${source.enabled ? "good" : ""}`}
                  >
                    {source.state.replaceAll("_", " ")}
                  </span>
                </div>
                <p>{source.detail}</p>
                <button
                  className="button outline"
                  disabled={busy || !source.enabled || source.id === "operator"}
                  onClick={() =>
                    void perform(
                      () =>
                        request(`/v1/admin/sources/${source.id}/sync`, {
                          query: "bó hoa Hà Nội",
                        }),
                      "Source sync queued.",
                    )
                  }
                >
                  {vi ? "Đồng bộ" : "Sync"}
                </button>
              </div>
            ))}
          </section>
        )}
        {tab === "takedown" && (
          <section className="studio-section">
            <h2>
              {vi
                ? "Gỡ khỏi bộ sưu tập & xóa dữ liệu."
                : "Suppress a listing and purge its data."}
            </h2>
            <p className="studio-note">
              {vi
                ? "Bản ghi sẽ bị ẩn ngay, sau đó worker xử lý xóa nội dung, ảnh, vector và các tham chiếu nhóm liên quan."
                : "The listing is hidden immediately. The worker then purges its content, media, vectors and affected comparison snapshots."}
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const f = new FormData(event.currentTarget);
                void perform(
                  () =>
                    request("/v1/admin/takedowns", {
                      listing_id: String(f.get("listing")),
                      reason: String(f.get("reason")),
                    }),
                  vi
                    ? "Đã ẩn bản ghi và đưa tác vụ xóa vào hàng đợi."
                    : "Listing suppressed and purge queued.",
                );
              }}
            >
              <label className="form-field">
                <span>Listing ID</span>
                <input name="listing" required pattern="[a-fA-F0-9-]{36}" />
              </label>
              <label className="form-field">
                <span>{vi ? "Lý do" : "Reason"}</span>
                <input name="reason" required minLength={3} maxLength={1000} />
              </label>
              <button className="button primary" disabled={busy} type="submit">
                {vi ? "Ẩn & xóa" : "Suppress & purge"}
              </button>
            </form>
          </section>
        )}
      </div>
    </>
  );
}
