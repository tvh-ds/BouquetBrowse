"use client";
import { useState } from "react";
import {
  Feedback,
  Loading,
  request,
  short,
  useAction,
  useData,
  type PanelProps,
} from "./shared";
import styles from "../research-studio.module.css";

interface Category {
  supported: boolean;
  sufficiently_sampled: boolean;
  joint_holdout: {
    precision: number | null;
    recall: number | null;
    positive: number;
    negative: number;
  };
}
interface Proof {
  id: string;
  kind: string;
  state: string;
  report_hash: string;
  configuration_hash: string;
  report: {
    dataset_kind: string;
    dataset_ready: boolean;
    images?: number;
    conversations?: number;
    failures?: string[];
    categories?: Record<string, Category>;
  };
}
export function ProofsPanel({ lang, refresh, onChange }: PanelProps) {
  const vi = lang === "vi";
  const { data, error, reload } = useData<{ items: Proof[] }>(
    "admin/pilot/proofs",
    refresh,
  );
  const [selected, setSelected] = useState("");
  const action = useAction(onChange);
  if (!data) return <Loading error={error} />;
  const proof = data.items.find((p) => p.id === selected);
  const canApprove =
    proof?.report.dataset_kind === "permitted_real" &&
    proof.report.dataset_ready &&
    (proof.kind !== "recognition" ||
      Object.values(proof.report.categories || {}).some((c) => c.supported));
  return (
    <>
      <h3>{vi ? "Bằng chứng mở cổng xuất bản" : "Release proofs"}</h3>
      <p>
        {vi
          ? "Kết quả minh họa không chứng nhận chất lượng thực tế. Cần cả kiểm chứng hội thoại và nhận diện đúng cấu hình."
          : "Synthetic results do not establish live quality. Both conversation and recognition proofs must match the current configuration."}
      </p>
      <Feedback error={error || action.error} notice={action.notice} />
      <details>
        <summary>
          {vi
            ? "Tạo báo cáo từ tham chiếu riêng tư"
            : "Stage operator reference data"}
        </summary>
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action.perform(
              async () => {
                let values = JSON.parse(String(form.get("values")));
                if (!Array.isArray(values))
                  throw new Error("Reference data must be a JSON array.");
                if (
                  form.get("kind") === "conversation" &&
                  values.some(
                    (row) =>
                      Array.isArray(row.offers) &&
                      row.offers.some(
                        (offer: Record<string, unknown>) =>
                          "commercial_reference" in offer,
                      ),
                  )
                ) {
                  values = (
                    await request<{ values: unknown[] }>(
                      "admin/evaluations/conversation-references",
                      { values },
                    )
                  ).values;
                }
                const result = await request<{ id: string }>(
                  "admin/pilot/proofs",
                  {
                    kind: form.get("kind"),
                    dataset_kind: form.get("provenance"),
                    values,
                  },
                );
                reload();
                setSelected(result.id);
              },
              vi
                ? "Đã tạo báo cáo chờ duyệt."
                : "Reference report staged for review.",
            );
          }}
        >
          <label>
            {vi ? "Loại kiểm chứng" : "Proof kind"}
            <select name="kind">
              <option value="conversation">Conversation workflow</option>
              <option value="recognition">Mixed-flower recognition</option>
            </select>
          </label>
          <label>
            {vi ? "Nguồn dữ liệu" : "Reference provenance"}
            <select name="provenance">
              <option value="synthetic">Synthetic / demonstration</option>
              <option value="permitted_real">Permitted real data</option>
            </select>
          </label>
          <label>
            {vi
              ? "Tham chiếu đã đối chiếu (mảng JSON)"
              : "Reviewed reference values (JSON array)"}
            <textarea
              name="values"
              required
              rows={7}
              maxLength={1000000}
              defaultValue="[]"
              spellCheck={false}
            />
          </label>
          <p className={styles.muted}>
            {vi
              ? "Tự ghi nhận giá, số lượng, bằng chứng và trường hợp phải bỏ qua. Không sao chép câu trả lời mô hình làm đáp án tham chiếu."
              : "Author expected prices, counts, evidence and abstentions independently. Do not use model answers as reference truth."}
          </p>
          <button disabled={action.busy}>
            {vi ? "Tính báo cáo tham chiếu" : "Compute reference report"}
          </button>
        </form>
      </details>
      {data.items.length === 0 && (
        <p>
          {vi
            ? "Chưa có báo cáo. Chạy và đối chiếu dữ liệu thật theo lệnh của bạn trước khi mở cổng."
            : "No proof reports yet. Real evaluation and joint review remain pending your explicit live-test command."}
        </p>
      )}
      <ul className={styles.rows}>
        {data.items.map((p) => (
          <li key={p.id}>
            <div>
              <strong>
                {p.kind} · {short(p.id)}
              </strong>
              <p>
                {p.state} · {p.report.dataset_kind} ·{" "}
                {p.report.images ?? p.report.conversations ?? 0}{" "}
                {p.kind === "recognition" ? "images" : "conversations"}
              </p>
            </div>
            <button
              type="button"
              className="outline"
              onClick={() => setSelected(p.id)}
            >
              {vi ? "Xem báo cáo" : "Inspect proof report"}
            </button>
          </li>
        ))}
      </ul>
      {proof && (
        <section className={styles.inspector}>
          <h3>
            {proof.kind === "recognition"
              ? vi
                ? "Kết quả nhận diện"
                : "Recognition results"
              : vi
                ? "Kết quả kiểm chứng hội thoại"
                : "Conversation workflow results"}
          </h3>
          <p>
            {proof.report.dataset_kind === "synthetic"
              ? vi
                ? "Báo cáo minh họa — không thể phê duyệt cho dữ liệu thực."
                : "Synthetic report — ineligible for real-data approval."
              : proof.report.dataset_ready
                ? vi
                  ? "Đủ số mẫu; cần người quản trị đối chiếu và phê duyệt."
                  : "Sample gate met; administrator review and attestation still required."
                : vi
                  ? "Chưa đạt yêu cầu mẫu hoặc chất lượng."
                  : "Sample or quality gate has not passed."}
          </p>
          {proof.report.categories && (
            <div className={styles.table}>
              <table>
                <caption>
                  {vi
                    ? "Kết quả tập holdout theo loài hoa"
                    : "Held-out performance by flower type"}
                </caption>
                <thead>
                  <tr>
                    <th>Flower</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>Positive / negative</th>
                    <th>Support</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(proof.report.categories).map(
                    ([flower, category]) => (
                      <tr key={flower}>
                        <th scope="row">{flower}</th>
                        <td>{percent(category.joint_holdout.precision)}</td>
                        <td>{percent(category.joint_holdout.recall)}</td>
                        <td>
                          {category.joint_holdout.positive} /{" "}
                          {category.joint_holdout.negative}
                        </td>
                        <td>
                          {category.supported
                            ? "Supported"
                            : category.sufficiently_sampled
                              ? "Target unmet"
                              : "Under-sampled"}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          )}
          {proof.report.failures && (
            <p>
              {vi ? "Lỗi được ghi nhận" : "Recorded failures"}:{" "}
              {proof.report.failures.length
                ? proof.report.failures.join(", ")
                : vi
                  ? "Không có trong tập này"
                  : "None in this set"}
            </p>
          )}
          <details>
            <summary>
              {vi
                ? "Báo cáo và mã cấu hình đầy đủ"
                : "Full report and configuration identity"}
            </summary>
            <pre className={styles.wrap}>
              {JSON.stringify(
                {
                  configuration_hash: proof.configuration_hash,
                  report_hash: proof.report_hash,
                  report: proof.report,
                },
                null,
                2,
              )}
            </pre>
          </details>
          {(canApprove || proof.state === "approved") && (
            <form
              className={styles.form}
              key={proof.id}
              onSubmit={(event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                const revoke = proof.state === "approved";
                void action.perform(
                  async () => {
                    await request(
                      `admin/pilot/proofs/${proof.id}/${revoke ? "revoke" : "approve"}`,
                      {
                        expected_report_hash: proof.report_hash,
                        permission_reference: form.get("permission"),
                        joint_review_confirmed: form.has("joint"),
                      },
                    );
                    reload();
                  },
                  revoke
                    ? vi
                      ? "Đã thu hồi chứng nhận."
                      : "Proof approval revoked."
                    : vi
                      ? "Đã phê duyệt bằng chứng cho đúng cấu hình."
                      : "Proof approved for its exact configuration.",
                );
              }}
            >
              <label>
                {vi
                  ? "Mã hồ sơ quyền sử dụng riêng tư"
                  : "Private permission-record reference"}
                <input name="permission" required maxLength={160} />
              </label>
              {proof.state !== "approved" && (
                <label className={styles.check}>
                  <input name="joint" type="checkbox" required />
                  {vi
                    ? "Đã cùng đối chiếu các nhãn tham chiếu độc lập."
                    : "Joint review of independent reference labels is complete."}
                </label>
              )}
              <button disabled={action.busy}>
                {proof.state === "approved"
                  ? vi
                    ? "Thu hồi phê duyệt"
                    : "Revoke approval"
                  : vi
                    ? "Phê duyệt bằng chứng thực"
                    : "Approve real-data proof"}
              </button>
            </form>
          )}
        </section>
      )}
    </>
  );
}
function percent(value: number | null) {
  return value === null ? "Not assessable" : `${(value * 100).toFixed(1)}%`;
}
