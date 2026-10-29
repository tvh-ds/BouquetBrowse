"use client";
import { useState } from "react";
import {
  Feedback,
  Loading,
  date,
  request,
  short,
  useAction,
  useData,
  type PanelProps,
} from "./shared";
import styles from "../research-studio.module.css";

interface Capture {
  id: string;
  url: string;
  at: string;
  sorting: string;
  stop_reason: string;
  remaining_expansions: number | null;
}
interface CaptureDetail {
  id: string;
  stop_reason: string;
  sorting: string;
  remaining_expansions: number | null;
  messages: {
    version_id: string;
    post_id: string;
    text: string;
    author: string;
    account_id: string;
    profile_saved: boolean;
    published_at: string | null;
  }[];
  edges: {
    source_id: string;
    target_id: string | null;
    unresolved_platform_id: string | null;
    kind: string;
  }[];
  offers: {
    id: string;
    state: string;
    seller_id: string | null;
    listing_id: string | null;
  }[];
}
interface OfferEvidence {
  id: string;
  state: string;
  evidence: {
    messages: { version_id: string; text: string; seller: boolean }[];
    media: { media_id: string; role: string; region: number[] | null }[];
  };
}
export interface Selection {
  offer_id: string;
  media_id: string;
  split: "development" | "holdout";
  image_family: string;
}
export function ConversationsPanel({
  lang,
  refresh,
  addImage,
  onChange,
}: PanelProps & { addImage: (selection: Selection) => void }) {
  const vi = lang === "vi";
  const list = useData<{ items: Capture[] }>("admin/conversations", refresh);
  const [captureId, setCaptureId] = useState("");
  const [offerId, setOfferId] = useState("");
  const capture = useData<CaptureDetail>(
    captureId ? `admin/conversations/${captureId}` : null,
    refresh,
  );
  const offer = useData<OfferEvidence>(
    offerId ? `admin/conversations/offers/${offerId}` : null,
    refresh,
  );
  const action = useAction(onChange);
  if (!list.data) return <Loading error={list.error} />;
  const detail = capture.data?.id === captureId ? capture.data : null;
  const evidence = offer.data?.id === offerId ? offer.data : null;
  return (
    <>
      <h3>
        {vi
          ? "Bài đăng và các nhánh trả lời"
          : "Conversations and reply branches"}
      </h3>
      <p>
        {vi
          ? "Mỗi lần ghi nhận chỉ phản ánh nội dung đã quan sát. Không thấy một trả lời không có nghĩa là nó đã bị xóa."
          : "Each capture describes what was observed. An unobserved reply is not a deleted reply."}
      </p>
      <Feedback
        error={list.error || capture.error || offer.error || action.error}
        notice={action.notice}
      />
      {list.data.items.length === 0 && (
        <p>
          {vi
            ? "Chưa có hội thoại được ghi nhận. Bắt đầu bằng một lần chạy có giới hạn sau khi cấu hình."
            : "No conversations captured yet. Configure the dedicated browser before an explicit bounded run."}
        </p>
      )}
      <ul className={styles.rows}>
        {list.data.items.map((row) => (
          <li key={row.id}>
            <div>
              <strong>{short(row.id)}</strong>
              <p>
                {date(row.at)} ICT · {row.stop_reason}
              </p>
            </div>
            <button
              type="button"
              className="outline"
              onClick={() => {
                setCaptureId(row.id);
                setOfferId("");
              }}
            >
              {vi ? "Xem hội thoại" : "Inspect conversation"}
            </button>
          </li>
        ))}
      </ul>
      {captureId && !detail && <Loading error={capture.error} />}
      {detail && (
        <div className={styles.inspector}>
          <h3>{vi ? "Bằng chứng hội thoại" : "Conversation evidence"}</h3>
          <p>
            {vi ? "Thứ tự hiển thị" : "Sorting"}: {detail.sorting} ·{" "}
            {vi ? "Lý do dừng" : "Stop reason"}: {detail.stop_reason} ·{" "}
            {vi ? "Nhánh chưa mở" : "Remaining expansions"}:{" "}
            {detail.remaining_expansions ?? (vi ? "Chưa rõ" : "Unknown")}
          </p>
          {detail.messages.map((message) => {
            const edge = detail.edges.find(
              (e) => e.source_id === message.post_id && e.kind === "reply_to",
            );
            const parent = detail.messages.find(
              (m) => m.post_id === edge?.target_id,
            );
            return (
              <article className={styles.message} key={message.version_id}>
                <h4>@{message.author}</h4>
                <p className={styles.muted}>{date(message.published_at)} ICT</p>
                {edge && (
                  <p>
                    {parent
                      ? `${vi ? "Trả lời" : "Reply to"} @${parent.author}`
                      : vi
                        ? "Chưa ghi nhận tin nhắn gốc của nhánh."
                        : "Reply ancestor not captured."}
                  </p>
                )}
                <blockquote>
                  {message.text ||
                    (vi
                      ? "Bằng chứng đã hết hạn hoặc được gỡ."
                      : "Evidence expired or was removed.")}
                </blockquote>
                <details>
                  <summary>
                    {vi ? "Mã bằng chứng" : "Evidence identifiers"}
                  </summary>
                  <p className={styles.wrap}>{message.version_id}</p>
                </details>
                {message.profile_saved && (
                  <button
                    type="button"
                    className="outline"
                    disabled={action.busy}
                    onClick={() =>
                      void action.perform(
                        async () => {
                          await request(
                            `admin/curation/profiles/${message.account_id}/remove`,
                            {},
                          );
                          capture.reload();
                        },
                        vi
                          ? "Đã gỡ thông tin hồ sơ đã lưu."
                          : "Saved public profile details removed.",
                      )
                    }
                  >
                    {vi
                      ? "Gỡ thông tin hồ sơ đã lưu"
                      : "Remove saved profile details"}
                  </button>
                )}
              </article>
            );
          })}
          <h4>
            {vi ? "Quảng cáo được tách từ hội thoại" : "Offers in this capture"}
          </h4>
          <ul className={styles.rows}>
            {detail.offers.map((row) => (
              <li key={row.id}>
                <span>
                  {short(row.id)} · {row.state}
                </span>
                <button
                  type="button"
                  className="outline"
                  onClick={() => setOfferId(row.id)}
                >
                  {vi ? "Xem ảnh và liên kết" : "Inspect offer images"}
                </button>
              </li>
            ))}
          </ul>
          <details>
            <summary>
              {vi
                ? "Quan hệ trích dẫn và trả lời"
                : "Reply and quote relationships"}
            </summary>
            <ul>
              {detail.edges.map((edge, index) => (
                <li className={styles.wrap} key={index}>
                  {short(edge.source_id)} · {edge.kind} →{" "}
                  {edge.target_id
                    ? short(edge.target_id)
                    : vi
                      ? "Chưa ghi nhận"
                      : "Unresolved ancestor"}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
      {offerId && !evidence && <Loading error={offer.error} />}
      {evidence && (
        <section className={styles.inspector}>
          <h3>{vi ? "Ảnh đã gắn với quảng cáo" : "Associated offer images"}</h3>
          <p>
            {short(evidence.id)} · {evidence.state}
          </p>
          <div className={styles.images}>
            {evidence.evidence.media.map((media) => (
              <figure key={media.media_id}>
                {/* Private operational evidence may use same-origin authenticated image endpoints. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/v1/admin/conversations/offers/${evidence.id}/media/${media.media_id}`}
                  alt={
                    vi
                      ? "Ảnh bằng chứng của quảng cáo"
                      : "Offer evidence photograph"
                  }
                  width={240}
                  height={300}
                  loading="lazy"
                />
                <figcaption>
                  {media.role}
                  {media.region &&
                    ` · ${vi ? "Vùng ảnh đã duyệt" : "Reviewed image region"}`}
                </figcaption>
                <button
                  type="button"
                  className="outline"
                  onClick={() =>
                    addImage({
                      offer_id: evidence.id,
                      media_id: media.media_id,
                      split: "development",
                      image_family: media.media_id,
                    })
                  }
                >
                  {vi
                    ? "Thêm vào bản nháp đánh giá"
                    : "Add to evaluation draft"}
                </button>
              </figure>
            ))}
          </div>
          <p className={styles.muted}>
            {vi
              ? "Các trường hợp liên kết mơ hồ được xử lý ở thẻ Khám phá Threads."
              : "Resolve ambiguous associations in the Threads discovery tab before publication."}
          </p>
        </section>
      )}
    </>
  );
}
