import { useEffect, useRef, useState } from "react";
import { api, type JobGreetingDraft, type BatchPlatformResult } from "./lib/api";
import type { JobPosting } from "./types";

export const JOB_BATCH_LIMIT = 8;

export function JobBatchDialog({ jobs, onClose, onRefresh }: {
  jobs: JobPosting[]; onClose: () => void; onRefresh: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const dispatched = useRef(false);
  const [busy, setBusy] = useState<"prepare" | "apply" | null>(null);
  const [drafts, setDrafts] = useState<JobGreetingDraft[]>([]);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [included, setIncluded] = useState<number[]>([]);
  const [approval, setApproval] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [outcomes, setOutcomes] = useState<BatchPlatformResult[]>([]);
  const [feedback, setFeedback] = useState("");
  useEffect(() => {
    const trigger = document.activeElement;
    const node = dialog.current;
    node?.showModal();
    return () => {
      node?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus({ preventScroll: true });
    };
  }, []);

  async function prepare() {
    if (inFlight.current || dispatched.current) return;
    inFlight.current = true;
    setBusy("prepare");
    setFeedback("");
    setApproval(false);
    setDrafts([]);
    setIncluded([]);
    setEdits({});
    try {
      const { items } = await api.prepareJobGreetings(jobs.map(job => job.id));
      const ready = items.filter(item => item.status === "ready");
      setDrafts(items);
      setIncluded(ready.map(item => item.job_id));
      setFeedback(`已为 ${ready.length} 个岗位生成草稿；没有发出任何消息。`);
    } catch (error) {
      setFeedback(`未能准备招呼语：${error instanceof Error ? error.message : "请求失败"}`);
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  async function apply() {
    if (!approval || !included.length || inFlight.current || dispatched.current) return;
    inFlight.current = true;
    dispatched.current = true;
    setAttempted(true);
    setBusy("apply");
    setFeedback("");
    try {
      const { items } = await api.applyPlatformBatch(included, true);
      setOutcomes(items);
      const confirmed = items.filter(item => item.status === "confirmed").length;
      setFeedback(`本批 ${confirmed} / ${included.length} 项获得平台确认。未确认项请先在平台核对，不要直接重发。`);
      await onRefresh().catch(() => setFeedback(`本批 ${confirmed} 项获得平台确认；本地列表刷新失败，请刷新页面核对。`));
    } catch {
      setFeedback("未收到批次结果，状态未知。请先到平台核对，不要直接重发。");
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  async function copy(job: JobPosting, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setFeedback(`已复制「${job.title}」招呼语，未发送。`);
    } catch {
      setFeedback("无法自动复制，请选中文案手动复制。");
    }
  }

  return <dialog ref={dialog} className="job-detail-modal job-focus-dialog" aria-label="招呼语与批量投递"
    onCancel={event => { event.preventDefault(); if (!inFlight.current) onClose(); }}>
    <div className="job-focus-content">
      <header className="modal-heading"><div><span>岗位行动清单</span><h2>为 {jobs.length} 个岗位准备招呼语</h2></div>
        <button type="button" autoFocus disabled={!!busy} onClick={onClose}>关闭</button></header>
      <p>先按每份 JD 生成草稿，可编辑后复制到对应岗位的聊天框。平台原生批量操作不会发送下面这些自定义文案。</p>
      <div className="job-detail-actions">
        <button type="button" className="primary" disabled={!!busy || attempted} onClick={() => void prepare()}>{busy === "prepare" ? "逐个读取 JD 并生成…" : "一键生成各岗位招呼语"}</button>
      </div>
      {feedback && <div className="inline-note" role="status">{feedback}</div>}
      {jobs.map(job => {
        const draft = drafts.find(item => item.job_id === job.id);
        const result = outcomes.find(item => item.job_id === job.id);
        const value = edits[job.id] ?? draft?.text ?? "";
        return <section key={job.id} aria-label={job.title}>
          <h3>{job.title}</h3><small>{job.company} · {job.platform === "boss" ? "BOSS直聘" : "实习僧"}</small>
          {draft?.status === "ready" ? <>
            <p>{draft.mode === "model" ? `模型草稿 · ${draft.model}` : "本地规则草稿 · 未调用模型"}</p>
            <textarea aria-label={`${job.title}招呼语`} rows={3} value={value} onChange={event => setEdits(current => ({ ...current, [job.id]: event.target.value }))} />
            <div className="job-detail-actions">
              <button type="button" disabled={!value.trim()} onClick={() => void copy(job, value)}>复制招呼语</button>
              <a href={job.url} target="_blank" rel="noreferrer">打开原岗位</a>
              <label className="bulk-select-all"><input className="record-checkbox" type="checkbox" disabled={attempted || !!busy}
                checked={included.includes(job.id)} onChange={() => {
                  setApproval(false);
                  setIncluded(current => current.includes(job.id) ? current.filter(id => id !== job.id) : [...current, job.id]);
                }} />加入原生操作</label>
            </div>
          </> : draft ? <p>{draft.message}</p> : null}
          {result && <p><b>{result.status === "confirmed" ? "平台已确认" : "未记为成功"}</b> · {result.message}</p>}
        </section>;
      })}
      {drafts.length > 0 && <section aria-label="批量操作确认">
        <p>这一步可能按平台原生流程发送默认招呼或投递简历，已发送的动作无法由本工作台撤销。</p>
        <label><input className="record-checkbox" type="checkbox" checked={approval} disabled={!included.length || attempted || !!busy}
          onChange={event => setApproval(event.target.checked)} /> 我确认对勾选的 {included.length} 个岗位执行平台原生沟通／投递，不发送自定义招呼语。</label>
        <div className="job-detail-actions">
          <button type="button" disabled={!approval || !included.length || attempted || !!busy} onClick={() => void apply()}>
            {busy === "apply" ? "按顺序执行，等待平台证明…" : `确认批量执行 ${included.length} 项`}
          </button>
        </div>
      </section>}
    </div>
  </dialog>;
}
