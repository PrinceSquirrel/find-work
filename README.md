# 松鼠世界（agent-business）

![松鼠世界 Logo](outputs/squirrel-world-logo-20260903/squirrel-world-logo-v2-512.png)

本项目是一个本地单用户求职投递多 Agent 工作台。它把简历解析、真实浏览器 CDP 岗位搜索、岗位匹配、简历改写、招呼语生成、真实平台投递确认、投递状态跟踪、LLM token/金额统计和投递数据分析串成一条可验证的工作流。

当前项目保留 demo 模式用于自动化测试。真实工作流使用用户本机启动、由本人登录的 CDP 浏览器。搜索、提取和预检为只读；原生沟通／投递或发送审核后的 BOSS 招呼语必须由本人确认。投递记录只在平台返回确认信号后入库，并保存结构化 `platform_proof`。

## 架构概览

- 后端：FastAPI，入口为 `backend/app/main.py`。
- 数据：SQLite，本地默认路径为 `data/agent-business.sqlite3`。
- Agent：`backend/app/agents/` 中按职责拆分，包括简历解析、岗位匹配、简历改写、招呼语、投递状态、审核和指标统计。
- 平台适配器：`backend/app/platforms/` 保留 Boss 直聘和实习僧的 demo adapter；真实平台能力由 `backend/app/services/browser_job_extractor_service.py` 通过 CDP 控制已登录浏览器页面完成。
- 服务编排：`backend/app/services/job_application_service.py` 串联简历、岗位、改写、投递和分析流程。
- 测试：`backend/tests/`，使用 demo/fake CDP 数据、临时 SQLite 和本地 token 估算；自动测试不访问真实招聘平台账号。
- 前端：`frontend/` 提供“松鼠世界”模块化本地工作台，使用 Vite + React。

## 怎么用：匹配分、生成中心与批量操作

- **岗位雷达**：系统匹配分比较简历与 JD，本地规则以 35 为基础分，重点技能命中加 10 分、重合词项每项加 4 分，上限 100；没有重点命中时最高 45 分，缺口至少 4 项再扣 10 分。有效的岗位匹配模型可根据职责修正参考分。点「查看要求」或「放大阅读」可看完整 JD 和「我的岗位评分」：对工资、福利、地区、工作时长、工作内容、技能匹配分别给重要度和该岗位的满意度，未评项不参与加权，评分 0 不等于未评。重要度跨岗位复用；评分只保存在当前浏览器。可选择「按我的评分」排序，不改原系统匹配、不触发投递。
- **生成中心**：给一个岗位准备定制简历和招呼语，修改后需要重新核对再定稿导出。只要招呼语时点「只写招呼语」，无需生成整份简历。
- **批量发送**：在岗位雷达勾选尚无投递记录的岗位（每批 1–8 个），点「准备招呼语／批量发送」。在「我的招呼开场」确认一次真实身份及可选到岗安排，之后本地复用，不交给外部模型。生成使用每份完整 JD 和已确认事实；模型报错逐项显示，无有效模型时标明本地草稿。核对、编辑正文并勾选确认后，BOSS 队列才尝试进入对应聊天发送原文；未确认不发，修改后必须重新确认。只记录匹配会话中有回执的本人出站原文，不代发简历附件；其余平台可复制后手动发送。
- **平台边界**：首次点击平台沟通入口可能有平台自己的开聊动作，松鼠世界不能替换平台的默认行为，也不绕过验证码、登录或限额。没有可核对的会话或出站回执，就暂停后续项；未知结果已留防重标记，请到原会话核对，不要直接重发。批量发送不是 BOSS 官方集成；测试使用隔离会话，不保证所有真实账号、页面变体均可发送。
- **模型设置**：保存并测试主模型后，在「按任务查看实际模型与连接」查看匹配或材料任务。无独立配置时沿用主模型。独立配置缺 Key 时，只有服务商和 API 地址一致才可使用主模型 Key。档案、主模型和任务配置是不同对象；档案可由服务端直接套用，不必在网页反复粘贴密钥。任务级「测试此任务」检查实际生效的配置；本地解析、核验和操作不依赖模型。
- **任务技能**：业务任务说明和执行器集中在 `backend/app/services/task_skills.py`，`GET /api/skills` 可查。匹配、抽取、改写和招呼语请求分别加载对应规则；解析、核验和平台操作按程序规则执行，模型不能发送。依据与取舍见[求职技能调研与修改记录](docs/research/2026-11-20-greeting-and-task-skill-review.md)。

## 工作台模块

- **仪表盘**：Token、费用与系统状态概览，不再混放求职漏斗和最近动作。
- **资料工作台**：统一展示资料上传、在线预览、OCR 识别和 WPS 在线编辑入口；DOCX/PDF/TXT/MD/PNG/JPG/JPEG 已接入资料检查和事实确认，其他格式处理服务按 `docs/MATERIAL_WORKSPACE_PLAN.md` 分阶段接入。
- **岗位雷达**：岗位搜索、筛选和详情核验。
- **生成中心**：单个入口生成证据材料，在同一结果区切换简历/招呼语、编辑、审核、定稿和导出；支持历史版本与刷新恢复。实施记录见 [生成中心精简计划](docs/STUDIO_SIMPLIFICATION_PLAN.md)。
- **投递跟踪**：森林主题进度概览、左侧结果表与右侧转化/时段统计；岗位／关键词／来源地点组合筛选和 25／50／100 条服务端分页已接通。换条件或换页清空勾选，批量删除只处理当前页选中记录；漏斗／转化／时段仍明确统计全部投递。接口与边界见 [投递跟踪实施计划](docs/APPLICATION_TRACKING_PLAN.md)。
- **系统设置**：模型、API、CDP 和系统能力检查。

桌面端导航固定显示在左侧，主内容区会为导航预留空间；移动端自动切换为底部导航。首页包含产品说明、功能搜索和四个快捷入口。

用户界面保留以上六个模块，已移除 Agent 运行页面，后台 Agent、用量统计和任务执行仍保留。按用户最后确认，仪表盘和资料工作台已恢复原布局；其余四页在桌面视口宽度大于 1100px、高度至少 600px 时使用一屏工作区，长记录、展开详情和超长表单在卡片内部滚动。小屏保留自然滚动，不缩放整页。各页统一森林绿、奶油白与松鼠标识，导航和主要卡片支持悬停高亮。

桌面布局回归（先启动项目）：运行 `npx --yes --package @playwright/cli playwright-cli -s=workspace-check open http://127.0.0.1:5173/`，再运行 `npx --yes --package @playwright/cli playwright-cli -s=workspace-check run-code --filename scripts/check-workspace-viewport.js`。检查首页搜索与功能跳转、侧栏工具归属、导航和主要卡片悬停高亮、六页品牌主题及 Logo 加载；在 1600×900、1280×720 下保护两页原布局、验证其余四页无整页溢出及模块重叠，并验证 390×844 的六页底部导航与宽度。脚本只读取页面，不发起模型调用或真实投递。

资料工作台当前接受 WPS 文字/表格/演示、PDF、常见图片、ZIP/7Z/7P、HTML、Python、Markdown、TXT、MP3、MP4 和 MKV 的前端选择。在线预览、图片/PDF OCR 与 WPS 编辑入口目前明确标记为“下一阶段接入”，不会伪装成已可用的后端能力；详细边界、安全要求和验收顺序见 [资料工作台实施计划](docs/MATERIAL_WORKSPACE_PLAN.md)。

格式能力地图区分七种已接入格式和未来格式：DOCX／文字 PDF／TXT／MD 可上传检查；PNG／JPG／JPEG 可保存但需手工补字，扫描 PDF 同理。其他规划格式虽可选择查看分类，但不会上传。资料、岗位搜索和生成入口内提供“下一步”提示，复用现有资料检查／模型设置，不自动测试模型或执行投递。仅检测到平台标签页不代表已登录，配置 Key 也不代表连接有效。

投递分页接口为 `GET /api/applications/page?position=Python&keyword=SQL&location=上海&page=1&page_size=25`，返回 `items/total/page/page_size/pages/statistics_scope`；旧 `GET /api/applications` 数组接口保持兼容。新投递保存岗位地点／JD 快照；旧记录仅在有来源时迁移关联岗位，页面标注“历史关联岗位（迁移时）”，无地点来源显示“未提供”。最新备注参与关键词匹配；已删除／变更的候选岗位不会使已存快照漂移。

筛选分页独立浏览器回归：启动项目后，另开终端执行 `.\.venv\Scripts\python.exe scripts/serve_application_query_check.py`，确认 8767 端口的 `/__application_query_identity` 返回 `temporary-application-query-check`，再运行 `npx --yes --package @playwright/cli playwright-cli -s=workspace-check run-code --filename scripts/check-application-query.js`。测试所有请求均转至临时数据库，使用 137 条合成记录且只删除其当前末页 12 条，真实资料不受影响。重复执行前停止并重启该临时服务；不使用该测试修改你的正式记录。

最终品牌文件位于 `outputs/squirrel-world-logo-20260903/`：`squirrel-world-logo-v2.svg` 是可继续编辑的分层矢量源文件，`squirrel-world-logo-v2.png` 和 `squirrel-world-logo-v2-512.png` 是透明背景 PNG 导出。

## 批量清理岗位与投递记录

“岗位雷达”和“投递跟踪”均提供行勾选、全选当前结果、取消选择及批量删除，删除前明确确认数量。岗位筛选隐藏的勾选不会被删除，一次最多 1000 条。

- 岗位清理会保留已关联投递记录的岗位；未关联岗位删除时，其生成材料、引用和检索索引一并清理，资料库原文件保留。
- 投递跟踪可“选择待核对记录”快捷勾选缺少完整平台证明的旧记录，请先核对是否真实发送再删除。确认删除会移除所选本地投递、事件和索引，不撤销招聘平台上的招呼或投递；未勾选的记录保留。
- 新投递只在平台确认“已发送招呼/已投递”后保存。预检、打开聊天框、生成材料和手工备注均不能创建投递；重复确认同一岗位沿用原记录。旧数据不会因缺少证明而自动删除。
- 删除失败会保留勾选供重试，成功后更新列表及统计，刷新页面不会恢复已删除记录。

接口为 `POST /api/jobs/bulk-delete`、`POST /api/applications/bulk-delete`，请求体示例 `{"ids":[1,2],"confirmed":true}`。响应包含 `deleted_ids`、`protected_ids`、`missing_ids`。相关后端测试位于 `backend/tests/test_bulk_records.py`，前端组件测试位于 `frontend/src/BulkRecordActions.test.tsx`。

独立浏览器回归：项目正常启动后，另开终端执行 `.\.venv\Scripts\python.exe scripts/serve_bulk_delete_check.py`，看到 8766 端口就绪后，用上述 Playwright 会话执行 `run-code --filename scripts/check-bulk-deletion.js`。所有 API 请求都转至临时数据库，测试前校验服务身份；不删除用户数据，不访问真实招聘平台、不调用模型。重复测试需先停止并重新启动临时服务以重建测试数据。

## 可信经历资料库（AI 产品经理作品集 MVP）

上传保存与经历卡片提取是两个独立步骤。模型出错不删除已上传资料，无需重复上传。遇到 HTTP 401 时，当前服务商的 Key 无效或已失效；到“系统设置”更新并测试连接，若启用了独立配置，还需检查“简历/招呼语生成”的模型配置。

暂时没有可用模型时，可在“查看资料与确认事实”中点击“本地提取卡片”。它只从现有正文提取原文片段，不调用模型，生成明确标记的待确认草稿；扫描件/图片仍需先补全正文。接口为 `POST /api/evidence-sources/{id}/extract-cards?mode=local`，默认不传参数时沿用已配置模型；模型错误不会静默切换到本地模式。

生成中心统一使用可信闭环：用户上传分散的个人材料，系统提取候选经历卡片；只有用户确认过的卡片才能参与针对完整 JD 的推荐和生成。每条生成内容必须关联有效卡片，用户编辑后会重新变为待核验，核验并定稿后才能导出最终简历。普通生成的旧接口和历史数据保留兼容。

### JD、自动选经历和平台操作

- 进入生成中心自动补读缺失 JD，优先读取登录浏览器渲染后的正文，不把动态网页的空 HTML 壳当成岗位要求。登录／验证码或正文不可读时停止生成，可在岗位详情手动补充原文。
- 默认“智能体自动选择”：原有生成模型在一次调用中按 JD 选择已确认的相关经历，不需要逐张勾选；无外部模型时明确使用本地规则。基础简历和教育信息单独沿用，“手动调整经历”保留。输出显示真实引用，定稿仍需人审。
- 岗位雷达勾选 BOSS／实习僧后“启动 CDP 浏览器”，只打开所选平台；不强制关闭用户已有的其他标签页。`POST /api/browser/launch-cdp` 接收 `{"platforms":["boss"]}`，旧无参数请求兼容。
- “去沟通／投递”自动完成只读预检，发送前明确询问一次；取消不发送。只打开聊天不算投递成功，不创建记录、不自动重发。登录、验证码、资格限制必须本人处理。
- 搜索任务和预览均最多收集 50 条／平台；滚动保存虚拟列表快照并去重，达到上限、连续三轮无新增、最多 20 轮或平台验证时停止。多城市分配本轮预算，不是无限爬取，不保证覆盖平台所有岗位。
- 搜索直接进入所选城市／关键词的搜索地址，不点击隐藏的搜索控件；批量阶段最多补读 8 个静态详情，正文读取也受超时约束，其余岗位选中后再读取渲染 JD，避免几十个详情请求拖慢列表。
- 执行浏览器任务时会激活目标招聘页，避免后台标签页节流造成假超时；过程中请勿同时手动切换该页面的岗位或城市。

流程参考 [Job Application Agent](https://github.com/VedantSagare/job-application-agent) 的 JD 展示和自动匹配，以及 [JobAgent](https://github.com/Nanduu24/jobagent) 的已核验事实选择和人工发送确认；只借鉴流程，未引入其依赖或源码。

回归：后端运行 `.\.venv\Scripts\python.exe -m pytest`；前端在 `frontend` 运行 `npm test`、`npm run lint`、`npm run build`。`check-job-browser-scripts.js` 使用 `serve_workspace_bug_check.py` 的 8768 身份校验临时服务与合成 DOM；`check-studio-flow.js`、`check-platform-workflow.js` 拦截写请求，验证 JD、自动选经历、平台单选、取消、连点和聊天未发送状态，不使用真实模型或平台发送。

- 支持 DOCX、可提取文字的 PDF、TXT、MD；图片和扫描 PDF 解析失败时明确提示手工补全文本。
- 支持资料列表、解析状态、删除影响预览、候选卡片提取、确认/修改/拒绝、用户自述卡片和原文引用定位。
- 支持 JD 要求映射、相关卡片推荐、指定卡片可信生成、逐条接受/编辑/拒绝、重新关联证据和最终核验。
- 后端会拒绝 Draft、Rejected、不存在的卡片 ID 和不存在的文件原文引用，不把格式错误或证据不足静默标记为成功。
- 原文件保存在本地；调用外部模型时只发送完成当前任务所需的最少文本。XLSX、PPTX、音视频和代码仓库解析不在第一版范围内。

主要接口包括 `POST /api/evidence-sources`、`POST /api/evidence-sources/{id}/extract-cards`、`GET /api/jobs/{id}/evidence-recommendations`、`POST /api/jobs/{id}/evidence-tailor`、`PATCH /api/tailored-claims/{claim_id}` 和 `POST /api/trusted-tailors/{id}/finalize`。可编辑的用户研究、PRD、评测工作簿、评测报告和作品集材料位于 [outputs/trusted-evidence-portfolio-20260817](outputs/trusted-evidence-portfolio-20260817)。

## 安装

建议使用 Python 3.11+。

### Windows 一键安装并启动

在项目根目录打开 PowerShell，运行：

```powershell
.\scripts\start-project.ps1
```

脚本会自动创建 `.venv`、安装后端和前端依赖、启动 FastAPI 与 Vite，并在健康检查通过后打开工作台。Windows 依赖会包含 `pywin32`，用于调用本机 Microsoft Word 执行 DOCX 到 PDF 转换。再次运行时可复用已经启动的服务；依赖已经安装完成后，可用以下命令跳过安装：

```powershell
.\scripts\start-project.ps1 -SkipInstall
```

依赖已安装且不希望自动打开浏览器时，完整命令为：

```powershell
.\scripts\start-project.ps1 -SkipInstall -NoBrowser
```

停止由脚本启动的服务：

```powershell
.\scripts\stop-project.ps1
```

运行日志位于 `data/backend.log`、`data/backend-error.log`、`data/frontend.log` 和 `data/frontend-error.log`。如果 PowerShell 阻止本地脚本，可仅对当前窗口临时放行后再启动：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-project.ps1
```

### 手动安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

如需配置模型或跨域等参数，复制 `.env.example` 为 `.env` 后填写本地占位值。不要提交真实 API Key、Cookie 或招聘平台凭证。

## 启动后端

### 生成中心：同一材料审核与导出

仪表盘、资料工作台保留原布局。资料工作台的“查看资料与确认事实”打开检查弹窗，基础简历也在该弹窗维护；支持的资料上传后需提取并确认真实经历。岗位雷达选择岗位后进入生成中心，使用单个“生成求职材料”入口，右侧切换简历/招呼语、审核并定稿后导出。修改后必须重新核验；切换视图不会再次调用模型。

刷新后恢复最近的岗位批次与材料，右侧“材料版本”可查看旧结果。只读接口 `GET /api/jobs/{job_id}/materials` 返回同岗位版本与引用；不会删除或迁移历史数据。

模拟交互验证：在前后端启动后，使用上述 Playwright 会话运行 `run-code --filename scripts/check-studio-flow.js`。脚本拦截写请求，不调用真实模型或招聘平台。超出已支持范围的资料格式、OCR/WPS 编辑仍是后续计划。

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --app-dir backend
```

默认服务地址：

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- 健康检查: `GET /api/health`

## 启动前端

前端可按 Node.js 项目方式启动：

```powershell
cd frontend
npm install
npm run dev
```

默认后端 CORS 已允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`。

## 真实平台 CDP 工作流

真实平台能力依赖本机 Edge/Chrome 的 Chrome DevTools Protocol（CDP）窗口。系统不会自动登录、不会绕过验证码、不会保存 Cookie/密码。

1. 启动后端和前端。
2. 在前端点击“启动 CDP 浏览器”。如果 `127.0.0.1:9222` 或 `BROWSER_CDP_URL` 已可访问，后端会复用已有 CDP 浏览器，不重复启动。
3. 在新打开或已复用的浏览器窗口中，手动登录 BOSS 直聘和/或实习僧。
4. 回到工作台点击“刷新会话”，确认平台标签页已检测到。
5. 上传简历；刷新页面后，工作台会通过 `GET /api/resumes/latest` 恢复最近上传的简历。
6. 使用“浏览器 CDP”搜索模式，填写关键词和城市，点击“创建搜索任务”或“按关键词搜索并提取”。
7. 系统会控制已登录平台搜索页输入关键词/城市、滚动采集岗位卡片，并把真实候选导入岗位池；demo 模式只用于测试流程。
8. 对选中岗位点击“检查投递入口”，系统只读打开岗位页并检测平台原生沟通/投递按钮，不会点击。
9. 用户确认无误后，再点击“确认真实平台投递”。只有平台页面返回已沟通/已投递等确认信号时，系统才写入投递结果表。
10. 投递结果表会展示 `platform_proof`，包括平台、原岗位链接、按钮文本、动作、状态、页面摘要和确认时间。

## 运行测试

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
```

前端完整验证：

```powershell
cd frontend
npm test -- --run
npm run lint
npm run build
```

测试原则：

- 使用 `tmp_path` 临时数据库，不写入生产数据。
- 不访问真实招聘平台；真实平台能力通过 fake CDP 和脚本结构回归覆盖。
- 不调用真实 LLM API。
- token 和金额使用 `local-estimator` 或测试内的显式定价。

## API 概览

主要流程：

1. `POST /api/resumes` 上传简历文件，解析为本地 `ResumeDraft`。
2. `GET /api/resumes/latest` 刷新后恢复最近上传的简历。
3. `POST /api/browser/launch-cdp` 启动或复用本地 CDP 浏览器。
4. `GET /api/platform-sessions` 检测 BOSS/实习僧标签页和登录状态线索。
5. `POST /api/search-runs` 基于简历、关键词、城市和平台生成 demo 岗位，或在 `browser_cdp` 模式下控制真实平台搜索并导入岗位。
6. `POST /api/platform-jobs/search` 控制已登录平台页搜索并只读提取候选岗位。
7. `GET /api/jobs` 查看岗位和 `match` 结果。
8. `POST /api/jobs/{job_id}/refresh-detail` 从真实平台刷新单岗位详情。
9. `POST /api/jobs/{job_id}/tailor` 生成定制简历、招呼语和审核结果。
10. `POST /api/jobs/{job_id}/platform-apply-preview` 只读预检平台投递/沟通入口。
11. `POST /api/jobs/{job_id}/platform-apply` 用户二次确认后尝试真实平台投递；只有平台确认后才入库。
12. `POST /api/jobs/{job_id}/apply-record` 已禁用本地假投递，直接调用会返回 `409`。
13. `PATCH /api/applications/{application_id}/status` 更新投递状态，非法流转返回 `409`。
14. `GET /api/applications` 查看投递列表和结构化平台证明。
15. `GET /api/analytics/applications` 查看投递统计分桶。
16. `GET /api/metrics/llm-usage` 查看 token 和费用估算。
17. `POST /api/applications/sync` 返回只读同步建议，用户确认后才更新状态。

## 人工冒烟验收清单

自动测试不能证明真实账号侧已经完成投递。每次改动真实平台链路后，至少做一次人工冒烟：

- BOSS 搜索页已登录，页面左侧可见 5 条以上岗位卡片。
- 前端选择 `浏览器 CDP`，输入同样关键词和城市，创建搜索任务后岗位池出现 5 条以上相关真实岗位。
- 岗位详情弹窗能展示岗位标题、公司、城市、薪资和 JD；若 JD 不完整，应能刷新详情或人工补全。
- 点击“检查投递入口”只打开岗位并展示按钮证据，不创建投递记录。
- 点击“确认真实平台投递”后，BOSS/实习僧页面能看到已沟通/已投递/已申请等状态。
- 投递结果表新增记录，且展示 `platform_proof` 的平台链接、按钮文本、页面摘要和确认时间。
- 直接调用旧 `/api/jobs/{job_id}/apply-record` 应返回 `409`，不能创建本地假投递。

## 投递状态

当前合法状态流转：

- `applied -> read | rejected | closed`
- `read -> replied | rejected | closed`
- `replied -> interview | assessment | rejected | closed`
- `interview -> assessment | rejected | closed`
- `assessment -> interview | rejected | closed`
- `rejected -> closed`
- `closed` 为终态

状态更新应来自用户确认或明确的平台读取结果，不应由 Agent 擅自推断。

## 合规边界

- 不自动登录、不绕验证码、不保存账号密码或 Cookie。
- 不做未经用户确认的全自动投递；真实投递必须先预检，再由用户二次确认。
- 投递记录只在平台确认后写入；旧的本地假投递接口保持禁用。
- 不在简历改写中新增未经原始简历支持的公司、学历、项目、技能或经历。
- 不把 API Key、密码、Cookie、手机号、身份证号等敏感信息写入代码或文档。
- 模型调用应通过 OpenAI-compatible 配置注入，并保留超时、失败和空结果处理空间。
- 平台同步第一版保留为手动或半自动读取，真实平台适配器必须明确输入输出和失败边界。

更多可视化统计口径见 [docs/application-analytics.md](docs/application-analytics.md)。
