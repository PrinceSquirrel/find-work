import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { EvidenceUploadForm } from "./EvidenceUploadForm";

describe("evidence picker and explicit upload", () => {
  it("offers a labeled multi-file chooser and a choose-first action without uploading on render", () => {
    const upload = vi.fn();
    const html = renderToStaticMarkup(<EvidenceUploadForm files={[]} busy={false} onFilesChange={vi.fn()} onUpload={upload} />);
    expect(html).toContain('aria-label="选择个人资料文件"');
    expect(html).toContain('type="file"');
    expect(html).toContain('multiple=""');
    expect(html).toContain("加入本地资料库");
    expect(html).not.toContain('disabled=""');
    expect(upload).not.toHaveBeenCalled();
  });
  it("shows filenames and an explicit upload action after choosing", () => {
    const html = renderToStaticMarkup(<EvidenceUploadForm files={[{ name: "个人资料.txt" } as File]} busy={false} onFilesChange={vi.fn()} onUpload={vi.fn()} />);
    expect(html).toContain("已选择 1 份：个人资料.txt");
    expect(html).toContain("上传所选资料");
    expect(html).not.toContain("加入本地资料库");
    expect(html).toContain(".docx,.pdf,.txt,.md,.png,.jpg,.jpeg");
  });
  it("disables chooser and upload while a request is running", () => {
    const html = renderToStaticMarkup(<EvidenceUploadForm files={[]} busy onFilesChange={vi.fn()} onUpload={vi.fn()} />);
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(html).toContain("上传中...");
  });
});
