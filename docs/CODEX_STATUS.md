# Codex Recovery Status

Updated: 2026-06-30 Asia/Shanghai

## 当前真实状态

当前项目已经初始化为本地 Git 仓库，默认分支为 `main`。项目是可运行的本地单用户 MVP，不是完整企业级成品。后端 FastAPI、SQLite、前端 React/Vite、demo 搜索闭环、模型/API 配置、CDP 浏览器会话检测、一键启动 CDP 浏览器、只读岗位提取、browser_cdp 搜索入库、提取诊断结构化、前端诊断展示、只读投递状态同步建议、前端人工确认同步、单岗位材料生成的 OpenAI-compatible LLM 最小闭环，以及 LLM usage 的 status/error 可观察字段已经具备。

真实平台能力仍是“用户打开并登录平台页面后，系统只读提取当前页面可见数据”。系统不会自动登录、不会绕过验证码、不会保存 Cookie/密码、不会未经确认投递，也不会在同步时静默覆盖用户手工维护的投递状态。

## 已完成

- Git：
  - 已执行 `git init -b main`。
  - `.gitignore` 已覆盖 Python/Node 缓存、`node_modules`、`frontend/dist`、SQLite 本地数据、`.env`、证书密钥和临时目录。
- 后端基础：
  - `POST /api/resumes`
  - `POST /api/search-runs`
  - `GET /api/jobs`
  - `POST /api/jobs/{id}/tailor`
  - `POST /api/jobs/{id}/apply-record`
  - `PATCH /api/applications/{id}/status`
  - `POST /api/applications/sync`
  - `GET /api/applications`
  - `GET /api/analytics/applications`
  - `GET /api/metrics/llm-usage`
  - `GET /api/model-config`
  - `PUT /api/model-config`
  - `GET /api/platform-sessions`
  - `POST /api/platform-jobs/extract`
  - `POST /api/browser/launch-cdp`
- 前端工作台：
  - 简历上传、搜索任务、岗位列表、Agent 状态区域、投递结果表、进展看板、成本看板。
  - 模型/API 配置、CDP 会话状态、只读岗位提取结果、岗位提取诊断展示。
  - 投递同步建议展示与人工确认更新。
- 阶段 2A：搜索模式隔离，`demo` 与 `browser_cdp` 分开，真实模式不回退 demo。
- 阶段 2B：只读 CDP 岗位提取接口。
- 阶段 2C：前端展示搜索模式、平台会话和提取候选岗位。
- 阶段 2D：`browser_cdp` 搜索结果写入 `JobPosting` 并计算匹配分。
- 阶段 3A：一键启动本地 Edge/Chrome CDP 浏览器。
- 阶段 3B：提取诊断结构化、前端诊断展示、BOSS/实习僧 DOM 选择器增强。
- 阶段 3C：实现 `/api/applications/sync` 只读同步边界，只返回 `proposals` 和 `diagnostics`，不直接更新数据库。
- 阶段 3D：前端展示投递同步建议，用户点击“确认更新”后才调用状态更新接口。
- 阶段 4A：真实 LLM client 与模型配置最小闭环。
  - 新增 OpenAI-compatible `/chat/completions` client，不引入额外依赖。
  - 只先接入 `ApplicationWriterAgent` 的单岗位材料生成。
  - 成功时记录真实 provider、model、tokens、金额、耗时。
  - 调用失败、响应格式错误或模型输出不可解析时，本地规则生成自动回退，主流程不失败。
- 阶段 4B：模型 usage 可观察字段与非 LLM MetricsService。
  - 新增 `MetricsService`，`JobApplicationService` 不再依赖 `MetricsAgent` 记录运行时 usage。
  - `LLMUsageEntry` 增加 `status` 和 `error` 字段。
  - SQLite `llm_usage` 表新库直接创建 `status/error`，老库启动时自动补列。
  - 本地估算记录标记为 `estimated`。
  - 真实 LLM 成功记录标记为 `success`。
  - LLM 失败回退会写入 `failed` usage，并记录安全截断后的错误信息。
  - `/api/metrics/llm-usage` 的 `by_agent` 增加 `success_calls`、`estimated_calls`、`failed_calls`。

## 未完成

- “模型自动选择”尚未实现策略路由；当前仍使用当前启用的 provider/model。
- 多 Agent 当前是模块拆分，不是可并行调度运行时。
- `JobSearchAgent`/`Orchestrator`/`EventStreamService` 尚未按新版架构完整落地。
- 前端 Agent 状态还不是后端 SSE/WebSocket 实时推送。
- 浏览器自动化只做 CDP 只读提取和启动，不做自动点击、自动投递或自动打招呼。
- 没有真实 BOSS/实习僧页面回归样例快照，DOM 和状态关键词仍需在用户登录后的真实页面上继续校验。
- 没有完整数据库迁移系统、外键约束、并发保护、审计日志和密钥管理。

## 风险

- BOSS/实习僧页面 DOM 和文案随时可能变化，当前同步服务只能提高可诊断性，不能保证长期稳定。
- 用户如果未登录、页面停在验证码/风控页、结果为空页，系统只能返回诊断，不能绕过平台限制。
- LLM 输出仍需要 `ReviewAgent` 审核，模型可能返回不合规 JSON 或尝试虚构经历，因此保留本地回退。
- 当前 Git 已初始化，但还没有配置远程仓库；没有 remote 时无法 push。
- 文档和代码中不得写入真实 API Key、Cookie、密码或平台隐私数据。

## 下一步任务

建议进入 4C：模型路由最小策略。

目标：实现一个小型 `ModelRouterService`，按 Agent/任务选择模型配置。第一步只区分本地估算、ApplicationWriter 外部模型、Review 本地规则，不做复杂多模型池。

预计文件控制在 3-5 个：

- `backend/app/services/model_router_service.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

浏览器中应该看到：模型配置启用时，材料生成仍可调用外部模型；成本看板能继续区分 estimated/success/failed 调用。

## 最近修改文件

- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/services/metrics_service.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

## 最近验证

- `python -m pytest -q`：通过，27 个测试。
