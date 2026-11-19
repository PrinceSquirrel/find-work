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
  return { status: "passed", checks: ["hydrated JD instead of HTML shell", "verification stops", "virtual DOM reuse snapshots", "dedup and bounded scrolling"], collected: extracted.jobs.length };
}
