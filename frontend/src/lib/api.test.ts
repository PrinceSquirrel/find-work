import { afterEach, describe, expect, test, vi } from "vitest";

import { ApiError, api, getTailorBlockedMessage } from "./api";
import type { ModelConfigUpdate } from "../types";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("listJobs can request jobs for one search run", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => []
    } as Response);

    await api.listJobs(42);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs?search_run_id=42",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
  });

  test("tailoredResumePdfUrl points at the PDF download endpoint", () => {
    expect(api.tailoredResumePdfUrl(7)).toBe("/api/tailored-resumes/7/pdf");
  });

  test("getLatestResume requests the persisted resume snapshot", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 12,
        filename: "resume.docx",
        raw_text: "Python FastAPI",
        profile: {},
        file_type: "docx",
        template_available: true,
        created_at: "2026-07-03T12:00:00Z"
      })
    } as Response);

    const result = await api.getLatestResume();

    expect(result?.id).toBe(12);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resumes/latest",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
  });

  test("updateResumeManualText patches pasted resume text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 12,
        filename: "resume.png",
        raw_text: "技能: Python, React",
        profile: { extraction: { source_type: "manual", manual_text_required: false } },
        file_type: "png",
        template_available: false,
        created_at: "2026-07-05T12:00:00Z"
      })
    } as Response);

    const result = await api.updateResumeManualText(12, "技能: Python, React");

    expect(result.raw_text).toContain("Python");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resumes/12/manual-text",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ raw_text: "技能: Python, React" }),
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("model config endpoints support a DeepSeek preset", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        provider: "openai-compatible",
        model: "deepseek-v4-pro",
        base_url: "https://api.deepseek.com",
        api_key_env_var: "DEEPSEEK_API_KEY",
        api_key_configured: true,
        enabled: true,
        estimation_only: false,
        timeout_ms: 90000,
        input_price_per_million: 1,
        output_price_per_million: 2
      })
    } as Response);

    await api.getModelConfig();
    await api.updateModelConfig({
      provider: "openai-compatible",
      model: "deepseek-v4-pro",
      base_url: "https://api.deepseek.com",
      api_key_env_var: "DEEPSEEK_API_KEY",
      enabled: true,
      estimation_only: false,
      timeout_ms: 90000,
      input_price_per_million: 1,
      output_price_per_million: 2
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/model-config",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/model-config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          provider: "openai-compatible",
          model: "deepseek-v4-pro",
          base_url: "https://api.deepseek.com",
          api_key_env_var: "DEEPSEEK_API_KEY",
          enabled: true,
          estimation_only: false,
          timeout_ms: 90000,
          input_price_per_million: 1,
          output_price_per_million: 2
        })
      })
    );
  });

  test("model config update can send a saved real API key without an env var", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        provider: "openai-compatible",
        model: "deepseek-v4-pro",
        base_url: "https://api.deepseek.com",
        api_key_env_var: "",
        api_key_secret_id: "model_config:1",
        api_key_masked: "********7890",
        api_key_configured: true,
        enabled: true,
        estimation_only: false,
        timeout_ms: 90000,
        input_price_per_million: 1,
        output_price_per_million: 2
      })
    } as Response);
    const payload: ModelConfigUpdate = {
      provider: "openai-compatible",
      model: "deepseek-v4-pro",
      base_url: "https://api.deepseek.com",
      api_key_env_var: "",
      api_key: "sk-live-secret-1234567890",
      enabled: true,
      estimation_only: false,
      timeout_ms: 90000,
      input_price_per_million: 1,
      output_price_per_million: 2
    };

    const result = await api.updateModelConfig(payload);

    expect(result.api_key_configured).toBe(true);
    expect(result.api_key_masked).toBe("********7890");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/model-config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(payload)
      })
    );
  });

  test("testModelConfigConnection posts to the model connection endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "success",
        provider: "openai-compatible",
        model: "deepseek-v4-pro",
        duration_ms: 32,
        api_key_configured: true,
        message: "model connection ok"
      })
    } as Response);

    const result = await api.testModelConfigConnection();

    expect(result.status).toBe("success");
    expect(result.model).toBe("deepseek-v4-pro");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/model-config/test",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("model profile endpoints support manage models CRUD and apply", async () => {
    const profilePayload = {
      id: 7,
      name: "DeepSeek v4pro",
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
      created_at: "2026-07-04T00:00:00Z"
    };
    const configUpdate = {
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
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ profiles: [profilePayload] })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => profilePayload
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...profilePayload, name: "DeepSeek v4flash", model: "deepseek-v4-flash" })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...configUpdate, api_key_configured: true })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: async () => {
          throw new Error("204 should not read JSON");
        }
      } as unknown as Response);

    await api.getModelProfiles();
    await api.createModelProfile("DeepSeek v4pro", configUpdate);
    await api.updateModelProfile(7, "DeepSeek v4flash", { ...configUpdate, model: "deepseek-v4-flash" });
    await api.applyModelProfile(7);
    await api.deleteModelProfile(7);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/model-profiles",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/model-profiles",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "DeepSeek v4pro", ...configUpdate })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/model-profiles/7",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ name: "DeepSeek v4flash", ...configUpdate, model: "deepseek-v4-flash" })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/model-profiles/7/apply",
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/model-profiles/7",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  test("model route endpoints support per-agent model selection", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        routes: [
          {
            agent_name: "ApplicationWriterAgent",
            provider: "openai-compatible",
            model: "deepseek-v4-pro",
            base_url: "https://api.deepseek.com",
            api_key_env_var: "DEEPSEEK_API_KEY",
            api_key_configured: true,
            enabled: true,
            estimation_only: false,
            timeout_ms: 90000,
            input_price_per_million: 1,
            output_price_per_million: 2
          }
        ]
      })
    } as Response);

    const routes = await api.getModelRoutes();
    await api.updateModelRoute("JobMatchAgent", {
      provider: "openai-compatible",
      model: "deepseek-v4-flash",
      base_url: "https://api.deepseek.com",
      api_key_env_var: "DEEPSEEK_API_KEY",
      enabled: true,
      estimation_only: false,
      timeout_ms: 45000,
      input_price_per_million: 0.5,
      output_price_per_million: 1
    });

    expect(routes.routes[0].agent_name).toBe("ApplicationWriterAgent");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/model-routes",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/model-routes/JobMatchAgent",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          provider: "openai-compatible",
          model: "deepseek-v4-flash",
          base_url: "https://api.deepseek.com",
          api_key_env_var: "DEEPSEEK_API_KEY",
          enabled: true,
          estimation_only: false,
          timeout_ms: 45000,
          input_price_per_million: 0.5,
          output_price_per_million: 1
        })
      })
    );
  });

  test("getTailorBlockedMessage detects low-quality JD tailor conflicts", () => {
    const message = getTailorBlockedMessage(
      new ApiError("当前岗位需要先补全 JD 后再生成材料。原因：当前只读取到列表卡片。", 409)
    );

    expect(message).toContain("先补全 JD");
    expect(message).toContain("当前只读取到列表卡片");
    expect(getTailorBlockedMessage(new ApiError("not found", 404))).toBeNull();
  });

  test("refreshJobDetail posts to the single job detail refresh endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ id: 9 })
    } as Response);

    await api.refreshJobDetail(9);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs/9/refresh-detail",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("applyToPlatform posts to the platform-confirmed apply endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ id: 3, current_status: "applied" })
    } as Response);

    await api.applyToPlatform(3, "用户确认在平台投递");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs/3/platform-apply",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ note: "用户确认在平台投递" }),
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("previewPlatformApply posts to the read-only platform apply preview endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        ready: true,
        status: "ready",
        action: "preview",
        button_text: "立即沟通",
        evidence: "found platform button: 立即沟通",
        source_url: "https://www.zhipin.com/job_detail/abc.html",
        platform: "boss",
        job: { id: 9, title: "Python 实习", company: "示例公司" }
      })
    } as Response);

    const result = await api.previewPlatformApply(9);

    expect(result.ready).toBe(true);
    expect(result.button_text).toBe("立即沟通");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs/9/platform-apply-preview",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("updateJobManualDetail patches manual JD text and note", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ id: 11, detail_status: "manual_filled" })
    } as Response);

    await api.updateJobManualDetail(11, {
      description: "完整 JD：负责 Python、React 和 Agent 工作台开发。",
      note: "用户手动补全"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/jobs/11/manual-detail",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          description: "完整 JD：负责 Python、React 和 Agent 工作台开发。",
          note: "用户手动补全"
        }),
        headers: expect.objectContaining({ "Content-Type": "application/json" })
      })
    );
  });

  test("tailored resume revision endpoints support read, save, and preview", async () => {
    const revisionPayload = {
      id: 9,
      job_id: 3,
      resume_id: 12,
      editable_text: "初始简历改写",
      resume_rewrite: "初始简历改写",
      project_rewrite: "初始简历改写",
      resume_text: "初始简历改写",
      created_at: "2026-07-05T12:00:00Z"
    };
    const previewPayload = {
      id: 9,
      plain_text: "保存后的简历改写",
      html: "<article>保存后的简历改写</article>"
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => revisionPayload
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...revisionPayload, editable_text: "保存后的简历改写" })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => previewPayload
      } as Response);

    const revision = await api.getTailoredResumeRevision(9);
    const saved = await api.updateTailoredResumeRevision(9, "保存后的简历改写");
    const preview = await api.getTailoredResumePreview(9);

    expect(revision.editable_text).toBe("初始简历改写");
    expect(saved.editable_text).toBe("保存后的简历改写");
    expect(preview.html).toContain("保存后的简历改写");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/tailored-resumes/9/revision",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/tailored-resumes/9/revision",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ resume_rewrite: "保存后的简历改写" })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/tailored-resumes/9/preview",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
  });

  test("searchPlatformJobs sends keywords and city to the CDP search endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ cdp_url: "http://127.0.0.1:9222", extractions: [] })
    } as Response);

    await api.searchPlatformJobs({
      platforms: ["boss"],
      keywords: ["Python 实习"],
      city: "上海",
      limit: 5
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/platform-jobs/search",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          platforms: ["boss"],
          keywords: ["Python 实习"],
          city: "上海",
          limit: 5
        })
      })
    );
  });
});
