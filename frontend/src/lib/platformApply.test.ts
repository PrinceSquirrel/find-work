import { describe, expect, it, vi } from "vitest";
import type { JobPosting, PlatformApplyPreview } from "../types";
import { platformApplyHint, runPlatformApplication } from "./platformApply";
const job = { id: 1, company: "合成公司", title: "产品岗位" } as JobPosting;
const preview = { ready: true, button_text: "立即沟通" } as PlatformApplyPreview;
describe("automatic platform preflight with one explicit sending approval", () => {
  it("does not apply when preflight fails or user cancels", async () => {
    const apply = vi.fn(); const confirm = vi.fn().mockReturnValue(false);
    await runPlatformApplication(job, { preview: vi.fn().mockResolvedValue({ ...preview, ready: false, status: "button_not_found" }), confirm, apply });
    expect(confirm).not.toHaveBeenCalled();
    await runPlatformApplication(job, { preview: vi.fn().mockResolvedValue(preview), confirm, apply });
    expect(confirm).toHaveBeenCalledOnce(); expect(apply).not.toHaveBeenCalled();
  });
  it("runs preflight before approval and applies once", async () => {
    const order: string[] = [];
    const result = await runPlatformApplication(job, { preview: async () => { order.push("preview"); return preview; }, confirm: message => { expect(message).toContain("可能向招聘方发送"); order.push("confirm"); return true; }, apply: async () => { order.push("apply"); } });
    expect(order).toEqual(["preview", "confirm", "apply"]); expect(result.submitted).toBe(true);
  });
  it("does not mistake an open chat for a sent application", async () => {
    const apply = vi.fn();
    const result = await runPlatformApplication(job, { preview: vi.fn().mockResolvedValue({ ...preview, button_text: "chat/input" }), confirm: vi.fn(), apply });
    expect(result.submitted).toBe(false); expect(apply).not.toHaveBeenCalled();
    const pending = await runPlatformApplication(job, { preview: vi.fn().mockResolvedValue(preview), confirm: () => true, apply: async () => { throw new Error("已打开聊天窗口，但尚未确认发送"); } });
    expect(pending.message).toContain("未计入投递"); expect(pending.submitted).toBe(false);
  });
  it("preserves actionable authentication and genuine failures", async () => {
    expect(platformApplyHint("platform requires login or verification")).toContain("完成登录");
    await expect(runPlatformApplication(job, { preview: vi.fn().mockResolvedValue(preview), confirm: () => true, apply: async () => { throw new Error("服务不可用"); } })).rejects.toThrow("服务不可用");
  });
});
