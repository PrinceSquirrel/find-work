export const EVIDENCE_PARSE_EXTENSIONS = new Set(["docx", "pdf", "txt", "md", "png", "jpg", "jpeg"]);

export async function uploadEvidenceBatch<T extends { name: string }>(
  files: T[],
  upload: (file: T) => Promise<unknown>,
) {
  const uploaded: T[] = [];
  const remaining: T[] = [];
  const messages: string[] = [];
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!EVIDENCE_PARSE_EXTENSIONS.has(extension)) {
      remaining.push(file);
      messages.push(file.name + "：该格式的解析服务尚未接入，未上传。");
      continue;
    }
    try {
      await upload(file);
      uploaded.push(file);
      messages.push(file.name + "：已保存，请检查正文及解析状态。");
    } catch (error) {
      remaining.push(file);
      messages.push(file.name + "：" + (error instanceof Error ? error.message : "上传失败，请重试"));
    }
  }
  return { uploaded, remaining, messages };
}
