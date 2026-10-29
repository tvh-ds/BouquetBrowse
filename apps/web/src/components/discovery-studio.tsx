"use client";
import { useCallback, useEffect, useState } from "react";
import type { components } from "@/lib/generated-api";
import type { Locale } from "@/lib/types";
import styles from "./discovery-studio.module.css";

type Status = components["schemas"]["StatusView"];
interface Run {
  id: string;
  state: string;
  stop_reason: string | null;
  created_at: string;
  progress: Record<string, unknown>;
}
interface Frontier {
  id: string;
  kind: string;
  queue: string;
  target: string;
  due_at: string;
  evidence_gaps: string[];
}
interface Exception {
  id: string;
  offer_id: string;
  kind: string;
  fingerprint: string;
}
interface Call {
  id: string;
  state: string;
  model: string;
  attempt: number;
  amount_microusd: number;
  replay_authorized: boolean;
}
interface Offer {
  id: string;
  fingerprint: string;
  state: string;
  evidence: {
    messages: { version_id: string; seller: boolean; text: string }[];
    media: { media_id: string }[];
  };
  regions: {
    id: string;
    media_id: string;
    bounds: number[];
    kind: string;
    state: string;
  }[];
}

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method,
    headers:
      method === "GET"
        ? undefined
        : {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message ||
        "Operation failed. Reload current evidence before retrying.",
    );
  return data;
}

export function DiscoveryStudio({ lang }: { lang: Locale }) {
  const vi = lang === "vi";
  const [status, setStatus] = useState<Status | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [frontier, setFrontier] = useState<Frontier[]>([]);
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [runDetail, setRunDetail] = useState<{
    id: string;
    events: { kind: string; at: string; details: Record<string, unknown> }[];
  } | null>(null);
  const load = useCallback(async () => {
    const [s, r, f, e, c] = await Promise.all([
      request<Status>("admin/discovery/status"),
      request<{ items: Run[] }>("admin/discovery/runs"),
      request<{ items: Frontier[] }>("admin/discovery/frontier"),
      request<{ items: Exception[] }>("admin/conversations/exceptions"),
      request<{ items: Call[] }>("admin/model-calls"),
    ]);
    setStatus(s);
    setRuns(r.items);
    setFrontier(f.items);
    setExceptions(e.items);
    setCalls(c.items);
  }, []);
  useEffect(() => {
    let active = true;
    Promise.all([
      request<Status>("admin/discovery/status"),
      request<{ items: Run[] }>("admin/discovery/runs"),
      request<{ items: Frontier[] }>("admin/discovery/frontier"),
      request<{ items: Exception[] }>("admin/conversations/exceptions"),
      request<{ items: Call[] }>("admin/model-calls"),
    ])
      .then(([s, r, f, e, c]) => {
        if (!active) return;
        setStatus(s);
        setRuns(r.items);
        setFrontier(f.items);
        setExceptions(e.items);
        setCalls(c.items);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [load]);
  async function act(task: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      setNotice(message);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed.");
    } finally {
      setBusy(false);
    }
  }
  function inspectOffer(id: string) {
    return act(
      async () =>
        setOffer(await request<Offer>(`admin/conversations/offers/${id}`)),
      vi ? "Đã tải bằng chứng." : "Evidence loaded.",
    );
  }
  return (
    <section
      className={styles.studio}
      aria-label={vi ? "Thu thập Threads" : "Threads discovery"}
    >
      <div className={styles.heading}>
        <div>
          <h2>
            {vi ? "Theo dõi nguồn Threads." : "Follow the Threads sources."}
          </h2>
          <p>
            {vi
              ? "Tách biệt trạng thái thu thập, chất lượng và quyền xuất bản."
              : "Collection health, evidence quality and publication are separate states."}
          </p>
        </div>
        <button
          className="button outline"
          disabled={busy}
          onClick={() => act(load, vi ? "Đã làm mới." : "Refreshed.")}
        >
          {vi ? "Làm mới" : "Refresh"}
        </button>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!status ? (
        <p>{vi ? "Đang tải trạng thái…" : "Loading collection status…"}</p>
      ) : (
        <>
          <div className={styles.actions}>
            <button
              className="button primary"
              disabled={busy}
              onClick={() =>
                act(
                  () =>
                    request("admin/discovery/settings", "PATCH", {
                      expected_version: status.settings_version,
                      paused: !status.paused,
                    }),
                  vi ? "Đã cập nhật trạng thái." : "Collection state updated.",
                )
              }
            >
              {status.paused
                ? vi
                  ? "Tiếp tục thu thập"
                  : "Resume collection"
                : vi
                  ? "Tạm dừng"
                  : "Pause collection"}
            </button>
            <button
              className="button outline"
              disabled={
                busy ||
                status.paused ||
                !status.enabled ||
                !status.model_configured ||
                !status.postgres
              }
              onClick={() =>
                act(
                  () => request("admin/discovery/runs", "POST", {}),
                  vi ? "Đã xếp lượt thu thập." : "Discovery run queued.",
                )
              }
            >
              {vi ? "Chạy một lượt" : "Run once"}
            </button>
          </div>
          <dl className={styles.health}>
            <div>
              <dt>{vi ? "Thu thập" : "Collection"}</dt>
              <dd>
                {status.paused
                  ? vi
                    ? "Tạm dừng"
                    : "Paused"
                  : vi
                    ? "Đã bật"
                    : "Resumed"}
              </dd>
            </div>
            <div>
              <dt>{vi ? "Xuất bản tự động" : "Automatic publication"}</dt>
              <dd>
                {status.publication_enabled
                  ? vi
                    ? "Đủ điều kiện"
                    : "Qualified"
                  : vi
                    ? "Chưa qua kiểm định"
                    : "Release gates closed"}
              </dd>
            </div>
            <div>
              <dt>{vi ? "Cấu hình" : "Configuration"}</dt>
              <dd>
                {status.postgres &&
                status.browser_installed &&
                status.model_configured &&
                status.enabled
                  ? vi
                    ? "Đã cấu hình"
                    : "Configured"
                  : vi
                    ? "Còn thiếu cấu hình cục bộ"
                    : "Local setup incomplete"}
              </dd>
            </div>
          </dl>
          <p className="fine-print">
            {vi
              ? "Trình duyệt riêng cần đăng nhập trực tiếp. Không sao chép cookie. Mỗi lượt tối đa 20 phút; tài khoản AI dùng chung giới hạn 100 USD/tháng."
              : "The dedicated browser needs direct sign-in. Cookies are not copied. Runs stop at 20 minutes; shared AI spending is capped at $100/month."}
          </p>
        </>
      )}
      <h3>{vi ? "Các lượt gần đây" : "Recent runs"}</h3>
      {!runs.length ? (
        <p className="muted">
          {vi
            ? "Chưa có lượt thu thập. Cấu hình, đăng nhập và chạy thử khi sẵn sàng."
            : "No runs yet. Complete local setup and sign-in before an explicit test run."}
        </p>
      ) : (
        <ul className={styles.rows}>
          {runs.map((run) => (
            <li key={run.id}>
              <div>
                <strong>{run.state}</strong>
                <p>
                  {new Date(run.created_at).toLocaleString(
                    vi ? "vi-VN" : "en-GB",
                    { timeZone: "Asia/Ho_Chi_Minh" },
                  )}{" "}
                  · {run.stop_reason || "—"}
                </p>
              </div>
              <div className={styles.actions}>
                <button
                  className="button outline"
                  disabled={busy}
                  onClick={() =>
                    act(
                      async () =>
                        setRunDetail(
                          await request(`admin/discovery/runs/${run.id}`),
                        ),
                      vi ? "Đã tải lượt." : "Run loaded.",
                    )
                  }
                >
                  {vi ? "Xem lượt" : "Inspect run"}
                </button>
                {["queued", "running"].includes(run.state) && (
                  <button
                    className="button outline"
                    disabled={busy}
                    onClick={() =>
                      act(
                        () =>
                          request(
                            `admin/discovery/runs/${run.id}/cancel`,
                            "POST",
                            {},
                          ),
                        vi ? "Đã hủy lượt." : "Run cancelled.",
                      )
                    }
                  >
                    {vi ? "Hủy" : "Cancel"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {runDetail && (
        <section className={styles.inspector}>
          <h3>{vi ? "Sự kiện trong lượt" : "Run events"}</h3>
          <button className="button outline" onClick={() => setRunDetail(null)}>
            {vi ? "Đóng chi tiết" : "Close details"}
          </button>
          <ol>
            {runDetail.events.map((event, i) => (
              <li key={i}>
                <strong>{event.kind}</strong>
                <p>{event.at}</p>
                <pre>{JSON.stringify(event.details, null, 2)}</pre>
              </li>
            ))}
          </ol>
        </section>
      )}
      <h3>{vi ? "Bằng chứng cần làm rõ" : "Evidence exceptions"}</h3>
      {!exceptions.length ? (
        <p className="muted">
          {vi ? "Chưa có ngoại lệ đang chờ." : "No pending exceptions."}
        </p>
      ) : (
        <ul className={styles.rows}>
          {exceptions.map((item) => (
            <li key={item.id}>
              <span>{item.kind.replaceAll("_", " ")}</span>
              <button
                className="button outline"
                disabled={busy}
                onClick={() => inspectOffer(item.offer_id)}
              >
                {vi ? "Kiểm tra bằng chứng" : "Inspect evidence"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {offer && (
        <section className={styles.inspector}>
          <div className={styles.heading}>
            <h3>{vi ? "Hội thoại được ghi nhận" : "Captured conversation"}</h3>
            <button className="button outline" onClick={() => setOffer(null)}>
              {vi ? "Đóng" : "Close"}
            </button>
          </div>
          <p className="fine-print">
            {vi
              ? "Bối cảnh người mua chỉ xuất hiện trong khu vực quản trị này."
              : "Buyer context is restricted to this operational view."}
          </p>
          {offer.evidence.messages.map((m) => (
            <blockquote key={m.version_id}>
              <strong>
                {m.seller
                  ? vi
                    ? "Người bán của đề nghị này"
                    : "This offer’s seller"
                  : vi
                    ? "Tài khoản khác"
                    : "Other account"}
              </strong>
              <p>{m.text}</p>
            </blockquote>
          ))}
          <div className={styles.images}>
            {offer.evidence.media.map((m, i) => (
              <a
                key={`${m.media_id}-${i}`}
                href={`/api/v1/admin/media/${m.media_id}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {vi ? "Mở ảnh bằng chứng" : "Open evidence image"} {i + 1}
              </a>
            ))}
          </div>
          <form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const version = String(data.get("version"));
              act(
                () =>
                  request(
                    `admin/conversations/offers/${offer.id}/interpretation`,
                    "POST",
                    {
                      expected_fingerprint: offer.fingerprint,
                      interpretation: {
                        seller_offer: true,
                        ownership: {
                          version_id: version,
                          quote: String(data.get("ownership")),
                        },
                        location: {
                          version_id: version,
                          quote: String(data.get("location")),
                        },
                        multi_product: false,
                        fields: [],
                        warnings: [],
                      },
                    },
                  ),
                vi
                  ? "Đã ghi nhận bằng chứng và tiếp tục xử lý."
                  : "Evidence recorded; processing resumed.",
              );
            }}
          >
            <label>
              {vi ? "Tin của người bán" : "Seller message"}
              <select name="version" required>
                {offer.evidence.messages
                  .filter((m) => m.seller)
                  .map((m) => (
                    <option key={m.version_id} value={m.version_id}>
                      {m.text.slice(0, 85)}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {vi
                ? "Trích dẫn chính xác về đề nghị bán"
                : "Exact offer-ownership quote"}
              <input name="ownership" required maxLength={1000} />
            </label>
            <label>
              {vi
                ? "Trích dẫn chính xác về phục vụ Hà Nội"
                : "Exact Hanoi service quote"}
              <input name="location" required maxLength={1000} />
            </label>
            <button className="button primary" disabled={busy}>
              {vi ? "Ghi nhận bằng chứng" : "Record evidence"}
            </button>
          </form>
          {offer.regions
            .filter((r) => r.kind === "product")
            .map((region) => (
              <form
                className={styles.form}
                key={region.id}
                onSubmit={(event) => {
                  event.preventDefault();
                  const data = new FormData(event.currentTarget);
                  const quote = String(data.get("price"));
                  act(
                    () =>
                      request(
                        `admin/conversations/offers/${offer.id}/regions/${region.id}/split`,
                        "POST",
                        {
                          expected_fingerprint: offer.fingerprint,
                          price_target: quote
                            ? { version_id: String(data.get("version")), quote }
                            : null,
                        },
                      ),
                    vi
                      ? "Đã tách đề nghị theo vùng đã duyệt."
                      : "Reviewed crop offer queued.",
                  );
                }}
              >
                <h4>{vi ? "Duyệt vùng sản phẩm" : "Review product region"}</h4>
                <p>
                  {region.bounds.map((value) => value.toFixed(3)).join(" · ")}
                </p>
                <label>
                  {vi ? "Tin chứa giá" : "Price message"}
                  <select name="version">
                    {offer.evidence.messages
                      .filter((m) => m.seller)
                      .map((m) => (
                        <option key={m.version_id} value={m.version_id}>
                          {m.text.slice(0, 85)}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  {vi
                    ? "Trích dẫn riêng cho vùng này (có thể bỏ trống giá)"
                    : "Quote bound to this region (price may be unknown)"}
                  <input name="price" maxLength={1000} />
                </label>
                <button className="button outline" disabled={busy}>
                  {vi ? "Duyệt và tách vùng" : "Approve region offer"}
                </button>
              </form>
            ))}
        </section>
      )}
      <details>
        <summary>
          {vi ? "Hàng đợi khám phá" : "Discovery frontier"} · {frontier.length}
        </summary>
        <ul className={styles.rows}>
          {frontier.map((item) => (
            <li key={item.id}>
              <div>
                <strong>
                  {item.queue} · {item.kind}
                </strong>
                <p className={styles.target}>{item.target}</p>
                <p>{item.evidence_gaps.join(" · ")}</p>
              </div>
              <time>
                {new Date(item.due_at).toLocaleString(vi ? "vi-VN" : "en-GB", {
                  timeZone: "Asia/Ho_Chi_Minh",
                })}
              </time>
            </li>
          ))}
        </ul>
      </details>
      <details>
        <summary>
          {vi ? "Lượt gọi mô hình và chi phí" : "Model calls and spending"} ·{" "}
          {calls.length}
        </summary>
        <p className="fine-print">
          {vi
            ? "Lượt không chắc chắn vẫn giữ khoản dự trù. Chạy lại cần khoản dự trù mới; giới hạn ngân sách luôn có hiệu lực."
            : "Uncertain calls retain their reservation. Explicit replay needs a new reservation within the shared limit."}
        </p>
        <ul className={styles.rows}>
          {calls.map((call) => (
            <li key={call.id}>
              <div>
                <strong>
                  {call.model} · {call.state}
                </strong>
                <p>
                  ${(call.amount_microusd / 1_000_000).toFixed(4)} ·{" "}
                  {vi ? "Lần" : "Attempt"} {call.attempt}
                </p>
              </div>
              {["uncertain", "failed"].includes(call.state) && (
                <button
                  className="button outline"
                  disabled={busy || call.replay_authorized}
                  onClick={() =>
                    act(
                      () =>
                        request(`admin/model-calls/${call.id}/replay`, "POST", {
                          expected_state: call.state,
                        }),
                      vi
                        ? "Đã cho phép chạy lại có dự trù mới."
                        : "Explicit replay authorized; a new reservation is required.",
                    )
                  }
                >
                  {vi ? "Cho phép chạy lại" : "Authorize replay"}
                </button>
              )}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
