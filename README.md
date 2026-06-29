# agent-business

本项目是一个本地单用户求职投递多 Agent 工作台。它把简历解析、岗位搜索 demo、岗位匹配、简历改写、招呼语生成、投递状态跟踪、LLM token/金额统计和投递数据分析串成一条可验证的 API 流程。

当前后端以本地 demo 数据和 SQLite 为主，不依赖真实招聘平台账号，也不要求真实 LLM API 才能运行测试。涉及真实平台或模型的能力应通过适配器和环境变量扩展，并保持用户人工确认边界。

## 架构概览

- 后端：FastAPI，入口为 `backend/app/main.py`。
- 数据：SQLite，本地默认路径为 `data/agent-business.sqlite3`。
- Agent：`backend/app/agents/` 中按职责拆分，包括简历解析、岗位匹配、简历改写、招呼语、投递状态、审核和指标统计。
- 平台适配器：`backend/app/platforms/` 当前提供 Boss 直聘和实习僧的 demo adapter。
- 服务编排：`backend/app/services/job_application_service.py` 串联简历、岗位、改写、投递和分析流程。
- 测试：`backend/tests/`，使用 demo 数据、临时 SQLite 和本地 token 估算。
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

## 运行测试

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
```

测试原则：

- 使用 `tmp_path` 临时数据库，不写入生产数据。
- 不访问真实招聘平台。
- 不调用真实 LLM API。
- token 和金额使用 `local-estimator` 或测试内的显式定价。

## API 概览

主要流程：

1. `POST /api/resumes` 上传简历文件，解析为本地 `ResumeDraft`。
2. `POST /api/search-runs` 基于简历、关键词、城市和平台生成 demo 岗位并计算匹配度。
3. `GET /api/jobs` 查看岗位和 `match` 结果。
4. `POST /api/jobs/{job_id}/tailor` 生成定制简历、招呼语和审核结果。
5. `POST /api/jobs/{job_id}/apply-record` 用户确认后创建投递记录。
6. `PATCH /api/applications/{application_id}/status` 更新投递状态，非法流转返回 `409`。
7. `GET /api/applications` 查看投递列表。
8. `GET /api/analytics/applications` 查看投递统计分桶。
9. `GET /api/metrics/llm-usage` 查看 token 和费用估算。
10. `POST /api/applications/sync` 预留半自动同步入口，当前返回本地说明。

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

- 不自动登录、抓取或操作真实招聘平台账号。
- 不自动发送简历或招呼语；发送前必须由用户确认。
- 不在简历改写中新增未经原始简历支持的公司、学历、项目、技能或经历。
- 不把 API Key、密码、Cookie、手机号、身份证号等敏感信息写入代码或文档。
- 模型调用应通过 OpenAI-compatible 配置注入，并保留超时、失败和空结果处理空间。
- 平台同步第一版保留为手动或半自动读取，真实平台适配器必须明确输入输出和失败边界。

更多可视化统计口径见 [docs/application-analytics.md](docs/application-analytics.md)。
