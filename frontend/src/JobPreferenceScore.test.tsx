import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { JobPreferenceScore, parseJobPreferences, preferenceKey, PREFERENCE_FACTORS, summarizeJobPreference } from "./JobPreferenceScore";
import type { JobPosting } from "./types";

const job = { id: 12, platform: "boss", url: "https://www.zhipin.com/job_detail/fixture.html?source=test",
  city: "上海", salary: "200元/天", match: { score: 45 } } as JobPosting;

describe("personal job score", () => {
  it("keeps unrated separate from an explicit zero and applies weights", () => {
    expect(summarizeJobPreference({}, {})).toEqual({ score: null, rated: 0, enabled: 6 });
    expect(summarizeJobPreference({ salary: 5, hours: 1 }, { salary: 5, hours: 0 })).toEqual({ score: 83, rated: 2, enabled: 6 });
    expect(summarizeJobPreference({ salary: 0 }, { salary: 5, skills: 0 })).toEqual({ score: 0, rated: 1, enabled: 5 });
    const muted = Object.fromEntries(PREFERENCE_FACTORS.map(([key]) => [key, 0]));
    expect(summarizeJobPreference(muted, { salary: 5 })).toEqual({ score: null, rated: 0, enabled: 0 });
  });

  it("uses one platform job key across search runs and keeps other jobs separate", () => {
    expect(preferenceKey({ ...job, id: 91, url: job.url.replace("test", "new") })).toBe(preferenceKey(job));
    expect(preferenceKey({ ...job, url: job.url.replace("fixture", "other") })).not.toBe(preferenceKey(job));
    expect(preferenceKey({ ...job, url: "javascript:unauthorized" })).toBe("boss:local:12");
  });

  it("loads valid browser values while discarding invalid ones and bad cache entries", () => {
    const key = preferenceKey(job);
    const prefs = parseJobPreferences(JSON.stringify({ weights: { salary: 0, hours: 6, work: "5" }, jobs: { [key]: { salary: 5, location: -1 } } }));
    expect(prefs).toEqual({ weights: { salary: 0 }, jobs: { [key]: { salary: 5 } } });
    expect(parseJobPreferences("invalid JSON")).toEqual({ weights: {}, jobs: {} });
  });

  it("renders six separate controls and retains the model reference label", () => {
    const html = renderToStaticMarkup(<JobPreferenceScore job={job} saved change={vi.fn()} preferences={{ weights: {}, jobs: {} }} />);
    for (const [, label] of PREFERENCE_FACTORS) {
      expect(html).toContain(`aria-label="${label}重要度"`);
      expect(html).toContain(`aria-label="${label}岗位评分"`);
    }
    expect(html).toContain("系统参考 45 分");
    expect(html).toContain("未评／不确定");
  });
});
