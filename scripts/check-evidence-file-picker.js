// A native chooser is exercised; all API requests are forwarded to a verified disposable DB.
async (page) => {
  const origin = "http://127.0.0.1:8768";
  const marker = await (await page.request.get(origin + "/__workspace_bug_identity")).json();
  if (marker.fixture !== "temporary-workspace-bug-check") throw new Error("Wrong fixture; refusing upload");
  const baseline = await (await page.request.get(origin + "/api/evidence-sources")).json();
  let uploads = 0;
  let markUploadStarted;
  const uploadStarted = new Promise(resolve => { markUploadStarted = resolve; });
  let releaseUpload;
  const gate = new Promise(resolve => { releaseUpload = resolve; });
  const routeApi = async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" && !(url.pathname === "/api/evidence-sources" && request.method() === "POST")) throw new Error("Unexpected write");
    if (request.method() === "POST") { uploads++; markUploadStarted(); await gate; }
    return route.fulfill({ response: await page.request.fetch(origin + url.pathname + url.search, { method: request.method(), headers: request.headers(), data: request.postDataBuffer() ?? undefined }) });
  };
  await page.route("**/api/**", routeApi);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  try {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    await page.getByRole("button", { name: "查看资料与确认事实", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "资料检查与事实确认" });
    const form = dialog.getByRole("form", { name: "资料选择与上传" });
    const choose = form.getByRole("button", { name: "加入本地资料库", exact: true });
    const cancelled = page.waitForEvent("filechooser");
    await choose.click();
    await (await cancelled).setFiles([]);
    check(uploads === 0, "Cancelling a chooser uploaded a file");
    const chooser = page.waitForEvent("filechooser");
    await choose.click();
    const name = `picker-regression-${Date.now()}.txt`;
    await (await chooser).setFiles({ name, mimeType: "text/plain", buffer: Buffer.from("合成项目经历：负责需求分析与 Python 接口设计。") });
    await form.getByText(`已选择 1 份：${name}`, { exact: true }).waitFor();
    check(uploads === 0, "Choosing a file uploaded it without confirmation");
    await form.getByRole("button", { name: "上传所选资料", exact: true }).evaluate(button => { button.click(); button.click(); });
    await form.getByRole("button", { name: "上传中...", exact: true }).waitFor();
    await uploadStarted;
    check(uploads === 1, "Double click submitted duplicate uploads");
    check(await form.locator('input[type="file"]').isDisabled(), "Chooser remained enabled during upload");
    releaseUpload();
    await dialog.locator(".evidence-source-card").filter({ hasText: name }).waitFor();
    await choose.waitFor();
    const after = await (await page.request.get(origin + "/api/evidence-sources")).json();
    check(after.length === baseline.length + 1 && after.some(source => source.filename === name), "Selected file was not persisted in fixture");
    await page.reload();
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    await page.getByRole("button", { name: "查看资料与确认事实", exact: true }).click();
    await page.locator(".evidence-source-card").filter({ hasText: name }).waitFor();
    return { status: "passed", uploads, checks: ["native chooser opens from add button", "cancel does not upload", "filename and explicit upload", "double-click protection", "disabled while uploading", "persisted after reload"] };
  } finally {
    releaseUpload?.();
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("http://127.0.0.1:5173/");
  }
}
