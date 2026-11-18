// Real query/delete API on a verified disposable fixture; models and platforms are blocked.
async (page) => {
  const fixture = "http://127.0.0.1:8767";
  const identity = await page.request.get(fixture + "/__application_query_identity");
  if ((await identity.json()).fixture !== "temporary-application-query-check") throw new Error("Unsafe fixture identity");
  const initial = await (await page.request.get(fixture + "/api/applications/page")).json();
  if (initial.total !== 137) throw new Error("Restart disposable fixture before another run");
  const checks = [];
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  let failNext = false;
  let holdOld = false;
  let releaseOld;
  let oldReceived;
  let oldArrival;
  const deleted = [];
  const routed = async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/applications/page" && failNext) {
      failNext = false;
      return route.fulfill({ status: 503, json: { detail: "模拟查询失败" } });
    }
    if (url.pathname === "/api/applications/page" && holdOld && url.searchParams.get("keyword") === "旧请求") {
      oldReceived();
      await new Promise(resolve => { releaseOld = resolve; });
      return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 25, pages: 0, statistics_scope: "all_applications" } }).catch(() => {});
    }
    if (request.method() !== "GET" && url.pathname !== "/api/applications/bulk-delete") throw new Error("Unexpected write: " + url.pathname);
    if (url.pathname === "/api/applications/bulk-delete") deleted.push(request.postDataJSON().ids);
    // Every API request, including bootstrap, is sent to the disposable DB.
    return route.fulfill({ response: await page.request.fetch(fixture + url.pathname + url.search, { method: request.method(), headers: { "Content-Type": "application/json" }, data: request.postData() ?? undefined }) });
  };
  await page.route("**/api/**", routed);
  try {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    const guide = page.getByRole("region", { name: "下一步引导" }).first();
    await page.getByText("下一步 · 先准备基础简历", { exact: true }).first().waitFor();
    await guide.getByRole("button", { name: "检查基础简历与资料" }).click();
    await page.getByRole("dialog", { name: "资料检查与事实确认" }).waitFor();
    await page.getByRole("button", { name: "关闭资料检查", exact: true }).click();
    await guide.getByRole("button", { name: "查看模型设置" }).click();
    await page.waitForFunction(() => document.querySelector(".squirrel-app").dataset.activeModule === "settings");
    checks.push("safe next-step navigation without model calls");
    await page.getByRole("button", { name: "投递跟踪", exact: true }).click();
    const panel = page.locator(".applications-panel");
    const filters = panel.getByRole("form", { name: "投递筛选" });
    const footer = panel.getByLabel("投递分页", { exact: true });
    const rows = panel.locator(".application-table .table-row");
    const waitRange = async text => { await footer.getByText(text, { exact: false }).waitFor(); };
    await waitRange("第 1–25 条");
    check(await rows.count() === 25, "Default page is not bounded");
    check((await page.locator(".pipeline-grid").innerText()).includes("137"), "Global pipeline lost records");
    await rows.first().getByRole("checkbox").check();
    await footer.getByRole("button", { name: "下一页 ›" }).click();
    await waitRange("第 26–50 条");
    check(await rows.getByRole("checkbox", { checked: true }).count() === 0, "Selection leaked across pages");
    for (const size of ["50", "100", "25"]) {
      await footer.getByRole("combobox").selectOption(size);
      await waitRange(`第 1–${size} 条`);
      check(await rows.count() === Number(size), "Page size did not affect real rows");
    }
    checks.push("25/50/100 bounded pages and selection reset");
    await filters.locator('[name="position"]').fill(" python ");
    await filters.locator('[name="keyword"]').fill("sql");
    await filters.locator('[name="location"]').fill("张江");
    await filters.getByRole("button", { name: "筛选记录" }).click();
    await waitRange("共 45 条");
    check(await rows.count() === 25 && (await rows.allTextContents()).every(text => text.includes("Python 实习") && text.includes("上海张江")), "AND filters did not affect full result set");
    await filters.getByRole("button", { name: "重置条件" }).click();
    await waitRange("共 137 条");
    await filters.locator('[name="keyword"]').fill("100%_匹配");
    await filters.getByRole("button", { name: "筛选记录" }).click();
    await waitRange("共 1 条");
    await filters.locator('[name="keyword"]').fill("无匹配记录");
    await filters.locator('[name="keyword"]').press("Enter");
    await panel.getByText("暂无匹配记录", { exact: true }).waitFor();
    check(!(await footer.innerText()).includes("第 1 /"), "Empty result invented a page");
    checks.push("AND, normalization, literal wildcards, reset and empty results");
    failNext = true;
    await filters.getByRole("button", { name: "重置条件" }).click();
    await panel.getByRole("alert").filter({ hasText: "模拟查询失败" }).waitFor();
    check(await panel.getByRole("button", { name: "批量删除", exact: true }).isDisabled(), "Deletion enabled on failure");
    await footer.getByRole("button", { name: "重试查询" }).click();
    await waitRange("共 137 条");
    checks.push("retryable errors with destructive actions disabled");
    holdOld = true;
    oldArrival = new Promise(resolve => { oldReceived = resolve; });
    await filters.locator('[name="keyword"]').fill("旧请求");
    await filters.getByRole("button", { name: "筛选记录" }).click();
    await oldArrival;
    await filters.locator('[name="keyword"]').fill("分页测试公司136");
    await filters.getByRole("button", { name: "筛选记录" }).click();
    await waitRange("共 1 条");
    releaseOld();
    await page.waitForTimeout(150);
    check(await rows.count() === 1 && (await rows.first().innerText()).includes("分页测试公司136"), "Old response overwrote new filters");
    checks.push("aborted old query cannot overwrite latest results");
    await filters.getByRole("button", { name: "重置条件" }).click();
    await waitRange("共 137 条");
    for (let index = 0; index < 5; index++) {
      await footer.getByRole("button", { name: "下一页 ›" }).click();
      await waitRange(`第 ${(index + 1) * 25 + 1}–`);
    }
    check(await rows.count() === 12, "Last page should have 12 rows");
    await panel.getByRole("checkbox", { name: "全选当前投递记录", exact: true }).check();
    await page.evaluate(() => {
      window.__queryConfirmMessages = [];
      window.confirm = message => { window.__queryConfirmMessages.push(message); return true; };
    });
    await panel.getByRole("button", { name: "批量删除", exact: true }).click();
    await waitRange("共 125 条");
    check(deleted.length === 1 && deleted[0].length === 12, "Deletion included another page");
    check(await page.evaluate(() => window.__queryConfirmMessages.some(message => message.includes("12 条") && message.includes("不会撤销平台"))), "Missing explicit destructive confirmation");
    check((await footer.innerText()).includes("第 5 / 5 页"), "Deletion did not recover out-of-range page");
    checks.push("explicit current-page deletion and last-page recovery");
    await page.reload();
    await page.getByRole("button", { name: "投递跟踪", exact: true }).click();
    await waitRange("共 125 条");
    checks.push("reload persists the real fixture deletion");
    return { status: "passed", checks, initial: 137, remaining: 125 };
  } finally {
    releaseOld?.();
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("http://127.0.0.1:5173/");
  }
}
