// Synthetic upload + model failure + explicit local recovery. All writes are intercepted.
async (page) => {
  const text = "项目：资料库，负责需求分析与 Python 接口开发。";
  const source = { id: 991, filename: "upload-recovery.txt", file_type: "txt", raw_text: text, extraction_status: "success", extraction_method: "text", extraction_confidence: 1, manual_text_required: false, warnings: [], created_at: "2026-11-17T00:00:00Z", updated_at: "2026-11-17T00:00:00Z" };
  let sources = [];
  let cards = [];
  let uploads = 0;
  let configuredCalls = 0;
  let localCalls = 0;
  let releaseLocal;
  let releaseBoot;
  const bootGate = new Promise(resolve => { releaseBoot = resolve; });
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const reply = (json, status = 200) => route.fulfill({ json, status });
    if (url.pathname === "/api/system/health") {
      await bootGate;
      return route.continue();
    }
    if (url.pathname === "/api/evidence-sources" && request.method() === "POST") {
      uploads++;
      sources = [source];
      return reply(source, 201);
    }
    if (url.pathname === "/api/evidence-sources") return reply(sources);
    if (url.pathname === "/api/evidence-cards") return reply(cards);
    if (url.pathname === "/api/resumes/latest") return reply(null);
    if (url.pathname === "/api/evidence-sources/991/extract-cards") {
      if (url.searchParams.get("mode") !== "local") {
        configuredCalls++;
        return reply({ detail: "经历卡片模型调用失败：模型认证失败，Key 无效，请更新系统设置（HTTP 401）" }, 502);
      }
      localCalls++;
      await new Promise(resolve => { releaseLocal = resolve; });
      cards = [{ id: 992, source_id: source.id, category: "project", title: "资料库项目", organization: "", time_range: "", situation: text, actions: [text], results: [], skills: ["Python"], status: "draft", provenance_type: "document", source_quote: text, source_start: 0, source_end: text.length, quote_verified: true, user_note: "本地原文提取草稿，未调用模型，需用户核对确认", created_at: source.created_at, updated_at: source.updated_at }];
      return reply(cards, 201);
    }
    if (request.method() !== "GET") throw new Error("Unexpected write: " + url.pathname);
    return route.continue();
  });
  try {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    await page.locator(".material-drop-zone input").setInputFiles({ name: source.filename, mimeType: "text/plain", buffer: Buffer.from(text) });
    check(await page.getByRole("button", { name: "上传并检查资料", exact: true }).isDisabled(), "Upload was enabled before the initial snapshot finished");
    releaseBoot();
    await page.getByRole("button", { name: "上传并检查资料", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "资料检查与事实确认" });
    await dialog.waitFor();
    check(uploads === 1 && configuredCalls === 0, "Upload unexpectedly invoked the model");
    await dialog.getByRole("button", { name: "提取候选卡片", exact: true }).click();
    await dialog.getByRole("status").filter({ hasText: "无需重复上传" }).waitFor();
    check((await dialog.getByRole("status").innerText()).includes("HTTP 401"), "Missing actionable authentication error");
    check(sources.length === 1 && cards.length === 0 && uploads === 1, "Model failure lost or duplicated the upload");
    await dialog.getByRole("button", { name: "模型连接设置", exact: true }).click({ timeout: 5000 });
    await page.waitForFunction(() => document.querySelector(".squirrel-app")?.dataset.activeModule === "settings");
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    await page.getByRole("button", { name: "查看资料与确认事实", exact: true }).click();
    await dialog.getByRole("button", { name: "本地提取卡片", exact: true }).evaluate(button => { button.click(); button.click(); });
    await dialog.getByRole("button", { name: "处理中...", exact: true }).waitFor();
    check(localCalls === 1, "Duplicate local extraction request");
    releaseLocal();
    await dialog.getByRole("status").filter({ hasText: "本地原文提取，未调用模型" }).waitFor();
    await dialog.locator(".evidence-card").getByText("待确认", { exact: true }).waitFor();
    await dialog.getByText("本地原文提取草稿，未调用模型，需用户核对确认", { exact: true }).waitFor();
    check(uploads === 1 && configuredCalls === 1 && localCalls === 1 && cards.length === 1, "Recovery repeated upload or used external generation");
    check(await page.locator(".alert").count() === 0, "Stale error remained after successful local recovery");
    return { status: "passed", uploads, configuredCalls, localCalls, checks: ["bootstrap upload guard", "upload saved", "auth failure explained", "no re-upload", "settings shortcut", "explicit local recovery", "double click guarded", "draft and provenance labels", "stale error cleared"] };
  } catch (error) {
    const diagnostic = await page.locator(".evidence-dialog").evaluate(element => ({
      open: element.open,
      sources: element.querySelectorAll(".evidence-source-card").length,
      buttons: [...element.querySelectorAll("button")].map(button => button.textContent.trim()),
    }));
    throw new Error(error.message + "; recovery UI: " + JSON.stringify(diagnostic));
  } finally {
    releaseBoot?.();
    releaseLocal?.();
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("http://127.0.0.1:5173/");
  }
}
