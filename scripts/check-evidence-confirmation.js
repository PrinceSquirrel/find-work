// All writes are synthetic and forwarded only to the identity-checked disposable API.
async (page) => {
  const origin = "http://127.0.0.1:8768";
  const marker = await (await page.request.get(origin + "/__workspace_bug_identity")).json();
  if (marker.fixture !== "temporary-workspace-bug-check") throw new Error("Wrong fixture; refusing writes");
  const created = await page.request.post(origin + "/api/evidence-cards", { data: { title: `confirmation-${Date.now()}`, category: "project", actions: ["合成回归测试"], skills: ["Python"] } });
  if (created.status() !== 201) throw new Error("Could not create synthetic card");
  const initial = await created.json();
  const path = `/api/evidence-cards/${initial.id}`;
  let patches = 0;
  let failNext = false;
  let releaseSave;
  let savingStarted;
  const started = new Promise(resolve => { savingStarted = resolve; });
  const gate = new Promise(resolve => { releaseSave = resolve; });
  const routeApi = async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" && !(request.method() === "PATCH" && url.pathname === path)) throw new Error("Unexpected write");
    if (request.method() === "PATCH") {
      patches++;
      if (patches === 1) { savingStarted(); await gate; }
      if (failNext) { failNext = false; return route.fulfill({ status: 503, json: { detail: "合成保存失败，请重试" } }); }
    }
    return route.fulfill({ response: await page.request.fetch(origin + url.pathname + url.search, { method: request.method(), headers: request.headers(), data: request.postDataBuffer() ?? undefined }) });
  };
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const getStored = async () => (await (await page.request.get(origin + "/api/evidence-cards")).json()).find(item => item.id === initial.id);
  const open = async () => {
    await page.getByRole("button", { name: "资料工作台", exact: true }).click();
    await page.getByRole("button", { name: "查看资料与确认事实", exact: true }).click();
  };
  await page.route("**/api/**", routeApi);
  try {
    await page.goto("http://127.0.0.1:5173/");
    await open();
    const card = page.locator(".evidence-card").filter({ has: page.locator(`input[value="${initial.title}"]`) });
    // Keep a stable card locator after the controlled input's title changes.
    const article = page.locator(".evidence-card").filter({ has: page.getByText(`#${String(initial.id).padStart(2, "0")}`, { exact: true }) });
    await card.getByRole("button", { name: "确认事实", exact: true }).evaluate(button => { button.click(); button.click(); });
    await started;
    await article.getByRole("button", { name: "保存中...", exact: true }).waitFor();
    check(patches === 1, "Rapid clicks sent duplicate requests");
    check(await article.getByLabel("卡片标题", { exact: true }).isDisabled(), "Facts editable during save");
    releaseSave();
    const confirmedButton = article.getByRole("button", { name: "已确认", exact: true });
    await confirmedButton.waitFor();
    check(await confirmedButton.isDisabled(), "Confirmed card remains actionable");
    await confirmedButton.evaluate(button => { button.click(); button.click(); });
    check(patches === 1, "Confirmed button submitted again");
    const confirmed = await getStored();
    const repeat = await page.request.patch(origin + path, { data: { status: "confirmed" } });
    check(repeat.ok() && (await repeat.json()).updated_at === confirmed.updated_at, "API repeated confirmation rewrote timestamp");
    const title = article.getByLabel("卡片标题", { exact: true });
    await title.fill(initial.title + "修改");
    await article.getByText("有修改，待重新确认", { exact: true }).waitFor();
    check(await article.getByRole("button", { name: "重新确认", exact: true }).isEnabled(), "Editing did not enable reconfirmation");
    await title.fill(initial.title);
    check(await confirmedButton.isDisabled(), "Reverting still requires confirmation");
    await title.fill(initial.title + "修改");
    failNext = true;
    await article.getByRole("button", { name: "重新确认", exact: true }).click();
    await page.getByText("合成保存失败，请重试", { exact: true }).waitFor();
    await article.getByRole("button", { name: "重新确认", exact: true }).waitFor();
    check(await title.inputValue() === initial.title + "修改", "Failure lost unsaved facts");
    check((await getStored()).title === initial.title, "Failed save changed stored facts");
    await article.getByRole("button", { name: "重新确认", exact: true }).click();
    await confirmedButton.waitFor();
    check(await confirmedButton.isDisabled() && patches === 3, "Retry failed or duplicated");
    await page.reload();
    await open();
    await confirmedButton.waitFor();
    check(await confirmedButton.isDisabled(), "Reload restored a repeat confirmation action");
    check((await getStored()).title === initial.title + "修改", "Reconfirmed facts were not persisted");
    return { status: "passed", patches, checks: ["double click one request", "locked while saving", "confirmed disabled", "API idempotent", "edit and revert", "failure retains facts", "retry and reload"] };
  } finally {
    releaseSave?.();
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("http://127.0.0.1:5173/");
  }
}
