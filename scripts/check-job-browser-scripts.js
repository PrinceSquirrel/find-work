// The DOM and fetch responses are synthetic. Never navigate a real recruitment account.
async (page) => {
  const origin = "http://127.0.0.1:8768";
  const identity = await (await page.request.get(origin + "/__workspace_bug_identity")).json();
  if (identity.fixture !== "temporary-workspace-bug-check") throw new Error("Wrong fixture");
  const scripts = await (await page.request.get(origin + "/__job_scripts")).json();
  await page.route("**/job_detail/**", route => route.fulfill({ contentType: "text/html", body: "<html><title>SPA shell</title><body></body></html>" }));
  const check = (value, message) => { if (!value) throw new Error(message); };
  await page.goto(origin + "/job_detail/synthetic.html");
  await page.evaluate(() => {
    setTimeout(() => { document.body.innerHTML = '<h1 class="job-name">合成产品岗位</h1><section class="job-sec-text">岗位职责：' + '负责需求分析、用户调研和产品设计。'.repeat(12) + '</section>'; }, 300);
  });
  const detail = await page.evaluate(scripts.detail);
  check(detail.detail_status === "detail_fetched" && detail.description.includes("需求分析"), "Rendered JD not read");
  await page.setContent('<div class="job-sec-text">请完成安全验证</div><p>请完成安全验证</p>');
  check((await page.evaluate(scripts.detail)).detail_status === "detail_blocked", "Verification not respected");
  await page.goto(origin + "/job_detail/synthetic.html");
  await page.setContent('<div id="list" class="job-list" style="height:120px;overflow:auto"><div style="height:5000px"><article class="job-card-wrapper"><a href="/job_detail/1.html">岗位1</a><span class="company-name">合成公司</span><b class="salary">200-300元/天</b></article></div></div>');
  await page.evaluate(() => {
    let index = 1;
    document.querySelector('#list').addEventListener('scroll', () => {
      index++;
      const card = document.querySelector('article');
      card.querySelector('a').href = `/job_detail/${index}.html`;
      card.querySelector('a').textContent = `岗位${index}`;
    });
  });
  const extracted = await page.evaluate(scripts.extract);
  check(extracted.jobs.length >= 5 && new Set(extracted.jobs.map(job => job.url)).size === extracted.jobs.length, "Virtual scrolling lost or duplicated cards");
  check(extracted.jobs.some(job => job.url.includes('/1.html')), "Initial virtual card lost");
  await page.setContent('<div id="list" class="job-list" style="height:120px;overflow:auto"><div style="height:5000px"><article class="job-card-wrapper"><a href="/job_detail/1.html">岗位1</a><span class="company-name">合成公司</span></article></div></div>');
  await page.evaluate(() => document.querySelector('#list').addEventListener('scroll', () => document.body.append('请完成安全验证'), { once: true }));
  const interrupted = await page.evaluate(scripts.extract);
  check(interrupted.jobs.length === 0 && interrupted.diagnostics.page_state === 'blocked', "Scrolling continued into a verification screen");
  await page.setContent('<div class="btn btn-startchat-wrap">感兴趣 <a class="btn btn-startchat">立即沟通</a></div>');
  await page.evaluate(() => {
    window.syntheticClicks = 0;
    document.querySelector('a').onclick = () => { window.syntheticClicks++; setTimeout(() => document.body.append('已发送'), 900); };
  });
  const preview = await page.evaluate(scripts.preview);
  check(preview.ready && preview.button_text === '立即沟通', "Preflight picked wrapper text");
  const sent = await page.evaluate(scripts.apply);
  check(sent.confirmed && await page.evaluate(() => window.syntheticClicks) === 1, "Leaf click and delayed sending proof failed");
  await page.setContent('<div class="btn">感兴趣 <a class="btn">立即沟通</a></div>');
  await page.evaluate(() => { document.querySelector('a').onclick = () => document.body.append(document.createElement('textarea')); });
  const chat = await page.evaluate(scripts.apply);
  check(!chat.confirmed && chat.status === 'chat_opened_unconfirmed', "Open chat was saved as sent");
  await page.setContent('<p>请完成安全验证</p><a class="btn">立即沟通</a>');
  const blocked = await page.evaluate(scripts.apply);
  check(!blocked.confirmed && blocked.status === 'blocked_by_platform', "Apply ignored platform verification");
  await page.route("**/api/platform-sessions", route => route.fulfill({ json: { browser_connected: true, cdp_url: origin, sessions: [{ platform: "boss", status: "tab_detected", tab_detected: true, detail: "已检测到标签页", url: "https://www.zhipin.com/job_detail/" + "long-job-identifier".repeat(20) + ".html" }] } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("http://127.0.0.1:5173/");
  await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
  await page.locator('.platform-session').first().waitFor();
  check(await page.evaluate(() => document.documentElement.scrollWidth) <= 391, "Long platform link overflowed mobile page");
  return { status: "passed", checks: ["hydrated JD instead of HTML shell", "verification stops", "virtual DOM reuse snapshots", "dedup and bounded scrolling", "leaf button not wrapper", "delayed proof one click", "chat is not sent", "apply verification stop"], collected: extracted.jobs.length };
}
