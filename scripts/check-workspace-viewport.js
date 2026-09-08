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
  for (const size of [{ width: 1600, height: 900 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(size);
    for (const [id, name] of modules) {
      await page.getByRole("button", { name: new RegExp(name) }).first().click();
      await page.waitForFunction((moduleId) => document.querySelector(".squirrel-app")?.dataset.activeModule === moduleId, id);
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
  return results;
}
