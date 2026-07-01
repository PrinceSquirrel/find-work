import { afterEach, describe, expect, test, vi } from "vitest";

import { api } from "./api";

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
