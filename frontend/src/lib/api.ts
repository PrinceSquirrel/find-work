import type {
  ApplicationAnalytics,
  ApplicationRecord,
  ApplicationSyncRequest,
  ApplicationSyncResponse,
  ApplicationStatus,
  BrowserJobExtractRequest,
  BrowserJobExtractResponse,
  JobPosting,
  LLMUsageSummary,
  PlatformSessionsResponse,
  ResumeDraft,
  SearchRun,
  SearchRunRequest,
  TailorBundle
} from "../types";
import type { BackendAgentEventsSnapshot } from "./dashboard";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    }
  });

  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail || message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  uploadResume(file: File): Promise<ResumeDraft> {
    const formData = new FormData();
    formData.append("file", file);
    return request<ResumeDraft>("/api/resumes", {
      method: "POST",
      body: formData
    });
  },

  createSearchRun(payload: SearchRunRequest): Promise<SearchRun> {
    return request<SearchRun>("/api/search-runs", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  getPlatformSessions(): Promise<PlatformSessionsResponse> {
    return request<PlatformSessionsResponse>("/api/platform-sessions");
  },

  extractPlatformJobs(payload: BrowserJobExtractRequest): Promise<BrowserJobExtractResponse> {
    return request<BrowserJobExtractResponse>("/api/platform-jobs/extract", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listJobs(): Promise<JobPosting[]> {
    return request<JobPosting[]>("/api/jobs");
  },

  tailorJob(jobId: number, resumeId: number): Promise<TailorBundle> {
    return request<TailorBundle>(`/api/jobs/${jobId}/tailor`, {
      method: "POST",
      body: JSON.stringify({ resume_id: resumeId })
    });
  },

  createApplyRecord(jobId: number, note: string): Promise<ApplicationRecord> {
    return request<ApplicationRecord>(`/api/jobs/${jobId}/apply-record`, {
      method: "POST",
      body: JSON.stringify({ note })
    });
  },

  listApplications(): Promise<ApplicationRecord[]> {
    return request<ApplicationRecord[]>("/api/applications");
  },

  updateApplicationStatus(
    applicationId: number,
    status: ApplicationStatus,
    note: string
  ): Promise<ApplicationRecord> {
    return request<ApplicationRecord>(`/api/applications/${applicationId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, note })
    });
  },

  syncApplications(payload: ApplicationSyncRequest): Promise<ApplicationSyncResponse> {
    return request<ApplicationSyncResponse>("/api/applications/sync", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  getApplicationAnalytics(): Promise<ApplicationAnalytics> {
    return request<ApplicationAnalytics>("/api/analytics/applications");
  },

  getLlmUsage(): Promise<LLMUsageSummary> {
    return request<LLMUsageSummary>("/api/metrics/llm-usage");
  },

  getAgentEvents(): Promise<BackendAgentEventsSnapshot> {
    return request<BackendAgentEventsSnapshot>("/api/agent-events");
  }
};

export { ApiError };
