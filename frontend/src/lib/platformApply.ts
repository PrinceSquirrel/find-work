import type { JobPosting, PlatformApplyPreview } from "../types";

export function platformApplyHint(message: string): string {
  if (/已打开|尚未确认|clicked.*did not show|chat_opened_unconfirmed/i.test(message)) return "沟通入口已打开，尚未确认发送，未计入投递。请在招聘平台完成发送后同步投递状态；系统不会自动重发。";
  if (/login|captcha|verification|验证|登录/i.test(message)) return "请在招聘平台完成登录或安全验证，再重试；没有保存投递记录。";
  if (/button_not_found|no platform.*button/i.test(message)) return "未找到当前岗位的沟通／投递按钮，请在原岗位页面核对状态后重试。";
  return message;
}

export async function runPlatformApplication(job: JobPosting, actions: {
  preview: (id: number) => Promise<PlatformApplyPreview>;
  confirm: (message: string) => boolean;
  apply: (id: number) => Promise<unknown>;
}) {
  const preview = await actions.preview(job.id);
  if (!preview.ready) return { preview, submitted: false, message: platformApplyHint(preview.evidence || preview.status) };
  if (preview.button_text === "chat/input") return { preview, submitted: false, message: platformApplyHint("已打开聊天窗口，尚未确认发送") };
  if (!actions.confirm(`确认操作：${job.company} · ${job.title}\n将点击平台的“${preview.button_text || "沟通／投递"}”按钮，可能向招聘方发送招呼或简历。仅平台确认成功后保存记录。是否继续？`)) {
    return { preview, submitted: false, message: "已取消，未执行平台发送操作。" };
  }
  try {
    await actions.apply(job.id);
    return { preview, submitted: true, message: "平台已确认沟通／投递，记录已保存。" };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/已打开|尚未确认|clicked.*did not show|chat_opened_unconfirmed/i.test(message)) return { preview, submitted: false, message: platformApplyHint(message) };
    throw new Error(platformApplyHint(message));
  }
}
