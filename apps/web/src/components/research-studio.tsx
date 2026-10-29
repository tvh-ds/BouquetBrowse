"use client";
import { useCallback, useState } from "react";
import type { Locale } from "@/lib/types";
import { CanonicalPanel, TaxonomyPanel } from "./research/curation";
import { ConversationsPanel, type Selection } from "./research/conversations";
import { EvaluationPanel } from "./research/evaluation";
import { HealthPanel } from "./research/health";
import { ProofsPanel } from "./research/proofs";
import styles from "./research-studio.module.css";

export function ResearchStudio({ lang }: { lang: Locale }) {
  const vi = lang === "vi";
  const [workspace, setWorkspace] = useState("health");
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState("[]");
  const [draftError, setDraftError] = useState("");
  const onChange = useCallback(() => setRefresh((n) => n + 1), []);
  function addImage(selection: Selection) {
    let entries: Selection[] = [];
    try {
      const value = JSON.parse(draft);
      if (
        !Array.isArray(value) ||
        value.some((entry) => !entry || typeof entry.media_id !== "string")
      )
        throw new Error("invalid draft");
      entries = value;
    } catch {
      setDraftError(
        vi
          ? "Sửa JSON bản nháp hiện tại trước khi thêm ảnh; nội dung đã được giữ lại."
          : "Correct the existing draft JSON before adding images; your text has been preserved.",
      );
      setWorkspace("evaluation");
      return;
    }
    if (!entries.some((entry) => entry.media_id === selection.media_id))
      setDraft(JSON.stringify([...entries, selection], null, 2));
    setWorkspace("evaluation");
  }
  const props = { lang, refresh, onChange };
  return (
    <section className={styles.studio}>
      <div className={styles.heading}>
        <h2>{vi ? "Nghiên cứu và vận hành" : "Research & operations"}</h2>
        <button
          className="outline"
          type="button"
          onClick={() => setRefresh((n) => n + 1)}
        >
          {vi ? "Làm mới không gian" : "Refresh workspace"}
        </button>
      </div>
      <label className={styles.workspace}>
        {vi ? "Không gian nghiên cứu" : "Research workspace"}
        <select
          value={workspace}
          onChange={(event) => setWorkspace(event.target.value)}
        >
          <option value="health">
            {vi ? "Vận hành và cảnh báo" : "Health & alerts"}
          </option>
          <option value="conversations">
            {vi ? "Hội thoại và ảnh" : "Conversations & images"}
          </option>
          <option value="taxonomy">
            {vi ? "Danh mục loài hoa" : "Flower taxonomy"}
          </option>
          <option value="canonical">
            {vi ? "Cấu hình bó hoa" : "Canonical configurations"}
          </option>
          <option value="evaluation">
            {vi ? "Tập đánh giá và nhãn" : "Evaluation & annotations"}
          </option>
          <option value="proofs">
            {vi ? "Bằng chứng xuất bản" : "Release proofs"}
          </option>
        </select>
      </label>
      {draftError && (
        <p role="alert" className="form-error">
          {draftError}
        </p>
      )}
      <div className={styles.panel} hidden={workspace !== "health"}>
        <HealthPanel {...props} active={workspace === "health"} />
      </div>
      <div className={styles.panel} hidden={workspace !== "conversations"}>
        <ConversationsPanel {...props} addImage={addImage} />
      </div>
      <div className={styles.panel} hidden={workspace !== "taxonomy"}>
        <TaxonomyPanel {...props} />
      </div>
      <div className={styles.panel} hidden={workspace !== "canonical"}>
        <CanonicalPanel {...props} />
      </div>
      <div className={styles.panel} hidden={workspace !== "evaluation"}>
        <EvaluationPanel
          {...props}
          draft={draft}
          setDraft={(text) => {
            setDraft(text);
            setDraftError("");
          }}
        />
      </div>
      <div className={styles.panel} hidden={workspace !== "proofs"}>
        <ProofsPanel {...props} />
      </div>
    </section>
  );
}
