import { describe, expect, it } from "vitest";

import {
  formatMaterialSize,
  getMaterialFormatGroup,
  getMaterialCapability,
  MATERIAL_FORMAT_GROUPS,
  MATERIAL_UPLOAD_ACCEPT,
  MATERIAL_WORKBENCH_TOOLS,
} from "./materials";

describe("material workbench", () => {
  it("lists every format requested for the frontend upload surface", () => {
    const extensions = new Set(MATERIAL_FORMAT_GROUPS.flatMap((group) => group.extensions));

    expect([...extensions]).toEqual(expect.arrayContaining([
      "wps", "doc", "docx", "et", "xls", "xlsx", "dps", "ppt", "pptx",
      "pdf", "png", "jpg", "zip", "7z", "7p", "html", "py", "mp3", "mp4", "mkv", "md", "txt",
    ]));
    expect(MATERIAL_UPLOAD_ACCEPT).toContain(".mkv");
    expect(MATERIAL_UPLOAD_ACCEPT).toContain(".7p");
  });

  it("keeps preview, OCR and WPS editing visibly planned rather than falsely enabled", () => {
    expect(MATERIAL_WORKBENCH_TOOLS.map((tool) => tool.id)).toEqual(["upload", "preview", "ocr", "wps"]);
    expect(MATERIAL_WORKBENCH_TOOLS.find((tool) => tool.id === "upload")?.status).toBe("frontend-ready");
    expect(MATERIAL_WORKBENCH_TOOLS.filter((tool) => tool.id !== "upload").every((tool) => tool.status === "planned")).toBe(true);
  });

  it("maps selected files to their visual category", () => {
    expect(getMaterialFormatGroup("方案.WPS")?.id).toBe("wps-writer");
    expect(getMaterialFormatGroup("作品集.mkv")?.id).toBe("media");
    expect(getMaterialFormatGroup("项目.7p")?.id).toBe("archive-code");
    expect(getMaterialFormatGroup("unknown.bin")).toBeNull();
    expect(formatMaterialSize(1_572_864)).toBe("1.5 MB");
  });

  it("distinguishes supported uploads, manual text and future-only formats", () => {
    for (const extension of ["docx", "txt", "md"]) {
      expect(getMaterialCapability(`资料.${extension}`)).toBe("可上传检查");
    }
    expect(getMaterialCapability("扫描.PDF")).toContain("扫描件需补字");
    for (const extension of ["png", "jpg", "jpeg"]) {
      expect(getMaterialCapability(`图片.${extension}`)).toContain("需手工补字");
    }
    for (const extension of ["wps", "doc", "xlsx", "pptx", "zip", "7p", "html", "py", "mp3", "mp4", "mkv", "webp", "bin"]) {
      expect(getMaterialCapability(`资料.${extension}`)).toBe("规划格式 · 暂不上传");
    }
    expect(MATERIAL_WORKBENCH_TOOLS[0].description).toContain("其他格式暂不上传");
    expect(MATERIAL_WORKBENCH_TOOLS.slice(1).every(tool => tool.description.includes("规划能力"))).toBe(true);
  });
});
