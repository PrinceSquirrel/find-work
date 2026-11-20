async (page) => {
  const jobs = [401, 402].map((id, index) => ({ id, search_run_id: 1, platform: "boss", title: `合成批量岗位${id}`, company: "合成公司",
    city: "上海", salary: "面议", description: index ? "数据分析" : "用户访谈", url: `https://www.zhipin.com/job_detail/synthetic-${id}.html`,
    detail_status: "detail_fetched", created_at: "2026-11-20T00:00:00Z",
    match: { score: 80, recommendation: "strong_apply", hit_reasons: [], gap_reasons: [] } }));
  let preparations = 0;
  let submissions = 0;
  const reviewedText = "您好，我审核了用户调研的内容。\n方便交流吗？";
  const check = (value, message) => { if (!value) throw Error(message); };
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/jobs") return route.fulfill({ json: jobs });
    if (path === "/api/applications") return route.fulfill({ json: [] });
    if (path === "/api/job-batches/greetings") {
      preparations++;
      check(JSON.stringify([...request.postDataJSON().job_ids].sort()) === "[401,402]", "Incorrect greeting selection");
      return route.fulfill({ json: { items: jobs.map(job => ({ job_id: job.id, status: "ready", mode: "local", text: "您好，想交流：" + job.description })) } });
    }
    if (path === "/api/job-batches/send-greetings") {
      submissions++;
      check(JSON.stringify(request.postDataJSON()) === JSON.stringify({items: [{job_id: 401, text: reviewedText}], confirmed: true}), "Did not send the exact approved text");
      return route.fulfill({ json: { items: [{ job_id: 401, status: "unknown", message: "未取得证明，已暂停。" }] } });
    }
    if (request.method() !== "GET") throw Error("Unexpected write " + path);
    return route.continue();
  });
  try {
    await page.goto("http://127.0.0.1:5173/");
    await page.getByRole("button", { name: "岗位雷达", exact: true }).click();
    await page.getByRole("checkbox", { name: /选择岗位 #401/ }).check();
    await page.getByRole("checkbox", { name: /选择岗位 #402/ }).check();
    await page.getByRole("button", { name: "准备招呼语／批量投递（2）" }).click();
    const panel = page.getByRole("dialog", { name: "招呼语与批量投递" });
    await panel.getByRole("button", { name: "一键生成各岗位招呼语" }).click();
    await panel.getByText("已为 2 个岗位生成草稿；没有发出任何消息。").waitFor();
    check(preparations === 1 && submissions === 0, "Preparation sent a message");
    check((await panel.getByRole("textbox", { name: "合成批量岗位401招呼语" }).inputValue()).includes("用户访谈"), "Wrong JD for first draft");
    check((await panel.getByRole("textbox", { name: "合成批量岗位402招呼语" }).inputValue()).includes("数据分析"), "Wrong JD for second draft");
    await panel.getByRole("checkbox", { name: /我确认/ }).check();
    await panel.getByRole("region", { name: "合成批量岗位402" }).getByRole("checkbox", { name: "加入发送" }).uncheck();
    const submit = panel.getByRole("button", { name: "发送 1 条招呼语" });
    check(await submit.isDisabled(), "Changing selections did not invalidate approval");
    await panel.getByRole("checkbox", { name: /我确认/ }).check();
    await panel.getByRole("textbox", { name: "合成批量岗位401招呼语" }).fill(reviewedText);
    check(await submit.isDisabled(), "Editing the greeting did not invalidate approval");
    await panel.getByRole("checkbox", { name: /我确认/ }).check();
    await submit.evaluate(node => { node.click(); node.click(); });
    await panel.getByText("未取得证明，已暂停。", { exact: false }).waitFor();
    check(submissions === 1 && await submit.isDisabled(), "Result error triggered duplicate action");
    await panel.getByRole("button", { name: "关闭", exact: true }).click();
    await panel.waitFor({ state: "hidden" });
    return { passed: true, checks: ["different JD drafts", "explicit approval", "approval resets on selection and edit", "exact edited text", "single request", "unconfirmed result"] };
  } finally {
    await page.unrouteAll({ behavior: "wait" });
  }
}
