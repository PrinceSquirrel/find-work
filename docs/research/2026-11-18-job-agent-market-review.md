# 松鼠世界：求职 Agent 竞品与体验调研

调研日期：2026-11-18。状态：研究已整理，所有改进项待用户审批，未改产品代码。

## 1. 结论先行

建议定位为：**面向国内实习与初级岗位、基于真实经历、由本人确认的求职工作台**。这是待验证的定位假设，不是已经证明的市场结论。

优先把“能看懂 → 能用上 → 出错能继续 → 能找到真实投递”做顺，再扩功能。现阶段不建议把松鼠世界做成通用网盘、完整在线 Office 或无人值守海投机器人。

采用价值／成本框架：先看是否阻断核心任务、是否复用现有能力，再看开发和长期维护成本。不使用缺乏真实用户数支持的 RICE 精确分数，也不承诺增加面试率。

## 2. 方法和证据边界

- 核对本仓库 README、现有计划、页面控件、评分、存储、生成和导出代码；基线提交 `5b21966`。没有读取或对外发送用户简历正文，没有调用收费模型或招聘平台。
- 选择 7 个代表产品：国内直接竞品、海外自动化／求职管理工具、可借鉴的简历编辑器。能力以本次读取的官方 README／帮助文档为依据，**未逐个安装实测**，不把官方宣称当成效果验证。
- 反馈样本为 12 个公开页面中的 14 个不同作者的反馈单元：5 条 GitHub Issue、6 条 Simplify 相关帖子／评论、1 条 Huntr 帖子、2 条 Teal 相关帖子。按作者与同一问题去重，跟帖补充不重复计数。13 位自述使用者及 1 位项目成员；身份和实际使用均未独立验证。
- 搜索包含正面使用体验、比较、付费价值及故障，不只搜索差评。排除广告、作者回复、纯提问、无关内容和已删除评论。仍有强烈的自选择、问题报告和英语社区偏差，**不是市场抽样或满意度调查**。
- Reddit 相对时间按页面原样记录，不能当精确日期；2024 等历史评论只说明当时体验，不表示现版仍有同样问题。GitHub 状态以抓取时为准，Issue 的根因分析是报告者说法，本轮未复现。
- 小红书公开搜索未取得可核验评论；抖音发现[求职 Agent 展示](https://www.douyin.com/video/7667156818543627571)和[求职 Skill 展示](https://www.douyin.com/video/7652706371334807278)，但打开时无可读正文／访问失败。仅作为内容线索，**未计入反馈统计、未使用播放点赞量推断需求**。后续若有用户提供的可访问链接或评论导出，可增补国内样本。
- 逐条摘要、作者关系、时间和来源见 [反馈样本 CSV](2026-11-18-feedback-sample.csv)。主题为研究者人工编码，可多标签；小样本不做显著性或因果分析。

## 3. 代表产品对比

| 产品／类型 | 官方文档可确认的设计 | 值得借鉴 | 对松鼠世界的边界 |
| --- | --- | --- | --- |
| [BossHunter](https://github.com/shengjidaguai-china/BossHunter)／国内直接竞品 | 多平台采集、评分、人工确认、回复监测；不同平台能力分开说明 | 展示“哪个平台能做什么”；异常停止和连接诊断 | 人工确认和本地运行并非独家。其为 PolyForm 非商业许可的源码可用项目，不能按 MIT 项目直接搬用代码 |
| [OpenJob](https://github.com/Batianxieshen1/OpenJob)／国内直接竞品 | 今日待办、去重、评分理由、确认队列、Word 底稿改写；平台能力矩阵 | 每日待办和原文／改写对照；减少重复岗位 | README 功能、演示图不等于大量用户验证。只借工作流，不复制整套复杂模块 |
| [AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent)／搜索及表单自动化 | 简历驱动搜索、用户选择后处理申请、记录页面结果 | 清楚的步骤、显式选择、结果证据 | 海外表单和数据源不能直接替代 BOSS／实习僧。当前仓库并未归档；勿沿用旧测评中的“停止维护”结论 |
| [Simplify Copilot](https://simplifyjobs.featurebase.app/help/articles/8686025-manage-copilot-autofill-settings)／申请填写助手 | 可逐类关闭填充，使用档案生成回答，支持的多页表单连续填写；该 Copilot 流程仍由用户提交 | 可控字段、人工接管、少重复输入 | 不把该帮助页的边界扩大成“整个 Simplify 没有自动申请产品”；不建设一个全站通用填写插件 |
| [Teal](https://help.tealhq.com/en/articles/14435727-how-to-track-your-job-applications)／求职管理 | 保存 JD、阶段、跟进日期、备注、联系人及所用简历 | 岗位详情做统一入口；知道下一步和当时用了哪个版本 | 无需再新建一套材料库、联系人 CRM；先复用现有岗位和材料版本 |
| [Huntr](https://help.huntr.co/en/articles/10089169-contacts-and-documents)／求职管理 | 联系人与岗位关联，资料统一归类存放 | 让资料跟着岗位走，而不是让用户在模块间寻找 | 暂不做复杂人脉图谱；你的真实行动证明比漂亮漏斗更应保留 |
| [Reactive Resume](https://github.com/reactive-resume/reactive-resume)／相邻编辑工具 | 文档预览、可接受／拒绝的修改、版本、PDF／DOCX／Markdown／JSON 导出 | 可带走的可编辑文件和前后差异 | 你已有 PDF 和人工核验，不重建全能编辑器；先评估简单 DOCX 导出 |

以上仅为能力比较，不以 GitHub Star 代替活跃用户或产品质量，不比较未经核验的付费价格。BossHunter／OpenJob 对平台风险也有明确告知；保守节奏不能保证不受平台限制。

## 4. 公开反馈：实际读到了什么

14 个单元的主题计数如下。同一个单元可归入多个主题，因此不能相加成用户总数；频数不代表市场发生率。

| 主题 | 样本内单元数 | 样本 ID | 对产品的启发 |
| --- | ---: | --- | --- |
| 连接／自动化可靠性 | 4 | F01 F03 F06 F08 | 出错说明和手工继续路径，比增加自动化范围更重要 |
| 数据正确性／时效 | 4 | F02 F04 F05 F07 | 未知不能冒充不符合；日期、地点、公司和岗位上下文要可核对 |
| 人工改写／定制价值 | 4 | F07 F09 F10 F12 | 保留定制，但让人快速检查，避免反复重写 |
| 组织与跟进 | 3 | F12 F13 F14 | 可查找的记录和下一步有价值，复杂生成并非唯一价值 |
| 成本／可替代性 | 4 | F10 F11 F12 F13 | 用户会拿工具与手工／通用 AI 比；要量实际省时，不堆 AI 名称 |
| 地域适配 | 1 | F11 | 海外站点反馈不可直接外推国内，明确支持范围 |

具体例子与正反证据：

- **可靠性**：BossHunter 的[验证码报告](https://github.com/shengjidaguai-china/BossHunter/issues/235)描述无法取得岗位；其[Windows 连接报告](https://github.com/shengjidaguai-china/BossHunter/issues/47)来自项目成员，已关闭，不能当成仍未修复的用户差评。Simplify 用户也报告[常用回答不再复用](https://www.reddit.com/r/simplify/comments/1vzvm4b/help_simplify_copilot_stopped_learning_and/)。
- **信息和筛选**：[工资解析报告](https://github.com/shengjidaguai-china/BossHunter/issues/198)和[时间筛选报告](https://github.com/shengjidaguai-china/BossHunter/issues/317)提示错误过滤会比少一个功能更伤体验；AIHawk 的[数据更新报告](https://github.com/feder-cr/Jobs_Applier_AI_Agent/issues/1552)说明“没有结果”也可能是数据陈旧，而非没有合适岗位。
- **自动化不是越多越好**：一位 Simplify 用户同时肯定省时，又报告[公司名和是非题填错](https://www.reddit.com/r/simplify/comments/1qyzh17/ai_not_working_i_dont_have_it_enabled/)；另一帖子反映[定制表单兼容性](https://www.reddit.com/r/cscareerquestions/comments/1t650zw/simplify_vs_careerflow_autofill_both_free_tier/)。这支持保留你的审核闸门，而非取消人工确认。
- **定制有价值，也有修订成本**：[同一讨论](https://www.reddit.com/r/csMajors/comments/1aier4e/does_anyone_use_simplify_premium_is_it_worth/)中，三位不同作者分别表示仍需手改、认为定制有帮助、在德国网站适配差。不能只挑正面成功故事，也不能把某人的拿 Offer 归因为产品。
- **结果承诺要克制**：[Huntr 使用者](https://www.reddit.com/r/HuntrCo/comments/1pzydtq/my_results_after_over_8_months_of_using_huntr/)认为生成文字需精简，对长期付费和取消后的数据可用性不满，也承认起步帮助；这是个人经验，不证明工具导致求职失败。[Teal 用户](https://www.reddit.com/r/jobmarket/comments/1v3laea/is_teal_worth_paying_for_if_you_already_use/)认可记录功能但怀疑 AI 相对通用工具的增量；[另一用户](https://www.reddit.com/r/remotejobsfinders/comments/1tgzfnz/the_job_search_tools_i_actually_kept_after_trying/)肯定整理、备注和日常任务的帮助。相关线程含推广回复，本研究不计入。

## 5. 你的产品：保留什么，真正缺什么

### 已有优势，不再重复建设

1. 资料原文定位 → 草稿事实 → 人工确认 → 生成内容核验 → 定稿导出，已有严格链路。应把“可核对”变得易用，而不是再增加一个相同生成模块。证据：`backend/app/services/evidence_service.py:137`、`:188`、`:310`；`frontend/src/lib/studio.ts:11`。
2. 只有平台证明支持的真实动作才产生新投递记录；批量删除有保护和二次确认。继续保留，不用海投数量粉饰成果。证据：`README.md:7`、`backend/tests/test_bulk_records.py`。
3. 已有一键启动、CDP 启动、系统健康、模型测试、显式本地提取，不应将这些现成功能包装成“从零新增”。证据：`README.md:53`、`:71`。
4. 已有匹配理由／缺口、材料历史、手动补全现有岗位 JD、模板 PDF 导出。建议均是增量改善，不是重新发明。证据：`backend/app/services/job_application_service.py:291`、`:487`；`frontend/src/App.tsx:3028`、`:3097`。

### 当前明确缺口

| 缺口 | 本仓库依据 | 体验影响与建议 |
| --- | --- | --- |
| 控件看得到但不可用 | `frontend/src/ApplicationTrackingControls.tsx:26`、`:49`；`frontend/src/lib/materials.ts:78` | 先兑现筛选／分页；其他计划能力明确次级展示，不假装已支持 |
| 首次路径分散 | 现成启动、上传、连接、提取、设置位于不同入口；上轮状态记录上传成功但模型 401 | 复用已有检查，按任务给下一步；已保存与提取失败分开，不能让用户重复上传。401 为 11 月 17 日记录，本轮未重新验证外部 Key |
| 匹配还不等于“我想去” | `backend/app/agents/job_match.py:8` 固定技能词；`job_application_service.py:291` 同时有外部评分与规则回退 | 以后补少量求职偏好和否决条件；显示数据来源／缺失，不把分数解释成录取概率。不能声称现在“只有关键词评分” |
| 只有已有岗位能手补 JD | `job_application_service.py:487`；`storage.py:1246` 每轮直接写入岗位 | 可评估手动粘贴新 JD 的兜底与 URL 去重，不能把当前“有去重”或“完全无手动能力”说错；候选资料不冒充真实投递 |
| 产物编辑与跟进不足 | `backend/app/main.py:444` 有 PDF 导出；`schemas.py:178` 无下一次跟进日期字段 | 简单 DOCX 和本地下一步待办可评估；不要先集成完整 WPS、邮件监听或日历双向同步 |
| 旧计划容易误读现状 | `docs/MATERIAL_WORKSPACE_PLAN.md` 的早期边界仍写未持久化，但 README／当前代码已实现部分上传 | 批准后对齐能力与计划，保留历史标注，不直接覆盖你已确认的两页布局 |

### 我的体验判断／待验证假设（不是用户评论）

- 新用户可能把资料卡、基础简历、定制简历混淆；应显示“此步为什么需要、后续会用在哪里”。
- 每条先核事实、生成后再核句子可能有重复负担；先测每次审核耗时，再优化为聚焦新增／修改部分，**不取消事实确认**。
- 同等匹配分不代表都值得投：到岗时间、每周天数、城市和岗位方向可能比某个技能关键词更重要。未提供信息要标“待确认”，不自动淘汰。
- 一屏应是“核心任务一屏”，不是把全部材料、事件和高级设置挤成小字；保留内部滚动／抽屉。沿用用户最终要求：侧栏常驻，仪表盘和资料页保持已恢复布局。
- 不再新增一个“AI 对话助手”页面与现有表单并存；先改善具体任务按钮和下一步。品牌保持森林绿／奶油白／松鼠，不继续做无必要换肤。

## 6. 投入取舍与待审批建议

优先范围、估时、验收与放弃项见 [迭代审批单](2026-11-18-iteration-proposal.md)。推荐先批 **A 包：能力边界对齐＋任务引导＋真实筛选分页**，合计约 5–8 人日，含约 20% 缓冲；单人配合 AI、每日约 6 小时有效开发，含测试／文档，不是交付日期承诺。外部账号、付费授权与平台变化另计。

后续 DOCX、手动 JD 导入、偏好、跟进待办先保留候选；暂缓完整 WPS、全格式解析、音视频、更多平台自动发送和复杂面试数字人。原因是当前缺少足够使用证据，维护成本高，未证明比顺畅完成一次真实求职任务更有价值。

确认加入计划前，建议先用合成资料完成固定任务基线，再在用户同意后找 3–5 位目标使用者观察：首个完整流程时间、无帮助完成率、错误后能否继续、找到指定投递所需时间。研究招募、录屏和外部发送都需要另行授权，本轮没有执行。

**用户未批准前不修改旧实施计划的批准状态，不排开发日期，不进入功能实现。**
