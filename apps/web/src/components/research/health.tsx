"use client";
import { useEffect } from "react";
import {
  Feedback,
  Loading,
  date,
  money,
  request,
  useAction,
  useData,
  type PanelProps,
} from "./shared";
import styles from "../research-studio.module.css";

export interface Health {
  recurring_configured: boolean;
  backups_configured: boolean;
  readiness: {
    ready: boolean;
    conversation_proof: boolean;
    recognition_proof: boolean;
    live_results: string;
  };
  roles: {
    role: string;
    state: string;
    stale: boolean;
    last_seen_at: string;
  }[];
  coverage: Record<string, number>;
  model_cost_microusd: number;
  model_budget_microusd: number;
  alerts: {
    id: string;
    code: string;
    state: string;
    message: string;
    version: number;
    details: Record<string, unknown>;
  }[];
  backups: {
    id: string;
    state: string;
    created_at: string;
    result: { elapsed_seconds?: number; media_objects?: number } | null;
  }[];
}
export function HealthPanel({
  lang,
  refresh,
  active,
  onChange,
}: PanelProps & { active: boolean }) {
  const vi = lang === "vi";
  const { data, error, reload } = useData<Health>(
    "admin/operations/status",
    refresh,
  );
  const action = useAction(onChange);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, 30_000);
    return () => clearInterval(timer);
  }, [active, reload]);
  if (!data) return <Loading error={error} />;
  if (!Array.isArray(data.alerts))
    return (
      <Feedback
        error={
          vi
            ? "Khởi động lại API đã cập nhật, rồi làm mới không gian."
            : "Restart the updated API, then refresh this workspace."
        }
      />
    );
  return (
    <>
      <h3>{vi ? "Tình trạng vận hành" : "Runtime health"}</h3>
      <Feedback error={error || action.error} notice={action.notice} />
      <dl className={styles.summary}>
        <div>
          <dt>{vi ? "Thu thập định kỳ" : "Recurring collection"}</dt>
          <dd>
            {data.recurring_configured
              ? vi
                ? "Đã cấu hình"
                : "Configured"
              : vi
                ? "Chưa kích hoạt"
                : "Not activated"}
          </dd>
        </div>
        <div>
          <dt>{vi ? "Cổng xuất bản" : "Publication gates"}</dt>
          <dd>
            {data.readiness.ready
              ? vi
                ? "Đã đủ bằng chứng"
                : "Qualified proofs installed"
              : vi
                ? "Chưa mở"
                : "Closed"}
          </dd>
        </div>
        <div>
          <dt>{vi ? "Ngân sách AI tháng này" : "Monthly model budget"}</dt>
          <dd>
            {money(data.model_cost_microusd)} /{" "}
            {money(data.model_budget_microusd)}
          </dd>
        </div>
      </dl>
      <h3>{vi ? "Cần chú ý" : "Needs attention"}</h3>
      <p className={styles.muted}>
        {vi
          ? "Thông báo được hiển thị tại đây và ghi vào nhật ký cục bộ."
          : "Alerts appear here and in private local logs."}
      </p>
      {data.alerts.filter((a) => a.state !== "resolved").length === 0 && (
        <p>{vi ? "Không có sự cố đang mở." : "No open incidents."}</p>
      )}
      <ul className={styles.rows}>
        {data.alerts
          .filter((a) => a.state !== "resolved")
          .map((alert) => (
            <li key={alert.id}>
              <div>
                <strong>{alert.message}</strong>
                <p>{alert.state}</p>
              </div>
              <button
                type="button"
                className="outline"
                disabled={action.busy || alert.state === "acknowledged"}
                onClick={() =>
                  void action.perform(
                    async () => {
                      await request(
                        `admin/operations/alerts/${alert.id}/acknowledge`,
                        { expected_version: alert.version },
                      );
                      reload();
                    },
                    vi ? "Đã ghi nhận sự cố." : "Incident acknowledged.",
                  )
                }
              >
                {vi ? "Đã xem" : "Acknowledge"}
              </button>
            </li>
          ))}
      </ul>
      <h3>{vi ? "Tiến trình cục bộ" : "Local processes"}</h3>
      {data.roles.length === 0 ? (
        <p>
          {vi
            ? "Chưa có tiến trình báo trạng thái. Kích hoạt sau kiểm thử trực tiếp."
            : "No process has reported yet. Startup remains deferred until live validation."}
        </p>
      ) : (
        <ul className={styles.rows}>
          {data.roles.map((role) => (
            <li key={role.role}>
              <strong>{role.role}</strong>
              <span>
                {role.stale
                  ? vi
                    ? "Mất kết nối"
                    : "Heartbeat overdue"
                  : role.state}{" "}
                · {date(role.last_seen_at)} ICT
              </span>
            </li>
          ))}
        </ul>
      )}
      <h3>{vi ? "Phạm vi dữ liệu thực" : "Observed real-data coverage"}</h3>
      <dl className={styles.summary}>
        {Object.entries(data.coverage).map(([key, value]) => (
          <div key={key}>
            <dt>{key.replaceAll("_", " ")}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p>{data.readiness.live_results}</p>
      <h3>{vi ? "Sao lưu" : "Backups"}</h3>
      <p>
        {data.backups_configured
          ? vi
            ? "Đã cấu hình sao lưu ngày; kiểm tra kết quả bên dưới."
            : "Daily backups configured; inspect actual outcomes below."
          : vi
            ? "Sao lưu định kỳ chưa được kích hoạt."
            : "Daily backups are not activated."}
      </p>
      {data.backups.length === 0 ? (
        <p className={styles.muted}>
          {vi
            ? "Chưa ghi nhận bản sao lưu thành công."
            : "No successful backup is implied by an empty history."}
        </p>
      ) : (
        <ul className={styles.rows}>
          {data.backups.map((backup) => (
            <li key={backup.id}>
              <span>{date(backup.created_at)} ICT</span>
              <span>
                {backup.state}
                {backup.result?.elapsed_seconds !== undefined &&
                  ` · ${backup.result.elapsed_seconds.toFixed(1)}s`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
