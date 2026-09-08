import { describe, expect, it, vi } from "vitest";
import { uploadEvidenceBatch } from "./evidenceUpload";

describe("evidence upload queue", () => {
  it("only sends supported formats and keeps unconnected formats visible", async () => {
    const upload = vi.fn().mockResolvedValue({});
    const result = await uploadEvidenceBatch([{ name: "项目.MD" }, { name: "video.mp4" }], upload);
    expect(upload).toHaveBeenCalledTimes(1);
    expect(result.uploaded).toEqual([{ name: "项目.MD" }]);
    expect(result.remaining).toEqual([{ name: "video.mp4" }]);
    expect(result.messages[1]).toContain("未上传");
  });
  it("continues after a failure without requeueing successful files", async () => {
    const upload = vi.fn().mockRejectedValueOnce(new Error("网络失败")).mockResolvedValueOnce({});
    const result = await uploadEvidenceBatch([{ name: "a.pdf" }, { name: "b.txt" }], upload);
    expect(result.remaining).toEqual([{ name: "a.pdf" }]);
    expect(result.uploaded).toEqual([{ name: "b.txt" }]);
    expect(result.messages[0]).toContain("网络失败");
  });
  it("does not claim parsing succeeded merely because an upload succeeded", async () => {
    const result = await uploadEvidenceBatch([{ name: "scan.png" }], async () => ({ manual_text_required: true }));
    expect(result.messages[0]).toContain("检查正文及解析状态");
    expect(result.messages[0]).not.toContain("解析成功");
  });
});
