import { useEffect, useRef, useState } from "react";
import { api, type JobGreetingDraft, type BatchPlatformResult } from "./lib/api";
import type { JobPosting } from "./types";

export const JOB_BATCH_LIMIT = 8;

function canSend(job: JobPosting) {
  try {
    const url = new URL(job.url);
    return job.platform === "boss" && url.origin === "https://www.zhipin.com" && /^\/job_detail\/.+\.html$/.test(url.pathname);
  } catch {
    return false;
  }
}

function isReviewedText(text: string) {
  return text !== "" && text === text.trim() && Array.from(text).length <= 180 &&
    !Array.from(text).some(char => (char.charCodeAt(0) < 32 && char !== "\n") || char.charCodeAt(0) === 127);
}

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
  const reviewed = jobs.filter(job => included.includes(job.id) && canSend(job)).map(job => ({
    job_id: job.id, text: edits[job.id] ?? drafts.find(item => item.job_id === job.id)?.text ?? ""
  }));
  const sendable = reviewed.length > 0 && reviewed.every(item => isReviewedText(item.text));
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
      setIncluded(jobs.filter(job => canSend(job) && ready.some(item => item.job_id === job.id)).map(job => job.id));
      setFeedback(`已为 ${ready.length} 个岗位生成草稿；没有发出任何消息。`);
    } catch (error) {
      setFeedback(`未能准备招呼语：${error instanceof Error ? error.message : "请求失败"}`);
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  async function apply() {
    if (!approval || !sendable || inFlight.current || dispatched.current) return;
    inFlight.current = true;
    dispatched.current = true;
    setAttempted(true);
    setBusy("apply");
    setFeedback("");
    try {
      const { items } = await api.sendReviewedJobGreetings(reviewed);
      setOutcomes(items);
      const confirmed = items.filter(item => item.status === "confirmed").length;
      setFeedback(`本批 ${confirmed} / ${reviewed.length} 条招呼语获得平台确认。未确认项请先在平台核对，不要直接重发。`);
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
      <p>先按每份 JD 生成草稿，核对岗位和正文后再发送。BOSS 可发送审核后的招呼语；其他平台可复制后手动发送。</p>
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
            <textarea aria-label={`${job.title}招呼语`} rows={3} value={value} readOnly={attempted || !!busy} onChange={event => {
              setApproval(false);
              setEdits(current => ({ ...current, [job.id]: event.target.value }));
            }} />
            <small>{Array.from(value).length} / 180 字{!isReviewedText(value) && " · 请输入有效正文，不留首尾空白。"}</small>
            <div className="job-detail-actions">
              <button type="button" disabled={!value.trim()} onClick={() => void copy(job, value)}>复制招呼语</button>
              <a href={job.url} target="_blank" rel="noreferrer">打开原岗位</a>
              {canSend(job) ? <label className="bulk-select-all"><input className="record-checkbox" type="checkbox" disabled={attempted || !!busy}
                checked={included.includes(job.id)} onChange={() => {
                  setApproval(false);
                  setIncluded(current => current.includes(job.id) ? current.filter(id => id !== job.id) : [...current, job.id]);
                }} />加入发送</label> : <small>需在平台手动发送</small>}
            </div>
          </> : draft ? <p>{draft.message}</p> : null}
          {result && <p><b>{result.status === "confirmed" ? "平台已确认" : "未记为成功"}</b> · {result.message}</p>}
        </section>;
      })}
      {drafts.some(item => item.status === "ready" && jobs.some(job => job.id === item.job_id && canSend(job))) && <section aria-label="批量发送确认">
        <p>将对勾选的 BOSS 岗位尝试打开沟通并发送上方已审阅的原文；本动作不上传简历附件，平台操作不可在此撤回。如平台要求验证，队列会暂停。</p>
        <label><input className="record-checkbox" type="checkbox" checked={approval} disabled={!sendable || attempted || !!busy}
          onChange={event => setApproval(event.target.checked)} /> 我确认这 {reviewed.length} 个岗位和当前招呼语，可以发送。</label>
        <div className="job-detail-actions">
          <button type="button" className="primary" disabled={!approval || !sendable || attempted || !!busy} onClick={() => void apply()}>
            {busy === "apply" ? "逐岗发送并核对平台回执…" : `发送 ${reviewed.length} 条招呼语`}
          </button>
        </div>
      </section>}
    </div>
  </dialog>;
}
