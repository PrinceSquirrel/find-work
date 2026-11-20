import { useState } from "react";
import type { JobPosting } from "./types";

export const PREFERENCE_FACTORS = [
  ["salary", "工资"], ["benefits", "福利"], ["location", "地区"],
  ["hours", "工作时长"], ["work", "工作内容"], ["skills", "技能匹配"],
] as const;
export const JOB_PREFS_KEY = "squirrel-world.job-preferences.v1";
type Factor = (typeof PREFERENCE_FACTORS)[number][0];
type Ratings = Partial<Record<Factor, number>>;
type Preferences = { weights: Ratings; jobs: Record<string, Ratings> };
const SCALE = [0, 1, 2, 3, 4, 5];
const DEFAULT_WEIGHT = 3;

export function preferenceKey(job: JobPosting) {
  try {
    const url = new URL(job.url);
    if (["http:", "https:"].includes(url.protocol)) return `${job.platform}:${url.origin}${url.pathname}`;
  } catch { /* Unlinked entries are scored by local job id. */ }
  return `${job.platform}:local:${job.id}`;
}

function valid(value: unknown): value is number {
  return typeof value === "number" && SCALE.includes(value);
}

function cleanRatings(value: unknown): Ratings {
  if (!value || typeof value !== "object") return {};
  const row = value as Record<string, unknown>;
  const result: Ratings = {};
  for (const [key] of PREFERENCE_FACTORS) if (valid(row[key])) result[key] = row[key];
  return result;
}

export function parseJobPreferences(raw: string | null): Preferences {
  try {
    const cache = raw ? JSON.parse(raw) : null;
    if (!cache || typeof cache !== "object") return { weights: {}, jobs: {} };
    const jobs = cache.jobs && typeof cache.jobs === "object"
      ? Object.fromEntries(Object.entries(cache.jobs).filter(([key]) => /^(boss|shixiseng|demo):/.test(key)).map(([key, value]) => [key, cleanRatings(value)]))
      : {};
    return { weights: cleanRatings(cache.weights), jobs };
  } catch {
    return { weights: {}, jobs: {} };
  }
}

export function summarizeJobPreference(weights: Ratings, ratings: Ratings = {}) {
  let total = 0, ratedWeight = 0, rated = 0, enabled = 0;
  for (const [key] of PREFERENCE_FACTORS) {
    const weight = weights[key] ?? DEFAULT_WEIGHT;
    const rating = ratings[key];
    if (weight <= 0) continue;
    enabled++;
    if (!valid(rating)) continue;
    total += weight * rating;
    ratedWeight += weight;
    rated++;
  }
  return { score: ratedWeight ? Math.round(100 * total / (5 * ratedWeight)) : null, rated, enabled };
}

export function useJobPreferences() {
  const [preferences, setPreferences] = useState(() => {
    try { return parseJobPreferences(localStorage.getItem(JOB_PREFS_KEY)); }
    catch { return parseJobPreferences(null); }
  });
  const [saved, setSaved] = useState(true);
  function change(job: JobPosting, factor: Factor, kind: "weight" | "rating", value: number | undefined) {
    const key = preferenceKey(job);
    const ratings = { ...preferences.jobs[key], [factor]: value };
    const next = kind === "weight" ? { ...preferences, weights: { ...preferences.weights, [factor]: value } }
      : { ...preferences, jobs: { ...preferences.jobs, [key]: ratings } };
    setPreferences(next);
    try { localStorage.setItem(JOB_PREFS_KEY, JSON.stringify(next)); setSaved(true); }
    catch { setSaved(false); }
  }
  return { preferences, change, saved };
}

export function JobPreferenceScore({ job, preferences, change, saved }: {
  job: JobPosting;
} & ReturnType<typeof useJobPreferences>) {
  const ratings = preferences.jobs[preferenceKey(job)] ?? {};
  const { score, rated, enabled } = summarizeJobPreference(preferences.weights, ratings);
  const hints = { salary: job.salary || "未披露薪资", benefits: "有无你在意的补贴或保障？",
    location: job.city || "未披露地区", hours: "参考每周出勤、实习周期和工时",
    work: "根据 JD 判断是否愿意做这些工作", skills: `系统参考 ${job.match.score} 分，你可独立判断` };
  return <details className="job-preference-card">
    <summary><span>我的岗位评分</span><b aria-live="polite">{score === null ? "未评分" : `${score} / 100 · 已评 ${rated}/${enabled} 项`}</b></summary>
    <p>重要度适用于所有岗位（0＝不计入）；岗位评分只属于当前岗位（0＝不满意，5＝非常满意）。没披露或不确定的留空，不扣分。</p>
    <div className="job-preference-grid">
      {PREFERENCE_FACTORS.map(([id, label]) => <fieldset className="job-preference-factor" key={id}>
        <legend>{label}</legend>
        <small>{hints[id]}</small>
        <label>重要度<select aria-label={`${label}重要度`} value={preferences.weights[id] ?? DEFAULT_WEIGHT} onChange={event => change(job, id, "weight", Number(event.target.value))}>
          {SCALE.map(value => <option key={value} value={value}>{value === 0 ? "0 · 不计入" : value}</option>)}
        </select></label>
        <label>本岗位评分<select aria-label={`${label}岗位评分`} value={ratings[id] ?? ""} disabled={preferences.weights[id] === 0}
          onChange={event => change(job, id, "rating", event.target.value === "" ? undefined : Number(event.target.value))}>
          <option value="">未评／不确定</option>{SCALE.map(value => <option key={value} value={value}>{value}</option>)}
        </select></label>
      </fieldset>)}
    </div>
    <small>{saved ? "只保存在当前浏览器；不会传给模型或影响投递。" : "浏览器无法保存，本次修改只在当前页面有效。"} 少量已评项目的高分不能代表整体条件更好。</small>
  </details>;
}
