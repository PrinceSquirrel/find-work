import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { EvidenceCard, JobPosting } from "./types";
import { prepareStudioJob, StudioPreparation } from "./StudioPreparation";

const job = { id: 1, description: "岗位职责：用户调研", detail_status: "detail_fetched" } as JobPosting;
const cards = [{ id: 1, title: "项目事实", category: "project", status: "confirmed" }, { id: 2, title: "教育卡片", category: "education", status: "confirmed" }] as EvidenceCard[];
const props = { job, resume: null, cards, selected: [], manual: false, busy: false, onManual: vi.fn(), onToggle: vi.fn(), onRefresh: vi.fn() };
describe("JD and automatic experience preparation", () => {
  it("shows JD and foundation separately without default checkboxes", () => {
    const html = renderToStaticMarkup(<StudioPreparation {...props} />);
    expect(html).toContain("岗位职责：用户调研");
    expect(html).toContain("基础资料自动沿用");
    expect(html).not.toContain('type="checkbox"');
  });
  it("manual mode lists only confirmed non-education experiences", () => {
    const html = renderToStaticMarkup(<StudioPreparation {...props} manual />);
    expect(html.match(/type="checkbox"/g)).toHaveLength(1);
    expect(html).toContain("项目事实");
    expect(html).not.toContain("教育卡片");
  });
  it("refreshes a missing JD and blocks a failed refresh before generation", async () => {
    const refresh = vi.fn().mockResolvedValue(job);
    expect(await prepareStudioJob({ ...job, detail_status: "card_only" }, refresh)).toBe(job);
    expect(refresh).toHaveBeenCalledOnce();
    await expect(prepareStudioJob({ ...job, detail_status: "card_only" }, vi.fn().mockResolvedValue({ ...job, detail_status: "low_quality" }))).rejects.toThrow("未调用生成模型");
  });
  it("does not refetch complete or manually verified JD", async () => {
    const refresh = vi.fn();
    await prepareStudioJob(job, refresh);
    await prepareStudioJob({ ...job, detail_status: "manual_filled" }, refresh);
    expect(refresh).not.toHaveBeenCalled();
  });
});
