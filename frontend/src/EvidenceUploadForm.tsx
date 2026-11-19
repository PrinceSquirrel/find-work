import { useId, useRef } from "react";
import { EVIDENCE_PARSE_EXTENSIONS } from "./lib/evidenceUpload";

export function EvidenceUploadForm({ files, busy, onFilesChange, onUpload }: {
  files: File[]; busy: boolean; onFilesChange: (files: File[]) => void; onUpload: () => void | Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const inputId = useId();
  return <form className="evidence-upload" aria-label="资料选择与上传" onSubmit={event => {
    event.preventDefault();
    if (busy) return;
    if (!files.length) { input.current?.click(); return; }
    void onUpload();
  }}>
    <label className="file-drop evidence-file-drop" htmlFor={inputId}>
      <input ref={input} id={inputId} type="file" aria-label="选择个人资料文件" multiple disabled={busy}
        accept={[...EVIDENCE_PARSE_EXTENSIONS].map(extension => `.${extension}`).join(",")}
        onChange={event => {
          const selected = Array.from(event.currentTarget.files ?? []);
          // Keep File objects in state and reset the native value so the same file can be chosen again.
          event.currentTarget.value = "";
          if (selected.length) onFilesChange(selected);
        }} />
      <span style={{ overflowWrap: "anywhere" }}>{files.length ? `已选择 ${files.length} 份：${files.map(file => file.name).join("、")}` : "选择个人资料文件"}</span>
      <small>DOCX / 文字 PDF / TXT / MD / PNG / JPG；图片与扫描件需补字。未选文件时点击右侧按钮选择，选好后再确认上传。</small>
    </label>
    <button className="primary" type="submit" disabled={busy}>{busy ? "上传中..." : files.length ? "上传所选资料" : "加入本地资料库"}</button>
  </form>;
}
