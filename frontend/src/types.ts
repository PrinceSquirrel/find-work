export type Platform = "boss" | "shixiseng" | string;

export type ApplicationStatus =
  | "discovered"
  | "matched"
  | "generated"
  | "applied"
  | "read"
  | "replied"
  | "interview"
  | "assessment"
  | "rejected"
  | "closed";

export type Recommendation = "strong_apply" | "review" | "skip" | string;

export interface ResumeDraft {
  id: number;
  filename: string;
  raw_text: string;
  profile: Record<string, unknown>;
  file_type: string;
  template_available: boolean;
  created_at: string;
}

export interface ResumeManualTextRequest {
  raw_text: string;
}

export interface JobMatch {
  job_id: number | null;
  score: number;
  hit_reasons: string[];
  gap_reasons: string[];
  recommendation: Recommendation;
}

export interface JobPosting {
  id: number;
  search_run_id: number | null;
  platform: Platform;
  company: string;
  title: string;
  city: string;
  salary: string;
  description: string;
  url: string;
  job_type: string;
  detail_status?: string;
  detail_reason?: string;
  created_at: string;
  match: JobMatch;
}

export interface PlatformApplyPreview {
  job: JobPosting;
  platform: Platform;
  ready: boolean;
  status: string;
  action: string;
  button_text: string;
  evidence: string;
  source_url: string;
}

export interface SearchRun {
  id: number;
  resume_id: number;
  keywords: string[];
  city: string;
  platforms: Platform[];
  status: "pending" | "running" | "completed" | string;
  created_at: string;
}

export interface SearchRunRequest {
  resume_id: number;
  keywords: string[];
  city: string;
  platforms: Platform[];
  search_mode?: "demo" | "browser_cdp";
}

export interface TailoredResume {
  id: number;
  job_id: number;
  resume_id: number;
  resume_text: string;
  resume_rewrite: string;
  project_rewrite: string;
  diff_summary: string[];
  risk_flags: string[];
  truth_check_passed: boolean;
  created_at: string;
}

export interface GreetingMessage {
  id: number | null;
  job_id: number;
  message: string;
  tone: string;
  risk_flags: string[];
  created_at: string;
}

export interface TailorBundle extends TailoredResume {
  greeting: GreetingMessage;
  review: Record<string, unknown>;
}

export interface TailoredResumeRevision {
  id: number;
  job_id: number;
  resume_id: number;
  editable_text: string;
  resume_rewrite: string;
  project_rewrite: string;
  resume_text: string;
  created_at: string;
}

export interface TailoredResumePreview {
  id: number;
  plain_text: string;
  html: string;
}

export interface ApplicationEvent {
  id: number | null;
  application_id: number | null;
  status: ApplicationStatus;
  occurred_at: string;
  note: string;
}

export interface ApplicationPlatformProof {
  platform: string;
  source_url: string;
  action: string;
  status: string;
  evidence: string;
  button_text: string;
  confirmed_at: string | null;
  page_summary: string;
}

export interface ApplicationRecord {
  id: number;
  job_id: number;
  company: string;
  title: string;
  platform: Platform;
  applied_at: string;
  current_status: ApplicationStatus;
  read_at: string | null;
  replied_at: string | null;
  progress_stage: string;
  latest_note: string;
  platform_proof: ApplicationPlatformProof;
  events: ApplicationEvent[];
}

export interface AnalyticsBucket {
  applications: number;
  read: number;
  replied: number;
  progressed: number;
  read_rate: number;
  reply_rate: number;
  progress_rate: number;
}

export interface ApplicationAnalytics {
  totals: AnalyticsBucket;
  hourly: Record<string, AnalyticsBucket>;
  weekday: Record<string, AnalyticsBucket>;
  platform: Record<string, AnalyticsBucket>;
}

export interface LLMUsageAgentBucket {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  calls?: number;
  [key: string]: number | undefined;
}

export interface LLMUsageSummary {
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_agent: Record<string, LLMUsageAgentBucket>;
}

export interface ModelConfig {
  provider: string;
  model: string;
  base_url: string;
  api_key_env_var: string;
  api_key_secret_id?: string;
  api_key_masked?: string;
  api_key_configured: boolean;
  enabled: boolean;
  estimation_only: boolean;
  timeout_ms: number;
  input_price_per_million: number;
  output_price_per_million: number;
}

export interface ModelConfigUpdate {
  provider: string;
  model: string;
  base_url: string;
  api_key_env_var: string;
  api_key?: string;
  enabled: boolean;
  estimation_only: boolean;
  timeout_ms: number;
  input_price_per_million: number;
  output_price_per_million: number;
}

export interface ModelProfile extends ModelConfig {
  id: number;
  name: string;
  created_at: string;
}

export interface ModelProfilesResponse {
  profiles: ModelProfile[];
}

export interface ModelConfigTestResult {
  status: "success" | "failed" | string;
  provider: string;
  model: string;
  duration_ms: number;
  api_key_configured: boolean;
  message?: string;
  error?: string;
}

export interface SystemHealthCheck {
  id: string;
  label: string;
  status: "green" | "yellow" | "red" | string;
  summary: string;
  detail: string;
  next_action: string;
  metadata: Record<string, unknown>;
}

export interface SystemHealthResponse {
  status: "green" | "yellow" | "red" | string;
  generated_at: string;
  checks: SystemHealthCheck[];
}

export interface AgentModelRoute extends ModelConfig {
  agent_name: string;
}

export interface AgentModelRoutesResponse {
  routes: AgentModelRoute[];
}

export interface PlatformSession {
  platform: Platform;
  expected_hosts: string[];
  state: string;
  detected_url: string | null;
  authenticated: boolean | null;
  message: string;
}

export interface PlatformSessionsResponse {
  cdp_url: string | null;
  browser_connected: boolean;
  sessions: PlatformSession[];
  error: string;
}

export interface ExtractedJobCandidate {
  platform: Platform;
  company: string;
  title: string;
  city: string;
  salary: string;
  description: string;
  url: string;
  job_type: string;
  detail_status?: string;
  detail_reason?: string;
}

export interface BrowserExtractionDiagnostics {
  tab_detected: boolean;
  websocket_detected: boolean;
  matched_selector_counts: Record<string, number>;
  candidate_card_count: number;
  extracted_job_count: number;
  text_quality_warnings: string[];
  failure_reason: string;
  suggestion: string;
}

export interface PlatformJobExtraction {
  platform: Platform;
  status: string;
  source_url: string | null;
  jobs: ExtractedJobCandidate[];
  error: string;
  diagnostics: BrowserExtractionDiagnostics;
}

export interface BrowserJobExtractRequest {
  platforms: Platform[];
  limit: number;
}

export interface BrowserJobSearchRequest extends BrowserJobExtractRequest {
  keywords: string[];
  city: string;
}

export interface ManualJobDetailRequest {
  description: string;
  note?: string;
}

export interface BrowserJobExtractResponse {
  cdp_url: string | null;
  extractions: PlatformJobExtraction[];
}

export interface ApplicationSyncRequest {
  platforms: Platform[];
  limit?: number;
}

export interface ApplicationSyncDiagnostic {
  platform: Platform;
  status: string;
  source_url: string | null;
  tab_detected: boolean;
  websocket_detected: boolean;
  candidate_item_count: number;
  matched_status_keywords: Record<string, number>;
  failure_reason: string;
  suggestion: string;
}

export interface ApplicationSyncProposal {
  application_id: number;
  platform: Platform;
  company: string;
  title: string;
  current_status: ApplicationStatus;
  detected_status: ApplicationStatus;
  suggested_status: ApplicationStatus;
  confidence: number;
  evidence: string;
  source_url: string;
  note: string;
  requires_manual_confirmation: boolean;
}

export interface ApplicationSyncResponse {
  status: string;
  mode: string;
  updated: number;
  proposals: ApplicationSyncProposal[];
  diagnostics: ApplicationSyncDiagnostic[];
  message: string;
}

export interface JobFilters {
  platform: "all" | Platform;
  keyword: string;
  minScore: number;
}

export interface UsageCards {
  totalTokens: string;
  totalCost: string;
  topAgent: string;
}
