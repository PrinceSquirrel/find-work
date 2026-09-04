import { describe, expect, it } from "vitest";

import {
  formatMaterialSize,
  getMaterialFormatGroup,
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
});
