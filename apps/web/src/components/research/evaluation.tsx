"use client";
import { useState } from "react";
import type { components } from "@/lib/generated-api";
import {
  Feedback,
  Loading,
  lines,
  money,
  request,
  short,
  useAction,
  useData,
  type PanelProps,
} from "./shared";
import styles from "../research-studio.module.css";

interface Dataset {
  id: string;
  name: string;
  kind: string;
  version: number;
}
interface Item {
  id: string;
  offer_id: string;
  media_id: string;
  version: number;
  state: string;
  labels: string[] | null;
  assessable: string[];
  reviewers: string[];
  seller_group: string;
  image_family: string;
  split: string;
  cost_microusd: number;
  latency_ms: number;
}
interface Detail extends Dataset {
  taxonomy: Record<string, string[]>;
  items: Item[];
}
export function EvaluationPanel({
  lang,
  refresh,
  draft,
  setDraft,
  onChange,
}: PanelProps & { draft: string; setDraft: (text: string) => void }) {
  const vi = lang === "vi";
  const list = useData<{ items: Dataset[] }>("admin/evaluations", refresh);
  const setup = useData<components["schemas"]["StatusView"]>(
    "admin/discovery/status",
    refresh,
  );
  const [selected, setSelected] = useState("");
  const [selectedItem, setSelectedItem] = useState("");
  const detail = useData<Detail>(
    selected ? `admin/evaluations/${selected}` : null,
    refresh,
  );
  const action = useAction(onChange);
  if (!list.data) return <Loading error={list.error} />;
  const data = detail.data?.id === selected ? detail.data : null;
  const item = data?.items.find((i) => i.id === selectedItem);
  return (
    <>
      <h3>{vi ? "Đánh giá nhận diện hoa" : "Recognition evaluation"}</h3>
      <p>
        {vi
          ? "Gắn nhãn trước khi chạy nhận diện. Tách tập theo người bán và họ ảnh; kết quả đánh giá không xuất bản sản phẩm."
          : "Annotate before inference. Split by seller and reused-image family. Evaluation cannot publish listings."}
      </p>
      <Feedback
        error={list.error || detail.error || setup.error || action.error}
        notice={action.notice}
      />
      <details open={draft !== "[]"}>
        <summary>{vi ? "Tạo tập đánh giá" : "Create evaluation set"}</summary>
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action.perform(
              async () => {
                const created = await request<{ id: string }>(
                  "admin/evaluations",
                  {
                    name: form.get("name"),
                    dataset_kind: form.get("kind"),
                    items: JSON.parse(draft),
                  },
                );
                list.reload();
                setSelected(created.id);
                setDraft("[]");
              },
              vi
                ? "Đã tạo tập đánh giá. Gắn nhãn từng ảnh trước khi chạy."
                : "Evaluation set created. Annotate every image before running.",
            );
          }}
        >
          <label>
            {vi ? "Tên tập" : "Dataset name"}
            <input name="name" required maxLength={80} />
          </label>
          <label>
            {vi ? "Nguồn dữ liệu" : "Dataset provenance"}
            <select name="kind">
              <option value="synthetic">
                {vi ? "Dữ liệu minh họa" : "Synthetic / demonstration"}
              </option>
              <option value="permitted_real">
                {vi ? "Dữ liệu thực được phép dùng" : "Permitted real data"}
              </option>
            </select>
          </label>
          <label>
            {vi ? "Ảnh được chọn (JSON)" : "Selected offer images (JSON)"}
            <textarea
              rows={7}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={200000}
              spellCheck={false}
            />
          </label>
          <p className={styles.muted}>
            {vi
              ? "Thêm ảnh từ trình xem hội thoại, rồi chọn development/holdout và image_family. Không nhập nội dung người mua vào đây."
              : "Add images from the conversation inspector, then set development/holdout and image_family. Do not paste buyer text here."}
          </p>
          <button disabled={action.busy || draft.trim() === "[]"}>
            {vi ? "Tạo tập riêng tư" : "Create private dataset"}
          </button>
        </form>
      </details>
      {!list.data.items.length && (
        <p>
          {vi
            ? "Chưa có tập đánh giá. Chọn ảnh từ một hội thoại đã ghi nhận."
            : "No evaluation sets yet. Select evidence images from a captured conversation."}
        </p>
      )}
      <ul className={styles.rows}>
        {list.data.items.map((dataset) => (
          <li key={dataset.id}>
            <div>
              <strong>{dataset.name}</strong>
              <p>
                {dataset.kind === "synthetic"
                  ? vi
                    ? "Minh họa — không thể đạt cổng dữ liệu thực"
                    : "Synthetic — cannot qualify a real-data gate"
                  : vi
                    ? "Dữ liệu thực được phép dùng"
                    : "Permitted real data"}
              </p>
            </div>
            <button
              type="button"
              className="outline"
              onClick={() => {
                setSelected(dataset.id);
                setSelectedItem("");
              }}
            >
              {vi ? "Mở tập" : "Open evaluation set"}
            </button>
          </li>
        ))}
      </ul>
      {selected && !data && <Loading error={detail.error} />}
      {data && (
        <section className={styles.inspector}>
          <h3>{data.name}</h3>
          <p>
            {vi
              ? "Giới hạn dự trù tối đa $0.10/ảnh, trong ngân sách AI chung. Yêu cầu chưa rõ kết quả cần phát lại thủ công."
              : "Up to $0.10 reserved per image within the shared model budget. Uncertain requests require explicit replay."}
          </p>
          <div className={styles.actions}>
            <button
              type="button"
              disabled={
                action.busy ||
                !setup.data?.model_configured ||
                !setup.data?.postgres ||
                data.items.some((i) => i.labels === null) ||
                data.items.every((i) => i.state === "completed")
              }
              onClick={() =>
                void action.perform(
                  async () => {
                    await request(`admin/evaluations/${data.id}/run`, {
                      expected_version: data.version,
                    });
                    detail.reload();
                  },
                  vi ? "Đã xếp lịch đánh giá." : "Evaluation jobs queued.",
                )
              }
            >
              {vi ? "Chạy đánh giá" : "Run evaluation"}
            </button>
            <button
              className="outline"
              type="button"
              disabled={
                action.busy || !data.items.every((i) => i.state === "completed")
              }
              onClick={() =>
                void action.perform(
                  async () => {
                    await request(`admin/evaluations/${data.id}/stage`, {
                      expected_version: data.version,
                    });
                  },
                  vi
                    ? "Đã tạo báo cáo chờ duyệt ở mục Bằng chứng."
                    : "Proof report staged. Inspect it in Release proofs.",
                )
              }
            >
              {vi ? "Tạo báo cáo bằng chứng" : "Stage proof report"}
            </button>
            {data.items.every((i) => i.state === "completed") && (
              <a
                className="button outline"
                href={`/api/v1/admin/evaluations/${data.id}/export`}
              >
                {vi ? "Tải JSONL riêng tư" : "Download private JSONL"}
              </a>
            )}
          </div>
          {(!setup.data?.model_configured || !setup.data?.postgres) && (
            <p className={styles.muted}>
              {vi
                ? "Cần khóa mô hình cục bộ và PostgreSQL trước khi chủ động chạy suy luận."
                : "A local model key and PostgreSQL checkpoints are required before explicitly running inference."}
            </p>
          )}
          <ul className={styles.rows}>
            {data.items.map((row) => (
              <li key={row.id}>
                <div>
                  <strong>{short(row.media_id)}</strong>
                  <p>
                    {row.split} · {row.state} · {money(row.cost_microusd)} ·{" "}
                    {row.latency_ms}ms
                  </p>
                </div>
                <button
                  className="outline"
                  type="button"
                  onClick={() => setSelectedItem(row.id)}
                >
                  {vi ? "Gắn nhãn ảnh" : "Annotate image"}
                </button>
              </li>
            ))}
          </ul>
          {item && (
            <Annotation
              key={`${item.id}:${item.version}`}
              item={item}
              data={data}
              lang={lang}
              busy={action.busy}
              save={(body) =>
                void action.perform(
                  async () => {
                    await request(
                      `admin/evaluations/${data.id}/items/${item.id}/annotation`,
                      body,
                    );
                    detail.reload();
                    list.reload();
                  },
                  vi
                    ? "Đã lưu nhãn và lịch sử đối chiếu."
                    : "Annotation and review history saved.",
                )
              }
            />
          )}
        </section>
      )}
    </>
  );
}
function Annotation({
  item,
  data,
  lang,
  busy,
  save,
}: {
  item: Item;
  data: Detail;
  lang: PanelProps["lang"];
  busy: boolean;
  save: (body: components["schemas"]["AnnotationBody"]) => void;
}) {
  const vi = lang === "vi";
  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        save({
          expected_version: item.version,
          labels: form.getAll("labels").map(String),
          assessable: form.getAll("assessable").map(String),
          reviewers: lines(form.get("reviewers")),
          split: String(form.get("split")) as "development" | "holdout",
          image_family: String(form.get("family")),
        });
      }}
    >
      <h4>
        {vi ? "Nhãn tham chiếu độc lập" : "Independent reference annotation"}
      </h4>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className={styles.annotationImage}
        src={`/api/v1/admin/conversations/offers/${item.offer_id}/media/${item.media_id}`}
        alt={
          vi
            ? "Ảnh bó hoa cần gắn nhãn"
            : "Bouquet image for reference annotation"
        }
        width={320}
        height={400}
      />
      <p className={styles.muted}>
        {vi ? "Nhóm người bán" : "Seller group"}: {short(item.seller_group)}
      </p>
      <div className={styles.columns}>
        <label>
          {vi ? "Loài hoa nhìn thấy" : "Visible flower types"}
          <select
            name="labels"
            multiple
            size={6}
            defaultValue={item.labels || []}
          >
            {Object.keys(data.taxonomy).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>
        <label>
          {vi ? "Loài hoa có thể đánh giá" : "Assessable flower types"}
          <select
            name="assessable"
            multiple
            size={6}
            defaultValue={item.assessable}
          >
            {Object.keys(data.taxonomy).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className={styles.muted}>
        {vi
          ? "Chọn nhiều mục nếu cần. Để trống nhóm có thể đánh giá nếu không thể xác định loài nào."
          : "Select multiple types where appropriate. Leave assessable types empty if none can be judged."}
      </p>
      <label>
        {vi ? "Tập dữ liệu" : "Dataset split"}
        <select name="split" defaultValue={item.split}>
          <option value="development">Development</option>
          <option value="holdout">Holdout</option>
        </select>
      </label>
      <label>
        {vi ? "Họ ảnh tái sử dụng" : "Reused-image family"}
        <input
          name="family"
          required
          maxLength={160}
          defaultValue={item.image_family}
        />
      </label>
      <label>
        {vi
          ? "Người đối chiếu, phân cách bằng dấu phẩy"
          : "Reference reviewers, comma separated"}
        <input
          name="reviewers"
          required
          maxLength={800}
          defaultValue={item.reviewers.join(", ")}
        />
      </label>
      <button disabled={busy}>
        {vi ? "Lưu nhãn tham chiếu" : "Save reference annotation"}
      </button>
    </form>
  );
}
