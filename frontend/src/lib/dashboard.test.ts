import { describe, expect, it } from "vitest";

import {
  buildAgentStatusRows,
  buildAgentStatusRowsFromEvents,
  getJobDetailQuality,
  buildOrchestratorSummary,
  getAllowedNextStatuses,
  getRatePercent,
  getStatusTone,
  rankJobs,
  summarizeUsage
} from "./dashboard";
import type { AnalyticsBucket, JobPosting, LLMUsageSummary } from "../types";

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

describe("dashboard helpers", () => {
  it("ranks and filters jobs by platform, keyword, and minimum score", () => {
    const ranked = rankJobs(jobs, {
      platform: "boss",
      keyword: "react",
      minScore: 80
    });

    expect(ranked).toHaveLength(1);
    expect(ranked[0].company).toBe("星河智能科技");
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
});
