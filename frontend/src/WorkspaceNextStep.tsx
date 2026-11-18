export type NextStepAction = "materials" | "jobs" | "studio" | "connections" | "retry";

export type WorkspaceProgress = {
  loading: boolean; loadFailed: boolean; hasResume: boolean; resumeReadable: boolean;
  sources: number; needsText: number; draftFacts: number; confirmedFacts: number;
  hasJobs: boolean; tabsDetected: boolean; hasMaterial: boolean; finalized: boolean;
};

export function getWorkspaceNextStep(p: WorkspaceProgress): { title: string; detail: string; label: string; action: NextStepAction } {
  if (p.loading) return { title: "正在恢复本地进度", detail: "请等待资料与记录读取完成，暂不重复上传。", label: "读取中…", action: "retry" };
  if (p.loadFailed) return { title: "本地进度读取失败", detail: "不代表资料丢失。请重试读取，不需要重新上传。", label: "重试读取进度", action: "retry" };
  if (!p.hasResume) return { title: "先准备基础简历", detail: p.sources ? `已有 ${p.sources} 份资料保存成功；请在资料检查中添加基础简历，用于搜索条件和个人信息。` : "在资料检查中上传基础简历，再添加真实项目／经历资料。", label: "检查基础简历与资料", action: "materials" };
  if (!p.resumeReadable) return { title: "基础简历已保存，正文待补齐", detail: "图片或扫描件尚不能自动识别，请粘贴正文，不必重复上传。", label: "补全简历正文", action: "materials" };
  if (!p.confirmedFacts) {
    if (p.draftFacts) return { title: "核对待确认事实", detail: `已有 ${p.draftFacts} 张草稿；核对原文后逐条确认，未确认内容不会用于可信生成。`, label: "核对事实草稿", action: "materials" };
    if (p.needsText) return { title: "资料已保存，先补全正文", detail: `${p.needsText} 份资料需手工补字；保存正文后可显式选择本地提取。`, label: "补字与提取事实", action: "materials" };
    return { title: p.sources ? "资料已保存，下一步提取事实" : "添加可核对的真实经历", detail: "可显式选择本地提取（不调用模型），或手动添加真实经历；模型提取失败也会保留原资料。", label: "提取与确认事实", action: "materials" };
  }
  if (p.hasMaterial) return { title: p.finalized ? "材料已定稿，可以导出" : "材料已生成，下一步人工核验", detail: p.finalized ? "修改正文后需要重新核验；导出不等于已投递。" : "核对引用、接受或修改内容后定稿，不会自动发送给招聘方。", label: "查看求职材料", action: "studio" };
  if (p.hasJobs) return { title: "选择目标岗位，准备定制材料", detail: `已有 ${p.confirmedFacts} 张已确认事实；先核对完整 JD，再在生成中心生成。`, label: "选择目标岗位", action: "jobs" };
  if (!p.tabsDetected) return { title: "事实已就绪，检查平台连接", detail: "在岗位雷达启动专用浏览器、本人登录后刷新会话；遇验证码请在原平台手工处理，不绕过验证。", label: "检查平台连接", action: "connections" };
  return { title: "开始搜索目标岗位", detail: "已发现所选平台标签页，但不等于已登录。请本人确认登录，填写关键词与城市后再搜索。", label: "去岗位雷达搜索", action: "jobs" };
}

export function WorkspaceNextStep({ progress, onAction }: { progress: WorkspaceProgress; onAction: (action: NextStepAction | "settings") => void }) {
  const step = getWorkspaceNextStep(progress);
  return <section aria-label="下一步引导" className="source-banner">
    <b>下一步 · {step.title}</b><span>{step.detail}</span>
    <small>基础简历{progress.hasResume ? "已保存" : "待添加"} · 资料 {progress.sources} 份 · 已确认事实 {progress.confirmedFacts} 张</small>
    <small>本地提取不调用模型；已配置 Key 不代表连接有效，外部模型需在设置中由你主动测试。</small>
    <div className="evidence-actions">
      <button type="button" disabled={progress.loading} onClick={() => onAction(step.action)}>{step.label}</button>
      <button type="button" disabled={progress.loading} onClick={() => onAction("settings")}>查看模型设置</button>
    </div>
  </section>;
}
