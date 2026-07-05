import type {
  AnalyticsBucket,
  AgentModelRoute,
  ApplicationStatus,
  ApplicationPlatformProof,
  JobFilters,
  JobPosting,
  LLMUsageAgentBucket,
  LLMUsageSummary,
  ModelProfile,
  ResumeDraft,
  SystemHealthCheck,
  SystemHealthResponse,
  TailorBundle,
  UsageCards
} from "../types";

export type StatusTone = "muted" | "info" | "accent" | "success" | "warning" | "danger";
export type AgentRuntimeStatus = "pending" | "running" | "success" | "failed";
export type RuntimeAgentName =
  | "ResumeParserAgent"
  | "JobSearchAgent"
  | "JobMatchAgent"
  | "ApplicationWriterAgent"
  | "ReviewAgent";

export interface AgentRuntimeSnapshot {
  runningAgent: RuntimeAgentName | null;
  failedAgent: RuntimeAgentName | null;
  errorMessage: string | null;
  resumeName: string | null;
  searchSummary: string;
  selectedJobTitle: string | null;
  jobCount: number;
  tailoredCount: number;
  usageByAgent: Record<string, LLMUsageAgentBucket>;
}

export interface AgentStatusRow {
  agentName: RuntimeAgentName;
  status: AgentRuntimeStatus;
  currentStep: string;
  inputSummary: string;
  outputSummary: string;
  errorMessage: string;
  tokens: number;
}

export interface BackendAgentEvent {
  id: number;
  agent_name: string;
  status: string;
  step: string;
  input_summary: string;
  output_summary: string;
  error: string;
  total_tokens: number;
  cost_usd: number;
  created_at: string | null;
}

export interface BackendOrchestratorStep {
  event_id: number;
  agent_name: string;
  status: string;
  step: string;
  input_summary: string;
  output_summary: string;
  error: string;
  total_tokens: number;
  cost_usd: number;
}

export interface BackendRetrySuggestion {
  mode: string;
  retryable: boolean;
  automatic_retry_allowed: boolean;
  reason: string;
  next_action: string;
  safety_boundary: string;
}

export interface BackendOrchestratorTask {
  id: number;
  task_name: string;
  input_summary: string;
  status: string;
  error: string;
  started_at: string;
  completed_at: string | null;
  steps: BackendOrchestratorStep[];
  retry_suggestion?: BackendRetrySuggestion;
}

export interface BackendOrchestratorSnapshot {
  current_task_id: number | null;
  last_task: BackendOrchestratorTask | null;
  tasks: BackendOrchestratorTask[];
}

export interface BackendAgentEventsSnapshot {
  current_running_agent: string | null;
  total_cost_usd: number;
  agents: BackendAgentEvent[];
  events: BackendAgentEvent[];
  orchestrator?: BackendOrchestratorSnapshot;
}

export interface OrchestratorSummary {
  taskName: string;
  status: string;
  stepCount: number;
  currentTaskId: number | null;
  lastStep: string;
  errorMessage: string;
  detail: string;
}

export interface TailorModelSummary {
  statusLabel: string;
  tone: StatusTone;
  providerModel: string;
  routeLabel: string;
  usageLabel: string;
  detail: string;
  errorLabel: string;
  setupHint: string;
}

export interface JobMatchModelSummary {
  statusLabel: string;
  tone: StatusTone;
  modelLabel: string;
  usageLabel: string;
  detail: string;
}

export interface JobDetailQuality {
  isComplete: boolean;
  reason: string;
  actionHint: string;
  displayDescription: string;
}

export interface PlatformConfirmationSummary {
  confirmed: boolean;
  evidence: string;
  sourceUrl: string;
  note: string;
  buttonText: string;
  status: string;
  confirmedAt: string;
  pageSummary: string;
}

export interface PdfTemplateStatus {
  label: string;
  tone: StatusTone;
  detail: string;
  actionHint: string;
  canDownload: boolean;
}

export interface ResumeReadingStatus {
  label: string;
  tone: StatusTone;
  detail: string;
  actionHint: string;
  needsManualText: boolean;
  canGenerateMaterials: boolean;
}

export interface ModelRouteApplyOption {
  agentName: string;
  label: string;
  currentModel: string;
  targetModel: string;
  keyStatus: string;
  canApply: boolean;
}

export interface SystemHealthCardView {
  id: string;
  label: string;
  statusLabel: string;
  tone: StatusTone;
  summary: string;
  detail: string;
  nextAction: string;
}

export interface SystemHealthSummaryView {
  overallLabel: string;
  tone: StatusTone;
  generatedLabel: string;
  nextActionLabel: string;
  primaryCheck: SystemHealthCardView | null;
  recentError: string;
  cards: SystemHealthCardView[];
}

export type SystemHealthOperationStatus = "running" | "success" | "failed";

export interface SystemHealthOperationFeedback {
  actionLabel: string;
  status: SystemHealthOperationStatus;
  detail: string;
}

export interface SystemHealthOperationView {
  label: string;
  tone: StatusTone;
  detail: string;
}

const STATUS_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  discovered: [],
  matched: [],
  generated: [],
  applied: ["read", "rejected", "closed"],
  read: ["replied", "rejected", "closed"],
  replied: ["interview", "assessment", "rejected", "closed"],
  interview: ["assessment", "rejected", "closed"],
  assessment: ["interview", "rejected", "closed"],
  rejected: ["closed"],
  closed: []
};

const STATUS_TONES: Record<ApplicationStatus, StatusTone> = {
  discovered: "muted",
  matched: "info",
  generated: "accent",
  applied: "info",
  read: "accent",
  replied: "success",
  interview: "success",
  assessment: "success",
  rejected: "danger",
  closed: "muted"
};

const AGENT_ORDER: RuntimeAgentName[] = [
  "ResumeParserAgent",
  "JobSearchAgent",
  "JobMatchAgent",
  "ApplicationWriterAgent",
  "ReviewAgent"
];

export function filterJobsForActiveSearchRun(jobs: JobPosting[], activeSearchRunId: number | null): JobPosting[] {
  if (activeSearchRunId === null) {
    return [];
  }
  return jobs.filter((job) => job.search_run_id === activeSearchRunId);
}

export function filterModelProfiles(profiles: ModelProfile[], query: string): ModelProfile[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return profiles;
  }
  return profiles.filter((profile) => {
    const searchable = [
      profile.name,
      profile.provider,
      profile.model,
      profile.base_url,
      profile.api_key_env_var
    ]
      .join(" ")
      .toLowerCase();
    return searchable.includes(normalizedQuery);
  });
}

export function buildModelRouteApplyOptions(
  routes: AgentModelRoute[],
  selectedProfile: Pick<ModelProfile, "model" | "api_key_configured" | "api_key_env_var"> | null,
  labels: Record<string, string>
): ModelRouteApplyOption[] {
  return routes.map((route) => ({
    agentName: route.agent_name,
    label: labels[route.agent_name] ?? route.agent_name,
    currentModel: route.model || "未配置",
    targetModel: selectedProfile?.model ?? "未选择模型档案",
    keyStatus: selectedProfile
      ? selectedProfile.api_key_configured
        ? "Key 已配置"
        : `等待 ${selectedProfile.api_key_env_var || "API Key"}`
      : "请选择模型档案",
    canApply: Boolean(selectedProfile)
  }));
}

export function summarizeSystemHealth(
  health: SystemHealthResponse | null,
  recentError: string | null = null
): SystemHealthSummaryView {
  if (!health) {
    return {
      overallLabel: "未读取",
      tone: "muted",
      generatedLabel: "-",
      nextActionLabel: "刷新状态读取后端诊断",
      primaryCheck: null,
      recentError: recentError?.trim() ?? "",
      cards: []
    };
  }

  const cards = health.checks.map(toSystemHealthCard);
  const primaryCheck = cards.find((card) => card.tone === "danger") ?? cards.find((card) => card.tone === "warning") ?? null;

  return {
    overallLabel: getSystemHealthOverallLabel(health.status),
    tone: getSystemHealthTone(health.status),
    generatedLabel: formatDateTime(health.generated_at),
    nextActionLabel: primaryCheck?.nextAction || "可以继续搜索岗位或生成材料",
    primaryCheck,
    recentError: recentError?.trim() ?? "",
    cards
  };
}

export function summarizeSystemHealthOperation(
  feedback: SystemHealthOperationFeedback | null
): SystemHealthOperationView | null {
  if (!feedback) {
    return null;
  }
  const statusMeta: Record<SystemHealthOperationStatus, { suffix: string; tone: StatusTone }> = {
    running: { suffix: "进行中", tone: "info" },
    success: { suffix: "完成", tone: "success" },
    failed: { suffix: "失败", tone: "danger" }
  };
  const meta = statusMeta[feedback.status];
  return {
    label: `${feedback.actionLabel}${meta.suffix}`,
    tone: meta.tone,
    detail: feedback.detail
  };
}

function toSystemHealthCard(check: SystemHealthCheck): SystemHealthCardView {
  return {
    id: check.id,
    label: check.label,
    statusLabel: getSystemHealthStatusLabel(check.status),
    tone: getSystemHealthTone(check.status),
    summary: check.summary,
    detail: check.detail,
    nextAction: check.next_action
  };
}

function getSystemHealthTone(status: string): StatusTone {
  if (status === "green") {
    return "success";
  }
  if (status === "yellow") {
    return "warning";
  }
  if (status === "red") {
    return "danger";
  }
  return "muted";
}

function getSystemHealthStatusLabel(status: string): string {
  if (status === "green") {
    return "正常";
  }
  if (status === "yellow") {
    return "需处理";
  }
  if (status === "red") {
    return "异常";
  }
  return "未知";
}

function getSystemHealthOverallLabel(status: string): string {
  if (status === "green") {
    return "可用";
  }
  if (status === "yellow") {
    return "需要处理";
  }
  if (status === "red") {
    return "不可用";
  }
  return "未知";
}

export function rankJobs(jobs: JobPosting[], filters: JobFilters): JobPosting[] {
  const keyword = filters.keyword.trim().toLowerCase();
  return jobs
    .filter((job) => {
      const matchesPlatform = filters.platform === "all" || job.platform === filters.platform;
      const matchesScore = job.match.score >= filters.minScore;
      const searchable = [
        job.company,
        job.title,
        job.city,
        job.salary,
        job.description,
        job.job_type,
        job.platform,
        ...job.match.hit_reasons,
        ...job.match.gap_reasons
      ]
        .join(" ")
        .toLowerCase();
      const matchesKeyword = keyword.length === 0 || searchable.includes(keyword);
      return matchesPlatform && matchesScore && matchesKeyword;
    })
    .sort((left, right) => right.match.score - left.match.score || right.id - left.id);
}

export function getRatePercent(
  bucket: AnalyticsBucket | undefined,
  key: "read_rate" | "reply_rate" | "progress_rate"
): number {
  if (!bucket) {
    return 0;
  }
  return Math.round(bucket[key] * 1000) / 10;
}

export function getAllowedNextStatuses(status: ApplicationStatus): ApplicationStatus[] {
  return STATUS_TRANSITIONS[status] ?? [];
}

export function getStatusTone(status: ApplicationStatus): StatusTone {
  return STATUS_TONES[status] ?? "muted";
}

export function summarizeUsage(usage: LLMUsageSummary | null): UsageCards {
  if (!usage) {
    return {
      totalTokens: "0",
      totalCost: "$0.0000",
      topAgent: "暂无调用"
    };
  }

  const topAgent =
    Object.entries(usage.by_agent).sort(
      ([, left], [, right]) => (right.total_tokens ?? 0) - (left.total_tokens ?? 0)
    )[0]?.[0] ?? "暂无调用";

  return {
    totalTokens: usage.total_tokens.toLocaleString("en-US"),
    totalCost: `$${usage.total_cost_usd.toFixed(4)}`,
    topAgent
  };
}

export function buildAgentStatusRows(snapshot: AgentRuntimeSnapshot): AgentStatusRow[] {
  return AGENT_ORDER.map((agentName) => {
    const status = getRuntimeStatus(agentName, snapshot);
    return {
      agentName,
      status,
      currentStep: getCurrentStep(agentName, status),
      inputSummary: getInputSummary(agentName, snapshot),
      outputSummary: getOutputSummary(agentName, snapshot),
      errorMessage: snapshot.failedAgent === agentName ? snapshot.errorMessage ?? "" : "",
      tokens: snapshot.usageByAgent[agentName]?.total_tokens ?? 0
    };
  });
}

export function buildAgentStatusRowsFromEvents(snapshot: BackendAgentEventsSnapshot | null): AgentStatusRow[] {
  const latestByAgent = new Map((snapshot?.agents ?? []).map((event) => [event.agent_name, event]));
  return AGENT_ORDER.map((agentName) => {
    const event = latestByAgent.get(agentName);
    const status = event ? normalizeAgentStatus(event.status) : "pending";
    const effectiveStatus = snapshot?.current_running_agent === agentName && status !== "failed" ? "running" : status;
    return {
      agentName,
      status: effectiveStatus,
      currentStep: event?.step || getCurrentStep(agentName, effectiveStatus),
      inputSummary: event?.input_summary || "",
      outputSummary: event?.output_summary || "",
      errorMessage: event ? getEventErrorMessage(event, effectiveStatus) : "",
      tokens: event?.total_tokens ?? 0
    };
  });
}

export function buildOrchestratorSummary(snapshot: BackendAgentEventsSnapshot | null): OrchestratorSummary | null {
  const task = snapshot?.orchestrator?.last_task;
  if (!task) {
    return null;
  }
  const lastStep = task.steps[task.steps.length - 1];
  const errorStep = [...task.steps].reverse().find((step) => step.error);
  const stepCount = task.steps.length;
  return {
    taskName: task.task_name,
    status: task.status,
    stepCount,
    currentTaskId: snapshot?.orchestrator?.current_task_id ?? null,
    lastStep: lastStep ? `${lastStep.agent_name} / ${lastStep.step}` : "暂无步骤",
    errorMessage: task.error || errorStep?.error || "",
    detail: `${task.task_name} / ${task.status} / ${stepCount} steps`
  };
}

export function getJobDetailQuality(job: Pick<JobPosting, "description" | "detail_status" | "detail_reason">): JobDetailQuality {
  const description = job.description.trim();
  const actionHint = "请先打开原岗位核对详情；如果平台页面已经加载完整，回到工作台刷新会话后重新提取。";
  if (job.detail_status && job.detail_status !== "detail_fetched") {
    return {
      isComplete: false,
      reason: job.detail_reason || "后端标记该岗位详情未补全。",
      actionHint,
      displayDescription: description || "当前页面没有提取到完整岗位要求。"
    };
  }
  if (job.detail_status === "detail_fetched") {
    return {
      isComplete: true,
      reason: job.detail_reason || "已提取到较完整岗位要求。",
      actionHint: "",
      displayDescription: description
    };
  }
  if (!description) {
    return {
      isComplete: false,
      reason: "当前页面没有提取到岗位要求，可能是详情页被风控、未登录或页面还没加载完成。",
      actionHint,
      displayDescription: "当前页面没有提取到完整岗位要求。"
    };
  }

  const detailMarkers = /职位描述|岗位职责|任职要求|岗位要求|工作内容|Responsibilities|Requirements|Job Description/i;
  if (description.length < 80 && !detailMarkers.test(description)) {
    return {
      isComplete: false,
      reason: "当前 JD 过短，可能只读取到列表卡片，详情页没有补全。",
      actionHint,
      displayDescription: description
    };
  }

  return {
    isComplete: true,
    reason: "已提取到较完整岗位要求。",
    actionHint: "",
    displayDescription: description
  };
}

export function shouldShowTailorRetryAction({
  job,
  hasBundle,
  blockedMessage
}: {
  job: Pick<JobPosting, "detail_status"> | null;
  hasBundle: boolean;
  blockedMessage: string;
}): boolean {
  if (!job || hasBundle || blockedMessage) {
    return false;
  }
  return job.detail_status === "manual_filled" || job.detail_status === "detail_fetched";
}

export function getPdfTemplateStatus(
  resume: Pick<ResumeDraft, "file_type" | "template_available"> | null | undefined,
  hasBundle: boolean,
  overrideMessage: string | null | undefined
): PdfTemplateStatus {
  if (overrideMessage) {
    return {
      label: overrideMessage,
      tone: pdfToneFromMessage(overrideMessage),
      detail: overrideMessage,
      actionHint: "",
      canDownload: Boolean(resume?.template_available && hasBundle)
    };
  }
  if (!hasBundle) {
    return {
      label: "模板化 PDF：尚未生成材料",
      tone: "muted",
      detail: "请先在岗位列表生成简历改写和招呼语。",
      actionHint: "生成材料后这里会显示 PDF 下载状态。",
      canDownload: false
    };
  }
  if (!resume) {
    return {
      label: "模板化 PDF：请先上传简历",
      tone: "warning",
      detail: "没有可用于套用模板的简历记录。",
      actionHint: "上传 DOCX 简历可保留原模板排版。",
      canDownload: false
    };
  }
  if (resume.template_available) {
    return {
      label: "模板化 PDF：可下载",
      tone: "success",
      detail: "将使用原 DOCX 简历模板，只替换可编辑正文并导出一页 PDF。",
      actionHint: "下载前后端会校验 PDF 可解析且不超过一页。",
      canDownload: true
    };
  }
  if (resume.file_type === "pdf") {
    return {
      label: "模板化 PDF：PDF 简历可生成材料，但不能保留原 PDF 排版",
      tone: "warning",
      detail: "当前 PDF 已可用于简历改写和招呼语生成，但无法安全保留原 PDF 图片、版式和一页模板。",
      actionHint: "如需模板化一页 PDF，请上传 DOCX 版本简历。",
      canDownload: false
    };
  }
  return {
    label: "模板化 PDF：需重新上传 DOCX 简历",
    tone: "warning",
    detail: "当前简历没有保存可套用的 DOCX 模板。",
    actionHint: "上传 DOCX 简历后可以保留头像、基础信息、教育经历和原始排版。",
    canDownload: false
  };
}

export function getResumeReadingStatus(
  resume: Pick<ResumeDraft, "file_type" | "raw_text" | "profile"> | null | undefined
): ResumeReadingStatus {
  if (!resume) {
    return {
      label: "读取状态：等待上传",
      tone: "muted",
      detail: "上传简历后会显示文本提取、OCR 或手动补全状态。",
      actionHint: "",
      needsManualText: false,
      canGenerateMaterials: false
    };
  }

  const profile = asRecord(resume.profile);
  const extraction = asRecord(profile.extraction);
  const imageReading = asRecord(profile.image_reading);
  const reading = Object.keys(imageReading).length > 0 && !Object.keys(extraction).length ? imageReading : extraction;
  const sourceType = stringValue(reading.source_type);
  const status = stringValue(reading.status);
  const message = stringValue(reading.message);
  const textLength = numberValue(reading.text_length);
  const manualRequired = reading.manual_text_required === true;
  const canGenerateMaterials = profile.can_generate_materials === true || (Boolean(resume.raw_text.trim()) && !manualRequired);

  if (sourceType === "manual") {
    return {
      label: "读取状态：已手动补全",
      tone: "success",
      detail: `已使用你粘贴的简历正文，当前可用于搜索和生成材料。`,
      actionHint: "",
      needsManualText: false,
      canGenerateMaterials: true
    };
  }

  if (manualRequired || status === "needs_ocr" || status === "manual_required") {
    const isImage = resume.file_type === "png" || resume.file_type === "jpg" || resume.file_type === "jpeg" || sourceType.startsWith("image_");
    return {
      label: isImage ? "读取状态：图片简历需要补全文本" : "读取状态：需要 OCR 或手动补全",
      tone: "warning",
      detail: message || "当前文件没有可直接读取的简历正文，生成材料前需要补全文本。",
      actionHint: "请在下方粘贴简历正文，保存后会重新提取技能、关键词和城市。",
      needsManualText: true,
      canGenerateMaterials: false
    };
  }

  if (canGenerateMaterials) {
    return {
      label: "读取状态：已提取文本",
      tone: "success",
      detail: textLength ? `已提取 ${textLength.toLocaleString("en-US")} 个字符，可用于搜索和生成材料。` : "已提取到可用简历正文。",
      actionHint: "",
      needsManualText: false,
      canGenerateMaterials: true
    };
  }

  return {
    label: "读取状态：需要手动补全",
    tone: "warning",
    detail: message || "当前简历正文为空，无法创建有效搜索任务或生成材料。",
    actionHint: "请粘贴简历正文后保存。",
    needsManualText: true,
    canGenerateMaterials: false
  };
}

export function getPdfDownloadFailureMessage(status: number, detail: string): string {
  if (status === 503 || /converter|LibreOffice|Microsoft Word|转换器|soffice/i.test(detail)) {
    return `模板化 PDF：缺少转换器。${detail}`;
  }
  if (/renderer unavailable|render validation|pdftoppm|渲染/i.test(detail)) {
    return `模板化 PDF：渲染器不可用或渲染检查失败。${detail}`;
  }
  if (/DOCX|重新上传/i.test(detail)) {
    return "模板化 PDF：需重新上传 DOCX 简历以保留模板。";
  }
  return `模板化 PDF：${detail}`;
}

function pdfToneFromMessage(message: string): StatusTone {
  if (/已生成|开始下载|可下载/.test(message)) {
    return "success";
  }
  if (/失败|缺少|需|不可用|不能/.test(message)) {
    return "warning";
  }
  return "info";
}

export function extractPlatformConfirmation(note: string | null | undefined): PlatformConfirmationSummary {
  const text = (note ?? "").trim();
  const evidence = text.match(/平台确认[:：]\s*([^;；|｜\n]+)/)?.[1]?.trim() ?? "";
  const sourceUrl = text.match(/平台链接[:：]\s*(https?:\/\/[^;；|｜\s]+)/)?.[1]?.trim() ?? "";
  const cleanedNote = text
    .replace(/平台确认[:：]\s*([^;；|｜\n]+)/, "")
    .replace(/平台链接[:：]\s*(https?:\/\/[^;；|｜\s]+)/, "")
    .split(/[;；|｜]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .join("；");

  return {
    confirmed: Boolean(evidence || sourceUrl),
    evidence,
    sourceUrl,
    note: cleanedNote,
    buttonText: "",
    status: "",
    confirmedAt: "",
    pageSummary: ""
  };
}

export function summarizePlatformConfirmation(
  proof: Partial<ApplicationPlatformProof> | null | undefined,
  note: string | null | undefined
): PlatformConfirmationSummary {
  const legacy = extractPlatformConfirmation(note);
  const evidence = stringValue(proof?.evidence);
  const sourceUrl = stringValue(proof?.source_url);
  const confirmedAt = stringValue(proof?.confirmed_at);
  const status = stringValue(proof?.status);
  const pageSummary = stringValue(proof?.page_summary);
  const buttonText = stringValue(proof?.button_text);
  if (!evidence && !sourceUrl && !confirmedAt && !status && !pageSummary && !buttonText) {
    return legacy;
  }
  return {
    confirmed: true,
    evidence: evidence || pageSummary || status || legacy.evidence,
    sourceUrl: sourceUrl || legacy.sourceUrl,
    note: legacy.note,
    buttonText,
    status,
    confirmedAt,
    pageSummary
  };
}

export function buildTailorModelSummary(
  bundle: Pick<TailorBundle, "review"> | null | undefined,
  usage: LLMUsageSummary | null
): TailorModelSummary {
  const llm = asRecord(asRecord(bundle?.review).llm);
  const status = stringValue(llm.status) || "unknown";
  const provider = stringValue(llm.provider) || "unknown";
  const model = stringValue(llm.model) || "unknown";
  const route = asRecord(llm.route);
  const reviewRoute = asRecord(llm.review_route);
  const writerMode = stringValue(route.mode) || "unknown";
  const reviewMode = stringValue(reviewRoute.mode) || "unknown";
  const reason = stringValue(llm.reason);
  const error = stringValue(llm.error);
  const currentTotalTokens = numberValue(llm.total_tokens);
  const currentCost = numberValue(llm.cost_usd);
  const currentDurationMs = numberValue(llm.duration_ms);
  const writerUsage = usage?.by_agent.ApplicationWriterAgent;
  const totalTokens = Math.round(writerUsage?.total_tokens ?? 0);
  const totalCost = writerUsage?.total_cost_usd ?? writerUsage?.cost_usd ?? 0;
  const usageLabel =
    currentTotalTokens > 0 || currentCost > 0 || currentDurationMs > 0
      ? `本次 ${Math.round(currentTotalTokens).toLocaleString("en-US")} tokens / $${currentCost.toFixed(4)} / ${Math.round(currentDurationMs)}ms`
      : totalTokens > 0 || totalCost > 0
      ? `ApplicationWriterAgent 累计 ${totalTokens.toLocaleString("en-US")} tokens / $${totalCost.toFixed(4)}`
      : "暂无 token/成本记录";

  if (status === "success") {
    return {
      statusLabel: "DeepSeek/API 已调用",
      tone: "success",
      providerModel: `${provider} / ${model}`,
      routeLabel: `ApplicationWriterAgent: ${writerMode}; ReviewAgent: ${reviewMode}`,
      usageLabel,
      detail: "材料由外部模型生成，ReviewAgent 继续做事实边界审核。",
      errorLabel: "",
      setupHint: ""
    };
  }

  if (status === "fallback") {
    return {
      statusLabel: "模型调用失败，当前本地回退",
      tone: "warning",
      providerModel: `${provider} / ${model}`,
      routeLabel: `ApplicationWriterAgent: ${writerMode}; ReviewAgent: ${reviewMode}`,
      usageLabel,
      detail: "外部模型调用失败，本次材料使用本地规则兜底生成。",
      errorLabel: error ? `错误：${error}` : "",
      setupHint: "本次已经尝试调用外部模型但失败；请检查 API Key、base_url、模型名或网络后重新生成。"
    };
  }

  if (status === "local") {
    return {
      statusLabel: "未接入模型，当前本地规则生成",
      tone: "muted",
      providerModel: `${provider} / ${model}`,
      routeLabel: `ApplicationWriterAgent: ${writerMode}; ReviewAgent: ${reviewMode}`,
      usageLabel,
      detail: reason ? `未调用外部模型：${reason}` : "当前模型路由选择本地规则。",
      errorLabel: "",
      setupHint: "这不是 DeepSeek/AI 模型输出。请在“模型 / API”面板启用 Agent 路由，并在后端环境变量中配置 API Key。"
    };
  }

  return {
    statusLabel: "模型状态未知",
    tone: "muted",
    providerModel: `${provider} / ${model}`,
    routeLabel: `ApplicationWriterAgent: ${writerMode}; ReviewAgent: ${reviewMode}`,
    usageLabel,
    detail: "材料响应里没有可识别的模型调用状态。",
    errorLabel: error ? `错误：${error}` : "",
    setupHint: "无法确认本次是否调用模型；请查看 Agent 状态和成本记录。"
  };
}

export function buildJobMatchModelSummary(snapshot: BackendAgentEventsSnapshot | null): JobMatchModelSummary | null {
  const event = (snapshot?.agents ?? []).find((item) => item.agent_name === "JobMatchAgent");
  if (!event) {
    return null;
  }
  const fields = parseSummaryFields(event.output_summary);
  const route = fields.route || "local-estimator";
  const usageStatus = fields.usage_status || "";
  const tokens = event.total_tokens ?? 0;
  const usageLabel = tokens > 0 || event.cost_usd > 0
    ? `${tokens.toLocaleString("en-US")} tokens / $${event.cost_usd.toFixed(4)}`
    : "暂无 token/成本记录";

  if (usageStatus === "success") {
    return {
      statusLabel: "匹配分由模型评分",
      tone: "success",
      modelLabel: route,
      usageLabel,
      detail: event.output_summary || event.step
    };
  }

  if (usageStatus === "failed") {
    return {
      statusLabel: "模型评分失败，已规则兜底",
      tone: "warning",
      modelLabel: route,
      usageLabel,
      detail: event.error || event.output_summary || "搜索任务保留本地规则匹配结果。"
    };
  }

  return {
    statusLabel: "匹配分由本地规则生成",
    tone: "muted",
    modelLabel: route,
    usageLabel,
    detail: event.output_summary || "未启用 JobMatchAgent 外部模型路由。"
  };
}

function parseSummaryFields(summary: string): Record<string, string> {
  return Object.fromEntries(
    summary
      .split(";")
      .map((part) => part.trim())
      .map((part) => {
        const [key, ...rest] = part.split("=");
        return [key.trim(), rest.join("=").trim()];
      })
      .filter(([key, value]) => key && value)
  );
}

function normalizeAgentStatus(status: string): AgentRuntimeStatus {
  if (status === "running" || status === "success" || status === "failed") {
    return status;
  }
  return "pending";
}

function getEventErrorMessage(event: BackendAgentEvent, status: AgentRuntimeStatus): string {
  if (event.error) {
    return event.error;
  }
  if (status === "failed") {
    return event.output_summary || event.step || "Agent failed";
  }
  return "";
}

function getRuntimeStatus(agentName: RuntimeAgentName, snapshot: AgentRuntimeSnapshot): AgentRuntimeStatus {
  if (snapshot.failedAgent === agentName) {
    return "failed";
  }
  if (snapshot.runningAgent === agentName) {
    return "running";
  }
  if (agentName === "ResumeParserAgent") {
    return snapshot.resumeName ? "success" : "pending";
  }
  if (agentName === "JobSearchAgent" || agentName === "JobMatchAgent") {
    return snapshot.jobCount > 0 ? "success" : "pending";
  }
  if (agentName === "ApplicationWriterAgent" || agentName === "ReviewAgent") {
    return snapshot.tailoredCount > 0 ? "success" : "pending";
  }
  return "pending";
}

function getCurrentStep(agentName: RuntimeAgentName, status: AgentRuntimeStatus): string {
  if (status === "running") {
    return "正在执行";
  }
  if (status === "failed") {
    return "执行失败，等待人工处理";
  }
  const steps: Record<RuntimeAgentName, string> = {
    ResumeParserAgent: "解析简历并生成候选人画像",
    JobSearchAgent: "调用平台适配器搜索岗位",
    JobMatchAgent: "规则过滤并计算岗位匹配度",
    ApplicationWriterAgent: "为选中岗位生成定制简历和招呼语",
    ReviewAgent: "检查虚构经历和沟通风险"
  };
  return status === "success" ? "已完成最近一次任务" : steps[agentName];
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function getInputSummary(agentName: RuntimeAgentName, snapshot: AgentRuntimeSnapshot): string {
  const selectedJob = snapshot.selectedJobTitle ?? "未选择岗位";
  const inputs: Record<RuntimeAgentName, string> = {
    ResumeParserAgent: snapshot.resumeName ?? "等待上传简历",
    JobSearchAgent: snapshot.searchSummary,
    JobMatchAgent: `${snapshot.jobCount} 个岗位`,
    ApplicationWriterAgent: selectedJob,
    ReviewAgent: selectedJob
  };
  return inputs[agentName];
}

function getOutputSummary(agentName: RuntimeAgentName, snapshot: AgentRuntimeSnapshot): string {
  const outputs: Record<RuntimeAgentName, string> = {
    ResumeParserAgent: snapshot.resumeName ? "候选人画像已生成" : "暂无输出",
    JobSearchAgent: snapshot.jobCount ? `岗位池 ${snapshot.jobCount} 条` : "暂无岗位",
    JobMatchAgent: snapshot.jobCount ? "匹配结果已写入岗位表" : "等待岗位输入",
    ApplicationWriterAgent: snapshot.tailoredCount ? `已生成 ${snapshot.tailoredCount} 组材料` : "暂无材料",
    ReviewAgent: snapshot.tailoredCount ? "已完成事实边界检查" : "等待生成材料"
  };
  return outputs[agentName];
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function clampPercent(value: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}
