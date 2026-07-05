# agent-business

本项目是一个本地单用户求职投递多 Agent 工作台。它把简历解析、真实浏览器 CDP 岗位搜索、岗位匹配、简历改写、招呼语生成、真实平台投递确认、投递状态跟踪、LLM token/金额统计和投递数据分析串成一条可验证的工作流。

当前项目保留 demo 模式用于自动化测试，但真实工作流默认使用用户本机启动的 CDP 浏览器。用户需要自行登录 BOSS 直聘和实习僧；系统只在已登录页面中执行搜索、只读提取岗位、打开岗位、预检投递入口，并且只有用户二次确认后才尝试点击平台原生沟通/投递按钮。投递记录只在平台返回确认信号后入库，并保存结构化 `platform_proof`。

## 架构概览

- 后端：FastAPI，入口为 `backend/app/main.py`。
- 数据：SQLite，本地默认路径为 `data/agent-business.sqlite3`。
- Agent：`backend/app/agents/` 中按职责拆分，包括简历解析、岗位匹配、简历改写、招呼语、投递状态、审核和指标统计。
- 平台适配器：`backend/app/platforms/` 保留 Boss 直聘和实习僧的 demo adapter；真实平台能力由 `backend/app/services/browser_job_extractor_service.py` 通过 CDP 控制已登录浏览器页面完成。
- 服务编排：`backend/app/services/job_application_service.py` 串联简历、岗位、改写、投递和分析流程。
- 测试：`backend/tests/`，使用 demo/fake CDP 数据、临时 SQLite 和本地 token 估算；自动测试不访问真实招聘平台账号。
- 前端：`frontend/` 提供本地工作台页面，使用 Vite + React。

## 安装

建议使用 Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

如需配置模型或跨域等参数，复制 `.env.example` 为 `.env` 后填写本地占位值。不要提交真实 API Key、Cookie 或招聘平台凭证。

## 启动后端

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
