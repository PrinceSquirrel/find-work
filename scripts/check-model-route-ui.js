// Read effective production metadata, but intercept all mutations and provider-backed checks.
async (page) => {
  let routeTests = 0;
  await page.route("**/api/**", route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/model-routes/ApplicationWriterAgent/test") {
      routeTests++;
      return route.fulfill({ json: { status: "success", model: "合成任务模型", provider: "mock", duration_ms: 1 } });
    }
    if (request.method() !== "GET") throw Error("Unexpected write: " + path);
    return route.continue();
  });
  try {
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "系统设置", exact: true }).click();
    await page.getByText("按任务查看实际模型与连接", { exact: true }).click();
    const writer = page.locator(".model-route-simple").filter({ hasText: "简历/招呼语生成" });
    await writer.getByText(/同地址复用主模型 Key · Key 已配置/).waitFor();
    await writer.getByRole("button", { name: "测试此任务" }).click();
    await page.getByText("简历/招呼语生成 · 合成任务模型：连接成功", { exact: true }).waitFor();
    if (routeTests !== 1) throw Error("Unexpected model check count");
    return { passed: true, checked: ["effective writer metadata", "task-specific test target", "zero real provider calls"] };
  } finally {
    await page.unrouteAll({ behavior: "wait" });
  }
}
