// Run with playwright-cli run-code --filename scripts/check-workspace-viewport.js.
// Read-only browser regression: never starts searches, uploads or model requests.
async (page) => {
  const results = [];
  const modules = [
    ["dashboard", "仪表盘"], ["materials", "资料工作台"],
    ["jobs", "岗位雷达"], ["studio", "生成中心"],
    ["applications", "投递跟踪"], ["settings", "系统设置"],
  ];
  await page.goto("http://127.0.0.1:5173/");
  await page.setViewportSize({ width: 1600, height: 900 });
  const sidebar = page.getByRole("complementary", { name: "主导航" });
  const tools = sidebar.locator('[aria-label="工作台工具"]');
  if (await tools.getByRole("button").count() !== 2 ||
      !await sidebar.getByText("本地用户", { exact: true }).isVisible()) {
    throw new Error("Account and utility controls are not in navigation");
  }
  const search = page.getByRole("searchbox", { name: "搜索松鼠世界功能" });
  await search.fill("岗位");
  if (await page.locator(".home-feature-card").count() !== 1) throw new Error("Home search did not filter features");
  await page.locator(".home-feature-card").click();
  await page.waitForFunction(() => document.querySelector(".squirrel-app")?.dataset.activeModule === "jobs");
  await sidebar.getByRole("button", { name: "仪表盘", exact: true }).click();
  await search.fill("不存在的功能");
  await page.getByRole("status").filter({ hasText: "没有匹配的首页功能" }).waitFor();
  await search.fill("");
  if (await page.locator(".home-feature-card").count() !== 4) throw new Error("Product introduction did not reset");
  if (await page.locator(".pipeline-panel:visible, .recent-actions:visible").count() ||
      await page.getByRole("heading", { name: "最近动作", exact: true }).isVisible()) {
    throw new Error("Removed overview blocks are still on home");
  }
  for (const [, name] of modules.slice(1)) {
    const button = sidebar.getByRole("button", { name, exact: true });
    await page.mouse.move(1200, 10);
    const before = await button.evaluate(element => getComputedStyle(element).backgroundColor);
    await button.hover();
    await page.waitForFunction(({ name, before }) => {
      const element = document.querySelector(`.workspace-nav-button[aria-label="${name}"]`);
      return getComputedStyle(element).backgroundColor !== before;
    }, { name, before });
  }
  results.push({ requirement: "home search, product guide, relocated controls, navigation hover", status: "passed" });
  for (const size of [{ width: 1600, height: 900 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(size);
    for (const [id, name] of modules) {
      await page.getByRole("button", { name: new RegExp(name) }).first().click();
      await page.waitForFunction((moduleId) => document.querySelector(".squirrel-app")?.dataset.activeModule === moduleId, id);
      await page.mouse.move(size.width - 3, 3);
      const nav = await sidebar.boundingBox();
      if (!nav || nav.x < -1 || nav.width < 200 || nav.y < -1 || nav.height < size.height - 1) {
        throw new Error("Persistent desktop navigation is not visible: " + id);
      }
      if (!(await page.title()).includes(name + " · 松鼠世界")) throw new Error("Unbranded page title: " + id);
      const brand = await page.evaluate(() => {
        const logo = document.querySelector(".squirrel-brand img");
        const css = getComputedStyle(document.body);
        return { loaded: logo.complete && logo.naturalWidth > 0, background: css.backgroundImage,
          green: css.getPropertyValue("--green-deep").trim() };
      });
      if (!brand.loaded || brand.green !== "#123f38" || !brand.background.includes("radial-gradient")) {
        throw new Error("Shared forest theme or logo missing: " + id);
      }
      const card = page.locator(id === "materials" ? ".material-tool-card:visible" : ".module-panel.panel:visible").first();
      const original = await card.evaluate(element => getComputedStyle(element).boxShadow);
      await card.hover();
      await page.waitForFunction(({ selector, original }) => {
        const element = [...document.querySelectorAll(selector)].find(item => item.getBoundingClientRect().height > 0);
        return element && getComputedStyle(element).boxShadow !== original;
      }, { selector: id === "materials" ? ".material-tool-card" : ".module-panel.panel", original });
      await page.mouse.move(size.width - 3, 3);
      const layout = await page.evaluate(() => {
        const root = document.documentElement;
        const visible = (element) => element.getBoundingClientRect().height > 0;
        const panels = [...document.querySelectorAll(".module-panel, .workspace-page-heading, .dashboard-hero, .home-feature-intro, .dashboard-metrics")]
          .filter(visible).map((element) => {
            const rect = element.getBoundingClientRect();
            return { name: element.className, top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right };
          });
        return { width: root.scrollWidth, height: root.scrollHeight, panels };
      });
      if (id === "dashboard" || id === "materials") {
        const heroHeight = await page.locator(id === "dashboard" ? ".dashboard-hero" : ".workspace-page-heading").evaluate(element => element.getBoundingClientRect().height);
        if (heroHeight < 180) throw new Error("Restored page was compacted: " + id);
        if (layout.width > size.width + 1) throw new Error("Restored page has horizontal overflow");
        results.push({ module: id, viewport: size, status: "original-layout-passed" });
        continue;
      }
      if (layout.width > size.width + 1 || layout.height > size.height + 1 ||
          layout.panels.some((panel) => panel.top < 0 || panel.bottom > size.height + 1 || panel.right > size.width + 1)) {
        throw new Error(JSON.stringify({ id, size, layout }));
      }
      if (await page.getByRole("button", { name: /Agent 运行/ }).count()) throw new Error("Internal Agent page is still exposed");
      for (let i = 0; i < layout.panels.length; i++) {
        for (const other of layout.panels.slice(i + 1)) {
          const panel = layout.panels[i];
          const overlapX = Math.min(panel.right, other.right) - Math.max(panel.left, other.left);
          const overlapY = Math.min(panel.bottom, other.bottom) - Math.max(panel.top, other.top);
          if (overlapX > 1 && overlapY > 1) throw new Error("Overlapping modules: " + panel.name + " / " + other.name);
        }
      }
      if (id === "applications") {
        const footer = await page.locator(".application-pagination").boundingBox();
        if (!footer || footer.y + footer.height > size.height) throw new Error("Pagination is outside viewport");
      }
      results.push({ module: id, viewport: size, status: "passed" });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [id, name] of modules) {
    await sidebar.getByRole("button", { name, exact: true }).click();
    await page.waitForFunction(moduleId => document.querySelector(".squirrel-app")?.dataset.activeModule === moduleId, id);
    const nav = await sidebar.boundingBox();
    if (!nav || nav.y < 700 || nav.y + nav.height > 845 || nav.width > 391 ||
        await page.evaluate(() => document.documentElement.scrollWidth) > 391) {
      throw new Error("Mobile navigation or width regression: " + id);
    }
  }
  results.push({ requirement: "six mobile modules and bottom navigation", status: "passed" });
  return results;
}
