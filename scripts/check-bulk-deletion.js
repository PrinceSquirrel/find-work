// First run serve_bulk_delete_check.py. Every API request is forwarded to its temporary database.
async (page) => {
  const origin = "http://127.0.0.1:8766";
  const identity = await (await page.request.get(origin + "/__bulk_check_identity")).json();
  if (identity.fixture !== "temporary-bulk-deletion-check") throw new Error("Refusing to test deletion against a non-fixture database");
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const state = async () => (await (await page.request.get(origin + "/__bulk_check_state")).json());
  const initial = await state();
  check(initial.jobs === 4 && initial.applications === 2, "Restart the temporary fixture server before repeating this test");
  const installConfirmation = async () => page.evaluate(() => {
    window.__bulkConfirmAnswer = true;
    window.__bulkConfirmMessages = [];
    window.confirm = message => { window.__bulkConfirmMessages.push(message); return window.__bulkConfirmAnswer; };
  });
  let jobRequests = 0;
  let applicationRequests = 0;
  let releaseDeletion;
  let rejectNextJobDelete = true;
  const uiErrors = [];
  const onError = error => uiErrors.push(error.message);
  page.on("pageerror", onError);
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" && !["/api/jobs/bulk-delete", "/api/applications/bulk-delete"].includes(url.pathname)) {
      throw new Error("Unexpected write from bulk controls: " + url.pathname);
    }
    if (url.pathname === "/api/jobs/bulk-delete") {
      jobRequests++;
      if (rejectNextJobDelete) {
        rejectNextJobDelete = false;
        return route.fulfill({ status: 500, json: { detail: "测试删除失败" } });
      }
    }
    if (url.pathname === "/api/applications/bulk-delete") {
      applicationRequests++;
      if (applicationRequests === 1) await new Promise(resolve => { releaseDeletion = resolve; });
    }
    const response = await route.fetch({ url: origin + url.pathname + url.search });
    await route.fulfill({ response });
  });
  try {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("http://127.0.0.1:5173/");
    await installConfirmation();
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    const jobs = page.getByRole("group", { name: "岗位批量操作" });
    await page.getByRole("checkbox", { name: "选择岗位 #1 批删岗位A" }).waitFor();
    check(await page.getByRole("checkbox", { name: "选择岗位 #3 已联系岗位" }).isDisabled(), "Confirmed application lost job protection");
    check(await page.getByRole("checkbox", { name: "选择岗位 #4 旧记录岗位" }).isDisabled(), "Legacy job was assumed fake");
    const selectedBefore = await page.locator(".job-table .is-selected").innerText();
    await page.getByRole("checkbox", { name: "选择岗位 #1 批删岗位A" }).check();
    check(await page.locator(".job-table .is-selected").innerText() === selectedBefore, "Checking a row changed the active job");
    const keyword = page.getByPlaceholder("公司 / 职位 / 技能");
    await keyword.fill("批删岗位B");
    check(await jobs.getByRole("button", { name: "批量删除", exact: true }).isDisabled(), "Hidden selection could be deleted");
    await page.getByRole("checkbox", { name: "选择岗位 #2 批删岗位B" }).check();
    await keyword.fill("");
    check(await jobs.getByRole("checkbox", { name: "全选当前岗位", exact: true }).isChecked(), "All eligible selection is inconsistent");
    await page.evaluate(() => { window.__bulkConfirmAnswer = false; });
    await jobs.getByRole("button", { name: "批量删除", exact: true }).click();
    check(jobRequests === 0, "Cancel still sent deletion request");
    await page.evaluate(() => { window.__bulkConfirmAnswer = true; });
    await jobs.getByRole("button", { name: "批量删除", exact: true }).click();
    await jobs.getByRole("status").filter({ hasText: "测试删除失败" }).waitFor();
    check(await page.getByRole("checkbox", { name: "选择岗位 #1 批删岗位A" }).isChecked(), "Failure lost retry selection");
    await jobs.getByRole("button", { name: "批量删除", exact: true }).click();
    await jobs.getByRole("status").filter({ hasText: "已删除 2 条" }).waitFor();
    check(await page.locator(".job-table article").count() === 2, "Deleted jobs remain in list");
    const afterJobs = await state();
    check(afterJobs.jobs === 2 && afterJobs.applications === 2 && afterJobs.tailored_resumes === 0 && afterJobs.tailored_claims === 0, "Job deletion cascaded incorrectly");
    await page.reload();
    await installConfirmation();
    await page.getByRole("button", { name: "投递跟踪", exact: true }).click();
    const applications = page.getByRole("group", { name: "投递记录批量操作" });
    await applications.getByRole("button", { name: "选择待核对记录" }).click();
    check(await page.getByRole("checkbox", { name: "选择记录 #2 测试公司4" }).isChecked(), "Pending selection omitted unverified record");
    check(!await page.getByRole("checkbox", { name: "选择记录 #1 测试公司3" }).isChecked(), "Pending selection selected confirmed record");
    await applications.getByRole("button", { name: "批量删除", exact: true }).evaluate(button => { button.click(); button.click(); });
    await applications.getByRole("button", { name: "处理中…", exact: true }).waitFor();
    check(applicationRequests === 1, "Double click issued duplicate deletes");
    releaseDeletion();
    await applications.getByRole("status").filter({ hasText: "已删除 1 条" }).waitFor();
    check(await page.locator(".application-table article").count() === 1, "Unselected confirmed record was lost");
    let analytics = await (await page.request.get(origin + "/api/analytics/applications")).json();
    check(analytics.totals.applications === 1, "Statistics retained deleted record");
    await page.reload();
    await installConfirmation();
    await page.getByRole("button", { name: "投递跟踪", exact: true }).click();
    await page.getByRole("checkbox", { name: "选择记录 #1 测试公司3" }).waitFor();
    check(await page.locator(".application-table article").count() === 1, "Reload resurrected deleted records");
    await applications.getByRole("checkbox", { name: "全选当前投递记录", exact: true }).check();
    await applications.getByRole("button", { name: "批量删除", exact: true }).click();
    await page.getByText("暂无投递结果", { exact: true }).waitFor();
    const warning = await page.evaluate(() => window.__bulkConfirmMessages.at(-1));
    check(warning.includes("真实打过招呼") && warning.includes("不会撤销平台"), "Destructive impact was not explained");
    const final = await state();
    check(final.applications === 0 && final.application_events === 0 && final.jobs === 2, "Explicit application deletion damaged jobs or left events");
    analytics = await (await page.request.get(origin + "/api/analytics/applications")).json();
    check(analytics.totals.applications === 0, "Empty statistics did not refresh");
    check(uiErrors.length === 0, "Browser errors: " + uiErrors.join(";"));
    return { status: "passed", jobRequests, applicationRequests, checks: ["protected jobs", "checkbox isolation", "filtered selection", "cancel", "failure retry", "material cleanup", "pending selection", "duplicate click", "unselected preservation", "reload", "events and statistics"] };
  } finally {
    releaseDeletion?.();
    page.off("pageerror", onError);
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("http://127.0.0.1:5173/");
  }
}
