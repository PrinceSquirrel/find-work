// Mocked platform and launch responses only; no account action or real send.
async (page) => {
  const date = "2026-11-19T00:00:00Z";
  const job = { id: 950, search_run_id: 950, platform: "boss", company: "合成测试公司", title: "合成岗位", city: "上海", salary: "面议", description: "岗位职责：测试", detail_status: "detail_fetched", url: "https://example.invalid/job", created_at: date, match: { score: 90, recommendation: "strong_apply", hit_reasons: [], gap_reasons: [] } };
  let launches = []; let previews = 0; let applies = 0; let approval = false; let dialogs = 0;
  const check = (value, message) => { if (!value) throw new Error(message); };
  page.on("dialog", async dialog => { dialogs++; await (approval ? dialog.accept() : dialog.dismiss()); });
  await page.route("**/api/**", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    const reply = (json, status = 200) => route.fulfill({ json, status });
    if (path === "/api/jobs") return reply([job]);
    if (path === "/api/applications") return reply([]);
    if (path === "/api/browser/launch-cdp") { launches.push(request.postDataJSON().platforms); return reply({ message: "合成启动通过" }); }
    if (path.endsWith("/platform-apply-preview")) { previews++; return reply({ job, platform: "boss", ready: true, status: "ready", button_text: "立即沟通", evidence: "合成有效入口" }); }
    if (path.endsWith("/platform-apply")) { applies++; return reply({ detail: "已打开聊天窗口，但尚未确认招呼已发送或简历已投递" }, 409); }
    if (request.method() !== "GET") throw new Error("Unexpected write: " + path);
    return route.continue();
  });
  try {
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    const panel = page.locator(".module-jobs.search-panel");
    // Scope platform labels to their search form, not the repeated session cards.
    const boss = page.getByRole("checkbox", { name: "BOSS直聘", exact: true });
    const intern = page.getByRole("checkbox", { name: "实习僧", exact: true });
    await boss.check(); await intern.uncheck();
    await page.getByRole("button", { name: "启动 CDP 浏览器", exact: true }).click();
    await page.getByText("合成启动通过", { exact: true }).first().waitFor();
    check(JSON.stringify(launches[0]) === '["boss"]', "BOSS selection launched other platforms");
    await boss.uncheck(); await intern.check();
    await page.getByRole("button", { name: "启动 CDP 浏览器", exact: true }).click();
    await page.waitForFunction(() => ![...document.querySelectorAll('button')].some(button => button.textContent === '启动中'));
    check(JSON.stringify(launches[1]) === '["shixiseng"]', "Intern selection launched BOSS");
    const action = page.getByRole("button", { name: "去沟通／投递", exact: true });
    await action.click();
    await page.getByText("已取消，未执行平台发送操作。", { exact: true }).waitFor();
    check(previews === 1 && applies === 0 && dialogs === 1, "Cancel sent a platform action");
    approval = true;
    await action.evaluate(button => { button.click(); button.click(); });
    await page.getByRole("status").filter({ hasText: "未计入投递" }).waitFor();
    check(previews === 2 && applies === 1 && dialogs === 2, "Rapid clicks duplicated platform flow");
    check(await page.locator('.alert').count() === 0, "An open chat was incorrectly presented as a hard failure");
    return { status: "passed", launches, previews, applies, checks: ["only selected platform", "automatic preflight", "cancel never sends", "one explicit approval", "double-click lock", "unconfirmed chat not counted"] };
  } finally { await page.unrouteAll({ behavior: "wait" }); }
}
