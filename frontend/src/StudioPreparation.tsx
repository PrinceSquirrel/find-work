import type { EvidenceCard, JobPosting, ResumeDraft } from "./types";
import { getJobDetailQuality } from "./lib/dashboard";

export async function prepareStudioJob(job: JobPosting, refresh: (id: number) => Promise<JobPosting>) {
  if (job.detail_status === "manual_filled" || getJobDetailQuality(job).isComplete) return job;
  const updated = await refresh(job.id);
  if (updated.detail_status !== "manual_filled" && !getJobDetailQuality(updated).isComplete) {
    throw new Error(`未取得完整 JD，未调用生成模型。${updated.detail_reason || "请在平台完成登录或验证后重试，也可在岗位详情补充原文。"}`);
  }
  return updated;
}

export function StudioPreparation({ job, resume, cards, selected, manual, busy, onManual, onToggle, onRefresh }: {
  job: JobPosting | null; resume: ResumeDraft | null; cards: EvidenceCard[]; selected: number[];
  manual: boolean; busy: boolean; onManual: (value: boolean) => void; onToggle: (id: number) => void; onRefresh: () => void;
}) {
  const complete = job && (job.detail_status === "manual_filled" || getJobDetailQuality(job).isComplete);
  const experiences = cards.filter(card => card.status === "confirmed" && card.category !== "education");
  return <section aria-label="岗位与经历准备" className="recommendation-list">
    <details open>
      <summary>{complete ? "完整 JD · 岗位要求" : "JD 待补全 · 生成前自动读取"}</summary>
      <p style={{ maxHeight: 180, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{job?.description || "请选择目标岗位。"}</p>
      {!complete && job ? <small>当前仅为岗位摘要：{job.detail_reason || "生成前会自动读取登录浏览器中的详情。"}</small> : null}
      <button type="button" disabled={!job || busy} onClick={onRefresh}>{busy ? "读取 JD 中..." : "更新完整 JD"}</button>
    </details>
    <div className="inline-note"><b>基础资料自动沿用</b><span>{resume?.filename || "尚未上传基础简历"} · 姓名、联系方式和教育信息来自基础简历，不作为项目经历逐条勾选。</span></div>
    <div className="evidence-actions">
      <button type="button" aria-pressed={!manual} disabled={busy} onClick={() => onManual(false)}>智能体自动选择</button>
      <button type="button" aria-pressed={manual} disabled={busy} onClick={() => onManual(true)}>手动调整经历</button>
    </div>
    {manual ? experiences.map(card => <label className="recommendation-card" key={card.id}>
      <input type="checkbox" disabled={busy} checked={selected.includes(card.id)} onChange={() => onToggle(card.id)} />
      <span>{card.title} · 已确认</span>
    </label>) : <p>默认自动模式：智能体结合完整 JD，从 {experiences.length} 张已确认经历中选择相关事实，一次完成选择与生成；无模型时明确使用本地规则。</p>}
    {!experiences.length ? <p>没有可用证据：请先确认一张真实项目、实习或技能卡片。</p> : null}
    <small>生成后展示实际引用并保留人审；此操作不会投递。</small>
  </section>;
}
