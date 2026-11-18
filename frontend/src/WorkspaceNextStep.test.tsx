import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { getWorkspaceNextStep, WorkspaceNextStep, type WorkspaceProgress } from "./WorkspaceNextStep";

const ready: WorkspaceProgress = { loading: false, loadFailed: false, hasResume: true, resumeReadable: true, sources: 1, needsText: 0, draftFacts: 0, confirmedFacts: 1, hasJobs: false, tabsDetected: false, hasMaterial: false, finalized: false };

describe("workspace task guidance", () => {
  it("keeps recovery separate from missing or unsaved data", () => {
    expect(getWorkspaceNextStep({ ...ready, loading: true }).title).toContain("恢复本地进度");
    expect(getWorkspaceNextStep({ ...ready, loadFailed: true }).action).toBe("retry");
    expect(getWorkspaceNextStep({ ...ready, loadFailed: true }).detail).toContain("不需要重新上传");
    expect(getWorkspaceNextStep({ ...ready, hasResume: false }).detail).toContain("1 份资料保存成功");
    expect(getWorkspaceNextStep({ ...ready, resumeReadable: false }).label).toBe("补全简历正文");
  });
  it("requires review and offers explicit local extraction without bypassing facts", () => {
    expect(getWorkspaceNextStep({ ...ready, confirmedFacts: 0, draftFacts: 2 }).label).toBe("核对事实草稿");
    expect(getWorkspaceNextStep({ ...ready, confirmedFacts: 0, needsText: 1 }).title).toContain("补全正文");
    expect(getWorkspaceNextStep({ ...ready, confirmedFacts: 0 }).detail).toContain("显式选择本地提取");
  });
  it("does not mistake a platform tab for authenticated access", () => {
    expect(getWorkspaceNextStep(ready).action).toBe("connections");
    expect(getWorkspaceNextStep({ ...ready, tabsDetected: true }).detail).toContain("不等于已登录");
    expect(getWorkspaceNextStep({ ...ready, hasJobs: true }).action).toBe("jobs");
  });
  it("supports offline review and does not confuse export with applying", () => {
    expect(getWorkspaceNextStep({ ...ready, hasMaterial: true }).action).toBe("studio");
    expect(getWorkspaceNextStep({ ...ready, hasMaterial: true, finalized: true }).detail).toContain("导出不等于已投递");
  });
  it("renders status and navigation only without invoking actions", () => {
    let calls = 0;
    const html = renderToStaticMarkup(<WorkspaceNextStep progress={{ ...ready, loading: true }} onAction={() => calls++} />);
    expect(html).toContain('aria-label="下一步引导"');
    expect(html).toContain("已配置 Key 不代表连接有效");
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(calls).toBe(0);
  });
});
