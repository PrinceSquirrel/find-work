import type {
  AgentModelRoutesResponse,
  AgentModelRoute,
  ApplicationAnalytics,
  ApplicationRecord,
  ApplicationSyncRequest,
  ApplicationSyncResponse,
  ApplicationStatus,
  BrowserJobExtractRequest,
  BrowserJobExtractResponse,
  BrowserJobSearchRequest,
  JobPosting,
  LLMUsageSummary,
  ManualJobDetailRequest,
  ModelConfig,
  ModelProfile,
  ModelProfilesResponse,
  ModelConfigTestResult,
  ModelConfigUpdate,
  PlatformApplyPreview,
  PlatformSessionsResponse,
  ResumeManualTextRequest,
  ResumeDraft,
  SearchRun,
  SearchRunRequest,
  TailoredResumePreview,
  TailoredResumeRevision,
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

function getTailorBlockedMessage(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }
  if (!error.message.includes("补全 JD")) {
    return null;
  }
  return error.message;
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

  if (response.status === 204) {
    return undefined as T;
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

  getLatestResume(): Promise<ResumeDraft | null> {
    return request<ResumeDraft | null>("/api/resumes/latest");
  },

  updateResumeManualText(resumeId: number, rawText: string): Promise<ResumeDraft> {
    const payload: ResumeManualTextRequest = { raw_text: rawText };
    return request<ResumeDraft>(`/api/resumes/${encodeURIComponent(resumeId)}/manual-text`, {
      method: "PATCH",
      body: JSON.stringify(payload)
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

  searchPlatformJobs(payload: BrowserJobSearchRequest): Promise<BrowserJobExtractResponse> {
    return request<BrowserJobExtractResponse>("/api/platform-jobs/search", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listJobs(searchRunId?: number): Promise<JobPosting[]> {
    const query = searchRunId ? `?search_run_id=${encodeURIComponent(searchRunId)}` : "";
    return request<JobPosting[]>(`/api/jobs${query}`);
  },

  refreshJobDetail(jobId: number): Promise<JobPosting> {
    return request<JobPosting>(`/api/jobs/${encodeURIComponent(jobId)}/refresh-detail`, {
      method: "POST"
    });
  },

  updateJobManualDetail(jobId: number, payload: ManualJobDetailRequest): Promise<JobPosting> {
    return request<JobPosting>(`/api/jobs/${encodeURIComponent(jobId)}/manual-detail`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  },

  tailorJob(jobId: number, resumeId: number): Promise<TailorBundle> {
    return request<TailorBundle>(`/api/jobs/${jobId}/tailor`, {
      method: "POST",
      body: JSON.stringify({ resume_id: resumeId })
    });
  },

  tailoredResumePdfUrl(tailoredResumeId: number): string {
    return `${API_BASE_URL}/api/tailored-resumes/${encodeURIComponent(tailoredResumeId)}/pdf`;
  },

  getTailoredResumeRevision(tailoredResumeId: number): Promise<TailoredResumeRevision> {
    return request<TailoredResumeRevision>(`/api/tailored-resumes/${encodeURIComponent(tailoredResumeId)}/revision`);
  },

  updateTailoredResumeRevision(tailoredResumeId: number, resumeRewrite: string): Promise<TailoredResumeRevision> {
    return request<TailoredResumeRevision>(`/api/tailored-resumes/${encodeURIComponent(tailoredResumeId)}/revision`, {
      method: "PATCH",
      body: JSON.stringify({ resume_rewrite: resumeRewrite })
    });
  },

  getTailoredResumePreview(tailoredResumeId: number): Promise<TailoredResumePreview> {
    return request<TailoredResumePreview>(`/api/tailored-resumes/${encodeURIComponent(tailoredResumeId)}/preview`);
  },

  createApplyRecord(jobId: number, note: string): Promise<ApplicationRecord> {
    return request<ApplicationRecord>(`/api/jobs/${jobId}/apply-record`, {
      method: "POST",
      body: JSON.stringify({ note })
    });
  },

  applyToPlatform(jobId: number, note: string): Promise<ApplicationRecord> {
    return request<ApplicationRecord>(`/api/jobs/${jobId}/platform-apply`, {
      method: "POST",
      body: JSON.stringify({ note })
    });
  },

  previewPlatformApply(jobId: number): Promise<PlatformApplyPreview> {
    return request<PlatformApplyPreview>(`/api/jobs/${jobId}/platform-apply-preview`, {
      method: "POST"
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

  getModelConfig(): Promise<ModelConfig> {
    return request<ModelConfig>("/api/model-config");
  },

  updateModelConfig(payload: ModelConfigUpdate): Promise<ModelConfig> {
    return request<ModelConfig>("/api/model-config", {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  getModelProfiles(): Promise<ModelProfilesResponse> {
    return request<ModelProfilesResponse>("/api/model-profiles");
  },

  createModelProfile(name: string, payload: ModelConfigUpdate): Promise<ModelProfile> {
    return request<ModelProfile>("/api/model-profiles", {
      method: "POST",
      body: JSON.stringify({ name, ...payload })
    });
  },

  updateModelProfile(profileId: number, name: string, payload: ModelConfigUpdate): Promise<ModelProfile> {
    return request<ModelProfile>(`/api/model-profiles/${encodeURIComponent(profileId)}`, {
      method: "PUT",
      body: JSON.stringify({ name, ...payload })
    });
  },

  deleteModelProfile(profileId: number): Promise<void> {
    return request<void>(`/api/model-profiles/${encodeURIComponent(profileId)}`, {
      method: "DELETE"
    });
  },

  applyModelProfile(profileId: number): Promise<ModelConfig> {
    return request<ModelConfig>(`/api/model-profiles/${encodeURIComponent(profileId)}/apply`, {
      method: "POST"
    });
  },

  testModelConfigConnection(): Promise<ModelConfigTestResult> {
    return request<ModelConfigTestResult>("/api/model-config/test", {
      method: "POST"
    });
  },

  getModelRoutes(): Promise<AgentModelRoutesResponse> {
    return request<AgentModelRoutesResponse>("/api/model-routes");
  },

  updateModelRoute(agentName: string, payload: ModelConfigUpdate): Promise<AgentModelRoute> {
    return request<AgentModelRoute>(`/api/model-routes/${encodeURIComponent(agentName)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  getAgentEvents(): Promise<BackendAgentEventsSnapshot> {
    return request<BackendAgentEventsSnapshot>("/api/agent-events");
  }
};

export { ApiError, getTailorBlockedMessage };
