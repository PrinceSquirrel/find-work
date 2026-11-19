async (page) => {
  const job = { id: 401, search_run_id: 1, platform: "boss", title: "合成岗位长 JD", company: "合成公司",
    city: "上海", salary: "面议", description: "岗位职责：负责调研和分析。".repeat(70) + "可辨认的正文尾部",
    url: "https://example.invalid/job", detail_status: "detail_fetched", created_at: "2026-11-19T00:00:00Z",
    match: { score: 45, recommendation: "skip", hit_reasons: [], gap_reasons: [] } };
  await page.route("**/api/**", route => {
    if (route.request().method() !== "GET") throw Error("Unexpected write");
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/jobs") return route.fulfill({ json: [job] });
    if (path === "/api/applications") return route.fulfill({ json: [] });
    return route.continue();
  });
  try {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    const trigger = page.getByRole("button", { name: "放大阅读：合成岗位长 JD" });
    await trigger.waitFor();
    if ((await trigger.innerText()).includes("可辨认的正文尾部")) throw Error("List still shows full JD");
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "岗位聚焦阅读" });
    await dialog.getByText("匹配参考分 45 / 100").waitFor();
    if (!(await dialog.innerText()).includes("可辨认的正文尾部")) throw Error("JD lost in focus window");
    if ((await dialog.boundingBox()).width < 740) throw Error("Focus window too narrow");
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    if (!(await trigger.evaluate(node => document.activeElement === node))) throw Error("Focus not restored");
    await page.setViewportSize({ width: 390, height: 844 });
    await trigger.click();
    if ((await dialog.boundingBox()).width > 390) throw Error("Mobile focus window overflow");
    await dialog.getByRole("button", { name: "关闭", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    return { passed: true, checks: ["bounded summary", "full JD", "score explanation", "Escape", "focus restored", "mobile bounds"] };
  } finally {
    await page.unrouteAll({ behavior: "wait" });
  }
}
