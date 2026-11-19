import { useEffect, useRef, type ReactNode } from "react";

export function JobSummary({ title, description, onOpen }: { title: string; description: string; onOpen: () => void }) {
  const text = description.replace(/\s+/g, " ").trim();
  return <button className="job-focus-trigger" type="button" aria-label={`放大阅读：${title}`} onClick={event => {
    event.stopPropagation();
    onOpen();
  }}>
    <span>{text.length > 150 ? `${text.slice(0, 150)}…` : text || "暂无岗位正文"}</span>
    <b>放大阅读 ↗</b>
  </button>;
}

export function JobFocus({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const trigger = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={dialog} className="job-detail-modal job-focus-dialog" aria-label="岗位聚焦阅读"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="job-focus-content">{children}</div>
  </dialog>;
}
