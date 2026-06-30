# Codex Recovery Status

Updated: 2026-06-30 Asia/Shanghai

## 当前真实状态

当前项目已经初始化为本地 Git 仓库，默认分支为 `main`。项目是可运行的本地单用户 MVP，不是完整企业级成品。后端 FastAPI、SQLite、前端 React/Vite、demo 搜索闭环、模型/API 配置、CDP 浏览器会话检测、一键启动 CDP 浏览器、只读岗位提取、browser_cdp 搜索入库、提取诊断结构化、前端诊断展示、只读投递状态同步建议、前端人工确认同步、单岗位材料生成的 OpenAI-compatible LLM 最小闭环、LLM usage 的 status/error 可观察字段、最小模型路由策略、后端 Agent 状态事件接口、前端 Agent 状态轮询展示、Agent 失败事件可视化，以及 Orchestrator 最小编排摘要、SQLite 持久化草案和前端任务摘要展示已经具备。

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
  - `GET /api/agent-events`
- 前端工作台：
  - 简历上传、搜索任务、岗位列表、Agent 状态区域、投递结果表、进展看板、成本看板。
  - 模型/API 配置、CDP 会话状态、只读岗位提取结果、岗位提取诊断展示。
  - 投递同步建议展示与人工确认更新。
  - Agent 状态区已接入 `/api/agent-events`，初始化和每 5 秒轮询后端真实事件。
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
- 阶段 4C：模型路由最小策略。
  - 新增 `ModelRouterService`，集中决定 Agent 使用外部模型、本地估算或本地规则。
  - `ApplicationWriterAgent` 仅在模型配置启用、非估算模式且 API key 环境变量可用时走外部 OpenAI-compatible 模型。
  - `ReviewAgent` 在 4C 固定走本地规则审核，不消耗外部模型 token。
  - 材料生成接口返回的 `review.llm` 元数据包含 `route` 和 `review_route`，方便前端或调试时观察路由决策。
- 阶段 4D：Agent 状态事件流最小闭环。
  - 新增轻量 `EventStreamService`，先采用本地单用户进程内事件缓存，不引入额外依赖。
  - 后端在简历解析、岗位搜索、岗位匹配、材料生成、审核几个关键步骤记录 `running/success/failed` 事件。
  - 新增 `GET /api/agent-events`，返回 `current_running_agent`、每个 Agent 最新状态、事件列表和当前任务总成本。
  - 事件包含当前步骤、输入摘要、输出摘要、错误信息、token 和成本字段，供前端后续轮询展示。
- 阶段 4E：前端 Agent 状态轮询接入。
  - `frontend/src/lib/api.ts` 新增 `getAgentEvents()`，读取后端 Agent 事件快照。
  - `frontend/src/lib/dashboard.ts` 新增后端事件快照到 Agent 状态卡片的转换逻辑。
  - `frontend/src/App.tsx` 在初始化、业务刷新和每 5 秒轮询时刷新 Agent 事件。
  - Agent 状态区域优先显示后端真实事件；后端尚未就绪时保留原有前端推断兜底。
- 阶段 4F：Agent 失败事件补齐与前端错误态验证。
  - `browser_cdp` 搜索缺少平台标签页时，`JobSearchAgent` 会记录 `failed` 事件和错误摘要。
  - 浏览器岗位提取失败时，`JobSearchAgent` 最新状态会从 `running` 正确落到 `failed`。
  - 外部 LLM 材料生成失败并本地回退时，接口仍返回本地材料，但 `ApplicationWriterAgent` 状态会标记为 `failed` 并保留错误信息。
  - 前端 Agent 状态卡在 failed 事件没有 `error` 字段时，会用 `output_summary` 或步骤名兜底显示错误摘要。
- 阶段 5A：Orchestrator 最小编排骨架。
  - 新增 `OrchestratorService`，负责创建任务、记录 Agent 步骤、结束任务，并把步骤归档到任务摘要。
  - `JobApplicationService` 的简历解析、岗位搜索、材料生成/审核三个主流程已接入 Orchestrator。
  - `GET /api/agent-events` 继续返回原有 Agent 事件字段，同时新增 `orchestrator` 摘要，包含 `current_task_id`、`last_task` 和近期任务列表。
  - 当前 Orchestrator 只做本地单进程任务摘要，不做并行调度、持久化、重试或自动投递。
- 阶段 5B：Orchestrator 任务状态持久化草案。
  - SQLite 新增 `orchestrator_tasks` 和 `orchestrator_steps` 两张表，用于保存任务摘要和 Agent 步骤摘要。
  - `OrchestratorService` 启动时会从 SQLite 恢复最近任务，服务重启后 `/api/agent-events` 仍可返回 `orchestrator.last_task`。
  - `start_task`、`record_step`、`finish_task` 已同步写入 SQLite，同时保留进程内快照。
  - 当前只持久化摘要，不持久化完整 `EventStreamService` 事件流，也不做任务恢复执行、重试或并发调度。
- 阶段 5C：前端展示 Orchestrator 任务摘要。
  - `frontend/src/lib/dashboard.ts` 新增 Orchestrator 后端快照类型和 `buildOrchestratorSummary()` 转换函数。
  - Agent 状态区域新增最近编排任务摘要，展示任务名、状态、步骤数、最近步骤和错误信息。
  - 样式保持为紧凑状态条，不改变岗位表、投递结果表、成本看板和材料人审流程。
  - 当前只展示最近任务摘要，不提供任务详情弹窗、任务 ID 搜索、重试按钮或恢复执行入口。

## 未完成

- “模型自动选择”已有最小策略路由，但尚未实现多模型池、按成本/失败率自动切换、按 Agent 配置不同模型。
- 多 Agent 当前是模块拆分，不是可并行调度运行时。
- `JobSearchAgent` 尚未拆成独立任务级 Agent；Orchestrator 已有最小骨架和任务摘要持久化，但尚未实现重试、并行调度或任务恢复执行。
- `EventStreamService` 目前是进程内最小事件缓存，尚未持久化，也不是 SSE/WebSocket 实时推送。
- 浏览器自动化只做 CDP 只读提取和启动，不做自动点击、自动投递或自动打招呼。
- 没有真实 BOSS/实习僧页面回归样例快照，DOM 和状态关键词仍需在用户登录后的真实页面上继续校验。
- 没有完整数据库迁移系统、外键约束、并发保护、审计日志和密钥管理。

## 风险

- BOSS/实习僧页面 DOM 和文案随时可能变化，当前同步服务只能提高可诊断性，不能保证长期稳定。
- 用户如果未登录、页面停在验证码/风控页、结果为空页，系统只能返回诊断，不能绕过平台限制。
- LLM 输出仍需要 `ReviewAgent` 审核，模型可能返回不合规 JSON 或尝试虚构经历，因此保留本地回退。
- Git 远程仓库已配置为 `https://github.com/PrinceSquirrel/find-work.git`，`main` 已成功推送并跟踪 `origin/main`；后续 push 仍依赖本机 GitHub 凭据可用。
- 文档和代码中不得写入真实 API Key、Cookie、密码或平台隐私数据。

## 下一步任务

建议进入 5D：任务详情接口与前端详情入口。

目标：为 Orchestrator 增加最小任务详情读取能力，让前端可以从最近任务摘要进入步骤详情，为后续失败重试和恢复执行入口做准备。

预计文件控制在 3-5 个：

- `backend/app/main.py`
- `backend/app/services/job_application_service.py`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

浏览器中应该看到：最近编排任务摘要旁可查看任务步骤详情，但仍不自动重试、不自动恢复执行。

## 最近修改文件

- `backend/app/services/model_router_service.py`
- `backend/app/services/event_stream_service.py`
- `backend/app/services/orchestrator_service.py`
- `backend/app/services/job_application_service.py`
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/CODEX_STATUS.md`

## 最近验证

- 5C 红灯验证：
  - `npm test -- --run`：按预期失败，暴露缺少 `buildOrchestratorSummary()`。
- 5C 绿灯验证：
  - `npm test -- --run`：通过，8 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，30 个后端测试。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5B 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_orchestrator_task_summary_survives_service_restart -q`：按预期失败，暴露服务重启后 `orchestrator.last_task` 为 `None`。
- 5B 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_orchestrator_task_summary_survives_service_restart -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps backend\tests\test_api_flow.py::test_browser_cdp_search_mode_requires_detected_platform_tab backend\tests\test_api_flow.py::test_browser_cdp_search_mode_reports_extraction_failure_without_demo_jobs backend\tests\test_api_flow.py::test_tailor_falls_back_locally_when_openai_compatible_model_fails backend\tests\test_api_flow.py::test_orchestrator_task_summary_survives_service_restart -q`：通过，5 个测试。
  - `python -m pytest -q`：通过，30 个后端测试。
  - `npm test -- --run`：通过，7 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5A 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps -q`：按预期失败，暴露 `/api/agent-events` 缺少 `orchestrator` 摘要。
- 5A 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py::test_browser_cdp_search_mode_requires_detected_platform_tab backend\tests\test_api_flow.py::test_browser_cdp_search_mode_reports_extraction_failure_without_demo_jobs backend\tests\test_api_flow.py::test_tailor_falls_back_locally_when_openai_compatible_model_fails backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps -q`：通过，4 个测试。
- 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_browser_cdp_search_mode_requires_detected_platform_tab backend\tests\test_api_flow.py::test_browser_cdp_search_mode_reports_extraction_failure_without_demo_jobs backend\tests\test_api_flow.py::test_tailor_falls_back_locally_when_openai_compatible_model_fails -q`：按预期失败，暴露缺少 failed 事件/错误摘要兜底。
  - `npm test -- --run`：按预期失败，暴露前端 failed 事件缺少 `output_summary` 兜底。
- 4F 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_browser_cdp_search_mode_requires_detected_platform_tab backend\tests\test_api_flow.py::test_browser_cdp_search_mode_reports_extraction_failure_without_demo_jobs backend\tests\test_api_flow.py::test_tailor_falls_back_locally_when_openai_compatible_model_fails -q`：通过，3 个测试。
  - `npm test -- --run`：通过，7 个前端测试。
  - `python -m pytest -q`：通过，29 个后端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
- `python -m pytest -q`：通过，29 个测试。
- `git push -u origin main`：通过，`main` 已推送到 `PrinceSquirrel/find-work`。
- `python -m pytest backend\tests\test_api_flow.py::test_tailor_routes_application_writer_through_model_router -q`：通过。
- `python -m pytest backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps -q`：通过。
- `npm test -- --run`：通过，7 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：通过，29 个后端测试。
