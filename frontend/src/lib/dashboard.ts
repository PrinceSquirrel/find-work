import type {
  AnalyticsBucket,
  ApplicationStatus,
  JobFilters,
  JobPosting,
  LLMUsageAgentBucket,
  LLMUsageSummary,
  UsageCards
} from "../types";

export type StatusTone = "muted" | "info" | "accent" | "success" | "danger";
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

export interface BackendAgentEventsSnapshot {
  current_running_agent: string | null;
  total_cost_usd: number;
  agents: BackendAgentEvent[];
  events: BackendAgentEvent[];
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
