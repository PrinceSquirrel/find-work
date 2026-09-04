export type MaterialFormatGroup = {
  id: string;
  label: string;
  icon: string;
  description: string;
  extensions: string[];
};

export type MaterialWorkbenchTool = {
  id: "upload" | "preview" | "ocr" | "wps";
  eyebrow: string;
  title: string;
  description: string;
  icon: string;
  status: "frontend-ready" | "planned";
};

export const MATERIAL_FORMAT_GROUPS: MaterialFormatGroup[] = [
  {
    id: "wps-writer",
    label: "WPS 文字",
    icon: "W",
    description: "文档、简历与项目说明",
    extensions: ["wps", "doc", "docx", "rtf"],
  },
  {
    id: "wps-sheet",
    label: "WPS 表格",
    icon: "表",
    description: "数据表、清单与评测记录",
    extensions: ["et", "xls", "xlsx", "csv"],
  },
  {
    id: "wps-slides",
    label: "WPS 演示",
    icon: "演",
    description: "作品集、汇报与演示文稿",
    extensions: ["dps", "ppt", "pptx"],
  },
  {
    id: "document-visual",
    label: "PDF 与图片",
    icon: "图",
    description: "支持预览，后续接入 OCR",
    extensions: ["pdf", "png", "jpg", "jpeg", "webp", "bmp", "gif"],
  },
  {
    id: "archive-code",
    label: "压缩包与源码",
    icon: "包",
    description: "项目归档、网页和代码资料",
    extensions: ["zip", "7z", "7p", "html", "htm", "py", "md", "txt"],
  },
  {
    id: "media",
    label: "音视频",
    icon: "播",
    description: "录音、作品视频与会议材料",
    extensions: ["mp3", "mp4", "mkv"],
  },
];

export const MATERIAL_WORKBENCH_TOOLS: MaterialWorkbenchTool[] = [
  {
    id: "upload",
    eyebrow: "01 / COLLECT",
    title: "资料上传",
    description: "统一接收 WPS、图片、压缩包、源码、音频和视频资料。",
    icon: "↑",
    status: "frontend-ready",
  },
  {
    id: "preview",
    eyebrow: "02 / PREVIEW",
    title: "在线预览",
    description: "在工作台中预览文档、图片、PDF、代码和媒体内容。",
    icon: "◉",
    status: "planned",
  },
  {
    id: "ocr",
    eyebrow: "03 / RECOGNIZE",
    title: "OCR 识别",
    description: "把图片或扫描 PDF 转成可搜索、可校对的文本。",
    icon: "文",
    status: "planned",
  },
  {
    id: "wps",
    eyebrow: "04 / EDIT",
    title: "WPS 在线编辑",
    description: "调用 WPS 打开常见办公格式，并回写编辑后的版本。",
    icon: "✎",
    status: "planned",
  },
];

export const MATERIAL_UPLOAD_ACCEPT = MATERIAL_FORMAT_GROUPS
  .flatMap((group) => group.extensions)
  .map((extension) => `.${extension}`)
  .join(",");

export function getMaterialFormatGroup(filename: string): MaterialFormatGroup | null {
  const extension = filename.split(".").pop()?.toLocaleLowerCase("zh-CN") ?? "";
  return MATERIAL_FORMAT_GROUPS.find((group) => group.extensions.includes(extension)) ?? null;
}

export function formatMaterialSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
