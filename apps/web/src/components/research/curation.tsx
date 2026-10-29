"use client";
import { useState } from "react";
import type { components } from "@/lib/generated-api";
import {
  Feedback,
  Loading,
  lines,
  request,
  short,
  useAction,
  useData,
  type PanelProps,
} from "./shared";
import styles from "../research-studio.module.css";

interface Term {
  id: string;
  key: string;
  version: string;
  state: string;
  aliases: string[];
  fingerprint: string;
}
interface Taxonomy {
  version: string;
  vocabulary: Record<string, string[]>;
  items: Term[];
}
export function TaxonomyPanel({ lang, refresh, onChange }: PanelProps) {
  const vi = lang === "vi";
  const { data, error, reload } = useData<Taxonomy>(
    "admin/curation/taxonomy",
    refresh,
  );
  const [selected, setSelected] = useState("");
  const action = useAction(onChange);
  if (!data) return <Loading error={error} />;
  const term = data.items.find(
    (t) => t.id === selected && t.state === "proposed",
  );
  return (
    <>
      <h3>{vi ? "Danh mục loài hoa" : "Flower taxonomy"}</h3>
      <p>
        {vi ? "Phiên bản hiện tại" : "Current version"}:{" "}
        <strong>{data.version}</strong>.{" "}
        {vi
          ? "Nhãn mới cần đánh giá trước khi được hỗ trợ thị giác."
          : "New labels remain visually unvalidated until their benchmark passes."}
      </p>
      <Feedback error={error || action.error} notice={action.notice} />
      <ul className={styles.rows}>
        {data.items
          .filter((t) => t.state === "proposed")
          .map((t) => (
            <li key={t.id}>
              <div>
                <strong>{t.key}</strong>
                <p>{t.version}</p>
              </div>
              <button
                className="outline"
                type="button"
                onClick={() => setSelected(t.id)}
              >
                {vi ? "Xem đề xuất" : "Review proposal"}
              </button>
            </li>
          ))}
      </ul>
      {!data.items.some((t) => t.state === "proposed") && (
        <p>
          {vi
            ? "Chưa có nhãn hoặc bí danh chờ duyệt."
            : "No flower labels or aliases await review."}
        </p>
      )}
      {term && (
        <form
          key={term.id}
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const decision = ((
              event.nativeEvent as SubmitEvent
            ).submitter?.getAttribute("value") ||
              (term.version === data.version ? "promote" : "rebase")) as
              "promote" | "reject" | "rebase";
            const body: components["schemas"]["TaxonomyDecision"] = {
              expected_fingerprint: term.fingerprint,
              decision,
              new_version:
                decision === "rebase"
                  ? data.version
                  : String(form.get("version")),
              canonical_key: String(form.get("key") || "") || null,
              aliases: lines(form.get("aliases")),
              reason: String(form.get("reason")),
            };
            void action.perform(
              async () => {
                await request(
                  `admin/curation/taxonomy/${term.id}/decision`,
                  body,
                );
                reload();
                setSelected("");
              },
              vi ? "Đã lưu quyết định danh mục." : "Taxonomy decision saved.",
            );
          }}
        >
          <h4>{term.key}</h4>
          <label>
            {vi ? "Tên chuẩn" : "Canonical category key"}
            <input
              name="key"
              list="flower-category-keys"
              pattern="[a-z][a-z0-9-]{0,79}"
              maxLength={80}
              defaultValue={
                /^[a-z][a-z0-9-]{0,79}$/.test(term.key) ? term.key : ""
              }
              placeholder="garden-rose"
            />
          </label>
          <datalist id="flower-category-keys">
            {Object.keys(data.vocabulary).map((key) => (
              <option key={key} value={key} />
            ))}
          </datalist>
          <label>
            {vi ? "Bí danh, mỗi dòng một tên" : "Literal aliases, one per line"}
            <textarea
              name="aliases"
              rows={3}
              maxLength={2400}
              defaultValue={term.aliases.join("\n")}
            />
          </label>
          <label>
            {vi ? "Phiên bản mới" : "New taxonomy version"}
            <input
              name="version"
              required
              maxLength={80}
              pattern="[a-zA-Z0-9_-]{1,80}"
              defaultValue={
                data.version === "flowers-v2"
                  ? "flowers-v3"
                  : `${data.version.slice(0, 70)}-next`
              }
            />
          </label>
          <label>
            {vi ? "Lý do" : "Review reason"}
            <textarea
              name="reason"
              required
              minLength={10}
              maxLength={500}
              rows={3}
            />
          </label>
          <div className={styles.actions}>
            {term.version === data.version ? (
              <button type="submit" value="promote" disabled={action.busy}>
                {vi ? "Duyệt phiên bản mới" : "Approve new version"}
              </button>
            ) : (
              <button type="submit" value="rebase" disabled={action.busy}>
                {vi ? "Chuyển sang phiên bản hiện tại" : "Rebase proposal"}
              </button>
            )}
            <button
              type="submit"
              className="outline"
              value="reject"
              disabled={action.busy}
            >
              {vi ? "Từ chối" : "Reject proposal"}
            </button>
          </div>
        </form>
      )}
      <details>
        <summary>{vi ? "Các tên hiện có" : "Current category aliases"}</summary>
        <dl className={styles.summary}>
          {Object.entries(data.vocabulary).map(([key, aliases]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{aliases.join(", ")}</dd>
            </div>
          ))}
        </dl>
      </details>
    </>
  );
}
interface Canonical {
  offers: {
    id: string;
    seller_id: string;
    listing_id: string | null;
    fingerprint: string;
    links_hash: string;
  }[];
  configurations: { id: string; seller_id: string }[];
  links: {
    id: string;
    offer_id: string;
    configuration_id: string;
    state: string;
    fingerprint: string;
  }[];
}
export function CanonicalPanel({ lang, refresh, onChange }: PanelProps) {
  const vi = lang === "vi";
  const { data, error, reload } = useData<Canonical>(
    "admin/curation/canonical",
    refresh,
  );
  const [selected, setSelected] = useState("");
  const action = useAction(onChange);
  if (!data) return <Loading error={error} />;
  const offer = data.offers.find((o) => o.id === selected);
  return (
    <>
      <h3>
        {vi ? "Liên kết cấu hình bó hoa" : "Canonical bouquet configurations"}
      </h3>
      <p>
        {vi
          ? "Chỉ liên kết cùng người bán dựa trên bằng chứng hoặc đối chiếu đã duyệt. Mã quảng cáo và URL được giữ nguyên."
          : "Consolidate only within one seller using reviewed configuration evidence. Offer IDs and listing URLs stay unchanged."}
      </p>
      <Feedback error={error || action.error} notice={action.notice} />
      <label className={styles.field}>
        {vi ? "Chọn quảng cáo" : "Offer to link"}
        <select
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          <option value="">
            {vi
              ? "Chọn quảng cáo có người bán"
              : "Choose a seller-backed offer"}
          </option>
          {data.offers.map((o) => (
            <option key={o.id} value={o.id}>
              {short(o.id)} · seller {short(o.seller_id)}
            </option>
          ))}
        </select>
      </label>
      {data.offers.length === 0 && (
        <p>
          {vi
            ? "Chưa có quảng cáo đủ bằng chứng về người bán."
            : "No seller-backed offers are available yet."}
        </p>
      )}
      {offer && (
        <form
          className={styles.form}
          key={offer.id}
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action.perform(
              async () => {
                await request("admin/curation/canonical/link", {
                  offer_id: offer.id,
                  expected_fingerprint: offer.fingerprint,
                  expected_links_hash: offer.links_hash,
                  configuration_id: form.get("configuration") || null,
                  reason: form.get("reason"),
                });
                reload();
              },
              vi ? "Đã lưu liên kết." : "Canonical link saved.",
            );
          }}
        >
          <label>
            {vi
              ? "Nhóm cấu hình của người bán"
              : "Seller's configuration group"}
            <select name="configuration">
              <option value="">
                {vi ? "Tạo nhóm mới" : "Create a new group"}
              </option>
              {data.configurations
                .filter((c) => c.seller_id === offer.seller_id)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {short(c.id)}
                  </option>
                ))}
            </select>
          </label>
          <label>
            {vi ? "Lý do đối chiếu" : "Reason for reviewed match"}
            <textarea
              name="reason"
              required
              minLength={10}
              maxLength={500}
              rows={3}
            />
          </label>
          <button disabled={action.busy}>
            {vi ? "Lưu liên kết" : "Save canonical link"}
          </button>
        </form>
      )}
      <ul className={styles.rows}>
        {data.links.map((link) => (
          <li key={link.id}>
            <div>
              <strong>
                {short(link.offer_id)} → {short(link.configuration_id)}
              </strong>
              <p>{link.state}</p>
            </div>
            {link.state === "accepted" && (
              <details>
                <summary>{vi ? "Gỡ liên kết" : "Revoke link"}</summary>
                <form
                  className={styles.form}
                  onSubmit={(event) => {
                    event.preventDefault();
                    const form = new FormData(event.currentTarget);
                    void action.perform(
                      async () => {
                        await request(
                          `admin/curation/canonical/${link.id}/unlink`,
                          {
                            expected_fingerprint: link.fingerprint,
                            reason: form.get("reason"),
                          },
                        );
                        reload();
                      },
                      vi
                        ? "Đã gỡ liên kết, giữ lại lịch sử."
                        : "Link revoked; history preserved.",
                    );
                  }}
                >
                  <label>
                    {vi ? "Lý do gỡ" : "Revocation reason"}
                    <textarea
                      name="reason"
                      required
                      minLength={10}
                      maxLength={500}
                      rows={2}
                    />
                  </label>
                  <button className="outline" disabled={action.busy}>
                    {vi ? "Gỡ liên kết đã duyệt" : "Revoke reviewed link"}
                  </button>
                </form>
              </details>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
