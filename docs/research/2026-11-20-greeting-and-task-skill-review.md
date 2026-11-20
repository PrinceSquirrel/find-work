# 松鼠世界：招呼语、岗位评分与任务规则调研

调研日期：2026-11-20。复核了公开的高校就业指南、招聘平台资料、竞品文档及用户 Issue。没有安装竞品或联系招聘者，也没有取得可代表全市场的评论样本；以下为可验证的设计依据，不是回复率或面试率结论。

## 招呼语：招聘者为什么需要这些信息

- [东南大学求职沟通指南](https://em.seu.edu.cn/2020/0425/c9304a325678/page.htm)要求迅速说清身份和意向、按岗位选相关真实经历。它讨论的是邮件；本项目借用信息顺序，不搬用邮件标题、署名、长自述和联系方式。
- [小红书公开实习岗位](https://job.xiaohongshu.com/campus/intern/position/20506?referer_code=NUX4SLO4SHA6)是招聘方要求的实例：毕业年度、学位和每周出勤、实习周期可能是硬条件。不能外推到所有岗位，但这些确实是实习初聊中值得前置的内容。
- [BOSS 官方南北阁说明](https://stardustlm.zhipin.com/agreement/protocol)已提供按人岗匹配生成招呼语和开场问题建议；[CaiMaster-BossQuickApply 公共文档](https://github.com/ZionCai/CaiMaster-BossQuickApply)也描述了结合 JD／简历生成、可编辑重写。因此「AI 写一句招呼」不是差异点。松鼠世界应该把重点放在确认真实身份、每岗只用最相关事实，以及能核对是否发送了自己审核的原文。
- [抖音公开求职视频索引](https://www.douyin.com/shipin/7313023683889760290)可找到“按岗位描述写相关经历、不要照搬默认文案”的用户自述；样本不能证明因果。未取得足够可核对的小红书笔记评论；小红书证据仅采用其官方岗位文本，不用点赞量、视频标题或“回复率 100%”宣传当结论。

采用的消息结构：**问候 → 真实届别／学校／专业／学历 → 明确岗位及一项具体职责 → 一条已核验的本人行动 →（确有且相关时）到岗安排 → 一个便于回复的下一步**。身份、出勤由本人确认后在本地拼接；无证据只说对职责感兴趣，不虚构经历、成果、到岗日期或发送状态。公司宣传、无关技能堆砌、电话和邮箱不进入默认模板。

例如：「您好，我是2028届某大学管理科学与工程专业硕士研究生。对贵司实习岗位中的用户访谈工作感兴趣。方便交流一下这部分的工作安排吗？」若已有真实的访谈行动或可出勤安排，可在确认后加入；不能拿例句当成任何用户的实际经历。

## 其他任务：借鉴后怎么改

| 环节 | 资料依据 | 松鼠世界的规则 |
| --- | --- | --- |
| 岗位搜索、读 JD | [BossHunter 验证码 Issue](https://github.com/shengjidaguai-china/BossHunter/issues/235)、[薪资解析 Issue](https://github.com/shengjidaguai-china/BossHunter/issues/198)是单个实际报告，不证明普遍性 | 列表摘要不是完整 JD；无内容、仍在加载和平台阻断分别处理，未知福利和薪资不猜、不扩大全站抓取。 |
| 个人评价、简历匹配 | [LinkedIn 推荐说明](https://www.linkedin.com/help/linkedin/answer/a512279/)区分用户偏好和档案匹配；[CareerOneStop 工作价值工具](https://cloudfront.careeronestop.org/ExploreCareers/Assessments/work-values.aspx)、[O*NET 工作时间](https://www.onetonline.org/find/descriptor/result/4.C.3.d.8)将工作环境和工时作为独立维度 | 简历匹配只衡量有证据的资格和技能。六个个人维度由本人设置重要度和满意度；未披露不是差，显示覆盖。不自动换算日薪与月薪，也不把分数变成录用率。 |
| 事实抽取、生成和复核 | [俄勒冈州立大学简历定制指南](https://writingcenter.oregonstate.edu/tailoring-your-resume)、[MIT 简历指导](https://capd.mit.edu/resources/career-toolkit-crafting-an-effective-resume/)都强调按职责挑真实证据，而非照抄关键词 | 抽取时区分角色、本人行动、团队贡献和结果。生成时按必要条件/核心职责/加分项取舍；没有数据不给数字，有疑问显式留缺口。改动后重新核验。 |
| 引导、跟踪和人审 | [Simplify 表单控制](https://simplifyjobs.featurebase.app/help/articles/8686025-manage-copilot-autofill-settings)、[Teal 投递记录文档](https://help.tealhq.com/en/articles/14435727-how-to-track-your-job-applications) | 优先给一个下一步，沿用现有材料与版本；发送、已读、回复、推进分别处理，不把打开会话、生成或导出算成投递。 |

## 工期与实际提效

- 采用：一次确认身份、多岗位复用；继续沿用现有 JD 和资料卡，避免多一次模型调用；浏览器内即可设置评分，不引入偏好数据库或新生产依赖。
- 限定：发送只面向用户已审核的 BOSS 文案，按批次逐个执行。出现目标不符或未知结果就停止。原生开聊可能有平台默认动作，不去改变平台流程，不绕过验证和规则。其他平台先保留手工发送，真实兼容性不以合成测试冒充。
- 暂不做：无监督海投、自动发送附件、统一解析各种薪资周期、通过重复模型调用推测福利/工时、自动催回复。它们需要更多平台适配、反复维护或会带来错误触达，现阶段收益没有实测依据。

后续如要评估实际收益，可让用户自己选择少量真实岗位，比较“首次打开 JD 到确认草稿”的用时、需改动的草稿比例、发错/重复/未确认数；样本足够前不做回复率承诺。
