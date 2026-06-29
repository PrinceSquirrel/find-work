import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "./lib/api";
import {
  buildAgentStatusRows,
  clampPercent,
  formatDateTime,
  getAllowedNextStatuses,
  getRatePercent,
  getStatusTone,
  rankJobs,
  summarizeUsage
} from "./lib/dashboard";
import type {
  AnalyticsBucket,
  ApplicationAnalytics,
  ApplicationRecord,
  ApplicationSyncDiagnostic,
  ApplicationSyncProposal,
  ApplicationStatus,
  JobFilters,
  JobPosting,
  LLMUsageSummary,
  Platform,
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
  updateApplicationId: null
};

type SearchMode = "demo" | "browser_cdp";

function App() {
  const [resume, setResume] = useState<ResumeDraft | null>(null);
  const [jobs, setJobs] = useState<JobPosting[]>([]);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [analytics, setAnalytics] = useState<ApplicationAnalytics | null>(null);
  const [usage, setUsage] = useState<LLMUsageSummary | null>(null);
  const [tailorBundles, setTailorBundles] = useState<Record<number, TailorBundle>>({});
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [lastRun, setLastRun] = useState<SearchRun | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>("demo");
  const [platformSessions, setPlatformSessions] = useState<PlatformSession[]>([]);
  const [platformExtractions, setPlatformExtractions] = useState<PlatformJobExtraction[]>([]);
  const [syncProposals, setSyncProposals] = useState<ApplicationSyncProposal[]>([]);
  const [syncDiagnostics, setSyncDiagnostics] = useState<ApplicationSyncDiagnostic[]>([]);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [cdpLaunchMessage, setCdpLaunchMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failedAgent, setFailedAgent] = useState<ReturnType<typeof buildAgentStatusRows>[number]["agentName"] | null>(null);
  const [busy, setBusy] = useState<BusyState>(initialBusy);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [searchKeywords, setSearchKeywords] = useState("React 实习, Agent 实习");
  const [searchCity, setSearchCity] = useState("上海");
  const [platforms, setPlatforms] = useState<Record<"boss" | "shixiseng", boolean>>({
    boss: true,
    shixiseng: true
  });
  const [filters, setFilters] = useState<JobFilters>({
    platform: "all",
    keyword: "",
    minScore: 0
  });
  const [applyNotes, setApplyNotes] = useState<Record<number, string>>({});
  const [statusDrafts, setStatusDrafts] = useState<Record<number, ApplicationStatus>>({});
  const [statusNotes, setStatusNotes] = useState<Record<number, string>>({});

  useEffect(() => {
    void refreshWorkspace();
  }, []);

  const rankedJobs = useMemo(() => rankJobs(jobs, filters), [filters, jobs]);
  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? rankedJobs[0] ?? null,
    [jobs, rankedJobs, selectedJobId]
  );
  const selectedBundle = selectedJob ? tailorBundles[selectedJob.id] : undefined;
  const applicationsByJob = useMemo(() => {
    return new Map(applications.map((application) => [application.job_id, application]));
  }, [applications]);
  const usageCards = useMemo(() => summarizeUsage(usage), [usage]);
  const totalApplications = analytics?.totals.applications ?? applications.length;
  const runningAgent = useMemo(() => {
    if (busy.upload) return "ResumeParserAgent";
    if (busy.search) return "JobSearchAgent";
    if (busy.tailorJobId !== null) return "ApplicationWriterAgent";
    return null;
  }, [busy.upload, busy.search, busy.tailorJobId]);
  const agentRows = useMemo(
    () =>
      buildAgentStatusRows({
        runningAgent,
        failedAgent,
        errorMessage: error,
        resumeName: resume?.filename ?? null,
        searchSummary: `${searchCity || "未选城市"} / ${searchKeywords || "未填关键词"}`,
        selectedJobTitle: selectedJob?.title ?? null,
        jobCount: jobs.length,
        tailoredCount: Object.keys(tailorBundles).length,
        usageByAgent: usage?.by_agent ?? {}
      }),
    [error, failedAgent, jobs.length, resume?.filename, runningAgent, searchCity, searchKeywords, selectedJob?.title, tailorBundles, usage]
  );

  async function refreshWorkspace() {
    setBusy((current) => ({ ...current, boot: true }));
    setError(null);
    setFailedAgent(null);
    try {
      const [nextJobs, nextApplications, nextAnalytics, nextUsage, nextSessions] = await Promise.all([
        api.listJobs(),
        api.listApplications(),
        api.getApplicationAnalytics(),
        api.getLlmUsage(),
        api.getPlatformSessions()
      ]);
      setJobs(nextJobs);
      setApplications(nextApplications);
      setAnalytics(nextAnalytics);
      setUsage(nextUsage);
      setPlatformSessions(nextSessions.sessions);
    } catch (nextError) {
      setFailedAgent("ResumeParserAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, boot: false }));
    }
  }

  async function refreshOutcomeData() {
    const [nextApplications, nextAnalytics, nextUsage] = await Promise.all([
      api.listApplications(),
      api.getApplicationAnalytics(),
      api.getLlmUsage()
    ]);
    setApplications(nextApplications);
    setAnalytics(nextAnalytics);
    setUsage(nextUsage);
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
      await refreshOutcomeData();
    } catch (nextError) {
      setFailedAgent("JobSearchAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, upload: false }));
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resume?.id) {
      setError("请先上传简历，再创建搜索任务。");
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
    try {
      const run = await api.createSearchRun({
        resume_id: resume.id,
        keywords: searchKeywords
          .split(",")
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        city: searchCity.trim(),
        platforms: selectedPlatforms,
        search_mode: searchMode
      });
      const nextJobs = await api.listJobs();
      setLastRun(run);
      setJobs(nextJobs);
      setSelectedJobId(nextJobs[0]?.id ?? null);
      await refreshOutcomeData();
    } catch (nextError) {
      setFailedAgent("ApplicationWriterAgent");
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, search: false }));
    }
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
      const response = await api.extractPlatformJobs({ platforms: selectedPlatforms, limit: 10 });
      setPlatformExtractions(response.extractions);
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, extract: false }));
    }
  }

  async function handleTailor(job: JobPosting) {
    if (!resume?.id) {
      setError("请先上传简历，再生成定制材料。");
      return;
    }
    setBusy((current) => ({ ...current, tailorJobId: job.id }));
    setError(null);
    try {
      const bundle = await api.tailorJob(job.id, resume.id);
      setTailorBundles((current) => ({ ...current, [job.id]: bundle }));
      setSelectedJobId(job.id);
      await refreshOutcomeData();
    } catch (nextError) {
      setError(toErrorMessage(nextError));
    } finally {
      setBusy((current) => ({ ...current, tailorJobId: null }));
    }
  }

  async function handleApply(job: JobPosting) {
    setBusy((current) => ({ ...current, applyJobId: job.id }));
    setError(null);
    try {
      const note =
        applyNotes[job.id]?.trim() ||
        `人工确认后投递：${job.company} / ${job.title}`;
      await api.createApplyRecord(job.id, note);
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
                  accept=".txt,.pdf,.doc,.docx"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
                <span>{uploadFile?.name ?? "选择简历文件"}</span>
                <small>支持 txt/pdf/docx，文件只提交给本地后端解析。</small>
              </label>
              <button className="primary" type="submit" disabled={busy.upload}>
                {busy.upload ? "上传中..." : "上传并解析"}
              </button>
            </form>
            {resume ? (
              <div className="resume-card">
                <b>{resume.filename}</b>
                <span>ID #{resume.id} · {formatDateTime(resume.created_at)}</span>
                <p>{resume.raw_text.slice(0, 96)}{resume.raw_text.length > 96 ? "..." : ""}</p>
              </div>
            ) : (
              <EmptyState title="还没有简历" text="上传后才能创建搜索任务和生成定制材料。" />
            )}
          </Panel>

          <Panel title="搜索任务" kicker="Search Run">
            <form className="search-form" onSubmit={handleSearch}>
              <label>
                <span>关键词</span>
                <input
                  value={searchKeywords}
                  onChange={(event) => setSearchKeywords(event.target.value)}
                  placeholder="React 实习, Agent 实习"
                />
              </label>
              <label>
                <span>城市</span>
                <input
                  value={searchCity}
                  onChange={(event) => setSearchCity(event.target.value)}
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
              <button className="primary" type="submit" disabled={busy.search || !resume}>
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
                {busy.extract ? "提取中" : "只读提取岗位"}
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
                      <div className="selector-counts">
                        {formatSelectorCounts(extraction.diagnostics.matched_selector_counts).map((item) => (
                          <span key={item}>{item}</span>
                        ))}
                      </div>
                    </div>
                    {extraction.jobs.slice(0, 4).map((job) => (
                      <a className="candidate-row" href={job.url || extraction.source_url || "#"} target="_blank" rel="noreferrer" key={`${job.platform}-${job.title}-${job.company}`}>
                        <b>{job.title}</b>
                        <span>{job.company || "未知公司"} · {job.city || "未知城市"} · {job.salary || "薪资未展示"}</span>
                      </a>
                    ))}
                  </div>
                ))}
              </div>
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
            <b>当前任务总成本 {usageCards.totalCost}</b>
          </div>
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
                      <button type="button" onClick={(event) => { event.stopPropagation(); void handleTailor(job); }}>
                        {busy.tailorJobId === job.id ? "生成中" : tailorBundles[job.id] ? "重新生成" : "生成材料"}
                      </button>
                      <button
                        type="button"
                        disabled={Boolean(application) || busy.applyJobId === job.id}
                        onClick={(event) => { event.stopPropagation(); void handleApply(job); }}
                      >
                        {application ? "已记录" : busy.applyJobId === job.id ? "记录中" : "记录投递"}
                      </button>
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
                  <section>
                    <h3>定制简历摘要</h3>
                    <pre>{selectedBundle.resume_text}</pre>
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
                  <button
                    className="primary"
                    type="button"
                    disabled={Boolean(applicationsByJob.get(selectedJob.id)) || busy.applyJobId === selectedJob.id}
                    onClick={() => void handleApply(selectedJob)}
                  >
                    {applicationsByJob.get(selectedJob.id)
                      ? "已记录投递"
                      : busy.applyJobId === selectedJob.id
                        ? "记录中..."
                        : "确认后记录投递"}
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
                      <p>{application.latest_note || "暂无备注"}</p>
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

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "未知错误，请检查后端服务是否已启动。";
}

export default App;
