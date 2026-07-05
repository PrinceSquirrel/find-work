import { FormEvent, useEffect, useMemo, useState } from "react";

import { api, getTailorBlockedMessage } from "./lib/api";
import {
  buildAgentStatusRows,
  buildAgentStatusRowsFromEvents,
  buildJobMatchModelSummary,
  buildModelRouteApplyOptions,
  buildOrchestratorSummary,
  buildTailorModelSummary,
  clampPercent,
  filterJobsForActiveSearchRun,
  filterModelProfiles,
  formatDateTime,
  getAllowedNextStatuses,
  getJobDetailQuality,
  getPdfDownloadFailureMessage,
  getPdfTemplateStatus,
  getRatePercent,
  getResumeReadingStatus,
  getStatusTone,
  rankJobs,
  shouldShowTailorRetryAction,
  summarizePlatformConfirmation,
  summarizeUsage
} from "./lib/dashboard";
import type {
  AgentModelRoute,
  AnalyticsBucket,
  ApplicationAnalytics,
  ApplicationRecord,
  ApplicationSyncDiagnostic,
  ApplicationSyncProposal,
  ApplicationStatus,
  JobFilters,
  JobPosting,
  LLMUsageSummary,
  ModelConfig,
  ModelConfigTestResult,
  ModelProfile,
  ModelConfigUpdate,
  Platform,
  PlatformApplyPreview,
  PlatformJobExtraction,
  PlatformSession,
  ResumeDraft,
  SearchRun,
  TailorBundle
} from "./types";

const PLATFORM_LABELS: Record<string, string> = {
  boss: "BOSS直聘",
  shixiseng: "实习僧"
};

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  discovered: "已发现",
  matched: "已匹配",
  generated: "已生成",
  applied: "已投递",
  read: "已读",
  replied: "已回复",
  interview: "面试中",
  assessment: "笔试/测评",
  rejected: "已拒绝",
  closed: "已关闭"
};

const RECOMMENDATION_LABELS: Record<string, string> = {
  strong_apply: "强推荐",
  review: "人工复核",
  skip: "暂缓"
};

const STATUS_COLUMNS: ApplicationStatus[] = [
  "applied",
  "read",
  "replied",
  "interview",
  "assessment",
  "rejected",
  "closed"
];

const DEEPSEEK_MODEL_PRESET: ModelConfigUpdate = {
  provider: "openai-compatible",
  model: "deepseek-v4-pro",
  base_url: "https://api.deepseek.com",
  api_key_env_var: "DEEPSEEK_API_KEY",
  enabled: true,
  estimation_only: false,
  timeout_ms: 90000,
  input_price_per_million: 1,
  output_price_per_million: 2
};

const DEEPSEEK_FLASH_MODEL_PRESET: ModelConfigUpdate = {
  ...DEEPSEEK_MODEL_PRESET,
  model: "deepseek-v4-flash",
  timeout_ms: 45000,
  input_price_per_million: 0.5,
  output_price_per_million: 1
};

const MODEL_PROVIDER_OPTIONS = [
  { value: "openai-compatible", label: "DeepSeek / OpenAI 兼容" },
  { value: "local", label: "本地规则 / 不调用模型" }
];

const MODEL_VERSION_OPTIONS = [
  { value: "deepseek-v4-pro", label: "DeepSeek v4 Pro" },
  { value: "deepseek-v4-flash", label: "DeepSeek v4 Flash" },
  { value: "deepseek-chat", label: "DeepSeek Chat" }
];

const MODEL_ROUTE_AGENT_LABELS: Record<string, string> = {
  OrchestratorAgent: "总模型大脑",
  ResumeParserAgent: "简历解析",
  ApplicationWriterAgent: "简历/招呼语生成",
  JobMatchAgent: "岗位匹配评分",
  ReviewAgent: "事实风险审核"
};

type BusyState = {
  boot: boolean;
  upload: boolean;
  search: boolean;
  launchCdp: boolean;
  sessions: boolean;
  extract: boolean;
  syncApplications: boolean;
  tailorJobId: number | null;
  applyJobId: number | null;
  updateApplicationId: number | null;
  refreshDetailJobId: number | null;
  manualDetailJobId: number | null;
  manualResumeText: boolean;
  revisionTailoredResumeId: number | null;
  modelTest: boolean;
  modelRouteAgent: string | null;
  modelProfileAction: "save" | "apply" | "delete" | null;
};

const initialBusy: BusyState = {
  boot: true,
  upload: false,
  search: false,
  launchCdp: false,
  sessions: false,
  extract: false,
  syncApplications: false,
  tailorJobId: null,
  applyJobId: null,
  updateApplicationId: null,
  refreshDetailJobId: null,
  manualDetailJobId: null,
  manualResumeText: false,
  revisionTailoredResumeId: null,
  modelTest: false,
  modelRouteAgent: null,
  modelProfileAction: null
};

type SearchMode = "demo" | "browser_cdp";
type AgentEventsPayload = Awaited<ReturnType<typeof api.getAgentEvents>>;
type OrchestratorTaskDetail = NonNullable<NonNullable<AgentEventsPayload["orchestrator"]>["last_task"]>;

function toModelConfigUpdate(config: ModelConfig): ModelConfigUpdate {
  return {
    provider: config.provider,
    model: config.model,
    base_url: config.base_url,
    api_key_env_var: config.api_key_env_var,
    enabled: config.enabled,
    estimation_only: config.estimation_only,
    timeout_ms: config.timeout_ms,
    input_price_per_million: config.input_price_per_million,
    output_price_per_million: config.output_price_per_million
  };
}

function keyStatusText(config: Pick<ModelConfig, "api_key_configured" | "api_key_masked" | "api_key_env_var"> | null): string {
  if (!config) {
    return "未读取";
  }
  if (config.api_key_configured) {
    return config.api_key_masked ? `已保存 ${config.api_key_masked}` : "Key 已配置";
  }
  return config.api_key_env_var ? `等待 ${config.api_key_env_var}` : "未配置";
}

function withModelApiKey(draft: ModelConfigUpdate, apiKey: string): ModelConfigUpdate {
  return {
    ...draft,
    api_key_env_var: "",
    api_key: apiKey.trim()
  };
}

function App() {
  const [resume, setResume] = useState<ResumeDraft | null>(null);
  const [jobs, setJobs] = useState<JobPosting[]>([]);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [analytics, setAnalytics] = useState<ApplicationAnalytics | null>(null);
  const [usage, setUsage] = useState<LLMUsageSummary | null>(null);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [modelDraft, setModelDraft] = useState<ModelConfigUpdate>(DEEPSEEK_MODEL_PRESET);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [selectedModelProfileId, setSelectedModelProfileId] = useState<number | null>(null);
  const [modelProfileName, setModelProfileName] = useState("DeepSeek v4pro");
  const [modelProfileQuery, setModelProfileQuery] = useState("");
  const [isModelManagerOpen, setIsModelManagerOpen] = useState(false);
  const [modelMessage, setModelMessage] = useState<string | null>(null);
  const [modelTestResult, setModelTestResult] = useState<ModelConfigTestResult | null>(null);
  const [modelApiKey, setModelApiKey] = useState("");
  const [showModelApiKey, setShowModelApiKey] = useState(false);
  const [modelRoutes, setModelRoutes] = useState<AgentModelRoute[]>([]);
  const [modelRouteDrafts, setModelRouteDrafts] = useState<Record<string, ModelConfigUpdate>>({});
  const [modelRouteProfileSelections, setModelRouteProfileSelections] = useState<Record<string, number | "">>({});
  const [modelRouteMessage, setModelRouteMessage] = useState<string | null>(null);
  const [agentEvents, setAgentEvents] = useState<Awaited<ReturnType<typeof api.getAgentEvents>> | null>(null);
  const [tailorBundles, setTailorBundles] = useState<Record<number, TailorBundle>>({});
  const [tailoredRevisionDrafts, setTailoredRevisionDrafts] = useState<Record<number, string>>({});
  const [tailoredRevisionMessages, setTailoredRevisionMessages] = useState<Record<number, string>>({});
  const [tailorBlockedMessages, setTailorBlockedMessages] = useState<Record<number, string>>({});
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [detailJobId, setDetailJobId] = useState<number | null>(null);
  const [lastRun, setLastRun] = useState<SearchRun | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>("browser_cdp");
  const [platformSessions, setPlatformSessions] = useState<PlatformSession[]>([]);
  const [platformExtractions, setPlatformExtractions] = useState<PlatformJobExtraction[]>([]);
  const [syncProposals, setSyncProposals] = useState<ApplicationSyncProposal[]>([]);
  const [syncDiagnostics, setSyncDiagnostics] = useState<ApplicationSyncDiagnostic[]>([]);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [pdfStatusMessage, setPdfStatusMessage] = useState<string | null>(null);
  const [orchestratorDetail, setOrchestratorDetail] = useState<OrchestratorTaskDetail | null>(null);
  const [cdpLaunchMessage, setCdpLaunchMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failedAgent, setFailedAgent] = useState<ReturnType<typeof buildAgentStatusRows>[number]["agentName"] | null>(null);
  const [busy, setBusy] = useState<BusyState>(initialBusy);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [manualResumeText, setManualResumeText] = useState("");
  const [searchKeywords, setSearchKeywords] = useState("React 实习, Agent 实习");
  const [searchCity, setSearchCity] = useState("上海");
  const [searchFieldsTouched, setSearchFieldsTouched] = useState(false);
  const [platforms, setPlatforms] = useState<Record<"boss" | "shixiseng", boolean>>({
    boss: true,
    shixiseng: true
  });
  const [filters, setFilters] = useState<JobFilters>({
    platform: "all",
    keyword: "",
    minScore: 0
  });
  const [manualDetailDrafts, setManualDetailDrafts] = useState<Record<number, string>>({});
  const [manualDetailNotes, setManualDetailNotes] = useState<Record<number, string>>({});
  const [applyNotes, setApplyNotes] = useState<Record<number, string>>({});
  const [applyPreviews, setApplyPreviews] = useState<Record<number, PlatformApplyPreview>>({});
  const [statusDrafts, setStatusDrafts] = useState<Record<number, ApplicationStatus>>({});
  const [statusNotes, setStatusNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    void refreshWorkspace();
    const timerId = window.setInterval(() => {
      void refreshAgentEvents();
    }, 5000);
    return () => window.clearInterval(timerId);
  }, []);

  const rankedJobs = useMemo(() => rankJobs(jobs, filters), [filters, jobs]);
  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? rankedJobs[0] ?? null,
    [jobs, rankedJobs, selectedJobId]
  );
  const selectedBundle = selectedJob ? tailorBundles[selectedJob.id] : undefined;
  const selectedTailorBlockedMessage = selectedJob ? tailorBlockedMessages[selectedJob.id] : "";
  const selectedApplyPreview = selectedJob ? applyPreviews[selectedJob.id] : undefined;
  const selectedTailorModelSummary = useMemo(
    () => (selectedBundle ? buildTailorModelSummary(selectedBundle, usage) : null),
    [selectedBundle, usage]
  );
  const selectedRevisionDraft = selectedBundle
    ? tailoredRevisionDrafts[selectedBundle.id] ?? getBundleEditableText(selectedBundle)
    : "";
  const selectedPreviewText = selectedRevisionDraft;
  const selectedRevisionMessage = selectedBundle ? tailoredRevisionMessages[selectedBundle.id] ?? "" : "";
  const selectedPdfTemplateStatus = useMemo(
    () => getPdfTemplateStatus(resume, Boolean(selectedBundle), pdfStatusMessage),
    [pdfStatusMessage, resume, selectedBundle]
  );
  const resumeReadingStatus = useMemo(() => getResumeReadingStatus(resume), [resume]);
  const showTailorRetryAction = shouldShowTailorRetryAction({
    job: selectedJob,
    hasBundle: Boolean(selectedBundle),
    blockedMessage: selectedTailorBlockedMessage
  });
  const detailJob = useMemo(
    () => jobs.find((job) => job.id === detailJobId) ?? null,
    [detailJobId, jobs]
  );
  const detailQuality = useMemo(() => (detailJob ? getJobDetailQuality(detailJob) : null), [detailJob]);
  const applicationsByJob = useMemo(() => {
    return new Map(applications.map((application) => [application.job_id, application]));
  }, [applications]);
  const usageCards = useMemo(() => summarizeUsage(usage), [usage]);
  const totalApplications = analytics?.totals.applications ?? applications.length;
  const importableExtractionCount = useMemo(
    () =>
      platformExtractions.reduce(
        (total, extraction) => total + (extraction.status === "success" ? extraction.jobs.length : 0),
        0
      ),
    [platformExtractions]
  );
  const localRunningAgent = useMemo(() => {
    if (busy.upload || busy.manualResumeText) return "ResumeParserAgent";
    if (busy.search) return "JobSearchAgent";
    if (busy.refreshDetailJobId !== null) return "JobSearchAgent";
    if (busy.manualDetailJobId !== null) return "JobMatchAgent";
    if (busy.tailorJobId !== null) return "ApplicationWriterAgent";
    return null;
  }, [busy.manualDetailJobId, busy.manualResumeText, busy.refreshDetailJobId, busy.search, busy.tailorJobId, busy.upload]);
  const runningAgent = agentEvents?.current_running_agent ?? localRunningAgent;
  const agentRows = useMemo(
    () =>
      agentEvents
        ? buildAgentStatusRowsFromEvents(agentEvents)
        : buildAgentStatusRows({
            runningAgent: localRunningAgent,
            failedAgent,
            errorMessage: error,
            resumeName: resume?.filename ?? null,
            searchSummary: `${searchCity || "未选城市"} / ${searchKeywords || "未填关键词"}`,
            selectedJobTitle: selectedJob?.title ?? null,
            jobCount: jobs.length,
            tailoredCount: Object.keys(tailorBundles).length,
            usageByAgent: usage?.by_agent ?? {}
          }),
    [agentEvents, error, failedAgent, jobs.length, localRunningAgent, resume?.filename, searchCity, searchKeywords, selectedJob?.title, tailorBundles, usage]
  );
  const agentCost = agentEvents ? `$${agentEvents.total_cost_usd.toFixed(4)}` : usageCards.totalCost;
  const orchestratorSummary = useMemo(() => buildOrchestratorSummary(agentEvents), [agentEvents]);
  const jobMatchModelSummary = useMemo(() => buildJobMatchModelSummary(agentEvents), [agentEvents]);
  const orchestratorTaskId = agentEvents?.orchestrator?.last_task?.id ?? null;
  const visibleOrchestratorDetail = orchestratorDetail?.id === orchestratorTaskId ? orchestratorDetail : null;
  const selectedModelProfile = useMemo(
    () => modelProfiles.find((profile) => profile.id === selectedModelProfileId) ?? null,
    [modelProfiles, selectedModelProfileId]
  );
  const filteredModelProfiles = useMemo(
    () => filterModelProfiles(modelProfiles, modelProfileQuery),
    [modelProfileQuery, modelProfiles]
  );
  const modelRouteApplyOptions = useMemo(
    () => buildModelRouteApplyOptions(modelRoutes, selectedModelProfile, MODEL_ROUTE_AGENT_LABELS),
    [modelRoutes, selectedModelProfile]
  );

  async function refreshWorkspace() {
    setBusy((current) => ({ ...current, boot: true }));
    setError(null);
    setFailedAgent(null);
    try {
      const [
        nextResume,
        nextJobs,
        nextApplications,
        nextAnalytics,
        nextUsage,
        nextSessions,
        nextAgentEvents,
        nextModelConfig,
        nextModelRoutes,
        nextModelProfiles
      ] = await Promise.all([
        api.getLatestResume(),
        api.listJobs(),
        api.listApplications(),
        api.getApplicationAnalytics(),
        api.getLlmUsage(),
        api.getPlatformSessions(),
        api.getAgentEvents(),
        api.getModelConfig(),
        api.getModelRoutes(),
        api.getModelProfiles()
      ]);
      const visibleJobs = filterJobsForActiveSearchRun(nextJobs, lastRun?.id ?? null);
      setResume(nextResume);
      setManualResumeText(nextResume?.raw_text ?? "");
      if (nextResume && !searchFieldsTouched) {
        const suggestedKeywords = getProfileStringArray(nextResume.profile, "suggested_keywords");
        const suggestedCity = getProfileString(nextResume.profile, "suggested_city");
        if (suggestedKeywords.length) {
          setSearchKeywords(suggestedKeywords.join(", "));
        }
        if (suggestedCity) {
          setSearchCity(suggestedCity);
        }
      }
      setJobs(visibleJobs);
      setSelectedJobId(visibleJobs[0]?.id ?? null);
      setApplications(nextApplications);
      setAnalytics(nextAnalytics);
      setUsage(nextUsage);
      setPlatformSessions(nextSessions.sessions);
      setAgentEvents(nextAgentEvents);
      setModelConfig(nextModelConfig);
      setModelRoutes(nextModelRoutes.routes);
      setModelProfiles(nextModelProfiles.profiles);
      setModelRouteDrafts(Object.fromEntries(nextModelRoutes.routes.map((route) => [route.agent_name, toModelConfigUpdate(route)])));
      setModelRouteProfileSelections((current) => {
        const fallbackProfileId = nextModelProfiles.profiles[0]?.id ?? "";
        return Object.fromEntries(
          nextModelRoutes.routes.map((route) => [route.agent_name, current[route.agent_name] ?? fallbackProfileId])
        );
      });
      setModelDraft({
        provider: nextModelConfig.provider || DEEPSEEK_MODEL_PRESET.provider,
        model: nextModelConfig.model || DEEPSEEK_MODEL_PRESET.model,
        base_url: nextModelConfig.base_url || DEEPSEEK_MODEL_PRESET.base_url,
        api_key_env_var: nextModelConfig.api_key_env_var || "",
        enabled: nextModelConfig.enabled,
        estimation_only: nextModelConfig.estimation_only,
        timeout_ms: nextModelConfig.timeout_ms,
        input_price_per_million: nextModelConfig.input_price_per_million,
        output_price_per_million: nextModelConfig.output_price_per_million
      });
      setModelApiKey("");
      const firstProfile = nextModelProfiles.profiles[0] ?? null;
      if (firstProfile && selectedModelProfileId === null) {
        setSelectedModelProfileId(firstProfile.id);
        setModelProfileName(firstProfile.name);
      }
    } catch (nextError) {
      setFailedAgent("ResumeParserAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, boot: false }));
    }
  }

  async function refreshOutcomeData() {
    const [nextApplications, nextAnalytics, nextUsage, nextAgentEvents] = await Promise.all([
      api.listApplications(),
      api.getApplicationAnalytics(),
      api.getLlmUsage(),
      api.getAgentEvents()
    ]);
    setApplications(nextApplications);
    setAnalytics(nextAnalytics);
    setUsage(nextUsage);
    setAgentEvents(nextAgentEvents);
  }

  async function handleSaveModelConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setModelMessage(null);
    try {
      const saved = await api.updateModelConfig(withModelApiKey(modelDraft, modelApiKey));
      setModelConfig(saved);
      setModelTestResult(null);
      setModelApiKey("");
      setModelDraft({
        provider: saved.provider,
        model: saved.model,
        base_url: saved.base_url,
        api_key_env_var: saved.api_key_env_var || "",
        enabled: saved.enabled,
        estimation_only: saved.estimation_only,
        timeout_ms: saved.timeout_ms,
        input_price_per_million: saved.input_price_per_million,
        output_price_per_million: saved.output_price_per_million
      });
      setModelMessage(saved.api_key_configured ? `模型已接入：${saved.model}，${keyStatusText(saved)}。` : "已保存配置，但还没有 API Key。");
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    }
  }

  function handleSelectModelProfile(profileIdValue: string) {
    const profileId = profileIdValue ? Number(profileIdValue) : null;
    setSelectedModelProfileId(profileId);
    if (profileId === null) {
      setModelProfileName("");
      return;
    }
    const profile = modelProfiles.find((item) => item.id === profileId);
    if (!profile) {
      return;
    }
    setModelProfileName(profile.name);
    setModelDraft(toModelConfigUpdate(profile));
    setModelApiKey("");
    setModelTestResult(null);
    setModelMessage(`已载入模型档案：${profile.name}，${keyStatusText(profile)}。`);
  }

  function handleNewModelProfile() {
    setSelectedModelProfileId(null);
    setModelProfileName("");
    setModelProfileQuery("");
    setModelDraft(DEEPSEEK_MODEL_PRESET);
    setModelApiKey("");
    setModelTestResult(null);
    setModelMessage("已切换为新建模型档案，填写名称后保存。");
  }

  async function handleSaveModelProfile() {
    const profileName = modelProfileName.trim();
    if (!profileName) {
      setError("请先填写模型档案名称。");
      return;
    }
    setBusy((current) => ({ ...current, modelProfileAction: "save" }));
    setError(null);
    setModelMessage(null);
    try {
      const saved =
        selectedModelProfileId === null
          ? await api.createModelProfile(profileName, withModelApiKey(modelDraft, modelApiKey))
          : await api.updateModelProfile(selectedModelProfileId, profileName, withModelApiKey(modelDraft, modelApiKey));
      setModelProfiles((current) => {
        const nextProfiles = current.filter((profile) => profile.id !== saved.id);
        return [...nextProfiles, saved].sort((left, right) => left.id - right.id);
      });
      setSelectedModelProfileId(saved.id);
      setModelProfileName(saved.name);
      setModelDraft(toModelConfigUpdate(saved));
      setModelApiKey("");
      setModelMessage(saved.api_key_configured ? `模型档案已保存：${saved.name}，${keyStatusText(saved)}。` : `模型档案已保存：${saved.name}，但还没有 API Key。`);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelProfileAction: null }));
    }
  }

  async function handleApplyModelProfile() {
    if (selectedModelProfileId === null) {
      setError("请先选择一个已保存的模型档案。");
      return;
    }
    setBusy((current) => ({ ...current, modelProfileAction: "apply" }));
    setError(null);
    setModelMessage(null);
    try {
      const saved = await api.applyModelProfile(selectedModelProfileId);
      setModelConfig(saved);
      setModelDraft(toModelConfigUpdate(saved));
      setModelApiKey("");
      setModelTestResult(null);
      setModelMessage(`已套用模型档案到当前全局配置：${saved.model}，${keyStatusText(saved)}。`);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelProfileAction: null }));
    }
  }

  async function handleDeleteModelProfile() {
    if (selectedModelProfileId === null) {
      setError("请先选择要删除的模型档案。");
      return;
    }
    if (!window.confirm(`删除模型档案“${modelProfileName || selectedModelProfile?.name || selectedModelProfileId}”？`)) {
      return;
    }
    setBusy((current) => ({ ...current, modelProfileAction: "delete" }));
    setError(null);
    setModelMessage(null);
    try {
      await api.deleteModelProfile(selectedModelProfileId);
      setModelProfiles((current) => current.filter((profile) => profile.id !== selectedModelProfileId));
      setSelectedModelProfileId(null);
      setModelProfileName("");
      setModelApiKey("");
      setModelMessage("模型档案已删除，当前全局模型配置不会被自动清空。");
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelProfileAction: null }));
    }
  }

  async function handleTestModelConnection() {
    setBusy((current) => ({ ...current, modelTest: true }));
    setError(null);
    setModelMessage(null);
    setModelTestResult(null);
    try {
      const result = await api.testModelConfigConnection();
      setModelTestResult(result);
      setModelMessage(
        result.status === "success"
          ? `模型连接成功：${result.provider} / ${result.model} / ${result.duration_ms}ms`
          : `模型连接失败：${result.error || "请检查 API 地址、模型名和 API Key。"}`
      );
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelTest: false }));
    }
  }

  async function handleSaveModelRoute(event: FormEvent<HTMLFormElement>, agentName: string) {
    event.preventDefault();
    const draft = modelRouteDrafts[agentName];
    if (!draft) {
      setError(`未读取到 ${agentName} 的模型路由配置。`);
      return;
    }
    setBusy((current) => ({ ...current, modelRouteAgent: agentName }));
    setError(null);
    setModelRouteMessage(null);
    try {
      const saved = await api.updateModelRoute(agentName, draft);
      setModelRoutes((current) => {
        const nextRoutes = current.filter((route) => route.agent_name !== saved.agent_name);
        return [...nextRoutes, saved].sort((left, right) => left.agent_name.localeCompare(right.agent_name));
      });
      setModelRouteDrafts((current) => ({ ...current, [saved.agent_name]: toModelConfigUpdate(saved) }));
      setModelRouteMessage(`${MODEL_ROUTE_AGENT_LABELS[saved.agent_name] ?? saved.agent_name} 已保存为 ${saved.model}`);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelRouteAgent: null }));
    }
  }

  async function handleApplyProfileToModelRoute(agentName: string, profileIdOverride?: number | null) {
    const selectedProfileId = profileIdOverride ?? modelRouteProfileSelections[agentName];
    const profile = modelProfiles.find((item) => item.id === Number(selectedProfileId));
    if (!profile) {
      setError("请先选择一个已保存的模型档案。");
      return;
    }
    const nextDraft = toModelConfigUpdate(profile);
    setBusy((current) => ({ ...current, modelRouteAgent: agentName }));
    setError(null);
    setModelRouteMessage(null);
    try {
      const saved = await api.updateModelRoute(agentName, nextDraft);
      setModelRoutes((current) => {
        const nextRoutes = current.filter((route) => route.agent_name !== saved.agent_name);
        return [...nextRoutes, saved].sort((left, right) => left.agent_name.localeCompare(right.agent_name));
      });
      setModelRouteDrafts((current) => ({ ...current, [saved.agent_name]: toModelConfigUpdate(saved) }));
      setModelRouteMessage(`${MODEL_ROUTE_AGENT_LABELS[saved.agent_name] ?? saved.agent_name} 已套用模型档案 ${profile.name}`);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, modelRouteAgent: null }));
    }
  }

  async function refreshAgentEvents() {
    try {
      const nextAgentEvents = await api.getAgentEvents();
      setAgentEvents(nextAgentEvents);
    } catch {
      // Keep the inferred frontend status available if the backend is still starting.
    }
  }

  async function handleToggleOrchestratorDetail(taskId: number) {
    if (orchestratorDetail?.id === taskId) {
      setOrchestratorDetail(null);
      return;
    }
    setError(null);
    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
      const response = await fetch(`${apiBaseUrl}/api/orchestrator/tasks/${taskId}`);
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(payload.detail || `读取任务详情失败 (${response.status})`);
      }
      setOrchestratorDetail((await response.json()) as OrchestratorTaskDetail);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadFile) {
      setError("请先选择一份简历文件。");
      return;
    }
    setBusy((current) => ({ ...current, upload: true }));
    setError(null);
    setFailedAgent(null);
    try {
      const nextResume = await api.uploadResume(uploadFile);
      setResume(nextResume);
      setManualResumeText(nextResume.raw_text);
      if (!searchFieldsTouched) {
        const suggestedKeywords = getProfileStringArray(nextResume.profile, "suggested_keywords");
        const suggestedCity = getProfileString(nextResume.profile, "suggested_city");
        if (suggestedKeywords.length) {
          setSearchKeywords(suggestedKeywords.join(", "));
        }
        if (suggestedCity) {
          setSearchCity(suggestedCity);
        }
      }
      await refreshOutcomeData();
    } catch (nextError) {
      setFailedAgent("JobSearchAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, upload: false }));
    }
  }

  async function handleManualResumeTextUpdate() {
    if (!resume?.id) {
      setError("请先上传简历，再补全文本。");
      return;
    }
    const rawText = manualResumeText.trim();
    if (!rawText) {
      setError("请先粘贴简历正文。");
      return;
    }
    setBusy((current) => ({ ...current, manualResumeText: true }));
    setError(null);
    setFailedAgent(null);
    try {
      const nextResume = await api.updateResumeManualText(resume.id, rawText);
      setResume(nextResume);
      setManualResumeText(nextResume.raw_text);
      if (!searchFieldsTouched) {
        const suggestedKeywords = getProfileStringArray(nextResume.profile, "suggested_keywords");
        const suggestedCity = getProfileString(nextResume.profile, "suggested_city");
        if (suggestedKeywords.length) {
          setSearchKeywords(suggestedKeywords.join(", "));
        }
        if (suggestedCity) {
          setSearchCity(suggestedCity);
        }
      }
    } catch (nextError) {
      setFailedAgent("ResumeParserAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, manualResumeText: false }));
    }
  }

  async function createSearchRunFromCurrentForm(nextSearchMode: SearchMode) {
    if (!resume?.id) {
      setError("请先上传简历，再创建搜索任务。");
      return;
    }
    if (!resumeReadingStatus.canGenerateMaterials) {
      setError("当前简历还没有可用正文，请先补全文本。");
      return;
    }
    const selectedPlatforms = getSelectedPlatforms(platforms);
    if (selectedPlatforms.length === 0) {
      setError("请至少选择一个搜索平台。");
      return;
    }

    setBusy((current) => ({ ...current, search: true }));
    setError(null);
    setFailedAgent(null);
    setLastRun(null);
    setJobs([]);
    setSelectedJobId(null);
    setDetailJobId(null);
    setTailorBundles({});
    setTailoredRevisionDrafts({});
    setTailoredRevisionMessages({});
    setTailorBlockedMessages({});
    setManualDetailDrafts({});
    setManualDetailNotes({});
    setApplyPreviews({});
    try {
      const run = await api.createSearchRun({
        resume_id: resume.id,
        keywords: searchKeywords
          .split(",")
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        city: searchCity.trim(),
        platforms: selectedPlatforms,
        search_mode: nextSearchMode
      });
      const nextJobs = filterJobsForActiveSearchRun(await api.listJobs(run.id), run.id);
      setLastRun(run);
      setJobs(nextJobs);
      setSelectedJobId(nextJobs[0]?.id ?? null);
      setSearchMode(nextSearchMode);
      await refreshOutcomeData();
    } catch (nextError) {
      setFailedAgent("ApplicationWriterAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, search: false }));
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createSearchRunFromCurrentForm(searchMode);
  }

  async function handleRefreshSessions() {
    setBusy((current) => ({ ...current, sessions: true }));
    setError(null);
    try {
      const response = await api.getPlatformSessions();
      setPlatformSessions(response.sessions);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, sessions: false }));
    }
  }

  async function handleLaunchCdpBrowser() {
    setBusy((current) => ({ ...current, launchCdp: true }));
    setError(null);
    setCdpLaunchMessage(null);
    try {
      const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
      const response = await fetch(`${apiBaseUrl}/api/browser/launch-cdp`, { method: "POST" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(payload.detail || `启动浏览器失败 (${response.status})`);
      }
      const payload = (await response.json()) as { message?: string };
      setCdpLaunchMessage(payload.message ?? "已启动 CDP 浏览器。");
      await handleRefreshSessions();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, launchCdp: false }));
    }
  }

  async function handleExtractPlatformJobs() {
    const selectedPlatforms = getSelectedPlatforms(platforms);
    if (selectedPlatforms.length === 0) {
      setError("请至少选择一个平台后再提取浏览器岗位。");
      return;
    }
    setBusy((current) => ({ ...current, extract: true }));
    setError(null);
    try {
      const response = await api.searchPlatformJobs({
        platforms: selectedPlatforms,
        keywords: searchKeywords
          .split(",")
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        city: searchCity.trim(),
        limit: 10
      });
      setPlatformExtractions(response.extractions);
      if (response.extractions.some((extraction) => extraction.status === "success" && extraction.jobs.length > 0)) {
        setSearchMode("browser_cdp");
      }
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, extract: false }));
    }
  }

  async function handleRefreshJobDetail(job: JobPosting) {
    setBusy((current) => ({ ...current, refreshDetailJobId: job.id }));
    setError(null);
    try {
      const updatedJob = await api.refreshJobDetail(job.id);
      setJobs((current) => current.map((item) => (item.id === updatedJob.id ? updatedJob : item)));
      setTailorBlockedMessages((current) => {
        const { [updatedJob.id]: _removed, ...rest } = current;
        return rest;
      });
      setDetailJobId(updatedJob.id);
      await refreshAgentEvents();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, refreshDetailJobId: null }));
    }
  }

  async function handleManualDetailUpdate(job: JobPosting) {
    const description = (manualDetailDrafts[job.id] ?? job.description).trim();
    if (!description) {
      setError("请先粘贴完整岗位要求/JD，再保存并重新匹配。");
      return;
    }
    setBusy((current) => ({ ...current, manualDetailJobId: job.id }));
    setError(null);
    try {
      const updatedJob = await api.updateJobManualDetail(job.id, {
        description,
        note: manualDetailNotes[job.id] ?? "前端详情弹窗人工补全 JD"
      });
      setJobs((current) => current.map((item) => (item.id === updatedJob.id ? updatedJob : item)));
      setManualDetailDrafts((current) => ({ ...current, [updatedJob.id]: updatedJob.description }));
      setManualDetailNotes((current) => ({ ...current, [updatedJob.id]: "" }));
      setTailorBlockedMessages((current) => {
        const { [updatedJob.id]: _removed, ...rest } = current;
        return rest;
      });
      setSelectedJobId(updatedJob.id);
      setDetailJobId(updatedJob.id);
      await refreshAgentEvents();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, manualDetailJobId: null }));
    }
  }

  async function handleImportExtractedJobs() {
    if (importableExtractionCount === 0) {
      setError("请先按关键词搜索并提取到真实岗位后再导入。");
      return;
    }
    await createSearchRunFromCurrentForm("browser_cdp");
  }

  async function handleTailor(job: JobPosting) {
    if (!resume?.id) {
      setError("请先上传简历，再生成定制材料。");
      return;
    }
    if (!resumeReadingStatus.canGenerateMaterials) {
      setError("当前简历还没有可用正文，请先补全文本。");
      return;
    }
    setBusy((current) => ({ ...current, tailorJobId: job.id }));
    setError(null);
    setPdfStatusMessage(null);
    setTailorBlockedMessages((current) => {
      const { [job.id]: _removed, ...rest } = current;
      return rest;
    });
    try {
      const bundle = await api.tailorJob(job.id, resume.id);
      setTailorBundles((current) => ({ ...current, [job.id]: bundle }));
      const editableText = getBundleEditableText(bundle);
      setTailoredRevisionDrafts((current) => ({ ...current, [bundle.id]: editableText }));
      setTailoredRevisionMessages((current) => ({ ...current, [bundle.id]: "已生成初始可编辑版本。" }));
      setSelectedJobId(job.id);
      await refreshOutcomeData();
    } catch (nextError) {
      const blockedMessage = getTailorBlockedMessage(nextError);
      if (blockedMessage) {
        setSelectedJobId(job.id);
        setTailorBlockedMessages((current) => ({ ...current, [job.id]: blockedMessage }));
        setError("该岗位详情还不完整，需先刷新或人工补全 JD。");
      } else {
        setError(toErrorMessage(nextError));
      }
    } finally {
      setBusy((current) => ({ ...current, tailorJobId: null }));
    }
  }

  async function handleSaveTailoredRevision(bundle: TailorBundle) {
    const draft = (tailoredRevisionDrafts[bundle.id] ?? getBundleEditableText(bundle)).trim();
    if (!draft) {
      setError("简历改写正文不能为空。");
      return;
    }
    setBusy((current) => ({ ...current, revisionTailoredResumeId: bundle.id }));
    setError(null);
    try {
      const saved = await api.updateTailoredResumeRevision(bundle.id, draft);
      const preview = await api.getTailoredResumePreview(bundle.id);
      setTailorBundles((current) => {
        const entry = Object.entries(current).find(([, item]) => item.id === bundle.id);
        if (!entry) {
          return current;
        }
        const [jobId, currentBundle] = entry;
        return {
          ...current,
          [Number(jobId)]: {
            ...currentBundle,
            resume_text: saved.editable_text,
            resume_rewrite: saved.editable_text,
            project_rewrite: saved.editable_text
          }
        };
      });
      setTailoredRevisionDrafts((current) => ({ ...current, [bundle.id]: preview.plain_text || saved.editable_text }));
      setTailoredRevisionMessages((current) => ({ ...current, [bundle.id]: "已保存，PDF 下载将使用这版简历。" }));
      setPdfStatusMessage("模板化 PDF：已保存最新编辑，下载将使用此版本。");
    } catch (nextError) {
      setError(toErrorMessage(nextError));
      setTailoredRevisionMessages((current) => ({ ...current, [bundle.id]: "保存失败，请检查后端服务。" }));
    } finally {
      setBusy((current) => ({ ...current, revisionTailoredResumeId: null }));
    }
  }

  async function handleDownloadTailoredPdf(bundle: TailorBundle) {
    const pdfStatus = getPdfTemplateStatus(resume, true, null);
    if (!pdfStatus.canDownload) {
      setPdfStatusMessage(pdfStatus.label);
      return;
    }
    setPdfStatusMessage("模板化 PDF：正在生成一页 PDF...");
    try {
      const response = await fetch(api.tailoredResumePdfUrl(bundle.id));
      if (!response.ok) {
        let detail = `PDF 生成失败 (${response.status})`;
        try {
          const payload = (await response.json()) as { detail?: string };
          detail = payload.detail || detail;
        } catch {
          detail = response.statusText || detail;
        }
        setPdfStatusMessage(getPdfDownloadFailureMessage(response.status, detail));
        return;
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `tailored-resume-${bundle.id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setPdfStatusMessage("模板化 PDF：已生成并开始下载。");
    } catch (err) {
      setPdfStatusMessage(`模板化 PDF：${err instanceof Error ? err.message : "下载失败"}`);
    }
  }

  async function handleApplyPreview(job: JobPosting) {
    setBusy((current) => ({ ...current, applyJobId: job.id }));
    setError(null);
    try {
      const preview = await api.previewPlatformApply(job.id);
      setSelectedJobId(job.id);
      setApplyPreviews((current) => ({ ...current, [job.id]: preview }));
      if (!preview.ready) {
        setError(`平台投递预检未通过：${preview.evidence || preview.status}`);
      }
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, applyJobId: null }));
    }
  }

  async function handleConfirmPlatformApply(job: JobPosting) {
    const preview = applyPreviews[job.id];
    if (!preview?.ready) {
      setError("请先检查平台投递入口，预检通过后再确认真实投递。");
      return;
    }
    setBusy((current) => ({ ...current, applyJobId: job.id }));
    setError(null);
    try {
      const note =
        applyNotes[job.id]?.trim() ||
        `平台预检通过后真实投递：${job.company} / ${job.title} / ${preview.button_text || preview.status}`;
      await api.applyToPlatform(job.id, note);
      setApplyPreviews((current) => {
        const { [job.id]: _removed, ...rest } = current;
        return rest;
      });
      await refreshOutcomeData();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, applyJobId: null }));
    }
  }

  async function handleStatusUpdate(application: ApplicationRecord) {
    const nextStatus = statusDrafts[application.id];
    if (!nextStatus || nextStatus === application.current_status) {
      setError("请选择一个新的投递状态。");
      return;
    }
    setBusy((current) => ({ ...current, updateApplicationId: application.id }));
    setError(null);
    try {
      await api.updateApplicationStatus(
        application.id,
        nextStatus,
        statusNotes[application.id]?.trim() || `状态更新为 ${STATUS_LABELS[nextStatus]}`
      );
      setStatusDrafts((current) => {
        const next = { ...current };
        delete next[application.id];
        return next;
      });
      await refreshOutcomeData();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, updateApplicationId: null }));
    }
  }

  async function handleSyncApplications() {
    const selectedPlatforms = getSelectedPlatforms(platforms);
    if (selectedPlatforms.length === 0) {
      setError("请至少选择一个平台后再同步投递状态。");
      return;
    }
    setBusy((current) => ({ ...current, syncApplications: true }));
    setError(null);
    try {
      const response = await api.syncApplications({ platforms: selectedPlatforms, limit: 50 });
      setSyncProposals(response.proposals);
      setSyncDiagnostics(response.diagnostics);
      setSyncMessage(response.message || `同步完成：${response.status}`);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, syncApplications: false }));
    }
  }

  async function handleConfirmSyncProposal(proposal: ApplicationSyncProposal) {
    setBusy((current) => ({ ...current, updateApplicationId: proposal.application_id }));
    setError(null);
    try {
      await api.updateApplicationStatus(
        proposal.application_id,
        proposal.suggested_status,
        proposal.note || `同步确认：更新为 ${STATUS_LABELS[proposal.suggested_status]}`
      );
      setSyncProposals((current) =>
        current.filter((item) => item.application_id !== proposal.application_id)
      );
      await refreshOutcomeData();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, updateApplicationId: null }));
    }
  }

  return (
    <main className="app-shell">
      <section className="control-strip">
        <div>
          <p className="eyebrow">agent-business / local operator console</p>
          <h1>求职投递多 Agent 工作台</h1>
        </div>
        <div className="strip-metrics" aria-label="工作台概览">
          <Metric label="岗位池" value={jobs.length.toString()} detail={searchMode === "demo" ? "demo 搜索结果" : "浏览器模式"} />
          <Metric label="投递记录" value={totalApplications.toString()} detail="人审后入库" />
          <Metric label="Token" value={usageCards.totalTokens} detail={usageCards.totalCost} />
        </div>
      </section>

      {error ? (
        <div className="alert" role="alert">
          <strong>操作未完成</strong>
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            关闭
          </button>
        </div>
      ) : null}

      <section className="workspace-grid">
        <div className="stack">
          <Panel title="简历上传" kicker="Resume Intake">
            <form className="upload-form" onSubmit={handleUpload}>
              <label className="file-drop">
                <input
                  type="file"
                  accept=".txt,.pdf,.doc,.docx,.png,.jpg,.jpeg"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
                <span>{uploadFile?.name ?? "选择简历文件"}</span>
                <small>支持 txt/pdf/docx/png/jpg，文件只提交给本地后端解析。</small>
              </label>
              <button className="primary" type="submit" disabled={busy.upload}>
                {busy.upload ? "上传中..." : "上传并解析"}
              </button>
            </form>
            {resume ? (
              <div className="resume-card">
                <b>{resume.filename}</b>
                <span>ID #{resume.id} · {formatDateTime(resume.created_at)}</span>
                <div className="resume-reading-status">
                  <span
                    className={`chip ${
                      resumeReadingStatus.tone === "success"
                        ? "positive"
                        : resumeReadingStatus.tone === "warning"
                        ? "warning"
                        : ""
                    }`}
                  >
                    {resumeReadingStatus.label}
                  </span>
                  <small>{resumeReadingStatus.detail}</small>
                  {resumeReadingStatus.actionHint ? <small>{resumeReadingStatus.actionHint}</small> : null}
                </div>
                {resume.raw_text ? (
                  <p>{resume.raw_text.slice(0, 96)}{resume.raw_text.length > 96 ? "..." : ""}</p>
                ) : null}
                {resumeReadingStatus.needsManualText ? (
                  <div className="manual-resume-editor">
                    <label>
                      <span>粘贴简历正文</span>
                      <textarea
                        rows={7}
                        value={manualResumeText}
                        onChange={(event) => setManualResumeText(event.target.value)}
                        placeholder="如果 PDF/图片无法自动读取，请把简历正文粘贴到这里。保存后会重新提取技能、推荐关键词和城市。"
                      />
                    </label>
                    <button type="button" onClick={() => void handleManualResumeTextUpdate()} disabled={busy.manualResumeText}>
                      {busy.manualResumeText ? "保存中..." : "保存简历正文"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState title="还没有简历" text="上传后才能创建搜索任务和生成定制材料。" />
            )}
          </Panel>

          <Panel title="模型 / API" kicker="LLM Agent">
            <div className="model-simple-card">
              <div>
                <span>当前主模型</span>
                <b>{modelConfig ? modelConfig.model : "未读取"}</b>
                <small>{modelConfig ? `${modelConfig.provider} · ${modelConfig.enabled && !modelConfig.estimation_only ? "真实调用" : "本地/估算"}` : "后端启动后会自动读取。"}</small>
              </div>
              <div>
                <span>API Key</span>
                <b>{keyStatusText(modelConfig)}</b>
                <small>{modelApiKey ? "将保存新的 Key" : "留空会沿用已保存 Key。"}</small>
              </div>
            </div>
            <form className="model-simple-form" onSubmit={handleSaveModelConfig}>
              <label>
                <span>已保存模型</span>
                <select value={selectedModelProfileId ?? ""} onChange={(event) => handleSelectModelProfile(event.target.value)}>
                  <option value="">新建 / 当前主模型</option>
                  {modelProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name} · {profile.model}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>档案名称</span>
                <input
                  value={modelProfileName}
                  onChange={(event) => setModelProfileName(event.target.value)}
                  placeholder="例如：DeepSeek v4 Pro"
                />
              </label>
              <label>
                <span>服务商</span>
                <select
                  value={modelDraft.provider}
                  onChange={(event) =>
                    setModelDraft((current) => ({
                      ...current,
                      provider: event.target.value,
                      enabled: event.target.value !== "local",
                      estimation_only: event.target.value === "local"
                    }))
                  }
                >
                  {MODEL_PROVIDER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>模型版本</span>
                <input
                  list="model-version-options"
                  value={modelDraft.model}
                  onChange={(event) => setModelDraft((current) => ({ ...current, model: event.target.value }))}
                  placeholder="deepseek-v4-pro"
                />
                <datalist id="model-version-options">
                  {MODEL_VERSION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </datalist>
              </label>
              <label>
                <span>API 地址</span>
                <input
                  value={modelDraft.base_url}
                  onChange={(event) => setModelDraft((current) => ({ ...current, base_url: event.target.value }))}
                  placeholder="https://api.deepseek.com"
                />
              </label>
              <label className="api-key-field">
                <span>模型 API Key</span>
                <div className="secret-input-row">
                  <input
                    type={showModelApiKey ? "text" : "password"}
                    value={modelApiKey}
                    onChange={(event) => setModelApiKey(event.target.value)}
                    placeholder={modelConfig?.api_key_configured ? "留空沿用已保存 Key" : "粘贴你的真实 API Key"}
                    autoComplete="off"
                  />
                  <button type="button" onClick={() => setShowModelApiKey((current) => !current)}>
                    {showModelApiKey ? "隐藏" : "显示"}
                  </button>
                </div>
              </label>
              <div className="model-simple-actions">
                <button type="button" onClick={handleNewModelProfile}>
                  新建档案
                </button>
                <button className="primary" type="submit">
                  保存为当前模型
                </button>
                <button type="button" onClick={() => void handleSaveModelProfile()} disabled={busy.modelProfileAction === "save"}>
                  {busy.modelProfileAction === "save" ? "保存中..." : "保存/更新档案"}
                </button>
                <button type="button" onClick={() => void handleApplyModelProfile()} disabled={selectedModelProfileId === null || busy.modelProfileAction === "apply"}>
                  {busy.modelProfileAction === "apply" ? "套用中..." : "套用档案"}
                </button>
                <button type="button" onClick={() => void handleDeleteModelProfile()} disabled={selectedModelProfileId === null || busy.modelProfileAction === "delete"}>
                  {busy.modelProfileAction === "delete" ? "删除中..." : "删除档案"}
                </button>
                <button type="button" onClick={() => void handleTestModelConnection()} disabled={busy.modelTest}>
                  {busy.modelTest ? "测试中..." : "测试连接"}
                </button>
              </div>
            </form>
            {modelTestResult ? (
              <div className={`model-test-result ${modelTestResult.status === "success" ? "success" : "failed"}`}>
                <b>{modelTestResult.status === "success" ? "连接成功" : "连接失败"}</b>
                <span>{modelTestResult.provider} / {modelTestResult.model} · {modelTestResult.duration_ms}ms</span>
                {modelTestResult.status !== "success" ? <small>{modelTestResult.error || "请检查 API 地址、模型名和 API Key。"}</small> : null}
              </div>
            ) : null}
            {modelMessage ? <small className="model-message">{modelMessage}</small> : null}
            <details className="advanced-model-routes">
              <summary>高级：不同 Agent 使用不同模型</summary>
              <div className="model-route-simple-list">
                {modelRoutes.map((route) => {
                  const selectedRouteProfileId = modelRouteProfileSelections[route.agent_name] ?? "";
                  return (
                    <div className="model-route-simple" key={route.agent_name}>
                      <div>
                        <b>{MODEL_ROUTE_AGENT_LABELS[route.agent_name] ?? route.agent_name}</b>
                        <small>当前：{route.model} · {keyStatusText(route)}</small>
                      </div>
                      <select
                        value={selectedRouteProfileId}
                        onChange={(event) =>
                          setModelRouteProfileSelections((current) => ({
                            ...current,
                            [route.agent_name]: event.target.value ? Number(event.target.value) : ""
                          }))
                        }
                      >
                        <option value="">选择模型档案</option>
                        {modelProfiles.map((profile) => (
                          <option key={profile.id} value={profile.id}>
                            {profile.name} · {profile.model}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void handleApplyProfileToModelRoute(route.agent_name)}
                        disabled={!selectedRouteProfileId || busy.modelRouteAgent === route.agent_name}
                      >
                        {busy.modelRouteAgent === route.agent_name ? "保存中..." : "套用到此 Agent"}
                      </button>
                    </div>
                  );
                })}
              </div>
              {modelRouteMessage ? <small>{modelRouteMessage}</small> : null}
            </details>
          </Panel>

          <Panel title="搜索任务" kicker="Search Run">
            <form className="search-form" onSubmit={handleSearch}>
              <label>
                <span>关键词</span>
                <input
                  value={searchKeywords}
                  onChange={(event) => {
                    setSearchFieldsTouched(true);
                    setSearchKeywords(event.target.value);
                  }}
                  placeholder="React 实习, Agent 实习"
                />
              </label>
              <label>
                <span>城市</span>
                <input
                  value={searchCity}
                  onChange={(event) => {
                    setSearchFieldsTouched(true);
                    setSearchCity(event.target.value);
                  }}
                  placeholder="上海"
                />
              </label>
              <label className="search-mode-field">
                <span>搜索模式</span>
                <select value={searchMode} onChange={(event) => setSearchMode(event.target.value as SearchMode)}>
                  <option value="demo">Demo 样例</option>
                  <option value="browser_cdp">浏览器 CDP</option>
                </select>
              </label>
              <div className="segmented">
                {(["boss", "shixiseng"] as const).map((platform) => (
                  <label key={platform}>
                    <input
                      type="checkbox"
                      checked={platforms[platform]}
                      onChange={(event) =>
                        setPlatforms((current) => ({
                          ...current,
                          [platform]: event.target.checked
                        }))
                      }
                    />
                    <span>{PLATFORM_LABELS[platform]}</span>
                  </label>
                ))}
              </div>
              <button className="primary" type="submit" disabled={busy.search || !resume || !resumeReadingStatus.canGenerateMaterials}>
                {busy.search ? "搜索中..." : "创建搜索任务"}
              </button>
            </form>
            <div className="source-banner">
              <b>{searchMode === "demo" ? "当前使用样例数据" : "当前使用本机浏览器只读模式"}</b>
              <span>
                {searchMode === "demo"
                  ? "适合测试流程，不代表真实招聘平台结果。"
                  : "需要先用 CDP 启动浏览器并打开 BOSS/实习僧页面。"}
              </span>
            </div>
            <div className="session-toolbar">
              <button type="button" onClick={() => void handleLaunchCdpBrowser()} disabled={busy.launchCdp}>
                {busy.launchCdp ? "启动中" : "启动 CDP 浏览器"}
              </button>
              <button type="button" onClick={() => void handleRefreshSessions()} disabled={busy.sessions}>
                {busy.sessions ? "刷新中" : "刷新会话"}
              </button>
              <button type="button" onClick={() => void handleExtractPlatformJobs()} disabled={busy.extract}>
                {busy.extract ? "搜索提取中" : "按关键词搜索并提取"}
              </button>
            </div>
            {cdpLaunchMessage ? <p className="run-line">{cdpLaunchMessage}</p> : null}
            <div className="platform-session-grid">
              {platformSessions.length ? (
                platformSessions.map((session) => (
                  <div className={`platform-session state-${session.state}`} key={session.platform}>
                    <b>{PLATFORM_LABELS[session.platform] ?? session.platform}</b>
                    <span>{platformSessionLabel(session.state)}</span>
                    <small>{session.detected_url ?? session.message}</small>
                  </div>
                ))
              ) : (
                <EmptyState title="未读取平台会话" text="刷新后会显示 BOSS/实习僧标签页探测结果。" />
              )}
            </div>
            {platformExtractions.length ? (
              <div className="extraction-list">
                {platformExtractions.map((extraction) => (
                  <div className="extraction-block" key={extraction.platform}>
                    <div className="extraction-heading">
                      <b>{PLATFORM_LABELS[extraction.platform] ?? extraction.platform}</b>
                      <span>{extraction.status} · {extraction.jobs.length} 条候选</span>
                    </div>
                    {extraction.error ? <small className="extract-error">{extraction.error}</small> : null}
                    <div className="diagnostic-panel">
                      <div className="diagnostic-grid">
                        <span>标签页：{extraction.diagnostics.tab_detected ? "已检测" : "未检测"}</span>
                        <span>WebSocket：{extraction.diagnostics.websocket_detected ? "已检测" : "未检测"}</span>
                        <span>候选卡片：{extraction.diagnostics.candidate_card_count}</span>
                        <span>成功提取：{extraction.diagnostics.extracted_job_count}</span>
                      </div>
                      {extraction.diagnostics.failure_reason ? (
                        <p>{extraction.diagnostics.failure_reason}</p>
                      ) : null}
                      {extraction.diagnostics.suggestion ? (
                        <small>{extraction.diagnostics.suggestion}</small>
                      ) : null}
                      {extraction.diagnostics.text_quality_warnings.length ||
                      formatSelectorCounts(extraction.diagnostics.matched_selector_counts).length ? (
                        <details className="diagnostic-details">
                          <summary>查看诊断详情</summary>
                          {extraction.diagnostics.text_quality_warnings.length ? (
                            <div className="selector-counts">
                              {extraction.diagnostics.text_quality_warnings.map((warning) => (
                                <span key={warning}>文本质量：{warning}</span>
                              ))}
                            </div>
                          ) : null}
                          <div className="selector-counts">
                            {formatSelectorCounts(extraction.diagnostics.matched_selector_counts).map((item) => (
                              <span key={item}>{item}</span>
                            ))}
                          </div>
                        </details>
                      ) : null}
                    </div>
                    {extraction.jobs.slice(0, 4).map((job) => (
                      <a className="candidate-row" href={job.url || extraction.source_url || "#"} target="_blank" rel="noreferrer" key={`${job.platform}-${job.title}-${job.company}`}>
                        <b>{job.title}</b>
                        <span>{job.company || "未知公司"} · {job.city || "未知城市"} · {job.salary || "薪资读取失败"}</span>
                      </a>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
            {importableExtractionCount > 0 ? (
              <button
                className="primary"
                type="button"
                disabled={busy.search || !resume}
                onClick={() => void handleImportExtractedJobs()}
              >
                {busy.search ? "导入中..." : `导入这批真实岗位到岗位池（${importableExtractionCount}）`}
              </button>
            ) : null}
            <div className="run-line">
              {lastRun ? (
                <>
                  <span className="status-dot" />
                  最近任务 #{lastRun.id} · {lastRun.status} · {lastRun.platforms.join(" / ")}
                </>
              ) : (
                "等待创建搜索任务"
              )}
            </div>
          </Panel>
        </div>

        <Panel title="进展看板" kicker="Pipeline" className="pipeline-panel">
          {busy.boot ? (
            <LoadingRows count={7} />
          ) : applications.length ? (
            <div className="pipeline-grid">
              {STATUS_COLUMNS.map((status) => {
                const count = applications.filter((item) => item.current_status === status).length;
                return (
                  <div className={`pipeline-card tone-${getStatusTone(status)}`} key={status}>
                    <span>{STATUS_LABELS[status]}</span>
                    <b>{count}</b>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState title="暂无投递进展" text="从岗位表生成材料并确认投递后，这里会出现漏斗状态。" />
          )}
        </Panel>

        <Panel title="成本看板" kicker="LLM Cost" className="cost-panel">
          <div className="cost-grid">
            <Metric label="总 Token" value={usageCards.totalTokens} detail="估算调用量" />
            <Metric label="总成本" value={usageCards.totalCost} detail="USD" />
            <Metric label="最高消耗 Agent" value={usageCards.topAgent} detail="按 token 排序" />
          </div>
          <div className="usage-list">
            {usage && Object.keys(usage.by_agent).length ? (
              Object.entries(usage.by_agent).map(([agent, bucket]) => (
                <div className="usage-row" key={agent}>
                  <span>{agent}</span>
                  <div className="usage-meter">
                    <i
                      style={{
                        width: `${clampPercent(
                          ((bucket.total_tokens ?? 0) / Math.max(usage.total_tokens, 1)) * 100
                        )}%`
                      }}
                    />
                  </div>
                  <b>{(bucket.total_tokens ?? 0).toLocaleString("en-US")}</b>
                </div>
              ))
            ) : (
              <EmptyState title="暂无模型成本" text="上传、搜索、生成材料后会记录各 Agent 估算用量。" />
            )}
          </div>
        </Panel>
      </section>

      <section className="agent-monitor">
        <Panel title="Agent 状态" kicker="Runtime Trace">
          <div className="agent-monitor-head">
            <span>当前运行：{runningAgent ?? "无"}</span>
            <b>当前任务总成本 {agentCost}</b>
            {orchestratorTaskId ? (
              <button type="button" onClick={() => void handleToggleOrchestratorDetail(orchestratorTaskId)}>
                {visibleOrchestratorDetail ? "收起步骤" : "查看步骤"}
              </button>
            ) : null}
          </div>
          {orchestratorSummary ? (
            <div className={`orchestrator-summary status-${orchestratorSummary.status}`}>
              <div>
                <span>最近编排任务</span>
                <b>{orchestratorSummary.taskName}</b>
              </div>
              <div>
                <span>状态</span>
                <b>{orchestratorSummary.status}</b>
              </div>
              <div>
                <span>步骤</span>
                <b>{orchestratorSummary.stepCount} steps</b>
              </div>
              <div>
                <span>最近步骤</span>
                <b>{orchestratorSummary.lastStep}</b>
              </div>
              {orchestratorSummary.errorMessage ? <em>错误：{orchestratorSummary.errorMessage}</em> : null}
            </div>
          ) : null}
          {visibleOrchestratorDetail ? (
            <div className="event-stack" aria-label="编排任务步骤详情">
              {visibleOrchestratorDetail.retry_suggestion ? (
                <span>
                  重试边界：
                  {visibleOrchestratorDetail.retry_suggestion.mode === "manual_only"
                    ? "可人工重试，禁止自动重试"
                    : "当前无需重试"}
                  {" · "}
                  {visibleOrchestratorDetail.retry_suggestion.next_action}
                  {" · "}
                  {visibleOrchestratorDetail.retry_suggestion.safety_boundary}
                </span>
              ) : null}
              {visibleOrchestratorDetail.steps.map((step) => (
                <span key={`${step.event_id}-${step.agent_name}-${step.status}`}>
                  {step.agent_name} · {step.status} · {step.step}
                  {step.error ? ` · 错误：${step.error}` : ""}
                </span>
              ))}
            </div>
          ) : null}
          <div className="agent-status-grid">
            {agentRows.map((row) => (
              <article className={`agent-status-card status-${row.status}`} key={row.agentName}>
                <header>
                  <b>{row.agentName}</b>
                  <span>{row.status}</span>
                </header>
                <p>{row.currentStep}</p>
                <small>输入：{row.inputSummary}</small>
                <small>输出：{row.outputSummary}</small>
                {row.errorMessage ? <em>错误：{row.errorMessage}</em> : null}
                <strong>{row.tokens.toLocaleString("en-US")} tokens</strong>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <section className="table-layout">
        <Panel title="岗位筛选表" kicker="Job Pool" className="jobs-panel">
          <div className="toolbar">
            <label>
              平台
              <select
                value={filters.platform}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, platform: event.target.value as Platform }))
                }
              >
                <option value="all">全部</option>
                <option value="boss">BOSS直聘</option>
                <option value="shixiseng">实习僧</option>
              </select>
            </label>
            <label>
              关键词
              <input
                value={filters.keyword}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, keyword: event.target.value }))
                }
                placeholder="公司 / 职位 / 技能"
              />
            </label>
            <label>
              最低匹配分 {filters.minScore}
              <input
                type="range"
                min="0"
                max="100"
                value={filters.minScore}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, minScore: Number(event.target.value) }))
                }
              />
            </label>
          </div>
          <div className="source-banner">
            <b>JobMatchAgent：{jobMatchModelSummary?.statusLabel ?? "等待评分"}</b>
            <span>
              {jobMatchModelSummary
                ? `${jobMatchModelSummary.modelLabel} · ${jobMatchModelSummary.usageLabel} · ${jobMatchModelSummary.detail}`
                : "创建搜索任务后会显示模型路由、规则兜底和 token 成本。"}
            </span>
          </div>

          {busy.boot || busy.search ? (
            <LoadingRows count={5} />
          ) : rankedJobs.length ? (
            <div className="data-table job-table">
              <div className="table-head">
                <span>岗位</span>
                <span>匹配</span>
                <span>证据</span>
                <span>动作</span>
              </div>
              {rankedJobs.map((job) => {
                const application = applicationsByJob.get(job.id);
                const applyPreview = applyPreviews[job.id];
                return (
                  <article
                    className={`table-row ${selectedJob?.id === job.id ? "is-selected" : ""}`}
                    key={job.id}
                    onClick={() => setSelectedJobId(job.id)}
                  >
                    <div>
                      <div className="job-title">
                        <b>{job.title}</b>
                        <span>{PLATFORM_LABELS[job.platform] ?? job.platform}</span>
                      </div>
                      <p>{job.company} · {job.city} · {job.salary}</p>
                      <small>{job.description}</small>
                    </div>
                    <div className="score-cell">
                      <b>{job.match.score}</b>
                      <div className="score-bar">
                        <i style={{ width: `${clampPercent(job.match.score)}%` }} />
                      </div>
                      <span>{RECOMMENDATION_LABELS[job.match.recommendation] ?? job.match.recommendation}</span>
                    </div>
                    <div className="reason-cloud">
                      {job.match.hit_reasons.slice(0, 4).map((reason) => (
                        <span className="chip positive" key={reason}>{reason}</span>
                      ))}
                      {job.match.gap_reasons.slice(0, 3).map((reason) => (
                        <span className="chip warning" key={reason}>{reason}</span>
                      ))}
                    </div>
                    <div className="row-actions">
                      <button type="button" onClick={(event) => { event.stopPropagation(); setDetailJobId(job.id); }}>
                        查看要求
                      </button>
                      <button type="button" onClick={(event) => { event.stopPropagation(); void handleTailor(job); }}>
                        {busy.tailorJobId === job.id ? "生成中" : tailorBundles[job.id] ? "重新生成" : "生成材料"}
                      </button>
                      <button
                        type="button"
                        disabled={Boolean(application) || busy.applyJobId === job.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void (applyPreview?.ready ? handleConfirmPlatformApply(job) : handleApplyPreview(job));
                        }}
                      >
                        {application
                          ? "平台已确认"
                          : busy.applyJobId === job.id
                            ? "平台检查中"
                            : applyPreview?.ready
                              ? "确认真实投递"
                              : "检查投递入口"}
                      </button>
                      {applyPreview ? (
                        <small className={applyPreview.ready ? "chip positive" : "chip warning"}>
                          {applyPreview.ready
                            ? `已找到平台入口：${applyPreview.button_text || applyPreview.status}`
                            : `预检未通过：${applyPreview.status}`}
                        </small>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState title="暂无岗位" text="上传简历并创建搜索任务后，岗位会在这里按匹配度排序。" />
          )}
        </Panel>

        <Panel title="人审材料" kicker="Tailor Review" className="review-panel">
          {selectedJob ? (
            <>
              <div className="review-heading">
                <div>
                  <b>{selectedJob.company}</b>
                  <span>{selectedJob.title}</span>
                </div>
                <a href={selectedJob.url} target="_blank" rel="noreferrer">
                  打开岗位
                </a>
              </div>
              {selectedBundle ? (
                <div className="review-content">
                  <div className={`truth-badge ${selectedBundle.truth_check_passed ? "pass" : "risk"}`}>
                    {selectedBundle.truth_check_passed ? "事实校验通过" : "需要复核事实风险"}
                  </div>
                  {selectedTailorModelSummary ? (
                    <section>
                      <h3>模型调用状态</h3>
                      <div className={`truth-badge ${selectedTailorModelSummary.tone === "success" ? "pass" : "risk"}`}>
                        {selectedTailorModelSummary.statusLabel}
                      </div>
                      <div className="split-list">
                        <div>
                          <b>模型</b>
                          <small>{selectedTailorModelSummary.providerModel}</small>
                        </div>
                        <div>
                          <b>路由</b>
                          <small>{selectedTailorModelSummary.routeLabel}</small>
                        </div>
                      </div>
                      <p>{selectedTailorModelSummary.detail}</p>
                      <small>{selectedTailorModelSummary.usageLabel}</small>
                      {selectedTailorModelSummary.setupHint ? (
                        <p className="chip warning">{selectedTailorModelSummary.setupHint}</p>
                      ) : null}
                      {selectedTailorModelSummary.errorLabel ? (
                        <p className="chip warning">{selectedTailorModelSummary.errorLabel}</p>
                      ) : null}
                    </section>
                  ) : null}
                  <div className="pdf-download-row">
                    <button
                      type="button"
                      disabled={!selectedPdfTemplateStatus.canDownload}
                      onClick={() => void handleDownloadTailoredPdf(selectedBundle)}
                    >
                      下载模板化一页 PDF
                    </button>
                    <div className="pdf-status-text">
                      <span
                        className={`chip ${
                          selectedPdfTemplateStatus.tone === "success"
                            ? "positive"
                            : selectedPdfTemplateStatus.tone === "warning"
                            ? "warning"
                            : ""
                        }`}
                      >
                        {selectedPdfTemplateStatus.label}
                      </span>
                      <small>{selectedPdfTemplateStatus.detail}</small>
                      {selectedPdfTemplateStatus.actionHint ? <small>{selectedPdfTemplateStatus.actionHint}</small> : null}
                    </div>
                  </div>
                  <section>
                    <h3>在线编辑 / 预览</h3>
                    <div className="source-banner">
                      <b>修改后的简历正文</b>
                      <span>可直接编辑并实时预览；保存后 PDF 下载会使用保存后的版本。</span>
                    </div>
                    <div className="search-form">
                      <div>
                        <label>
                          <span>简历改写正文</span>
                          <textarea
                            rows={10}
                            value={selectedRevisionDraft}
                            onChange={(event) =>
                              setTailoredRevisionDrafts((current) => ({
                                ...current,
                                [selectedBundle.id]: event.target.value
                              }))
                            }
                          />
                        </label>
                        <button
                          type="button"
                          disabled={busy.revisionTailoredResumeId === selectedBundle.id}
                          onClick={() => void handleSaveTailoredRevision(selectedBundle)}
                        >
                          {busy.revisionTailoredResumeId === selectedBundle.id ? "保存中..." : "保存编辑版本"}
                        </button>
                        {selectedRevisionMessage ? <small>{selectedRevisionMessage}</small> : null}
                      </div>
                      <div>
                        <b>实时预览</b>
                        <pre>{selectedPreviewText}</pre>
                      </div>
                    </div>
                  </section>
                  <section>
                    <h3>招呼语</h3>
                    <p className="greeting">{selectedBundle.greeting.message}</p>
                  </section>
                  <section className="split-list">
                    <div>
                      <h3>改写重点</h3>
                      {selectedBundle.diff_summary.length ? (
                        selectedBundle.diff_summary.map((item) => <span className="chip positive" key={item}>{item}</span>)
                      ) : (
                        <small>暂无改写摘要</small>
                      )}
                    </div>
                    <div>
                      <h3>风险提示</h3>
                      {selectedBundle.risk_flags.length || selectedBundle.greeting.risk_flags.length ? (
                        [...selectedBundle.risk_flags, ...selectedBundle.greeting.risk_flags].map((item) => (
                          <span className="chip warning" key={item}>{item}</span>
                        ))
                      ) : (
                        <small>未发现明显风险</small>
                      )}
                    </div>
                  </section>
                  <label className="note-field">
                    投递备注
                    <textarea
                      value={applyNotes[selectedJob.id] ?? ""}
                      onChange={(event) =>
                        setApplyNotes((current) => ({ ...current, [selectedJob.id]: event.target.value }))
                      }
                      placeholder="例如：已人工核对岗位 JD 和招呼语，BOSS 站内投递。"
                    />
                  </label>
                  <div className="detail-recovery">
                    <b>真实平台投递预检</b>
                    {selectedApplyPreview ? (
                      <>
                        <p>
                          {selectedApplyPreview.ready
                            ? `已在平台页找到入口：${selectedApplyPreview.button_text || selectedApplyPreview.status}`
                            : `暂未找到可确认入口：${selectedApplyPreview.evidence || selectedApplyPreview.status}`}
                        </p>
                        <small>{selectedApplyPreview.source_url || selectedJob.url}</small>
                      </>
                    ) : (
                      <p>先点击“检查投递入口”，系统会打开真实岗位页，只读确认是否存在投递/沟通按钮。</p>
                    )}
                  </div>
                  <button
                    className="primary"
                    type="button"
                    disabled={Boolean(applicationsByJob.get(selectedJob.id)) || busy.applyJobId === selectedJob.id}
                    onClick={() =>
                      void (selectedApplyPreview?.ready
                        ? handleConfirmPlatformApply(selectedJob)
                        : handleApplyPreview(selectedJob))
                    }
                  >
                    {applicationsByJob.get(selectedJob.id)
                      ? "平台已确认投递"
                      : busy.applyJobId === selectedJob.id
                        ? "平台检查中..."
                        : selectedApplyPreview?.ready
                          ? "确认真实平台投递"
                          : "检查投递入口"}
                  </button>
                </div>
              ) : selectedTailorBlockedMessage ? (
                <div className="detail-recovery">
                  <b>生成已暂停：需要先补全 JD</b>
                  <p>{selectedTailorBlockedMessage}</p>
                  <button type="button" onClick={() => setDetailJobId(selectedJob.id)}>
                    查看/补全岗位要求
                  </button>
                </div>
              ) : showTailorRetryAction ? (
                <div className="detail-recovery">
                  <b>岗位要求已补全，可以重新生成材料</b>
                  <p>将使用当前完整 JD 调用 ApplicationWriterAgent，生成简历改写要求和招呼语。</p>
                  <button
                    type="button"
                    disabled={busy.tailorJobId === selectedJob.id}
                    onClick={() => void handleTailor(selectedJob)}
                  >
                    {busy.tailorJobId === selectedJob.id ? "生成中..." : "重新生成材料"}
                  </button>
                </div>
              ) : (
                <EmptyState title="尚未生成材料" text="在岗位表中点击“生成材料”，这里会展示定制简历、招呼语和风险提示。" />
              )}
            </>
          ) : (
            <EmptyState title="未选中岗位" text="搜索后选择一个岗位进行材料生成和人审。" />
          )}
        </Panel>
      </section>

      <section className="analytics-layout">
        <Panel title="投递结果表" kicker="Applications">
          <div className="sync-console">
            <div>
              <b>投递状态只读同步</b>
              <span>从当前 CDP 浏览器页面读取已读/回复/面试等线索，只生成待确认建议。</span>
            </div>
            <button
              type="button"
              onClick={() => void handleSyncApplications()}
              disabled={busy.syncApplications || applications.length === 0}
            >
              {busy.syncApplications ? "同步中..." : "同步投递状态"}
            </button>
          </div>
          {syncMessage ? <p className="sync-message">{syncMessage}</p> : null}
          {syncDiagnostics.length ? (
            <div className="sync-diagnostics">
              {syncDiagnostics.map((diagnostic) => (
                <div className={`sync-diagnostic status-${diagnostic.status}`} key={diagnostic.platform}>
                  <b>{PLATFORM_LABELS[diagnostic.platform] ?? diagnostic.platform}</b>
                  <span>{diagnostic.status}</span>
                  <small>
                    标签页：{diagnostic.tab_detected ? "已检测" : "未检测"} / WebSocket：
                    {diagnostic.websocket_detected ? "已检测" : "未检测"} / 候选文本：
                    {diagnostic.candidate_item_count}
                  </small>
                  {diagnostic.failure_reason ? <em>{diagnostic.failure_reason}</em> : null}
                  {diagnostic.suggestion ? <small>{diagnostic.suggestion}</small> : null}
                  <div className="selector-counts">
                    {formatKeywordCounts(diagnostic.matched_status_keywords).map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {syncProposals.length ? (
            <div className="sync-proposals">
              <div className="sync-proposals-head">
                <b>待确认同步建议</b>
                <span>{syncProposals.length} 条建议，确认后才会写入投递记录。</span>
              </div>
              {syncProposals.map((proposal) => (
                <article className="sync-proposal-card" key={`${proposal.application_id}-${proposal.suggested_status}`}>
                  <div>
                    <b>{proposal.company}</b>
                    <p>{proposal.title} / {PLATFORM_LABELS[proposal.platform] ?? proposal.platform}</p>
                    <small>{proposal.evidence}</small>
                  </div>
                  <div className="sync-status-flow">
                    <span>{STATUS_LABELS[proposal.current_status] ?? proposal.current_status}</span>
                    <strong>→</strong>
                    <span>{STATUS_LABELS[proposal.suggested_status] ?? proposal.suggested_status}</span>
                    <small>检测到：{STATUS_LABELS[proposal.detected_status] ?? proposal.detected_status}</small>
                  </div>
                  <button
                    type="button"
                    disabled={busy.updateApplicationId === proposal.application_id}
                    onClick={() => void handleConfirmSyncProposal(proposal)}
                  >
                    {busy.updateApplicationId === proposal.application_id ? "确认中..." : "确认更新"}
                  </button>
                </article>
              ))}
            </div>
          ) : null}
          {busy.boot ? (
            <LoadingRows count={4} />
          ) : applications.length ? (
            <div className="data-table application-table">
              <div className="table-head">
                <span>记录</span>
                <span>状态</span>
                <span>下一步</span>
                <span>事件</span>
              </div>
              {applications.map((application) => {
                const nextStatuses = getAllowedNextStatuses(application.current_status);
                const platformConfirmation = summarizePlatformConfirmation(
                  application.platform_proof,
                  application.latest_note
                );
                return (
                  <article className="table-row" key={application.id}>
                    <div>
                      <b>{application.company}</b>
                      <p>{application.title} · {PLATFORM_LABELS[application.platform] ?? application.platform}</p>
                      <small>投递于 {formatDateTime(application.applied_at)}</small>
                    </div>
                    <div>
                      <span className={`status-pill tone-${getStatusTone(application.current_status)}`}>
                        {STATUS_LABELS[application.current_status] ?? application.current_status}
                      </span>
                      <div className="event-stack">
                        <span className={`chip ${platformConfirmation.confirmed ? "positive" : "warning"}`}>
                          {platformConfirmation.confirmed ? "平台已确认" : "缺少平台确认证据"}
                        </span>
                        {platformConfirmation.evidence ? <small>{platformConfirmation.evidence}</small> : null}
                        {platformConfirmation.buttonText ? <small>按钮：{platformConfirmation.buttonText}</small> : null}
                        {platformConfirmation.pageSummary ? <small>{platformConfirmation.pageSummary}</small> : null}
                        {platformConfirmation.confirmedAt ? (
                          <small>确认于 {formatDateTime(platformConfirmation.confirmedAt)}</small>
                        ) : null}
                        {platformConfirmation.sourceUrl ? (
                          <a href={platformConfirmation.sourceUrl} target="_blank" rel="noreferrer">
                            打开平台记录
                          </a>
                        ) : null}
                      </div>
                      <p>{platformConfirmation.note || "暂无备注"}</p>
                    </div>
                    <div className="status-editor">
                      <select
                        value={statusDrafts[application.id] ?? ""}
                        disabled={nextStatuses.length === 0}
                        onChange={(event) =>
                          setStatusDrafts((current) => ({
                            ...current,
                            [application.id]: event.target.value as ApplicationStatus
                          }))
                        }
                      >
                        <option value="">选择状态</option>
                        {nextStatuses.map((status) => (
                          <option value={status} key={status}>
                            {STATUS_LABELS[status]}
                          </option>
                        ))}
                      </select>
                      <input
                        value={statusNotes[application.id] ?? ""}
                        onChange={(event) =>
                          setStatusNotes((current) => ({
                            ...current,
                            [application.id]: event.target.value
                          }))
                        }
                        placeholder="状态备注"
                      />
                      <button
                        type="button"
                        disabled={nextStatuses.length === 0 || busy.updateApplicationId === application.id}
                        onClick={() => void handleStatusUpdate(application)}
                      >
                        {busy.updateApplicationId === application.id ? "更新中" : "更新"}
                      </button>
                    </div>
                    <div className="event-stack">
                      {application.events.slice(-3).map((event) => (
                        <span key={`${event.id}-${event.status}`}>
                          {STATUS_LABELS[event.status]} · {formatDateTime(event.occurred_at)}
                        </span>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState title="暂无投递结果" text="确认投递后会记录平台、职位、当前状态和状态事件。" />
          )}
        </Panel>

        <Panel title="转化统计" kicker="Read / Reply / Progress">
          <div className="rate-summary">
            <RateCard title="已读率" bucket={analytics?.totals} rateKey="read_rate" countKey="read" />
            <RateCard title="回复率" bucket={analytics?.totals} rateKey="reply_rate" countKey="replied" />
            <RateCard title="推进率" bucket={analytics?.totals} rateKey="progress_rate" countKey="progressed" />
          </div>
          <RateChart title="按小时段" buckets={analytics?.hourly ?? {}} />
          <RateChart title="按平台" buckets={analytics?.platform ?? {}} labelMap={PLATFORM_LABELS} />
        </Panel>
      </section>
      {detailJob ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setDetailJobId(null)}>
          <aside
            className="job-detail-modal"
            role="dialog"
            aria-modal="true"
            aria-label="岗位要求详情"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <span>{PLATFORM_LABELS[detailJob.platform] ?? detailJob.platform}</span>
                <h2>{detailJob.title}</h2>
                <p>{detailJob.company || "未知公司"} · {detailJob.city || "未知城市"} · {detailJob.salary || "薪资读取失败"}</p>
              </div>
              <button type="button" onClick={() => setDetailJobId(null)}>关闭</button>
            </div>
            <div className="job-detail-actions">
              <a href={detailJob.url} target="_blank" rel="noreferrer">打开原岗位</a>
              <button type="button" onClick={() => void handleRefreshSessions()} disabled={busy.sessions}>
                {busy.sessions ? "刷新中" : "刷新会话"}
              </button>
              <button type="button" onClick={() => void handleExtractPlatformJobs()} disabled={busy.extract}>
                {busy.extract ? "提取中" : "重新提取"}
              </button>
              <button
                type="button"
                onClick={() => void handleRefreshJobDetail(detailJob)}
                disabled={busy.refreshDetailJobId === detailJob.id}
              >
                {busy.refreshDetailJobId === detailJob.id ? "刷新详情中" : "刷新当前岗位详情"}
              </button>
            </div>
            <section>
              <h3>岗位要求 / JD</h3>
              {detailQuality && !detailQuality.isComplete ? (
                <div className="detail-recovery">
                  <b>详情未补全</b>
                  <p>{detailQuality.reason}</p>
                  <small>{detailQuality.actionHint}</small>
                </div>
              ) : null}
              <pre>{detailQuality?.displayDescription ?? "当前页面没有提取到完整岗位要求。"}</pre>
              <div className="manual-detail-editor">
                <label>
                  <span>人工补全 / 修正 JD</span>
                  <textarea
                    rows={8}
                    value={manualDetailDrafts[detailJob.id] ?? detailQuality?.displayDescription ?? detailJob.description}
                    onChange={(event) =>
                      setManualDetailDrafts((current) => ({ ...current, [detailJob.id]: event.target.value }))
                    }
                    placeholder="从 BOSS/实习僧岗位详情页复制完整岗位要求，保存后会重新计算匹配分。"
                  />
                </label>
                <label>
                  <span>补全备注</span>
                  <input
                    value={manualDetailNotes[detailJob.id] ?? ""}
                    onChange={(event) =>
                      setManualDetailNotes((current) => ({ ...current, [detailJob.id]: event.target.value }))
                    }
                    placeholder="例如：手动从原岗位复制完整 JD"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void handleManualDetailUpdate(detailJob)}
                  disabled={busy.manualDetailJobId === detailJob.id}
                >
                  {busy.manualDetailJobId === detailJob.id ? "重新匹配中" : "保存并重新匹配"}
                </button>
              </div>
            </section>
            <section className="split-list">
              <div>
                <h3>匹配原因</h3>
                {detailJob.match.hit_reasons.length ? (
                  detailJob.match.hit_reasons.map((reason) => <span className="chip positive" key={reason}>{reason}</span>)
                ) : (
                  <small>暂无命中原因</small>
                )}
              </div>
              <div>
                <h3>风险 / 缺口</h3>
                {detailJob.match.gap_reasons.length ? (
                  detailJob.match.gap_reasons.map((reason) => <span className="chip warning" key={reason}>{reason}</span>)
                ) : (
                  <small>暂无明显缺口</small>
                )}
              </div>
            </section>
          </aside>
        </div>
      ) : null}
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{value}</b>
      <small>{detail}</small>
    </div>
  );
}

function Panel({
  title,
  kicker,
  className = "",
  children
}: {
  title: string;
  kicker: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <div>
          <span>{kicker}</span>
          <h2>{title}</h2>
        </div>
      </header>
      {children}
    </section>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <b>{title}</b>
      <span>{text}</span>
    </div>
  );
}

function LoadingRows({ count }: { count: number }) {
  return (
    <div className="loading-stack" aria-label="加载中">
      {Array.from({ length: count }).map((_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function RateCard({
  title,
  bucket,
  rateKey,
  countKey
}: {
  title: string;
  bucket: AnalyticsBucket | undefined;
  rateKey: "read_rate" | "reply_rate" | "progress_rate";
  countKey: "read" | "replied" | "progressed";
}) {
  const percent = getRatePercent(bucket, rateKey);
  return (
    <div className="rate-card">
      <span>{title}</span>
      <b>{percent}%</b>
      <small>{bucket?.[countKey] ?? 0} / {bucket?.applications ?? 0}</small>
      <div className="mini-bar">
        <i style={{ width: `${clampPercent(percent)}%` }} />
      </div>
    </div>
  );
}

function RateChart({
  title,
  buckets,
  labelMap = {}
}: {
  title: string;
  buckets: Record<string, AnalyticsBucket>;
  labelMap?: Record<string, string>;
}) {
  const rows = Object.entries(buckets);
  return (
    <div className="rate-chart">
      <h3>{title}</h3>
      {rows.length ? (
        rows.map(([key, bucket]) => (
          <div className="rate-row" key={key}>
            <b>{labelMap[key] ?? key}</b>
            <RateTrack label="已读" value={getRatePercent(bucket, "read_rate")} />
            <RateTrack label="回复" value={getRatePercent(bucket, "reply_rate")} />
            <RateTrack label="推进" value={getRatePercent(bucket, "progress_rate")} />
          </div>
        ))
      ) : (
        <EmptyState title="暂无统计样本" text="投递状态推进后会展示分时段和分平台转化。" />
      )}
    </div>
  );
}

function RateTrack({ label, value }: { label: string; value: number }) {
  return (
    <span className="rate-track">
      <em>{label}</em>
      <i>
        <strong style={{ width: `${clampPercent(value)}%` }} />
      </i>
      <small>{value}%</small>
    </span>
  );
}

function getSelectedPlatforms(platforms: Record<"boss" | "shixiseng", boolean>): Platform[] {
  return Object.entries(platforms)
    .filter(([, enabled]) => enabled)
    .map(([platform]) => platform);
}

function platformSessionLabel(state: string): string {
  const labels: Record<string, string> = {
    tab_detected: "已检测到标签页",
    tab_not_found: "未打开平台页",
    not_configured: "未配置 CDP",
    cdp_unreachable: "CDP 不可达"
  };
  return labels[state] ?? state;
}

function formatSelectorCounts(counts: Record<string, number>): string[] {
  const rows = Object.entries(counts)
    .filter(([, count]) => count > 0)
    .sort(([, left], [, right]) => right - left)
    .map(([selector, count]) => `${selector}: ${count}`);
  return rows.length ? rows : ["未命中岗位卡片选择器"];
}

function formatKeywordCounts(counts: Record<string, number>): string[] {
  const rows = Object.entries(counts)
    .filter(([, count]) => count > 0)
    .sort(([, left], [, right]) => right - left)
    .map(([keyword, count]) => `${keyword}: ${count}`);
  return rows.length ? rows : ["未命中状态关键词"];
}

function getProfileStringArray(profile: Record<string, unknown>, key: string): string[] {
  const value = profile[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function getProfileString(profile: Record<string, unknown>, key: string): string {
  const value = profile[key];
  return typeof value === "string" ? value.trim() : "";
}

function getBundleEditableText(bundle: TailorBundle): string {
  return bundle.resume_rewrite || bundle.project_rewrite || bundle.resume_text || "";
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "未知错误，请检查后端服务是否已启动。";
}

export default App;
