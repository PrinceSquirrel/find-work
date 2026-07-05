import { describe, expect, it } from "vitest";

import {
  buildAgentStatusRows,
  buildAgentStatusRowsFromEvents,
  buildJobMatchModelSummary,
  buildModelRouteApplyOptions,
  buildTailorModelSummary,
  getResumeReadingStatus,
  getPdfDownloadFailureMessage,
  getPdfTemplateStatus,
  extractPlatformConfirmation,
  filterModelProfiles,
  filterJobsForActiveSearchRun,
  getJobDetailQuality,
  shouldShowTailorRetryAction,
  summarizeSystemHealthOperation,
  summarizeSystemHealth,
  buildOrchestratorSummary,
  getAllowedNextStatuses,
  getRatePercent,
  getStatusTone,
  rankJobs,
  summarizePlatformConfirmation,
  summarizeUsage
} from "./dashboard";
import type {
  AgentModelRoute,
  AnalyticsBucket,
  JobPosting,
  LLMUsageSummary,
  ModelProfile,
  SystemHealthResponse
} from "../types";

const jobs: JobPosting[] = [
  {
    id: 1,
    search_run_id: 10,
    platform: "boss",
    company: "星河智能科技",
    title: "React Agent 前端实习生",
    city: "上海",
    salary: "200-300/天",
    description: "负责 React 工作台、数据看板、Agent 协同体验。",
    url: "https://example.test/1",
    job_type: "frontend",
    created_at: "2026-06-29T09:00:00Z",
    match: {
      job_id: 1,
      score: 92,
      hit_reasons: ["React", "Agent"],
      gap_reasons: [],
      recommendation: "strong_apply"
    }
  },
  {
    id: 2,
    search_run_id: 10,
    platform: "shixiseng",
    company: "启明数据实验室",
    title: "数据分析实习生",
    city: "杭州",
    salary: "180-260/天",
    description: "SQL 报表与数据分析。",
    url: "https://example.test/2",
    job_type: "data",
    created_at: "2026-06-29T10:00:00Z",
    match: {
      job_id: 2,
      score: 71,
      hit_reasons: ["SQL"],
      gap_reasons: ["React"],
      recommendation: "review"
    }
  }
];

const modelProfiles: ModelProfile[] = [
  {
    id: 1,
    name: "DeepSeek v4 Pro",
    provider: "openai-compatible",
    model: "deepseek-v4-pro",
    base_url: "https://api.deepseek.com",
    api_key_env_var: "DEEPSEEK_API_KEY",
    api_key_configured: true,
    enabled: true,
    estimation_only: false,
    timeout_ms: 90000,
    input_price_per_million: 1,
    output_price_per_million: 2,
    created_at: "2026-07-05T00:00:00Z"
  },
  {
    id: 2,
    name: "Local Rule",
    provider: "local",
    model: "local-rule",
    base_url: "local",
    api_key_env_var: "",
    api_key_configured: false,
    enabled: false,
    estimation_only: true,
    timeout_ms: 1000,
    input_price_per_million: 0,
    output_price_per_million: 0,
    created_at: "2026-07-05T00:00:00Z"
  }
];

const modelRoutes: AgentModelRoute[] = [
  {
    agent_name: "ApplicationWriterAgent",
    provider: "local",
    model: "local-rule",
    base_url: "local",
    api_key_env_var: "",
    api_key_configured: false,
    enabled: false,
    estimation_only: true,
    timeout_ms: 1000,
    input_price_per_million: 0,
    output_price_per_million: 0
  },
  {
    agent_name: "JobMatchAgent",
    provider: "openai-compatible",
    model: "deepseek-v4-flash",
    base_url: "https://api.deepseek.com",
    api_key_env_var: "DEEPSEEK_API_KEY",
    api_key_configured: true,
    enabled: true,
    estimation_only: false,
    timeout_ms: 45000,
    input_price_per_million: 0.5,
    output_price_per_million: 1
  }
];

describe("dashboard helpers", () => {
  it("summarizes system health into clear status cards and the next action", () => {
    const health: SystemHealthResponse = {
      status: "yellow",
      generated_at: "2026-07-06T12:00:00Z",
      checks: [
        {
          id: "backend",
          label: "Backend",
          status: "green",
          summary: "API is running",
          detail: "FastAPI responded",
          next_action: "",
          metadata: {}
        },
        {
          id: "model",
          label: "Model",
          status: "red",
          summary: "No API key",
          detail: "Saved model key is missing",
          next_action: "Save a model key",
          metadata: {}
        },
        {
          id: "ocr",
          label: "OCR",
          status: "yellow",
          summary: "OCR is unavailable",
          detail: "Manual text is still supported",
          next_action: "Install OCR if needed",
          metadata: {}
        }
      ]
    };

    const summary = summarizeSystemHealth(health, "Model connection failed");

    expect(summary.overallLabel).toBe("需要处理");
    expect(summary.tone).toBe("warning");
    expect(summary.primaryCheck?.id).toBe("model");
    expect(summary.nextActionLabel).toBe("Save a model key");
    expect(summary.recentError).toBe("Model connection failed");
    expect(summary.cards).toEqual([
      expect.objectContaining({ id: "backend", tone: "success", statusLabel: "正常" }),
      expect.objectContaining({ id: "model", tone: "danger", statusLabel: "异常" }),
      expect.objectContaining({ id: "ocr", tone: "warning", statusLabel: "需处理" })
    ]);
  });

  it("summarizes system health control operations into a compact result line", () => {
    expect(summarizeSystemHealthOperation(null)).toBeNull();
    expect(
      summarizeSystemHealthOperation({
        actionLabel: "测试模型",
        status: "running",
        detail: "正在连接 DeepSeek"
      })
    ).toEqual({
      label: "测试模型进行中",
      tone: "info",
      detail: "正在连接 DeepSeek"
    });
    expect(
      summarizeSystemHealthOperation({
        actionLabel: "启动 CDP",
        status: "success",
        detail: "浏览器已启动，状态已刷新"
      })
    ).toEqual({
      label: "启动 CDP完成",
      tone: "success",
      detail: "浏览器已启动，状态已刷新"
    });
    expect(
      summarizeSystemHealthOperation({
        actionLabel: "刷新平台会话",
        status: "failed",
        detail: "CDP 未连接"
      })
    ).toEqual({
      label: "刷新平台会话失败",
      tone: "danger",
      detail: "CDP 未连接"
    });
  });

  it("ranks and filters jobs by platform, keyword, and minimum score", () => {
    const ranked = rankJobs(jobs, {
      platform: "boss",
      keyword: "react",
      minScore: 80
    });

    expect(ranked).toHaveLength(1);
    expect(ranked[0].company).toBe("星河智能科技");
  });

  it("keeps the job pool empty until a current search run is selected", () => {
    expect(filterJobsForActiveSearchRun(jobs, null)).toEqual([]);
    expect(filterJobsForActiveSearchRun(jobs, 10)).toHaveLength(2);
    expect(filterJobsForActiveSearchRun(jobs, 99)).toEqual([]);
  });

  it("filters model profiles by name, provider, model, API URL, and key env var", () => {
    expect(filterModelProfiles(modelProfiles, "")).toHaveLength(2);
    expect(filterModelProfiles(modelProfiles, "deepseek")).toEqual([modelProfiles[0]]);
    expect(filterModelProfiles(modelProfiles, "LOCAL")).toEqual([modelProfiles[1]]);
    expect(filterModelProfiles(modelProfiles, "api.deepseek")).toEqual([modelProfiles[0]]);
    expect(filterModelProfiles(modelProfiles, "DEEPSEEK_API_KEY")).toEqual([modelProfiles[0]]);
    expect(filterModelProfiles(modelProfiles, "missing")).toEqual([]);
  });

  it("builds model route apply options for the selected profile", () => {
    const options = buildModelRouteApplyOptions(modelRoutes, modelProfiles[0], {
      ApplicationWriterAgent: "简历/招呼语生成",
      JobMatchAgent: "岗位匹配评分"
    });

    expect(options).toEqual([
      {
        agentName: "ApplicationWriterAgent",
        label: "简历/招呼语生成",
        currentModel: "local-rule",
        targetModel: "deepseek-v4-pro",
        keyStatus: "Key 已配置",
        canApply: true
      },
      {
        agentName: "JobMatchAgent",
        label: "岗位匹配评分",
        currentModel: "deepseek-v4-flash",
        targetModel: "deepseek-v4-pro",
        keyStatus: "Key 已配置",
        canApply: true
      }
    ]);

    expect(buildModelRouteApplyOptions(modelRoutes, null, {})).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          agentName: "ApplicationWriterAgent",
          targetModel: "未选择模型档案",
          canApply: false
        })
      ])
    );
  });

  it("formats rates from backend analytics buckets as display percentages", () => {
    const bucket: AnalyticsBucket = {
      applications: 8,
      read: 6,
      replied: 3,
      progressed: 2,
      read_rate: 0.75,
      reply_rate: 0.375,
      progress_rate: 0.25
    };

    expect(getRatePercent(bucket, "read_rate")).toBe(75);
    expect(getRatePercent(bucket, "reply_rate")).toBe(37.5);
    expect(getRatePercent(bucket, "progress_rate")).toBe(25);
  });

  it("keeps application status changes inside backend transition boundaries", () => {
    expect(getAllowedNextStatuses("applied")).toEqual(["read", "rejected", "closed"]);
    expect(getAllowedNextStatuses("read")).toEqual(["replied", "rejected", "closed"]);
    expect(getAllowedNextStatuses("closed")).toEqual([]);
  });

  it("maps statuses to stable visual tones", () => {
    expect(getStatusTone("applied")).toBe("info");
    expect(getStatusTone("interview")).toBe("success");
    expect(getStatusTone("rejected")).toBe("danger");
  });

  it("summarizes LLM usage into compact dashboard metrics", () => {
    const usage: LLMUsageSummary = {
      total_prompt_tokens: 1200,
      total_completion_tokens: 800,
      total_tokens: 2000,
      total_cost_usd: 0.0142,
      by_agent: {
        JobMatchAgent: {
          prompt_tokens: 500,
          completion_tokens: 100,
          total_tokens: 600,
          cost_usd: 0.004,
          calls: 2
        },
        ResumeTailorAgent: {
          prompt_tokens: 700,
          completion_tokens: 700,
          total_tokens: 1400,
          cost_usd: 0.0102,
          calls: 1
        }
      }
    };

    expect(summarizeUsage(usage)).toEqual({
      totalTokens: "2,000",
      totalCost: "$0.0142",
      topAgent: "ResumeTailorAgent"
    });
  });

  it("builds visible agent status rows from runtime snapshot and usage", () => {
    const rows = buildAgentStatusRows({
      runningAgent: "ApplicationWriterAgent",
      failedAgent: null,
      errorMessage: null,
      resumeName: "resume.pdf",
      searchSummary: "上海 / React 实习",
      selectedJobTitle: "React Agent 前端实习生",
      jobCount: 2,
      tailoredCount: 0,
      usageByAgent: {
        ResumeParserAgent: { total_tokens: 100, calls: 1 },
        ApplicationWriterAgent: { total_tokens: 350, calls: 1 }
      }
    });

    expect(rows).toHaveLength(5);
    expect(rows.find((row) => row.agentName === "ResumeParserAgent")?.status).toBe("success");
    expect(rows.find((row) => row.agentName === "ApplicationWriterAgent")?.status).toBe("running");
    expect(rows.find((row) => row.agentName === "ApplicationWriterAgent")?.tokens).toBe(350);
  });

  it("builds agent status rows from backend event snapshots", () => {
    const rows = buildAgentStatusRowsFromEvents({
      current_running_agent: null,
      total_cost_usd: 0.0024,
      agents: [
        {
          id: 1,
          agent_name: "ResumeParserAgent",
          status: "success",
          step: "parse resume",
          input_summary: "resume.pdf",
          output_summary: "resume_id=1",
          error: "",
          total_tokens: 120,
          cost_usd: 0,
          created_at: "2026-06-30T10:00:00Z"
        },
        {
          id: 2,
          agent_name: "ApplicationWriterAgent",
          status: "failed",
          step: "generate application materials",
          input_summary: "job_id=8",
          output_summary: "fallback used: upstream timeout",
          error: "",
          total_tokens: 0,
          cost_usd: 0,
          created_at: "2026-06-30T10:01:00Z"
        }
      ],
      events: []
    });

    expect(rows).toHaveLength(5);
    expect(rows.find((row) => row.agentName === "ResumeParserAgent")?.currentStep).toBe("parse resume");
    expect(rows.find((row) => row.agentName === "ResumeParserAgent")?.tokens).toBe(120);
    expect(rows.find((row) => row.agentName === "ApplicationWriterAgent")?.status).toBe("failed");
    expect(rows.find((row) => row.agentName === "ApplicationWriterAgent")?.errorMessage).toBe(
      "fallback used: upstream timeout"
    );
    expect(rows.find((row) => row.agentName === "ReviewAgent")?.status).toBe("pending");
  });

  it("summarizes backend orchestrator tasks for the runtime panel", () => {
    const summary = buildOrchestratorSummary({
      current_running_agent: null,
      total_cost_usd: 0.0024,
      agents: [],
      events: [],
      orchestrator: {
        current_task_id: null,
        last_task: {
          id: 3,
          task_name: "application.materials",
          input_summary: "resume_id=1; job_id=8",
          status: "success",
          error: "",
          started_at: "2026-06-30T10:00:00Z",
          completed_at: "2026-06-30T10:01:00Z",
          steps: [
            {
              event_id: 7,
              agent_name: "ApplicationWriterAgent",
              status: "running",
              step: "generate application materials",
              input_summary: "job_id=8",
              output_summary: "",
              error: "",
              total_tokens: 0,
              cost_usd: 0
            },
            {
              event_id: 8,
              agent_name: "ReviewAgent",
              status: "success",
              step: "review generated materials",
              input_summary: "job_id=8",
              output_summary: "truth_check_passed=True",
              error: "",
              total_tokens: 0,
              cost_usd: 0
            }
          ]
        },
        tasks: []
      }
    });

    expect(summary).toEqual({
      taskName: "application.materials",
      status: "success",
      stepCount: 2,
      currentTaskId: null,
      lastStep: "ReviewAgent / review generated materials",
      errorMessage: "",
      detail: "application.materials / success / 2 steps"
    });
  });

  it("marks empty or card-only job detail as incomplete with manual recovery guidance", () => {
    const emptyQuality = getJobDetailQuality({ ...jobs[0], description: "" });
    const cardOnlyQuality = getJobDetailQuality({
      ...jobs[0],
      description: "AI Agent优化工程师实习 - 元/天 4天/周 硕士 上海"
    });
    const completeQuality = getJobDetailQuality({
      ...jobs[0],
      description: "职位描述：负责 Agent 工具链评测、提示词优化和数据分析。任职要求：熟悉 Python、SQL、React，了解大模型调用和实验记录。"
    });

    expect(emptyQuality.isComplete).toBe(false);
    expect(emptyQuality.reason).toContain("没有提取到岗位要求");
    expect(cardOnlyQuality.isComplete).toBe(false);
    expect(cardOnlyQuality.reason).toContain("只读取到列表卡片");
    expect(cardOnlyQuality.actionHint).toContain("刷新会话");
    expect(completeQuality.isComplete).toBe(true);
  });

  it("uses backend structured detail reason before frontend text heuristics", () => {
    const quality = getJobDetailQuality({
      ...jobs[0],
      description: "职位描述：负责 Agent 工具链评测、提示词优化。",
      detail_status: "detail_blocked",
      detail_reason: "详情页请求失败：HTTP 403。"
    });

    expect(quality.isComplete).toBe(false);
    expect(quality.reason).toBe("详情页请求失败：HTTP 403。");
  });

  it("shows tailor retry action only after JD is complete and generation is not blocked", () => {
    expect(
      shouldShowTailorRetryAction({
        job: { ...jobs[0], detail_status: "manual_filled" },
        hasBundle: false,
        blockedMessage: ""
      })
    ).toBe(true);

    expect(
      shouldShowTailorRetryAction({
        job: { ...jobs[0], detail_status: "detail_fetched" },
        hasBundle: false,
        blockedMessage: ""
      })
    ).toBe(true);

    expect(
      shouldShowTailorRetryAction({
        job: { ...jobs[0], detail_status: "card_only" },
        hasBundle: false,
        blockedMessage: ""
      })
    ).toBe(false);

    expect(
      shouldShowTailorRetryAction({
        job: { ...jobs[0], detail_status: "manual_filled" },
        hasBundle: true,
        blockedMessage: ""
      })
    ).toBe(false);

    expect(
      shouldShowTailorRetryAction({
        job: { ...jobs[0], detail_status: "manual_filled" },
        hasBundle: false,
        blockedMessage: "该岗位 JD 过短，需要先补全。"
      })
    ).toBe(false);
  });

  it("summarizes material generation model route and usage", () => {
    const externalSummary = buildTailorModelSummary(
      {
        review: {
          llm: {
            status: "success",
            provider: "openai-compatible",
            model: "deepseek-chat",
            prompt_tokens: 120,
            completion_tokens: 60,
            total_tokens: 180,
            cost_usd: 0.00024,
            duration_ms: 88,
            usage_status: "success",
            route: { mode: "external" },
            review_route: { mode: "local_rule" }
          }
        }
      },
      {
        total_prompt_tokens: 120,
        total_completion_tokens: 60,
        total_tokens: 180,
        total_cost_usd: 0.0003,
        by_agent: {
          ApplicationWriterAgent: {
            total_tokens: 180,
            total_cost_usd: 0.0003,
            success_calls: 1
          }
        }
      }
    );

    expect(externalSummary.statusLabel).toBe("DeepSeek/API 已调用");
    expect(externalSummary.providerModel).toBe("openai-compatible / deepseek-chat");
    expect(externalSummary.routeLabel).toContain("ApplicationWriterAgent: external");
    expect(externalSummary.routeLabel).toContain("ReviewAgent: local_rule");
    expect(externalSummary.usageLabel).toBe("本次 180 tokens / $0.0002 / 88ms");
    expect(externalSummary.setupHint).toBe("");
    expect(externalSummary.tone).toBe("success");

    const localSummary = buildTailorModelSummary(
      {
        review: {
          llm: {
            status: "local",
            provider: "local",
            model: "local-rule",
            reason: "API key is not configured",
            route: { mode: "local_rule" }
          }
        }
      },
      null
    );

    expect(localSummary.statusLabel).toBe("未接入模型，当前本地规则生成");
    expect(localSummary.detail).toContain("API key is not configured");
    expect(localSummary.setupHint).toContain("这不是 DeepSeek/AI 模型输出");
    expect(localSummary.setupHint).toContain("模型 / API");
    expect(localSummary.setupHint).toContain("API Key");
    expect(localSummary.tone).toBe("muted");

    const fallbackSummary = buildTailorModelSummary(
      {
        review: {
          llm: {
            status: "fallback",
            provider: "openai-compatible",
            model: "deepseek-chat",
            error: "upstream timeout",
            route: { mode: "external" }
          }
        }
      },
      null
    );

    expect(fallbackSummary.statusLabel).toBe("模型调用失败，当前本地回退");
    expect(fallbackSummary.errorLabel).toContain("upstream timeout");
    expect(fallbackSummary.setupHint).toContain("检查 API Key");
    expect(fallbackSummary.tone).toBe("warning");
  });

  it("summarizes PDF template readiness for DOCX, PDF, and old resume data", () => {
    const docxStatus = getPdfTemplateStatus(
      { file_type: "docx", template_available: true },
      true,
      null
    );
    const pdfStatus = getPdfTemplateStatus(
      { file_type: "pdf", template_available: false },
      true,
      null
    );
    const oldDocxStatus = getPdfTemplateStatus(
      { file_type: "docx", template_available: false },
      true,
      null
    );
    const noBundleStatus = getPdfTemplateStatus(
      { file_type: "docx", template_available: true },
      false,
      null
    );

    expect(docxStatus.canDownload).toBe(true);
    expect(docxStatus.label).toContain("可下载");
    expect(docxStatus.tone).toBe("success");
    expect(pdfStatus.canDownload).toBe(false);
    expect(pdfStatus.label).toContain("PDF 简历可生成材料");
    expect(pdfStatus.actionHint).toContain("DOCX");
    expect(pdfStatus.tone).toBe("warning");
    expect(oldDocxStatus.canDownload).toBe(false);
    expect(oldDocxStatus.label).toContain("重新上传 DOCX");
    expect(noBundleStatus.canDownload).toBe(false);
    expect(noBundleStatus.label).toContain("尚未生成材料");
  });

  it("summarizes resume reading status for text, scanned PDF, image, and manual text", () => {
    const readable = getResumeReadingStatus({
      file_type: "pdf",
      raw_text: "技能: Python",
      profile: {
        extraction: {
          source_type: "pdf_text",
          status: "success",
          text_length: 10,
          manual_text_required: false
        }
      }
    });
    const scanned = getResumeReadingStatus({
      file_type: "pdf",
      raw_text: "",
      profile: {
        extraction: {
          source_type: "pdf_scan",
          status: "needs_ocr",
          manual_text_required: true,
          message: "PDF looks like a scanned/image PDF; OCR or manual text is required."
        }
      }
    });
    const image = getResumeReadingStatus({
      file_type: "png",
      raw_text: "",
      profile: {
        image_reading: {
          source_type: "image_png",
          status: "manual_required",
          manual_text_required: true
        }
      }
    });
    const manual = getResumeReadingStatus({
      file_type: "png",
      raw_text: "技能: Python",
      profile: {
        extraction: {
          source_type: "manual",
          status: "success",
          manual_text_required: false
        }
      }
    });

    expect(readable.label).toBe("读取状态：已提取文本");
    expect(readable.canGenerateMaterials).toBe(true);
    expect(scanned.label).toBe("读取状态：需要 OCR 或手动补全");
    expect(scanned.needsManualText).toBe(true);
    expect(image.label).toBe("读取状态：图片简历需要补全文本");
    expect(image.actionHint).toContain("粘贴简历正文");
    expect(manual.label).toBe("读取状态：已手动补全");
    expect(manual.tone).toBe("success");
  });

  it("maps PDF download failures to actionable frontend messages", () => {
    expect(getPdfDownloadFailureMessage(503, "missing converter")).toContain("缺少转换器");
    expect(getPdfDownloadFailureMessage(500, "PDF render validation failed: renderer unavailable")).toContain("渲染器不可用");
    expect(getPdfDownloadFailureMessage(409, "请重新上传 DOCX 简历以保留模板")).toContain("重新上传 DOCX");
    expect(getPdfDownloadFailureMessage(500, "invalid PDF output")).toContain("invalid PDF output");
  });

  it("summarizes job match model route from backend agent events", () => {
    const summary = buildJobMatchModelSummary({
      current_running_agent: null,
      total_cost_usd: 0.0024,
      agents: [
        {
          id: 9,
          agent_name: "JobMatchAgent",
          status: "success",
          step: "score matched jobs",
          input_summary: "resume_id=1; jobs=3",
          output_summary: "matches=3; route=deepseek-v4-flash; usage_status=success",
          error: "",
          total_tokens: 150,
          cost_usd: 0.00004,
          created_at: "2026-07-03T10:00:00Z"
        }
      ],
      events: []
    });

    expect(summary).not.toBeNull();
    expect(summary?.statusLabel).toBe("匹配分由模型评分");
    expect(summary?.modelLabel).toBe("deepseek-v4-flash");
    expect(summary?.usageLabel).toBe("150 tokens / $0.0000");
    expect(summary?.detail).toContain("matches=3");
    expect(summary?.tone).toBe("success");
  });

  it("extracts platform confirmation evidence from application notes", () => {
    const summary = extractPlatformConfirmation(
      "已人工核对岗位 JD；平台确认：clicked platform button: 立即沟通；平台链接：https://www.zhipin.com/job_detail/abc.html"
    );

    expect(summary.confirmed).toBe(true);
    expect(summary.evidence).toBe("clicked platform button: 立即沟通");
    expect(summary.sourceUrl).toBe("https://www.zhipin.com/job_detail/abc.html");
    expect(summary.note).toBe("已人工核对岗位 JD");
  });

  it("does not mark ordinary application notes as platform-confirmed", () => {
    const summary = extractPlatformConfirmation("用户手动备注：等待 HR 回复");

    expect(summary.confirmed).toBe(false);
    expect(summary.evidence).toBe("");
    expect(summary.sourceUrl).toBe("");
    expect(summary.note).toBe("用户手动备注：等待 HR 回复");
  });

  it("prefers structured platform proof over legacy note parsing", () => {
    const summary = summarizePlatformConfirmation(
      {
        platform: "boss",
        source_url: "https://www.zhipin.com/job_detail/live.html",
        action: "clicked_apply",
        status: "applied",
        evidence: "clicked platform button: 立即沟通",
        button_text: "立即沟通",
        confirmed_at: "2026-07-04T13:30:00+08:00",
        page_summary: "平台页面显示已沟通"
      },
      "用户备注；平台确认：old evidence；平台链接：https://old.example/job"
    );

    expect(summary.confirmed).toBe(true);
    expect(summary.evidence).toBe("clicked platform button: 立即沟通");
    expect(summary.sourceUrl).toBe("https://www.zhipin.com/job_detail/live.html");
    expect(summary.buttonText).toBe("立即沟通");
    expect(summary.status).toBe("applied");
    expect(summary.confirmedAt).toBe("2026-07-04T13:30:00+08:00");
    expect(summary.pageSummary).toBe("平台页面显示已沟通");
    expect(summary.note).toBe("用户备注");
  });
});
