// Playwright CLI run-code. All writes are intercepted; no model or platform action.
async (page) => {
  const date = "2026-10-26T00:00:00Z";
  const card = { id: 901, source_id: null, category: "project", title: "测试真实项目", organization: "", time_range: "", situation: "", actions: ["开发接口"], results: [], skills: ["Python"], status: "confirmed", provenance_type: "user_statement", source_quote: "", quote_verified: false, user_note: "", created_at: date, updated_at: date };
  const jobs = [901, 902].map(id => ({ id, search_run_id: 901, platform: "boss", company: "测试公司", title: `测试岗位${id}`, city: "上海", salary: "面议", description: "Python 接口开发", url: "https://example.com/job", job_type: "internship", detail_status: "complete", created_at: date, match: { score: 90, hit_reasons: [], gap_reasons: [], recommendation: "strong_apply" } }));
  let materials = [];
  let requests = 0;
  let allowGeneration;
  let empty = false;
  let noJob = false;
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  await page.route("**/api/**", async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const reply = (json, status = 200) => route.fulfill({ json, status });
    if (path === "/api/resumes/latest") return reply({ id: 901, filename: "test.docx", file_type: "docx", raw_text: "测试资料", profile: {}, template_available: true, created_at: date });
    if (path === "/api/jobs") return reply(noJob ? [] : jobs);
    if (path === "/api/evidence-cards") return reply(empty ? [] : [card]);
    if (/\/jobs\/\d+\/materials$/.test(path)) return reply(materials.filter(item => path.includes(`/${item.job_id}/`)));
    if (path.endsWith("/evidence-recommendations")) return reply([{ card, score: 90, hit_reasons: ["技能匹配"] }]);
    if (path.endsWith("/evidence-tailor")) {
      requests++;
      if (requests === 1) return reply({ detail: "测试生成失败，可重试" }, 502);
      await new Promise(resolve => { allowGeneration = resolve; });
      const bundle = { id: 901, job_id: 901, resume_id: 901, resume_text: "开发接口", resume_rewrite: "开发接口", project_rewrite: "", diff_summary: [], risk_flags: [], truth_check_passed: true, created_at: date, review: { trusted_evidence_finalized: false }, greeting: { id: 901, job_id: 901, message: "测试招呼语", risk_flags: [], tone: "", created_at: date }, claims: [{ id: 901, text: "开发接口", evidence_card_ids: [901], user_decision: "pending", support_status: "supported" }] };
      materials = [bundle];
      return reply(bundle, 201);
    }
    if (path === "/api/tailored-claims/901") {
      const data = req.postDataJSON();
      Object.assign(materials[0].claims[0], data, { support_status: data.confirm_support ? "supported" : "needs_review", user_decision: data.confirm_support ? "accepted" : "pending" });
      materials[0].review.trusted_evidence_finalized = false;
      return reply(materials[0].claims[0]);
    }
    if (path === "/api/trusted-tailors/901/finalize") {
      materials[0].review.trusted_evidence_finalized = true;
      return reply(materials[0]);
    }
    if (path === "/api/trusted-tailors/901") return reply(materials[0]);
    if (req.method() !== "GET") throw new Error("Unexpected write: " + path);
    return route.continue();
  });
  try {
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    const generate = page.getByRole("button", { name: "生成求职材料", exact: true });
    await generate.click();
    await page.getByText("测试生成失败，可重试", { exact: true }).waitFor();
    await generate.evaluate(button => { button.click(); button.click(); });
    await page.getByRole("button", { name: "推荐与生成中..." }).waitFor();
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    await page.locator(".job-table article").filter({ hasText: "测试岗位902" }).click();
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    allowGeneration();
    await generate.waitFor();
    check(await page.locator(".trusted-tailor-result").count() === 0, "Late response attached to wrong job");
    check(requests === 2, "Duplicate generation request");
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    await page.locator(".job-table article").filter({ hasText: "测试岗位901" }).click();
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    await page.locator(".trusted-tailor-result").waitFor();
    await page.getByRole("button", { name: "招呼语", exact: true }).click();
    await page.getByText("测试招呼语", { exact: true }).waitFor();
    check(requests === 2, "Tab switch generated new material");
    await page.getByRole("button", { name: "简历", exact: true }).click();
    await page.getByRole("button", { name: "核对证据并接受", exact: true }).click();
    await page.getByText("已接受", { exact: true }).first().waitFor();
    await page.getByRole("button", { name: "完成核验并定稿", exact: true }).click();
    const exportButton = page.locator(".trusted-tailor-result").getByRole("button", { name: "导出模板化 PDF" });
    await page.getByText("已定稿", { exact: true }).waitFor();
    check(await exportButton.isEnabled(), "Finalized result cannot export");
    await page.locator(".trusted-claim textarea").fill("修改后未保存");
    check(await exportButton.isDisabled(), "Unsaved edit bypassed export gate");
    await page.reload();
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    await page.getByText("已定稿", { exact: true }).waitFor();
    check(await page.getByRole("combobox", { name: "材料版本" }).inputValue() === "901", "Refresh lost material ID");
    empty = true;
    await page.reload();
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    await page.getByText("没有可用证据", { exact: true }).waitFor();
    check(await generate.isDisabled(), "Empty evidence allowed generation");
    noJob = true;
    await page.reload();
    await page.getByRole("button", { name: "生成中心", exact: true }).click();
    await page.getByText("尚未选择岗位", { exact: true }).waitFor();
    check(await generate.isDisabled(), "Missing job allowed generation");
    return { status: "passed", generationRequests: requests, checks: ["failure retry", "double click", "late response job isolation", "tabs", "review", "finalization", "dirty export gate", "refresh", "empty evidence", "missing job"] };
  } finally {
    await page.unrouteAll({ behavior: "wait" });
  }
}
