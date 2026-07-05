# Codex Recovery Status

## 7G-5：OrchestratorAgent 任务编排证据
### 当前真实状态
- `OrchestratorAgent` 不再只是模型路由配置项；后端每次创建核心任务时会先记录一条 `plan workflow` 编排步骤。
- 已接入的任务入口包括：`resume.parse`、`job.search`、`job.detail.refresh`、`job.detail.manual_update`、`application.materials`。
- 编排步骤会显示当前总模型大脑路由：`local_planner` 或 `external_planner`，并记录 provider/model 和人工确认边界。
- 本阶段只记录编排证据，不让总模型自动投递、不绕验证码、不执行任意命令。

### 已完成
- `ModelRouterService` 新增 `OrchestratorAgent` 路由判断。
- `JobApplicationService` 在核心任务创建后写入 `OrchestratorAgent: success / plan workflow` 事件。
- 后端测试更新并覆盖 Agent 状态、任务详情、服务重启后的步骤恢复和模型路由调用顺序。

### 未完成
- `OrchestratorAgent` 还没有真正调用外部 LLM 生成任务计划；当前只是可观察的编排路由证据。
- 还没有把 7H 的“系统状态 / 后端控制台”页面做出来。
- RAG / Skill / MCP 企业级扩展仍排在后续阶段。

### 风险
- Agent 事件列表会多一条 OrchestratorAgent 步骤，依赖旧步骤顺序的测试或前端逻辑需要按新语义理解。
- `external_planner` 当前表示“已配置可用主脑模型路线”，不等于已经调用模型消费 token。

### 下一步任务
- 7H：新增一眼看懂的系统状态 / 后端控制台，展示后端、数据库、CDP、平台会话、模型、PDF、OCR 状态。
- 后续再做 OrchestratorAgent 的低风险 LLM 规划输出，但必须保持人审边界。

### 最近修改文件
- `backend/app/services/model_router_service.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_agent_events_endpoint_reports_real_backend_steps backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp backend\tests\test_api_flow.py::test_manual_job_detail_update_recalculates_match_and_records_agent_event -q` 先失败于缺少 `OrchestratorAgent` 步骤。
- 绿测：同一命令通过，3 条测试通过。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py -k "agent_events or orchestrator or model_route or tailor_routes_application_writer" -q` 通过，9 条测试通过。
- 后端全量：`python -m pytest -q` 通过，94 条测试通过，只有 reportlab 的 Python 3.14 弃用预告警告。
- 空白检查：`git diff --check` 通过，仅有 Windows 换行转换提示。

## 7G-4B：前端删除当前保存 API Key
### 当前真实状态
- “模型 / API”面板新增“删除当前 Key”按钮。
- 按钮只在后端返回了本地保存 Key 的脱敏值时启用，避免把环境变量模式误判为可从页面删除。
- 点击后会二次确认，然后调用 `DELETE /api/model-config/api-key`。
- 删除成功后会刷新当前模型配置、清空 Key 输入框、清空模型连接测试结果，并显示删除结果提示。

### 已完成
- 前端 API client 新增 `deleteModelConfigApiKey()`。
- API 单测覆盖 `DELETE /api/model-config/api-key` 请求。
- `App.tsx` 新增删除 Key 忙碌状态、二次确认和模型配置回填。
- 模型操作区新增“删除当前 Key”按钮。

### 未完成
- 模型档案和 Agent 路由自己的本地 Key 删除按钮还未做；当前只删除全局主模型 Key。
- 还没有提供“撤销删除”或历史 Key 恢复，删除后需要用户重新粘贴。

### 风险
- 如果用户通过环境变量提供 Key，按钮不会因为环境变量而启用；这是为了避免误导用户以为能从前端删除系统环境变量。
- 删除后如果后端仍通过其他来源检测到 Key，状态提示会显示仍已配置。

### 下一步任务
- 7G-5：让 OrchestratorAgent 在任务创建时记录编排路由证据，并逐步接入低风险规划。
- 7H：新增一眼看懂的系统状态 / 后端控制台。
- 后续扩展：模型档案和 Agent 路由级别的 Key 删除。

### 最近修改文件
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm test -- --run src/lib/api.test.ts -t deleteModelConfigApiKey` 先失败于 `api.deleteModelConfigApiKey is not a function`。
- 绿测：同一命令通过。
- `npm test -- --run` 通过，39 条前端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_model_config_saved_api_key_can_be_deleted -q` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7G-4A：删除当前保存 API Key（后端接口）
### 当前真实状态
- 后端新增 `DELETE /api/model-config/api-key`，用于清空当前全局模型配置中本地保存的真实 API Key。
- 删除操作只清空 SQLite 里的 `api_key_ciphertext` 和 `api_key_masked`，不改变 provider、model、base_url、启用状态、价格字段。
- 如果用户仍配置了环境变量名并且本机环境变量可用，旧环境变量兼容路径仍会继续生效；本接口只删除“本地保存的真实 Key”。
- 删除后 `GET /api/model-config` 会返回空 `api_key_secret_id`、空 `api_key_masked`，并根据实际 Key 来源重新计算 `api_key_configured`。

### 已完成
- `SQLiteStore.delete_model_config_api_key()` 清空本地保存 Key 并返回更新后的模型配置。
- FastAPI 增加 `DELETE /api/model-config/api-key`。
- 后端测试覆盖：保存真实 Key、删除 Key、确认响应不泄露明文、数据库密文字段清空、测试连接变为未配置。

### 未完成
- 前端“模型 / API”面板还没有接入“删除当前 Key”按钮；下一阶段做 `7G-4B`。
- Agent 路由和模型档案自己的本地 Key 删除接口还未做；本阶段只处理全局主模型 Key。

### 风险
- 如果用户通过环境变量提供 Key，删除本地保存 Key 后 `api_key_configured` 仍可能为 true，这是兼容旧环境变量模式的预期行为。
- 前端按钮未接入前，只能通过 API 调用删除。

### 下一步任务
- 7G-4B：前端接入删除当前 Key 按钮和 API client 测试。
- 7G-5：让 OrchestratorAgent 在任务创建时记录编排路由证据，并逐步接入低风险规划。
- 7H：新增一眼看懂的系统状态 / 后端控制台。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_model_config_saved_api_key_can_be_deleted -q` 先失败于 `DELETE /api/model-config/api-key` 返回 404。
- 绿测：同一命令通过。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py -k "model_config" -q` 通过，7 条后端测试通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7G-3：总模型大脑与简历解析模型路由
### 当前真实状态
- 后端 `GET /api/model-routes` 现在会返回 5 个可配置路由：`OrchestratorAgent`、`ResumeParserAgent`、`ApplicationWriterAgent`、`JobMatchAgent`、`ReviewAgent`。
- `PUT /api/model-routes/OrchestratorAgent` 和 `PUT /api/model-routes/ResumeParserAgent` 可以保存独立 provider、model、base_url、真实 Key/环境变量兼容配置、启用状态和价格字段。
- `OrchestratorAgent` 默认继承当前主模型配置，符合“总模型大脑”的使用预期。
- `ResumeParserAgent` 默认仍是本地规则；用户显式套用模型档案后可以保存外部模型路由。
- 前端高级路由表新增中文标签：“总模型大脑”“简历解析”，页面会显示总模型、简历解析、简历/招呼语生成、岗位匹配评分、事实风险审核。

### 已完成
- `MODEL_ROUTE_AGENTS` 加入 `OrchestratorAgent` 和 `ResumeParserAgent`。
- 默认 Agent 路由顺序调整为：总模型大脑、简历解析、简历/招呼语生成、岗位匹配评分、事实风险审核。
- 后端测试覆盖新 Agent 路由的默认返回和保存能力。
- 前端模型路由标签补齐，用户不再看到裸英文 Agent 名称作为主要说明。

### 未完成
- `OrchestratorAgent` 目前只是可配置路由，尚未真正调用外部模型做任务规划或 Agent 编排决策。
- `ResumeParserAgent` 仍优先规则解析/OCR/手动补全，尚未调用模型做复杂简历结构化。
- 高级路由表仍只能套用已保存模型档案，不能在每个 Agent 行内直接粘贴不同 API Key。

### 风险
- 如果用户为 `ResumeParserAgent` 启用外部模型，当前解析链路仍不会消耗该路由；这属于后续接入任务。
- `OrchestratorAgent` 默认继承主模型配置，但实际运行时暂未记录独立 token/cost。

### 下一步任务
- 7G-4：补“删除当前保存 API Key”的后端接口和前端按钮。
- 7G-5：让 OrchestratorAgent 在任务创建时记录编排路由证据，并逐步接入低风险规划。
- 7H：新增一眼看懂的系统状态 / 后端控制台。

### 最近修改文件
- `backend/app/storage.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_agent_model_routes_can_be_saved_per_agent -q` 先失败于路由列表缺少 `OrchestratorAgent` 和 `ResumeParserAgent`。
- 绿测：同一命令通过。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py -k "model_route or model_profiles or model_config" -q` 通过，12 条后端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7G-2：前端简化模型/API 面板
### 当前真实状态
- “模型 / API”面板已从复杂的 Model Picker、环境变量名、模型档案表单和完整 Agent 路由表单，收敛成简单模式。
- 用户现在可以在同一块区域完成：选择服务商、选择/输入模型版本、填写 API 地址、粘贴真实 API Key、显示/隐藏 Key、保存为当前模型、测试连接。
- API Key 输入框是密码框；保存后会清空输入框，只显示后端返回的脱敏 Key 状态。
- 模型档案仍保留，但入口简化为“已保存模型 / 档案名称 / 保存更新 / 套用 / 删除档案”。
- 不同 Agent 使用不同模型的能力先收进“高级：不同 Agent 使用不同模型”折叠区，只允许从已保存模型档案套用，避免暴露大量后端字段。

### 已完成
- 前端 `ModelConfig` 类型支持 `api_key_secret_id`、`api_key_masked`，`ModelConfigUpdate` 支持真实 `api_key`。
- `api.updateModelConfig()` 测试覆盖：真实 Key + 空环境变量名会进入请求体，响应不需要明文 Key。
- `App.tsx` 新增真实 Key 输入、显示/隐藏、保存后清空、脱敏状态展示。
- 可见模型面板删掉环境变量名入口，不再要求用户理解 `DEEPSEEK_API_KEY`。
- 新增简洁模型面板和折叠 Agent 路由样式，并适配移动端。

### 未完成
- 后端还没有独立“删除当前保存 API Key”的接口；当前删除按钮删除的是模型档案，不是全局 Key。
- `OrchestratorAgent` 总模型大脑路由还未加入前端/后端白名单。
- 后端操作页 `GET /api/system/health` 和对应系统状态 UI 还未开始。

### 风险
- 旧的模型管理弹窗渲染块已删除，但部分旧状态/handler 仍留在 `App.tsx` 供后续路由表收敛时复用；后续可以继续瘦身。
- 如果用户没有输入新 Key，保存配置会沿用后端已有 Key；如果从未保存过 Key，测试连接仍会失败并提示检查 API Key。
- 高级 Agent 路由当前只能套用已保存模型档案，不能在折叠区直接输入新的 Key。

### 下一步任务
- 7G-3：加入 `OrchestratorAgent` 总模型大脑，并把总模型、简历解析、岗位匹配、简历/招呼语生成、审核做成简洁路由表。
- 7G-4：补“删除当前保存 API Key”的后端接口和前端按钮。
- 7H：新增一眼看懂的系统状态 / 后端控制台。

### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm run lint` 先失败于 `api_key` 和 `api_key_masked` 类型不存在。
- 绿测：`npm test -- --run src/lib/api.test.ts` 通过，16 条前端 API 单测通过。
- `npm test -- --run` 通过，38 条前端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_model_config_accepts_saved_api_key_without_leaking_plaintext -q` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7G-1：后端真实 API Key 本地保存
### 当前真实状态
- `/api/model-config` 现在可以接收真实 `api_key`，也允许 `api_key_env_var=""`，不再强迫用户填写环境变量名。
- API Key 会以本地派生密钥处理后的密文写入 SQLite，响应中不会返回明文，只返回 `api_key_configured`、`api_key_secret_id` 和脱敏尾号 `api_key_masked`。
- `OpenAICompatibleClient` 调用模型时会优先使用已保存的隐藏 Key；没有保存 Key 时继续兼容旧的环境变量 / 外部 `.env` 读取方式。
- 模型档案和 Agent 模型路由也已经具备同样的密文字段，后续前端简化模型选择器可以直接复用。

### 已完成
- `ModelConfig` / `ModelProfile` / `AgentModelRoute` 增加隐藏 `api_key`、`api_key_secret_id`、`api_key_masked`。
- `ModelConfigUpdate` 支持真实 `api_key` 输入，并允许空 `api_key_env_var`。
- SQLite 自动迁移 `model_config`、`model_profiles`、`agent_model_routes` 的密文和掩码字段。
- 保存模型配置时不会把明文 Key 写入普通配置字段；读取时只在后端内存对象中恢复隐藏 Key。
- 后端测试覆盖：真实 Key 保存、响应不泄露明文、SQLite 不出现明文、测试连接能拿到保存 Key。

### 未完成
- 前端模型/API 面板还没有简化成“选择服务商/模型 + 输入真实 Key + 显示/隐藏 + 删除”的新界面。
- 还没有实现单独删除已保存 API Key 的接口；当前空 Key 更新会保留已有 Key。
- 本阶段未引入 Windows DPAPI；当前使用项目内本地派生密钥处理 SQLite 中的 Key，后续可升级为 DPAPI 或系统凭据库。

### 风险
- 本地派生密钥适合本地单用户第一版，不能等同于企业云端 KMS。
- 如果更换系统用户或机器，旧 SQLite 中保存的 Key 可能无法恢复，需要重新填写。
- 前端旧 UI 仍显示环境变量相关文案，下一阶段需要收敛，否则用户体验仍会显得复杂。

### 下一步任务
- 7G-2：把前端模型/API 面板改成简单模式：服务商、模型、真实 Key、保存、测试、删除/隐藏。
- 7G-3：增加总模型大脑 `OrchestratorAgent` 和简洁模型路由表。
- 7H：新增一眼看懂的系统状态 / 后端控制台。

### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_model_config_accepts_saved_api_key_without_leaking_plaintext -q` 先失败于 422，暴露后端仍强制环境变量名。
- 绿测：同一命令通过。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py -k "model_config or model_profiles or model_route or model_connection or tailor_uses_enabled_openai or tailor_uses_application_writer" -q` 通过，14 条相关后端测试通过。

## 7F-2：前端定制简历在线编辑与实时预览
### 当前真实状态
- 人审材料区现在把“简历改写要求”升级为“在线编辑 / 预览”。
- 用户可以直接在 textarea 中修改定制简历正文，右侧/下方预览会跟随输入实时变化。
- 点击“保存编辑版本”会调用 `PATCH /api/tailored-resumes/{id}/revision` 保存当前编辑内容。
- 保存成功后会调用 `GET /api/tailored-resumes/{id}/preview` 回填后端预览文本，并更新当前 `TailorBundle` 的 `resume_text/resume_rewrite/project_rewrite`。
- PDF 下载入口保持不变，但保存后的编辑版本会进入后端 revision，因此下载会使用最新版本。

### 已完成
- 前端 API client 新增 `getTailoredResumeRevision()`、`updateTailoredResumeRevision()`、`getTailoredResumePreview()`。
- 新增 `TailoredResumeRevision` 和 `TailoredResumePreview` 类型。
- 人审材料区新增可编辑正文、实时预览、保存状态提示。
- 前端 API 单测覆盖 revision 读取、保存和 preview endpoint。

### 未完成
- 当前没有单独的 React 组件测试；本阶段用 API 单测、TypeScript build 和 lint 验证。
- preview 仍是文本级预览，不是最终 DOCX/PDF 版式预览。
- 暂未提供“恢复 AI 原始版本”或 revision 历史版本。

### 风险
- 前端保存后会把当前页面里的材料文本同步为编辑版本；如果用户想保留 AI 初稿，需要后续加历史版本或恢复按钮。
- PDF 最终版式仍受 DOCX 模板和本机 Word/LibreOffice 转换能力影响。

### 下一步任务
- 7G：简化模型/API 设置，支持真实 Key 本地加密保存、隐藏、测试和删除。
- 7H：新增一眼看懂的后端操作页。

### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm test -- --run src/lib/api.test.ts -t "tailored resume revision"` 先失败于 `api.getTailoredResumeRevision is not a function`。
- 绿测：同一命令通过。
- `npm test -- --run src/lib/api.test.ts` 通过，15 条前端 API 单测通过。
- `npm run build` 通过。
- `npm run lint` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_tailored_resume_revision_can_be_edited_previewed_and_used_for_pdf -q` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7F-1：定制简历在线编辑 Revision/Preview 后端
### 当前真实状态
- 后端新增 `GET /api/tailored-resumes/{id}/revision`，可以读取当前可编辑简历正文。
- 后端新增 `PATCH /api/tailored-resumes/{id}/revision`，可以保存用户在线编辑后的简历正文。
- 后端新增 `GET /api/tailored-resumes/{id}/preview`，返回当前 revision 的纯文本和简单 HTML 预览。
- 保存 revision 后会同步更新 `resume_text`、`resume_rewrite`、`project_rewrite`，因此现有 PDF 下载链路会使用最新编辑内容。

### 已完成
- `SQLiteStore` 增加读取和更新 tailored resume revision 的方法。
- FastAPI 增加 revision 读取、保存和 preview 路由。
- 回归测试覆盖：读取初始 revision、保存编辑文本、preview 返回新内容、PDF 渲染拿到编辑后的文本、空文本返回 400。

### 未完成
- 前端还没有在线编辑器 UI；当前只能通过 API 调用 revision/preview。
- preview 目前是轻量 HTML，不是最终 PDF 渲染预览。
- 还没有 revision 历史版本表；第一版只保留最新编辑版本。

### 风险
- 当前 PATCH 会覆盖 `resume_text/resume_rewrite/project_rewrite` 三个字段，适合第一版“最新编辑即当前版本”；如果后续要保留 AI 原始输出，需要新增历史表。
- preview HTML 只做基础转义和换行，不代表最终 DOCX/PDF 排版。

### 下一步任务
- 7F-2：前端人审材料区接入在线编辑器和实时预览，保存后刷新当前材料。
- 7G：简化模型/API 设置，支持真实 Key 本地加密保存、隐藏、测试和删除。
- 7H：新增一眼看懂的后端操作页。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_tailored_resume_revision_can_be_edited_previewed_and_used_for_pdf -q` 先失败于 `/revision` 返回 404。
- 绿测：同一命令通过。
- `python -m pytest backend\tests\test_api_flow.py::test_tailored_resume_revision_can_be_edited_previewed_and_used_for_pdf backend\tests\test_api_flow.py::test_tailored_resume_pdf_can_be_downloaded_after_material_generation backend\tests\test_api_flow.py::test_tailored_resume_pdf_requires_docx_template -q` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7E-5：前端简历读取状态 + 手动补全入口
### 当前真实状态
- 简历上传区现在支持选择 `.png/.jpg/.jpeg` 图片简历，文案已从 `txt/pdf/docx` 扩展为 `txt/pdf/docx/png/jpg`。
- 上传后会显示“读取状态”：已提取文本、需要 OCR 或手动补全、图片简历需要补全文本、已手动补全。
- 当后端标记 `manual_text_required=true` 时，前端会显示“粘贴简历正文”文本框和“保存简历正文”按钮。
- 保存手动正文会调用 `PATCH /api/resumes/{id}/manual-text`，成功后刷新当前简历、重新带出推荐关键词和城市。
- 当前简历没有可用正文时，创建搜索任务和生成材料会被前端拦截，避免继续跑空材料。

### 已完成
- `api.updateResumeManualText()` 接入手动补全文本接口。
- 新增 `getResumeReadingStatus()`，把后端 extraction/image_reading 状态转成前端可读状态。
- 上传面板显示读取状态 chip、详情说明、操作建议和手动补全文本框。
- 前端单测覆盖手动正文 API 和读取状态 helper。

### 未完成
- 图片简历原图预览还没展示到前端；当前只支持上传后补全文本。
- 扫描 PDF 页面的图像预览还没做，仍需要用户粘贴正文。
- 在线编辑简历、简化模型/API 面板、后端操作页仍未开始。

### 风险
- OCR 依赖仍是后端可选能力；大多数本机没有装好 OCR 时，会进入手动补全路径。
- 前端目前只根据后端 profile 状态显示，不能单独判断 PDF 是否真的有图片页。
- 当前项目仍有大量历史未提交改动，本阶段只处理 7E-5 前端入口。

### 下一步任务
- 7F：生成材料后增加在线编辑和实时预览，PDF 下载使用最新 revision。
- 7G：简化模型/API 设置，支持真实 Key 本地加密保存、隐藏、测试和删除。
- 7H：新增一眼看懂的后端操作页。

### 最近修改文件
- `frontend/src/lib/api.ts`
- `frontend/src/types.ts`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm test -- --run src/lib/api.test.ts src/lib/dashboard.test.ts` 先失败于 `api.updateResumeManualText is not a function` 和 `getResumeReadingStatus is not a function`。
- 绿测：同一命令通过，36 条前端 helper/API 单测通过。
- `python -m pytest backend\tests\test_api_flow.py::test_scanned_pdf_upload_requires_manual_text_before_materials backend\tests\test_api_flow.py::test_image_resume_upload_keeps_image_and_requests_manual_text -q` 通过。
- `npm run build` 通过。
- `npm run lint` 通过。
- `git diff --check` 通过，仅有 Windows 行尾转换提示。

## 7E-4：简历读取增强 + 截图兜底（后端最小闭环）
### 当前真实状态
- `/api/resumes` 现在能区分普通可读文本、可读 PDF、扫描版/图片型 PDF、图片简历上传。
- 扫描版 PDF 不再假装解析成功；`profile.pdf_reading.status` 会返回 `needs_ocr`，并标记 `manual_text_required=true` 和 `can_generate_materials=false`。
- `.png/.jpg/.jpeg` 简历截图可以上传；本机 OCR 可用时会尝试提取文本，不可用或无文字时返回 `manual_required`，并保存原始图片 bytes 供后续预览/人工补全使用。
- 新增 `PATCH /api/resumes/{resume_id}/manual-text`，允许用户把手动补全的简历正文写回同一份简历，重新生成技能、推荐关键词、城市和可生成材料状态。

### 已完成
- `ResumeParserAgent` 增加图片简历分支、扫描 PDF 状态、可选本机 OCR 尝试和手动文本 profile 重建。
- 存储层会保留图片简历原始 bytes，同时继续只把 DOCX 标记为模板可用。
- 上传扫描 PDF/图片后的 API 响应包含 `source_type`、`status`、`confidence`、`manual_text_required` 等读取状态。
- 后端测试覆盖扫描 PDF、图片简历保存、手动补全文本和旧 PDF/TXT 解析兼容。

### 未完成
- 前端还没有展示“已提取文本 / 需要 OCR / 需要手动补全”的新版读取状态。
- 图片简历预览和手动补全文本输入框尚未接到页面。
- OCR 只做可选本机尝试；没有安装 OCR 依赖时会走手动补全，不会自动识别图片中文字。
- 在线编辑简历、简化模型/API 面板、后端操作页仍未开始。

### 风险
- `pytesseract` / PIL 若未安装或本机没有 OCR 引擎，图片解析会稳定降级为手动补全，这是预期行为。
- 扫描 PDF 目前只通过 `pypdf` 判断“无可提取文本”，后续如果要做页面截图预览，需要继续保存或渲染 PDF 页面图像。
- 当前项目仍有大量历史未提交改动，本阶段只处理 7E-4 后端闭环。

### 下一步任务
- 7E-5：前端上传区显示简历读取状态，并在需要时提供手动补全文本入口。
- 7F：生成材料后增加在线编辑和实时预览，PDF 下载使用最新 revision。
- 7G：简化模型/API 设置，支持真实 Key 本地加密保存、隐藏、测试和删除。
- 7H：新增一眼看懂的后端操作页。

### 最近修改文件
- `backend/app/agents/resume_parser.py`
- `backend/app/storage.py`
- `backend/app/services/job_application_service.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_scanned_pdf_upload_requires_manual_text_before_materials backend\tests\test_api_flow.py::test_image_resume_upload_keeps_image_and_requests_manual_text backend\tests\test_api_flow.py::test_pdf_resume_upload_can_generate_tailored_materials -q` 通过。
- `python -m pytest backend\tests\test_agents.py::test_resume_parser_agent_extracts_plain_text_and_known_skills_locally backend\tests\test_agents.py::test_resume_parser_agent_extracts_pdf_text_with_reading_metadata -q` 通过。

## 7D-6：ReviewAgent 独立模型路由
### 当前真实状态
- 后端 `agent_model_routes` 白名单已加入 `ReviewAgent`，`GET /api/model-routes` 会返回 `ApplicationWriterAgent`、`JobMatchAgent` 和 `ReviewAgent`。
- `PUT /api/model-routes/ReviewAgent` 可以保存独立 provider、model、base_url、Key 环境变量、启用状态和价格字段。
- 材料生成链路在执行 ReviewAgent 时会读取 `self.store.get_agent_model_route("ReviewAgent")`，不再用全局模型配置代替 ReviewAgent 路由。
- 当前 ReviewAgent 的事实审核逻辑仍是确定性本地规则；即使路由配置了外部模型，`ModelRouterService` 也会在 `review_route` 中明确标记 `mode=local_rule`，并保留所选 provider/model 作为配置证据。

### 已完成
- `MODEL_ROUTE_AGENTS` 增加 `ReviewAgent`。
- `JobApplicationService.tailor_for_job()` 的 ReviewAgent 阶段改为读取独立 Agent 路由。
- `ModelRouterService` 为 ReviewAgent 返回可观察的配置路由，同时明确审核仍本地执行，避免误报“外部模型已审核事实”。
- 后端回归测试覆盖 ReviewAgent 路由列表、保存、Key 配置状态、真实 Key 不泄露，以及材料生成时使用 ReviewAgent 独立路由。

### 未完成
- ReviewAgent 还没有真正调用外部 LLM 做二次审核；当前仍由本地 `ReviewAgent.review()` 做事实边界检查。
- 前端 `MODEL_ROUTE_AGENT_LABELS` 暂未新增中文 label；弹窗会显示后端返回的 `ReviewAgent` 名称，功能可用但文案可继续打磨。
- 尚未把 ReviewAgent 的单次审核 token/成本写成独立外部 LLM usage，因为本阶段没有新增外部审核调用。

### 风险
- 如果后续把 ReviewAgent 改成外部模型审核，必须继续保留本地事实规则作为兜底，不能让模型自行放行虚构经历。
- 当前 ReviewAgent route 的 provider/model 是“配置证据”，不是“外部审核已执行”的证据；前端和文档必须避免混淆。
- 当前项目仍有大量历史未提交改动，本阶段只处理 ReviewAgent 模型路由相关后端文件和状态文档。

### 下一步任务
- 7D-7：前端为 `ReviewAgent` 增加中文路由标签，并在模型调用状态区更清楚地区分“配置了模型路由”和“实际调用外部模型”。
- 7E-4：继续增强 PDF 读取 Skill 路线，增加前端 PDF 读取状态展示，并评估 OCR/扫描件处理入口。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 7B-2：Skill Runner 接入已有低风险业务函数，并记录 skill run 到 Agent/Orchestrator 事件流。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/services/model_router_service.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`python -m pytest backend\tests\test_api_flow.py::test_agent_model_routes_can_be_saved_per_agent backend\tests\test_api_flow.py::test_tailor_routes_application_writer_through_model_router -q` 先失败于 ReviewAgent 不在路由列表，以及 ReviewAgent 仍使用全局模型配置。
- 绿测：同一命令通过。
- `python -m pytest backend\tests\test_api_flow.py -k "model_profiles or model_config or model_route or model_connection or tailor_routes_application_writer" -q` 通过，12 条相关后端回归通过。

## 7D-5：Manage Models 弹窗内 Agent 路由套用
### 当前真实状态
- `Manage Models...` 弹窗现在不仅能管理全局模型档案，还能把当前选中的模型档案直接套用到后端已返回的 Agent 路由。
- 弹窗内新增“套用到 Agent 路由”区域，显示每个可配置 Agent 的当前模型、目标模型和 Key 状态。
- 点击“套用到此 Agent”会复用现有 `/api/model-routes/{agent_name}` 保存流程，不新增后端接口，也不保存真实 API Key。
- 当前后端持久化路由只包含 `ApplicationWriterAgent` 和 `JobMatchAgent`；`ReviewAgent` 仍未进入 `agent_model_routes` 白名单，因此本阶段不伪造 ReviewAgent 路由。

### 已完成
- 新增 `buildModelRouteApplyOptions()` helper，集中生成弹窗里的 Agent 路由套用卡片数据。
- 新增前端单测覆盖：选中模型档案时可套用到 Agent；未选择档案时按钮不可用。
- `App.tsx` 的 `handleApplyProfileToModelRoute()` 支持传入弹窗当前选中的 profile id，同时保留下方旧路由表单行为。
- `Manage Models...` 弹窗新增 Agent 路由卡片和套用按钮。
- `styles.css` 新增路由套用卡片样式和移动端布局。

### 未完成
- `ReviewAgent` 尚未支持独立模型路由；如果要让它也出现在弹窗中，需要后续修改后端 `MODEL_ROUTE_AGENTS`、默认配置、调用链和测试。
- 弹窗仍未提供批量“一键套用到全部 Agent”；当前是逐个 Agent 点击，避免误覆盖。
- 尚未做浏览器截图级冒烟；本阶段以单测、TypeScript build 和 lint 验证。

### 风险
- 删除模型档案不会自动回滚已经套用到 Agent 的路由，这是当前设计的安全边界；档案是模板，Agent 路由是保存后的实际配置。
- 当前后端 ReviewAgent 仍偏本地/全局路径，前端不会假装它已独立可配，避免用户以为 ReviewAgent 已接入外部模型。
- 当前项目仍有大量历史未提交改动，本阶段只处理模型路由弹窗相关前端文件和状态文档。

### 下一步任务
- 7D-6：后端补 `ReviewAgent` 独立模型路由，让弹窗可以真实套用到 ReviewAgent，并确保调用链使用该路由或明确保持本地审核。
- 7E-4：继续增强 PDF 读取 Skill 路线，增加前端 PDF 读取状态展示，并评估 OCR/扫描件处理入口。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 7B-2：Skill Runner 接入已有低风险业务函数，并记录 skill run 到 Agent/Orchestrator 事件流。

### 最近修改文件
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm test -- --run src/lib/dashboard.test.ts` 先失败于 `buildModelRouteApplyOptions is not a function`。
- 绿测：`npm test -- --run src/lib/dashboard.test.ts` 通过，21 条前端 dashboard 单测通过。
- `npm run build` 通过。
- `npm run lint` 通过。

## 7D-4：Manage Models 弹窗式多模型选择器
### 当前真实状态
- “模型 / API”面板顶部新增 `Model Picker` 摘要和 `Manage Models...` 入口。
- 点击 `Manage Models...` 会打开独立弹窗，左侧可搜索和选择模型档案，右侧可编辑当前档案或新建档案。
- 搜索支持按档案名称、provider、model、API 地址和 Key 环境变量名过滤。
- 弹窗复用已有模型档案后端接口：保存/更新、套用为当前全局模型、删除档案，仍不保存真实 API Key。
- 弹窗里保留 `Auto` 选项，用于回到当前全局模型配置；DeepSeek v4pro 仍可一键填入。

### 已完成
- 新增 `filterModelProfiles()` helper，并用前端单测覆盖搜索行为。
- `App.tsx` 新增模型管理弹窗状态、搜索状态、过滤后的模型档案列表和弹窗 UI。
- `styles.css` 新增模型选择器、模型列表、编辑区和移动端布局样式。
- 保留原有面板内模型配置表单和 Agent 路由套用能力，避免破坏已完成的模型 API 工作流。

### 未完成
- 还没有把 `Manage Models...` 做成全局顶部下拉菜单；当前入口仍在“模型 / API”面板内。
- 当前模型档案仍只保存环境变量名，不保存真实 API Key；用户需要在本机环境或 `.env` 中放入 Key。
- Agent 路由仍需要在下方 Agent 模型路由区分别套用档案；弹窗暂未提供“保存后立即批量套用到多个 Agent”的能力。
- 尚未做 Playwright 视觉截图冒烟；本阶段用单测、TypeScript build 和 lint 验证。

### 风险
- 因为保留了面板内旧入口和新增弹窗，短期存在两个 UI 入口操作同一批模型档案；功能一致，但后续可以把旧入口收敛成只读摘要。
- 删除档案不会清空当前全局模型配置，也不会清空已保存 Agent 路由；这是安全行为，但用户需要理解“档案”和“已套用配置”不是同一个对象。
- 当前项目仍有大量历史未提交改动，本阶段只处理模型选择器相关前端文件和状态文档。

### 下一步任务
- 7D-5：把 Agent 路由套用入口也接入模型选择器体验，允许从弹窗直接选择档案并套用到 `ApplicationWriterAgent` / `JobMatchAgent` / `ReviewAgent`。
- 7E-4：继续增强 PDF 读取 Skill 路线，增加前端 PDF 读取状态展示，并评估 OCR/扫描件处理入口。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 7B-2：Skill Runner 接入已有低风险业务函数，并记录 skill run 到 Agent/Orchestrator 事件流。

### 最近修改文件
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红测：`npm test -- --run src/lib/dashboard.test.ts` 先失败于 `filterModelProfiles is not a function`。
- 绿测：`npm test -- --run src/lib/dashboard.test.ts` 通过，20 条前端 dashboard 单测通过。
- `npm run build` 通过。
- `npm run lint` 通过。

## 7E-3：前端 PDF 模板状态展示
### 当前真实状态
- 人审材料区现在会根据当前简历、是否已有生成材料、后端下载错误，显示模板化 PDF 的可用状态。
- DOCX 模板可用且已有材料时显示“模板化 PDF：可下载”，下载按钮可用。
- PDF 简历或旧数据没有 DOCX 模板时，前端会明确提示“PDF 简历可生成材料，但不能保留原 PDF 排版”或“需重新上传 DOCX 简历”，下载按钮不可用。
- 后端返回缺少转换器、渲染器不可用、需重新上传 DOCX 等错误时，前端会显示可执行的原因提示。

### 已完成
- 新增 `getPdfTemplateStatus()`，集中判断 DOCX / PDF / 旧简历 / 未生成材料的 PDF 下载状态。
- 新增 `getPdfDownloadFailureMessage()`，把 PDF 下载失败原因映射成前端可读提示。
- 人审材料区的“下载模板化一页 PDF”按钮接入状态判断，避免无模板时仍让用户点击失败。
- PDF 状态区域增加 label、说明和操作建议，避免只显示一行模糊错误。

### 未完成
- 仍未实现 PDF 原排版模板化改写；当前 PDF 简历只支持读取文本并生成材料，不保证保留 PDF 图片和原版式。
- 仍未接入 OCR，扫描版 PDF 可能只能得到空文本或读取警告。
- 仍未实现更接近截图里 `Manage Models...` 的弹窗式模型搜索/选择器；当前是面板内模型档案管理和 Agent 路由套用。

### 风险
- 没有 Microsoft Word 或 LibreOffice 时，DOCX -> PDF 下载仍会失败；本阶段只把错误提示前置和结构化。
- PDF 简历用于改写时需要继续依赖 `ReviewAgent` 审核事实边界，不能把模型输出直接当作真实经历。
- 当前项目有大量历史 diff，本阶段只处理前端 PDF 状态和状态文档。

### 下一步任务
- 7D-4：做类似 `Manage Models...` 的弹窗式多模型选择器，支持搜索、选择不同 provider/model 版本、新增、修改、删除、套用到 Agent 路由。
- 7E-4：继续增强 PDF 读取 Skill 路线，增加前端 PDF 读取状态展示，并评估 OCR/扫描件处理入口。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 7B-2：Skill Runner 接入已有低风险业务函数，并记录 skill run 到 Agent/Orchestrator 事件流。

### 最近修改文件
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/CODEX_STATUS.md`

### 验证结果
- `npm test -- --run src/lib/dashboard.test.ts` 通过，19 条前端 dashboard 单测通过。
- `npm run build` 通过。
- `npm run lint` 通过。

## 7E-2：模板化 PDF 导出校验与渲染器探测
### 当前真实状态
- 模板化简历 PDF 生成结果返回前会先经过 `PdfRenderValidator` 校验：必须能被 `pypdf` 解析、必须至少 1 页、默认最多 1 页。
- 当首次导出的 PDF 超过 1 页时，仍会压缩可编辑简历正文后重新导出；压缩后仍超过 1 页会返回明确错误。
- 如果本机 `pdftoppm` 可用，校验器会渲染第一页并确认输出 PNG 存在且非空；如果默认 `pdftoppm` 包装脚本不可运行，会降级跳过渲染，不阻断 DOCX -> PDF 下载。

### 已完成
- 新增 `PdfRenderValidator`，集中处理 PDF 可解析性、页数和可选渲染检查。
- `TailoredResumePdfService` 返回 PDF 前接入校验器，并保留多页压缩重试逻辑。
- 新增回归测试：无效 PDF bytes 返回清晰错误；默认渲染器不可用时不误伤下载；服务返回前会调用校验器。
- 保持前端下载入口不变，后端错误仍通过现有 PDF 下载接口返回。

### 未完成
- 当前只渲染第一页；完整视觉人工/自动检查仍需要后续对真实 DOCX 模板导出的 PDF 做截图级检查。
- 本机 bundled `pdftoppm.cmd` 存在但执行失败，因此本阶段自动验证实际走的是 `pypdf` 解析 + 一页校验，未完成真实 PNG 渲染冒烟。
- PDF 源模板原排版改写仍未实现；当前模板化生成仍以 DOCX 源模板为主。

### 风险
- 没有 Microsoft Word 或 LibreOffice 时，DOCX -> PDF 转换仍会失败；本阶段只加固转换后的 PDF 校验，不新增转换器。
- `pypdf` 页数校验无法发现所有视觉问题；渲染器可用时才会进一步检查第一页是否能渲染。
- 当前项目仍存在大量历史未提交改动，本阶段只处理 PDF 服务相关文件。

### 下一步任务
- 7E-3：在前端人审材料区显示 PDF 模板状态：可下载 / 需 DOCX / 转换器缺失 / 渲染器缺失。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 7B-2：Skill Runner 接入已有低风险业务函数，并记录 skill run 到 Agent/Orchestrator 事件流。

### 最近修改文件
- `backend/app/services/pdf_service.py`
- `backend/tests/test_template_resume_pdf_service.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- `python -m pytest backend\tests\test_template_resume_pdf_service.py -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_tailored_resume_pdf_can_be_downloaded_after_material_generation backend\tests\test_api_flow.py::test_tailored_resume_pdf_requires_docx_template -q` 通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

## 7E-1：PDF 简历读取 Skill 元数据与生成链路
### 当前真实状态
- PDF 简历上传会通过已有 `pypdf` 抽取文本，并在 `profile.extraction` / `profile.pdf_reading` 中记录读取方式、状态、页数、空白页数、文本长度和警告。
- 上传 PDF 后仍可生成 `skills`、`suggested_keywords` 和 `can_generate_materials`，可继续进入搜索任务、岗位匹配和材料生成链路。
- `ResumeParserAgent` 成功事件的输出摘要会显示 `source`、`extraction` 和 PDF 页数，前端 Agent 状态区可观察 PDF 读取结果。

### 已完成
- `ResumeParserAgent` 从单纯返回文本升级为“文本 + 抽取元数据”。
- 保留旧 `_extract_text()` 字符串返回兼容，避免旧测试或内部调用被 tuple 破坏。
- 新增 PDF 解析单测，覆盖 `pypdf` 读取、技能识别、推荐关键词和读取元数据。
- 新增 API 链路测试，覆盖 PDF 上传后创建搜索任务并生成定制材料。

### 未完成
- 扫描版 PDF/OCR 尚未接入，当前只支持可抽取文本的 PDF。
- PDF 原排版模板化改写与一页导出尚未完成；当前模板化 PDF 下载仍以 DOCX 源模板为主。
- 前端尚未专门展示 `pdf_reading` 详细字段，只能通过简历摘要和 Agent 状态摘要间接观察。

### 风险
- `pypdf` 只能保证文本抽取，不保证布局顺序完全等同视觉排版；后续如果要基于 PDF 原排版生成，需要按 PDF Skill 做渲染检查。
- 空白页或扫描件会返回 `empty`/warning，需要后续 OCR 或提示用户上传 DOCX。
- 当前项目存在大量历史未提交改动，本阶段未处理这些无关 diff。

### 下一步任务
- 7E-2：评估 PDF 生成/导出路径，按 PDF Skill 渲染检查，避免乱码、黑底、溢出和不可读。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。
- 后续前端可补一个 PDF 读取状态提示，显示页数、读取状态和是否需要 OCR/DOCX。

### 最近修改文件
- `backend/app/agents/resume_parser.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_agents.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- `python -m pytest backend\tests\test_agents.py::test_resume_parser_agent_extracts_pdf_text_with_reading_metadata -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_pdf_resume_upload_can_generate_tailored_materials -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py::test_full_resume_to_application_flow -q` 通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。

## 7D-3：Agent 路由一键套用模型档案
### 当前真实状态
- `ApplicationWriterAgent` 和 `JobMatchAgent` 的模型路由卡片已能从已保存模型档案中选择配置。
- 点击“套用并保存到此 Agent”会把模型档案里的 provider、model、base_url、api_key_env_var、启用状态、超时和价格字段保存到对应 Agent 路由。
- 套用后会同步更新前端路由草稿和已保存路由显示，减少重复填写 API 地址、模型名和 Key 环境变量名。

### 已完成
- `App.tsx` 新增每个 Agent 路由的模型档案选择状态。
- 新增 `handleApplyProfileToModelRoute()`，复用现有 `/api/model-routes/{agent_name}` 保存接口。
- Agent 路由表单新增“从模型档案套用”下拉和“套用并保存到此 Agent”按钮。

### 未完成
- 还没有做独立弹窗式 `Manage Models...` 体验；当前仍是面板内管理。
- PDF 简历读取 Skill 支持尚未实现。
- RAG 还没有接入 `ApplicationWriterAgent` / `ReviewAgent` 的生成上下文。

### 风险
- 套用模型档案会直接覆盖当前 Agent 路由配置；如果用户临时手改了草稿但未保存，再点击套用会以档案为准。
- 仍然不保存真实 API Key，只保存环境变量名。

### 下一步任务
- 7E-1：接入 PDF 读取 Skill，支持 PDF 简历文本抽取、结构化画像和后续 LLM 简历改写。
- 7E-2：PDF 生成/导出按 PDF Skill 渲染检查，避免乱码、黑底、溢出和不可读。
- 7A-2：把 RAG 检索结果接入 `ApplicationWriterAgent` / `ReviewAgent` 的上下文。

### 最近修改文件
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- `npm run build` 通过。
- `npm run lint` 通过。

## 7D-2：前端多模型管理器最小闭环
### 当前真实状态
- “模型 / API”面板已接入后端模型档案接口，前端可以读取、选择、新建、保存/更新、套用和删除模型档案。
- 选择某个模型档案后，会把该档案的模型名、API 地址、Key 环境变量名、启用状态和价格字段载入现有模型配置表单。
- 套用模型档案会调用 `POST /api/model-profiles/{profile_id}/apply`，把该档案写入当前全局模型配置。
- 删除模型档案只删除档案本身，不会清空当前全局模型配置。

### 已完成
- 前端新增 `ModelProfile`、`ModelProfilesResponse` 类型。
- 前端 API client 新增模型档案 CRUD 和 apply 方法。
- API client 支持 `204 No Content`，避免删除档案后读空 JSON 报错。
- `App.tsx` 启动时读取模型档案，并在“模型 / API”面板顶部显示模型档案管理区。
- 新增前端 API 回归测试，覆盖模型档案列表、创建、更新、套用、删除。

### 未完成
- Agent 路由仍需要手工填写配置；尚未支持从模型档案一键套用到 `ApplicationWriterAgent` 或 `JobMatchAgent`。
- 还没有做更像桌面应用“Manage Models...”的弹窗式搜索/筛选体验；当前是面板内最小可用管理器。
- PDF 简历读取 Skill 支持尚未开始实现。

### 风险
- 当前 UI 复用旧面板样式，功能已通，但视觉上还不是独立弹窗；后续如果要完全接近截图里的模型下拉，需要再做一刀前端交互。
- 仍然只保存环境变量名，不保存真实 Key；用户需要在本机环境或 `.env` 中配置真实 API Key。
- `docs/CODEX_STATUS.md` 历史内容已有编码显示异常，本阶段继续只追加新状态，不重写旧历史。

### 下一步任务
- 7D-3：Agent 路由支持从已保存模型档案一键套用，减少重复填写 API 地址和 Key 环境变量名。
- 7E-1：接入 PDF 读取 Skill，支持 PDF 简历文本抽取和结构化画像，用于 LLM 简历改写。
- 7E-2：PDF 生成结果按 PDF Skill 做渲染检查，避免乱码、黑底、溢出和不可读。

### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- `npm test -- --run src/lib/api.test.ts` 通过，13 条前端 API 测试通过。
- `npm run build` 通过。
- `npm run lint` 通过。

## 7D-1：多模型/API 配置档案后端底座
### 当前真实状态
- 用户新增目标已纳入路线：简历修改/生成需要支持 PDF 读取 Skill；模型/API 区需要升级为类似“Manage Models”的多模型版本管理器，可保存、修改、删除和套用不同模型配置。
- 本阶段已先完成后端底座：新增模型档案列表、创建、更新、删除、套用到全局模型配置接口。
- API Key 仍不写入数据库和代码；模型档案只保存环境变量名，并返回 `api_key_configured` 供前端判断 Key 是否已配置。
- `v4pro`、`v4flash` 等已有别名仍会归一化为 `deepseek-v4-pro`、`deepseek-v4-flash`。

### 已完成
- 新增 `ModelProfile`、`ModelProfileCreate`、`ModelProfileUpdate`、`ModelProfilesResponse`。
- SQLite 新增 `model_profiles` 表。
- 新增 API：`GET /api/model-profiles`、`POST /api/model-profiles`、`PUT /api/model-profiles/{profile_id}`、`DELETE /api/model-profiles/{profile_id}`、`POST /api/model-profiles/{profile_id}/apply`。
- 新增回归测试覆盖模型档案创建、更新、列表、套用、删除，以及真实 Key 不泄露。

### 未完成
- 前端“Manage Models”样式的模型选择器/管理弹窗尚未接入。
- Agent 路由尚未直接从模型档案下拉选择；当前仍通过已有 `/api/model-routes` 保存具体配置。
- PDF 简历读取 Skill 支持尚未实现；当前只是把该目标加入路线。后续需要让 PDF 简历可被读取、分析，并参与简历改写/生成。
- PDF 版本的“基于原简历模板尽量保留排版生成”仍是高风险能力，后续需要按 PDF Skill 要求做渲染校验。

### 风险
- 不保存真实 API Key 会更安全，但前端只能保存环境变量名；用户仍需要在本机环境或 `.env` 中配置真实 Key。
- PDF 原版排版修改比 DOCX 更难，尤其是保留图片、基础信息和一页限制；后续应先做“PDF 文本读取 + 生成材料”，再评估可编辑 PDF 模板能力。
- 当前 `docs/CODEX_STATUS.md` 历史内容已有编码显示异常，本阶段只追加新状态，不重写旧历史。

### 下一步任务
- 7D-2：前端模型管理器，做“选择模型版本 / 管理模型 / 新增 / 修改 / 删除 / 套用”界面，并接入本阶段 API。
- 7D-3：让 Agent 模型路由可从已保存的模型档案中选择，减少重复填写 API 地址和环境变量名。
- 7E-1：接入 PDF 读取 Skill 路线，支持上传 PDF 后抽取简历文本、结构化信息和可改写区域，并用于 LLM 简历改写。
- 7E-2：验证 PDF 生成/导出效果，按 PDF Skill 要求渲染检查，避免黑底、乱码、溢出和不可读。

### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_model_profiles_can_be_created_updated_applied_and_deleted -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py -k "model_profiles or model_config or model_route or model_connection" -q` 通过，12 条相关回归通过。

## 7C-1：MCP Gateway 默认禁用与 allowlist 外壳
### 当前真实状态
- MCP Gateway 第一版安全外壳已落地：默认不启用任何外部 MCP server。
- 后端新增 `GET /api/mcp/servers`、`GET /api/mcp/tools`、`POST /api/mcp/tools/{server_id}/{tool_name}/call`。
- 当前运行环境未配置 `AGENT_BUSINESS_MCP_SERVERS`，因此 servers/tools 均为空。
- 未 allowlist 的 MCP tool 调用返回 403，不会启动外部进程。
### 已完成
- 新增 MCP schema：`McpServerConfig`、`McpToolDescriptor`、`McpToolCallRequest`、`McpToolCallResult`。
- `AGENT_BUSINESS_MCP_SERVERS` 支持 JSON allowlist 配置，默认空列表。
- `GET /api/mcp/tools` 会从启用 server 的 `allowed_tools` 生成工具描述。
- `POST /api/mcp/tools/{server_id}/{tool_name}/call` 会先检查 server/tool allowlist；未确认时返回 `requires_confirmation`，默认不执行外部命令。
### 未完成
- 尚未接入 stdio MCP JSON-RPC client，因此还不能真实执行 MCP tools/list 或 tools/call。
- 尚未记录 MCP tool 调用耗时、输出、错误到审计表或 Orchestrator 事件流。
- 前端尚未展示 MCP server/tool 配置状态。
### 风险
- 当前阶段是安全边界和配置外壳，不是完整 MCP client；下一阶段才会启动 allowlist 中的 stdio server。
- `AGENT_BUSINESS_MCP_SERVERS` 是环境变量 JSON，格式错误时会被忽略并返回空列表。
### 下一步任务
- 7C-2：实现 stdio MCP client，支持 allowlist server 的 `tools/list` 和人工确认后的 `tools/call`，并记录耗时、错误和输出摘要。
- 7B-2：Skill Runner 统一接入现有业务函数和 Orchestrator 事件流。
- 6N-14C 仍需用户确认岗位后才能执行真实平台投递人工冒烟。
### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_mcp_gateway_defaults_to_empty_allowlist_and_rejects_unknown_tools backend\tests\test_api_flow.py::test_mcp_gateway_lists_configured_allowlist_and_requires_confirmation -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py -k "mcp_gateway or skill_registry or knowledge_reindex or browser_cdp_search_mode or platform_apply" -q` 通过，12 条相关回归通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机 API 冒烟：`GET /api/mcp/servers` 返回 `[]`，`GET /api/mcp/tools` 返回 `[]`，未授权调用 `/api/mcp/tools/not-allowed/echo/call` 返回 403。

## 7B-1：Skill Registry 固定 allowlist 与高风险确认边界
### 当前真实状态
- 项目内 Skill Registry 第一版已落地，提供固定 allowlist，不允许任意 skill id 执行。
- 后端新增 `GET /api/skills` 和 `POST /api/skills/{skill_id}/run`。
- 当前 allowlist 共 7 个技能：`job.search.browser_cdp`、`job.detail.refresh`、`application.materials.generate`、`application.apply.preview`、`application.apply.platform`、`application.sync.readonly`、`knowledge.reindex`。
- 高风险技能 `application.apply.platform` 默认返回 `requires_confirmation`，不会在未确认时点击真实平台或写入投递。
- 低风险技能 `knowledge.reindex` 已可直接执行，当前运行库返回 `documents=460`。
### 已完成
- 新增 Skill schema：`SkillDefinition`、`SkillRunRequest`、`SkillRunResult`。
- 建立固定技能清单，标注风险等级、确认要求和输入参数形态。
- 高风险真实平台投递技能需要显式 `confirmed=true` 才能进入后续执行阶段；当前阶段未接入真实点击执行器。
- 新增回归：allowlist 可列出、高风险技能未确认时被拦截、未知 skill 返回 404、低风险知识库重建可直接运行。
### 未完成
- `job.search.browser_cdp`、`job.detail.refresh`、`application.materials.generate`、`application.apply.preview`、`application.sync.readonly` 仍是已注册能力卡，尚未统一通过 Skill Runner 调用现有业务函数。
- Orchestrator 事件流尚未记录每次 skill run。
- 前端尚未展示 Skill Registry 或 Skill run 审计日志。
- MCP Gateway 尚未开始。
### 风险
- 当前 Skill Registry 是后端 allowlist 和确认边界，不是完整插件系统；下一阶段需要把现有业务 API 迁到统一 Skill Runner，避免双入口长期并存。
- 高风险技能即便传 `confirmed=true`，当前也只返回注册状态，不会真实投递；这避免误触，但还没有完成最终 Skill 编排闭环。
### 下一步任务
- 7B-2：实现 Skill Runner，把低风险技能接到现有业务函数，并把 skill run 写入 Orchestrator/Agent 事件流。
- 7C-1：MCP Gateway 第一阶段，默认禁用外部 server，只读取 allowlist 配置并列出 server/tools。
- 6N-14C 仍需用户确认岗位后才能执行真实平台投递人工冒烟。
### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_skill_registry_lists_allowlist_and_enforces_high_risk_confirmation backend\tests\test_api_flow.py::test_low_risk_knowledge_reindex_skill_runs_directly -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py -k "skill_registry or knowledge_reindex or browser_cdp_search_mode or platform_apply or platform_sessions" -q` 通过，13 条相关回归通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机 API 冒烟：`GET /api/skills` 返回 7 个技能；`POST /api/skills/application.apply.platform/run` 在 `confirmed=false` 时返回 `requires_confirmation=true`；`POST /api/skills/knowledge.reindex/run` 返回 `status=success`、`documents=460`。

## 7A-1：SQLite FTS5 本地 RAG 最小闭环
### 当前真实状态
- 本地知识库第一版已落地，使用 SQLite + FTS5，不引入向量数据库。
- 后端新增知识库重建、文档列表和 RAG 查询 API；查询结果必须带来源，不返回无来源结论。
- 当前运行库冒烟：`POST /api/knowledge/reindex` 重建出 460 个来源文档、557 个 chunk，来源类型包括 `resume`、`job`、`application`、`tailored_resume`。
- 当前运行库查询 `FastAPI SQL Agent` 返回 5 个带来源命中的 chunk，answer 前缀明确为“基于本地知识库检索到以下来源”。
### 已完成
- 新增 RAG schema：`KnowledgeDocument`、`KnowledgeChunk`、`RetrievalHit`、`KnowledgeReindexResponse`、`RagQueryRequest`、`RagQueryResponse`。
- SQLite 新增 `knowledge_documents`、`knowledge_chunks`、`knowledge_chunks_fts`。
- 支持从简历、岗位、投递记录、生成材料重建知识库。
- 新增 API：
  - `GET /api/knowledge/documents`
  - `POST /api/knowledge/reindex`
  - `POST /api/rag/query`
- 新增回归：上传简历和生成岗位后可重建知识库，RAG 查询返回带来源的 chunk。
### 未完成
- RAG 尚未接入 `JobMatchAgent`、`ApplicationWriterAgent`、`ReviewAgent` 的上下文增强。
- 前端尚未提供知识库/检索面板。
- 尚未做删除/增量索引；当前第一版是全量重建。
- 尚未实现 RAG 评估指标、命中率统计和引用质量评分。
### 风险
- SQLite FTS5 默认分词对中文语义检索有限；第一版适合关键词检索，后续可加 embedding/vector DB。
- 当前运行库包含历史 demo 岗位和旧记录；真实工作流需要结合 search_run 过滤或来源标签进一步区分。
- answer 目前是来源汇总，不直接调用 LLM 生成长答案，避免无来源编造。
### 下一步任务
- 7A-2：把 RAG 检索结果接入 Agent 上下文，至少先让 `ApplicationWriterAgent`/`ReviewAgent` 可读取岗位 JD、原简历和历史材料来源。
- 7B-1：建立 Skill Registry 固定 allowlist，先封装“搜索岗位、刷新详情、生成材料、预检投递、真实平台投递、同步状态”。
- 6N-14C 仍需用户确认岗位后才能执行真实平台投递人工冒烟。
### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_knowledge_reindex_and_rag_query_return_source_chunks -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py -k "knowledge_reindex or browser_cdp_search_mode or platform_apply or platform_sessions or platform_job_extraction" -q` 通过，18 条相关回归通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机 API 冒烟：`POST /api/knowledge/reindex` 返回 `documents=460`、`chunks=557`；`POST /api/rag/query` 返回 `query_hits=5`。

## 6N-14C-Prep：真实 BOSS 入库与只读投递预检
### 当前真实状态
- 正式 `browser_cdp` 搜索任务已能把真实 BOSS 上海岗位写入岗位池，不再因内部 `limit=20` 导致 BOSS CDP 脚本超时。
- 本机真实入库冒烟：使用最新简历 `resume_id=29` 创建 BOSS `browser_cdp` 搜索任务 `run_id=37`，任务状态 `completed`，岗位池写入 7 条真实 BOSS 岗位。
- run #37 前 5 条岗位包括：`AI全栈开发工程师（实习）/即刻/400-410元/天`、`数据平台研发实习生(A207032)/上海源策未来智能科技/150-200元/天`、`IT运维实习生/衣特佳/150-280元/天`、`全栈开发工程师（实习生）/柿野文化/250-350元/天`、`全栈研发工程师实习生/上海璞康数据科技/150-200元/天`。
- 已对岗位 `job_id=406` 执行只读投递预检，平台页返回 `ready=true`，检测到按钮文本 `感兴趣 立即沟通`，source_url 为 BOSS 真实岗位详情页。
- 本阶段未调用 `/api/jobs/{id}/platform-apply`，没有点击平台投递/沟通按钮；投递表中不存在 `job_id=406` 的新增投递记录。
### 已完成
- 将正式 `browser_cdp` 搜索任务的首批入库上限收敛为 8 条，和已验证稳定的只读搜索路径一致。
- 更新后端回归，明确 `search-runs` 的 CDP 入库路径使用 `limit=8`。
- 完成真实 BOSS 入库 + 只读投递预检冒烟，证明下一步真实投递前的按钮证据可获取。
### 未完成
- 真实平台投递人工冒烟仍未执行：需要用户明确选择岗位并确认后，才允许调用 `/platform-apply` 点击平台原生按钮。
- `platform_proof` 的真实账号侧闭环还未产生新证据；目前只完成到预检 ready。
- 7A RAG、7B Skill Registry、7C MCP Gateway 尚未进入实现阶段。
### 风险
- 当前入库上限优先保证稳定，暂不追求一次导入更多岗位；后续应做分页或分段快照，而不是重新拉高单次 CDP 脚本负载。
- 预检 ready 只证明按钮存在，不等于平台已投递；只有 `/platform-apply` 返回 confirmed 后才能入库真实投递记录。
### 下一步任务
- 6N-14C：用户确认具体岗位后执行一次真实平台投递人工冒烟，核验 BOSS 页面“已沟通/已投递”和投递表 `platform_proof`。
- 若用户暂不确认真实投递，下一步可进入 7A：SQLite + FTS5 本地 RAG 第一阶段，但状态中需保留真实投递闭环未完成。
### 最近修改文件
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_browser_cdp_search_mode_saves_extracted_jobs_without_demo_fallback backend\tests\test_api_flow.py::test_browser_cdp_search_mode_controls_page_with_keywords_before_extracting -q` 通过。
- `python -m pytest backend\tests\test_api_flow.py -k "browser_cdp_search_mode or platform_apply or platform_sessions or platform_job_extraction or cdp_runtime_client" -q` 通过，18 条相关回归通过。
- `git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机真实冒烟：`POST /api/search-runs` 创建 run #37，`GET /api/jobs?search_run_id=37` 返回 7 条真实 BOSS 岗位。
- 本机只读预检：`POST /api/jobs/406/platform-apply-preview` 返回 `ready=true`、`status=ready`、`button_text=感兴趣 立即沟通`。
- 安全边界核验：`GET /api/applications` 中 `contains_job_406=false`，说明预检没有创建投递记录。

## 6N-14B：BOSS CDP 超时与占位岗位过滤修复
### 当前真实状态
- BOSS 真实只读搜索已从 `extract_failed: timed out` 修复为 `success`。
- 本机只读冒烟：BOSS 上海搜索页返回 7 条真实岗位，前 5 条包含 `Python`、`agent开发实习生`、`全栈研发工程师实习生`、`全栈开发工程师（实习生）`、`IT运维实习生`。
- BOSS 薪资字段可读，前 5 条示例包括 `150-250元/天`、`290-300元/天`、`150-200元/天`、`250-350元/天`、`150-280元/天`。
- BOSS 页面里的搜索框/加载占位项 `职位搜索/加载中` 已被过滤，不再作为岗位进入抽取结果。
### 已完成
- `CdpRuntimeClient.evaluate()` 增加连接超时和长脚本读取超时常量，连接成功后将 Runtime.evaluate 读取超时扩展到 30 秒。
- BOSS 非岗位候选过滤提前到 `job_detail` URL 判断之前，避免平台占位项伪装成 `job_detail/` 被误收。
- 补充回归：CDP runtime 必须延长 evaluate socket timeout；BOSS 搜索控件即使带 `job_detail/` URL 也应被丢弃。
### 未完成
- 尚未执行真实平台投递人工冒烟；本阶段仍然没有点击“立即沟通/投递”类按钮，也没有调用 `/platform-apply`。
- 真实岗位详情的完整 JD 质量还需要继续观察，当前本阶段只验证列表岗位、城市、薪资和过滤。
- 7A RAG、7B Skill Registry、7C MCP Gateway 尚未进入实现阶段。
### 风险
- BOSS 真实抽取已能返回列表，但后续若平台弹验证码、登录失效或 DOM 大改，仍可能退回 `extract_failed` 或 `empty`。
- CDP evaluate 读取超时延长后，失败反馈会更慢；后续可以把 BOSS 抽取拆成“快照列表”和“详情补全”两步进一步提速。
### 下一步任务
- 6N-14C：在用户明确确认并已登录真实平台后，执行真实平台投递人工冒烟，验证平台侧“已沟通/已投递”和 `platform_proof` 入库。
- 7A：真实平台闭环后，开始 SQLite + FTS5 本地 RAG 第一阶段。
### 最近修改文件
- `backend/app/services/browser_job_extractor_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_cdp_runtime_client_extends_socket_timeout_for_long_running_scripts -q` 初次失败，证明 CDP 仍使用旧 3 秒超时。
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_boss_extraction_recovers_live_card_salary_company_and_drops_search_widgets -q` 在占位 URL 改为 `job_detail/` 后失败，证明占位候选会漏进岗位池。
- 绿灯：两条定向测试通过。
- 绿灯：`python -m pytest backend\tests\test_api_flow.py -k "platform_sessions or platform_job_extraction or application_sync or browser_cdp_search_mode or platform_apply or latest_resume or boss_browser_script or cdp_runtime_client" -q` 通过，24 条相关回归通过。
- 本机只读搜索冒烟：`POST /api/platform-jobs/search`，platforms=`["boss"]`，city=`上海`，limit=`8`，返回 `status=success`、`job_count=7`。

## 6N-14A：本地默认 CDP 复用与真实只读冒烟
### 当前真实状态
- 本机 `127.0.0.1:9222` CDP 已可访问，当前检测到 BOSS 直聘和实习僧标签页。
- 后端 `/api/platform-sessions` 已能在未设置 `BROWSER_CDP_URL` 时自动复用默认 `127.0.0.1:9222`，前端刷新会话不再直接显示“未配置 BROWSER_CDP_URL”。
- `/api/platform-jobs/search` 只读冒烟已把 BOSS URL 拉到 `city=101020100` 的上海搜索页；实习僧 URL 也进入上海搜索页。
- 实习僧只读搜索冒烟成功，抽到 2 条上海岗位，薪资分别可读为 `180-200/天`、`200-300/天`。
- BOSS 只读搜索冒烟仍未通过：标签页和 WebSocket 可检测，但提取脚本执行 `timed out`，本阶段没有拿到 BOSS 岗位列表。
### 已完成
- `PlatformSessionService` 增加默认本机 CDP 探测：显式 `BROWSER_CDP_URL` 优先；未配置时仅在 `127.0.0.1:9222/json` 可访问时复用。
- `BrowserJobExtractorService` 接入同一默认 CDP 解析路径，支持读取岗位和搜索时自动复用本机 CDP。
- `ApplicationSyncService` 接入同一默认 CDP 解析路径，支持只读同步时自动复用本机 CDP。
- 补充回归：未设置环境变量但默认 CDP 可访问时，平台会话、岗位抽取、只读同步都能走通；默认 CDP 不可访问时仍保持“未配置”提示。
### 未完成
- BOSS 真实只读抽取仍存在 `Runtime.evaluate timed out`，需要下一阶段专门拆解脚本超时、验证码/加载层或 DOM 过重问题。
- 尚未执行真实平台投递人工冒烟；本阶段没有点击“立即沟通/投递”类按钮，也没有调用 `/platform-apply`。
- 7A RAG、7B Skill Registry、7C MCP Gateway 尚未进入实现阶段。
### 风险
- 当前运行后端虽然已热重载到默认 CDP 逻辑，但用户重启后端前仍应确认 `/api/platform-sessions` 返回 `browser_connected=true`。
- BOSS 页面如果出现验证码、风控加载层或脚本执行超时，不能把前端岗位池少量/空结果视为真实无岗位。
- PowerShell 直接发送中文 JSON 曾把关键词/城市编码为 `??`；后续人工验证应通过前端或 UTF-8/Unicode 转义请求发送，避免误导平台搜索 URL。
### 下一步任务
- 6N-14B：专门修 BOSS `Runtime.evaluate timed out`，优先把抽取脚本拆成更短的候选卡片快照脚本，必要时先返回卡片文本再异步补详情。
- 6N-14C：在用户明确确认并已登录真实平台后，执行一次真实平台投递人工冒烟，验证平台侧“已沟通/已投递”和 `platform_proof` 入库。
- 7A：完成真实平台闭环后，开始 SQLite + FTS5 本地 RAG 第一阶段。
### 最近修改文件
- `backend/app/services/platform_session_service.py`
- `backend/app/services/browser_job_extractor_service.py`
- `backend/app/services/application_sync_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：新增默认 CDP 复用测试初次失败，`/api/platform-sessions` 和只读同步仍返回 `not_configured`。
- 绿灯：`python -m pytest backend\tests\test_api_flow.py::test_platform_sessions_reuses_default_local_cdp_when_env_is_missing backend\tests\test_api_flow.py::test_platform_job_extraction_reads_visible_jobs_from_detected_browser_tab backend\tests\test_api_flow.py::test_application_sync_returns_read_only_proposals_without_overwriting_status -q` 通过。
- 绿灯：`python -m pytest backend\tests\test_api_flow.py -k "platform_sessions or platform_job_extraction or application_sync or browser_cdp_search_mode or platform_apply or latest_resume or boss_browser_script" -q` 通过，23 条相关回归通过。
- 本机接口探测：`GET /api/platform-sessions` 返回 `browser_connected=true`，BOSS/实习僧均为 `tab_detected`。
- 本机只读搜索冒烟：实习僧成功 2 条；BOSS `extract_failed`，错误为 `timed out`。

## 6N-13：README 真实 CDP 工作流与人工冒烟清单
### 当前真实状态
- README 已从“demo 为主、不依赖真实平台账号”的旧说明更新为当前真实 CDP 工作流说明。
- README 明确真实工作流依赖用户本机 CDP 浏览器和用户手动登录 BOSS/实习僧；系统不自动登录、不绕验证码、不保存 Cookie/密码。
- README 已记录真实平台搜索、只读预检、用户二次确认投递、`platform_proof` 入库和投递结果表展示的完整使用路径。
- README 已新增人工冒烟验收清单，说明自动测试不能替代真实账号侧验收。
### 已完成
- 更新项目定位和架构概览，区分 demo adapter 与真实 CDP 平台能力。
- 新增“真实平台 CDP 工作流”章节。
- 更新 API 概览，补充 `/api/resumes/latest`、`/api/browser/launch-cdp`、`/api/platform-sessions`、`/api/platform-jobs/search`、`/platform-apply-preview`、`/platform-apply`，并标明旧 `/apply-record` 已禁用。
- 新增“人工冒烟验收清单”。
- 更新合规边界，明确真实投递必须先预检、再用户确认、平台确认后才入库。
### 未完成
- 尚未完成真实已登录 BOSS/实习僧账号端到端人工冒烟记录。
- RAG、Skill Registry、MCP Gateway 尚未进入实现阶段。
### 风险
- README 的人工冒烟步骤需要用户已登录真实平台页面；没有真实平台会话时只能完成自动化回归，不能证明账号侧投递成功。
- 平台 DOM 或按钮文案变化时，人工冒烟可能暴露新的适配需求。
### 下一步任务
- 6N-14：真实浏览器人工冒烟记录；若用户授权并提供已登录 CDP 页面，核对 BOSS/实习僧账号侧状态。
- 7A：完成旧目标验收后，开始本地 RAG 知识库第一阶段。
### 最近修改文件
- `README.md`
- `docs/CODEX_STATUS.md`
### 验证结果
- `git diff --check` 通过；仅有 Windows LF/CRLF 提示。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 通过，29 条前端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。

## 6N-12B：投递结果表优先展示结构化平台证明
### 当前真实状态
- 前端 `ApplicationRecord` 类型已包含 `platform_proof`。
- 投递结果表不再只解析 `latest_note`；新记录会优先展示后端结构化 `platform_proof`。
- 旧记录仍通过 `latest_note` 中的 `平台确认/平台链接` 兜底解析，避免历史数据完全丢失证据展示。
- 投递表现在可展示平台证据、平台按钮文本、页面摘要、确认时间和原平台链接。
### 已完成
- 新增 `summarizePlatformConfirmation(proof, note)`，优先使用结构化 proof，旧数据 fallback 到备注解析。
- 新增前端单测，确认结构化 proof 会覆盖旧备注里的平台证据和链接。
- `App.tsx` 投递结果表接入 proof 展示。
### 未完成
- 尚未完成真实已登录 BOSS/实习僧账号端到端人工冒烟。
- 尚未补 README 的真实 CDP 工作流说明和人工验收清单。
### 风险
- 旧记录没有 proof 仍会显示“缺少平台确认证据”或仅显示备注解析结果，这是保守展示。
- 如果后端 proof 字段未来扩展，前端 helper 需要同步补展示字段。
### 下一步任务
- 6N-13：更新 README，把 demo 说明改成当前真实 CDP 工作流，并写清人工冒烟验收步骤。
- 6N-14：真实浏览器人工冒烟记录；若用户授权并提供已登录 CDP 页面，核对 BOSS/实习僧账号侧状态。
### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`npm test -- --run src/lib/dashboard.test.ts` 按预期失败，提示 `summarizePlatformConfirmation is not a function`。
- 绿灯：同一条定向测试通过，17 条 dashboard 测试通过。
- `npm run lint` 通过。

## 6N-12A：真实平台投递结构化证明后端落库
### 当前真实状态
- `ApplicationRecord` 新增 `platform_proof` 结构化字段，用于保存真实平台确认后的证据。
- SQLite `applications` 表新增 `platform_proof_json`，老库启动时会自动补列，旧记录默认返回空 proof。
- `/api/jobs/{job_id}/platform-apply` 仍然只有在平台返回 `confirmed=true` 后才创建投递记录；成功后会保存平台、岗位 URL、动作、状态、证据、按钮文本、确认时间和页面摘要。
- `/api/applications` 会返回持久化后的 `platform_proof`，不再只能从 `latest_note` 文本里解析真实平台证据。
### 已完成
- `ApplicationPlatformProof` schema。
- `SQLiteStore.create_application()` 支持写入结构化平台证明。
- `SQLiteStore.get_application()` 和 `list_applications()` 支持读取 proof。
- `JobApplicationService.apply_to_platform()` 成功时构造并保存 proof。
- 新增回归断言：平台确认投递后，接口响应和投递列表都包含同一份 `platform_proof`。
### 未完成
- 前端投递结果表尚未直接读取 `platform_proof`；下一阶段需要替换当前从 `latest_note` 解析证据的兜底逻辑。
- 真实已登录 BOSS/实习僧端到端人工冒烟仍未完成。
### 风险
- 当前 CDP 点击脚本返回的字段有限，`button_text` 和 `page_summary` 会优先使用平台结果字段，不足时从 evidence/status 保守兜底。
- 结构化 proof 能证明系统记录了平台确认信号，但真实账号侧最终状态仍需要人工冒烟核对。
### 下一步任务
- 6N-12B：前端投递结果表改为优先展示 `platform_proof`，保留 `latest_note` 解析作为旧数据兼容。
- 6N-13：更新 README 和人工冒烟验收清单。
### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_platform_apply_creates_application_only_after_platform_confirmation -q` 按预期失败，提示接口缺少 `platform_proof`。
- 绿灯：同一条定向测试通过。
- `python -m pytest backend\tests\test_api_flow.py -k "platform_apply or latest_resume or boss_browser_script or platform_job_extraction" -q` 通过，14 条相关回归通过。

## 6N-11：BOSS 虚拟列表滚动快照 fallback
### 当前真实状态
- BOSS 抽取脚本不再只保存滚动过程中发现的 DOM 节点引用；发现岗位卡片时会立即保存独立 payload 快照。
- `rawJobs` 会优先使用滚动快照，再合并当前 DOM 详情 payload，降低 BOSS 虚拟列表复用 DOM 节点时“页面有很多岗位但前端只显示少量/后面岗位覆盖前面岗位”的概率。
- 诊断中的 `candidate_card_count` 会取 DOM 节点数和快照数的最大值，更贴近滚动过程中实际发现的候选卡片数量。
### 已完成
- `BrowserJobExtractorService._extract_script()` 新增 `cardSnapshots`、`snapshotCandidateCard()`、`snapshotKey()` 和 `rawPayloads` 合并逻辑。
- 新增脚本级回归测试，要求 BOSS 抽取脚本包含滚动快照 fallback。
- 已跑 BOSS/CDP/平台投递/简历恢复相关后端回归，确认不破坏已有平台边界。
### 未完成
- 尚未在真实已登录 BOSS 页面人工冒烟确认“页面 5+ 岗位卡片 -> 前端岗位池 5+ 条相关岗位”。
- 尚未进入 6N-12 的结构化平台投递证明字段；当前投递表仍主要依赖 `latest_note` 解析平台确认信息。
### 风险
- 快照 payload 只能保存滚动时卡片可见文本；如果平台卡片本身不含完整 JD，仍需要单岗位详情刷新或人工补全 JD。
- BOSS 页面结构继续变化时，还需要继续补真实脱敏 HTML/DOM 回归样例。
### 下一步任务
- 6N-12：为真实平台投递结果增加结构化 `platform_proof`，保存按钮文本、确认状态、确认时间和页面摘要，并让投递结果表直接展示结构化证据。
- 6N-13：更新 README，把 demo 说明改成当前真实 CDP 工作流，并补人工冒烟验收清单。
### 最近修改文件
- `backend/app/services/browser_job_extractor_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_boss_browser_script_snapshots_cards_during_scroll_for_virtual_lists -q` 按预期失败，提示脚本缺少 `cardSnapshots`。
- 绿灯：同一条定向测试通过。
- `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or boss_browser_script or boss_extraction or detail_refresh_html or platform_apply or latest_resume" -q` 通过，16 条相关回归通过。

## 6N-9：真实平台投递证据前端展示
### 当前真实状态
- 投递结果表会从 `latest_note` 中解析后端真实平台投递写入的 `平台确认` 和 `平台链接`。
- 有平台确认的记录会在状态列显示“平台已确认”、平台按钮/动作证据和“打开平台记录”链接。
- 没有平台确认证据的历史记录会显示“缺少平台确认证据”，避免用户误以为旧本地记录已经真实投递到 BOSS/实习僧账号。
- 该阶段只增强前端展示；真实投递是否入库仍由后端 `platform-apply` 的平台确认边界控制。
### 已完成
- 新增 `extractPlatformConfirmation()`，负责从投递备注中拆出平台证据、平台链接和普通备注。
- 新增前端单测，覆盖平台确认备注解析和普通备注不误判。
- 投递结果表状态列接入平台确认摘要。
### 未完成
- 尚未在真实已登录 BOSS/实习僧账号中做人工冒烟：点击“检查投递入口 -> 确认真实平台投递”，再回到投递结果表核对“平台已确认”和平台链接。
- 尚未做更细的“投递成功后平台聊天窗口/申请记录截图式证据”采集；当前只保存文字 evidence 与原平台 URL。
### 风险
- 老数据没有 `平台确认/平台链接` 时会被标为缺少证据，这是预期的保守展示。
- 如果后端备注格式未来变化，需要同步更新前端解析规则。
### 下一步任务
- 6N-11：真实浏览器人工冒烟 BOSS 多岗位抽取；若仍少于页面可见卡片数，继续增加滚动过程文本快照 fallback。
- 6N-12：真实平台投递端到端人工冒烟，核对 BOSS/实习僧账号侧动作与投递结果表证据一致。
### 最近修改文件
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`npm test -- --run src/lib/dashboard.test.ts` 按预期失败，提示 `extractPlatformConfirmation is not a function`。
- 绿灯：同一条定向测试通过，16 条 dashboard 测试通过。
- `npm run lint` 通过。
- `npm test -- --run` 通过，28 个前端测试通过。
- `npm run build` 通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。

## 6N-10：BOSS 多卡片抽取与滚动采集增强
### 当前真实状态
- BOSS 抽取脚本已增强为“等待渲染 -> 采集当前可见卡片 -> 滚动页面/列表 -> 重复采集”，减少真实页面明明有很多岗位但只抽到一个的情况。
- BOSS `job_detail` 链接兜底不再只取链接文字，会向上寻找包含薪资、公司或城市信息的完整岗位卡片根节点。
- BOSS 选择器补充了 `job-card-wrap/job-card-body/jobCard/JobCard/searchJob/JobList/search-job-result/rec-job-list` 等大小写和新旧类名变体。
- 去重从单纯 DOM 节点引用扩展为 URL/文本 key，降低虚拟滚动列表复用 DOM 节点导致漏卡的概率。
### 已完成
- `BrowserJobExtractorService._extract_script()`：增强 BOSS 列表滚动采集与候选卡片恢复逻辑。
- 新增脚本级回归测试，要求 BOSS 脚本包含滚动采集、重复收集和 `job_detail` 链接向上恢复卡片根节点。
- 已跑现有 BOSS/CDP 抽取、薪资和详情页回归，确认没有破坏已有字段清洗。
### 未完成
- 尚未在真实已登录 BOSS 页面人工冒烟确认“截图中 5+ 左侧卡片 -> 前端岗位池 5+ 条”。
- 若 BOSS 使用完全虚拟化且滚动时复用同一批 DOM 节点，仍可能需要进一步在滚动过程中立刻快照 raw text，而不是保留 DOM 引用。
### 风险
- 自动滚动会改变当前 BOSS 标签页的位置；这是为了读取更多可见岗位，但用户操作时会看到页面滚动。
- 平台 DOM 持续变化时还可能需要继续补真实脱敏 HTML 回归样例。
### 下一步任务
- 6N-9：加强真实平台投递成功后的前端反馈，显示平台确认 evidence/note，并补人工冒烟检查清单。
- 6N-11：真实浏览器人工冒烟 BOSS 多岗位抽取；若仍少于页面可见卡片数，继续增加滚动过程文本快照 fallback。
### 最近修改文件
- `backend/app/services/browser_job_extractor_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_boss_browser_script_scrolls_and_recovers_cards_from_job_detail_links -q` 按预期失败，暴露脚本缺少 `scrollForMoreCards`。
- 绿灯：同一条定向测试通过。
- `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or boss_browser_script or boss_extraction or detail_refresh_html" -q` 通过，11 条 BOSS/CDP 回归通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 通过，26 个前端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。

## 6N-8：前端接入真实平台投递预检
### 当前真实状态
- 前端“平台投递/确认后在平台投递”流程已拆成两步：第一步只读检查真实平台岗位页，第二步用户再次确认后才调用真实平台投递接口。
- 第一次点击会调用 `POST /api/jobs/{job_id}/platform-apply-preview`，显示是否找到平台投递/沟通入口、按钮文本、证据和原平台链接。
- 只有预检 `ready=true` 后，按钮才切换为“确认真实投递/确认真实平台投递”；第二次点击才调用 `POST /api/jobs/{job_id}/platform-apply`。
- 投递结果表仍然只从 `/api/applications` 读取，而后端只有平台动作返回 `confirmed=true` 时才会创建记录。
### 已完成
- `frontend/src/types.ts` 新增 `PlatformApplyPreview` 类型。
- `frontend/src/lib/api.ts` 新增 `previewPlatformApply(jobId)`。
- `frontend/src/App.tsx` 新增 `applyPreviews` 状态，创建新搜索任务时会清空旧预检结果。
- 岗位列表动作按钮从“直接平台投递”改为“检查投递入口 -> 确认真实投递”。
- 人审材料区增加“真实平台投递预检”提示，展示预检证据和平台 URL。
- 新增前端 API 单测覆盖 preview endpoint。
### 未完成
- 尚未做真实 BOSS/实习僧端到端人工冒烟：需要在已登录 CDP 浏览器里选择一个真实岗位，先预检，再确认真实投递，并在平台页面确认账号侧可见。
- 尚未在按钮旁展示更细的失败恢复动作，例如“需要登录/验证码/按钮未找到”分别给出专门引导。
### 风险
- 如果平台页面 DOM 变化，预检可能返回 `button_not_found`，前端会阻止继续真实投递，不会伪造投递记录。
- 预检会打开岗位链接并切换当前平台标签页；这符合真实投递前检查，但用户需要知道当前浏览器页面会被导航。
### 下一步任务
- 6N-9：加强真实平台投递执行后的前端反馈，显示平台确认 note/evidence，并补一个人工冒烟检查清单。
- 6N-10：继续排查 BOSS 搜索多岗位但前端只显示少量的问题，聚焦真实 DOM 列表抽取和分页/滚动候选。
### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`npm test -- --run src/lib/api.test.ts` 按预期失败，暴露 `api.previewPlatformApply is not a function`。
- 绿灯：同一条前端 API 定向测试通过，12 个测试通过。
- `npm run lint` 通过。
- `npm test -- --run` 通过，26 个前端测试通过。
- `npm run build` 通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。

## 6N-7：真实平台投递前只读预检
### 当前真实状态
- 新增后端 `POST /api/jobs/{job_id}/platform-apply-preview`，用于在真实平台投递前打开目标岗位页并只读检测页面状态。
- 该接口只返回是否发现投递/沟通入口、按钮文本、页面证据、平台链接和岗位信息，不会点击按钮，不会创建 `ApplicationRecord`。
- 真实投递入库仍只允许走 `POST /api/jobs/{job_id}/platform-apply`，并且必须由平台动作返回 `confirmed=true` 后才写入投递记录。
### 已完成
- `JobApplicationService.preview_platform_application()`：按岗位 ID 获取岗位并调用 CDP 预检服务。
- `BrowserJobExtractorService.preview_apply_to_job()`：复用已登录 CDP 标签页，打开目标岗位 URL，再执行只读 preview 脚本。
- CDP preview 脚本可识别：登录/验证码/安全验证阻塞、已沟通/已投递状态、可点击的投递/沟通按钮、已打开的聊天/申请输入区。
- 新增后端回归测试，确认 preview 成功时不会写入 `/api/applications`。
### 未完成
- 前端尚未接入“先预检、再让用户确认真实投递”的 UI；下一阶段需要把 `记录投递` 按钮拆成“检查平台投递入口 -> 用户确认 -> 平台执行投递”。
- 尚未做真实 BOSS/实习僧端到端人工冒烟；当前自动化验证使用 fake CDP 服务。
### 风险
- 不同平台按钮文案和 DOM 可能继续变化；preview 找不到按钮时会返回 `button_not_found`，不会猜测或自动投递。
- preview 会导航到岗位 URL，但不会点击投递/沟通按钮；用户若在真实页面手动操作，需要再通过平台确认接口或后续同步记录真实状态。
### 下一步任务
- 6N-8：前端接入平台投递预检，显示预检证据和按钮文本，用户确认后再调用真实平台投递接口。
### 最近修改文件
- `backend/app/main.py`
- `backend/app/services/job_application_service.py`
- `backend/app/services/browser_job_extractor_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`
### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_platform_apply_preview_reports_button_without_creating_application -q` 按预期失败，暴露 preview 接口尚不存在。
- 绿灯：同一条定向测试通过，确认 preview 不创建投递记录。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py::test_platform_apply_preview_reports_button_without_creating_application backend\tests\test_api_flow.py::test_platform_apply_creates_application_only_after_platform_confirmation backend\tests\test_api_flow.py::test_legacy_apply_record_endpoint_rejects_local_only_application_records -q` 通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 通过，25 个前端测试通过。
- `npm run lint` 通过。
- `npm run build` 通过。

Updated: 2026-07-03 Asia/Shanghai

## 当前真实状态

当前项目已经初始化为本地 Git 仓库，默认分支为 `main`。项目是可运行的本地单用户 MVP，不是完整企业级成品。后端 FastAPI、SQLite、前端 React/Vite、demo 搜索闭环、模型/API 配置、CDP 浏览器会话检测、一键启动 CDP 浏览器、只读岗位提取、browser_cdp 搜索入库、CDP 控制网页搜索、提取诊断结构化、前端诊断展示、岗位详情弹窗、低质量 JD 人工补全提示、详情补全状态结构化、只读投递状态同步建议、前端人工确认同步、单岗位材料生成的 OpenAI-compatible LLM 最小闭环、LLM usage 的 status/error 可观察字段、最小模型路由策略、后端 Agent 状态事件接口、前端 Agent 状态轮询展示、Agent 失败事件可视化、Orchestrator 最小编排摘要、SQLite 持久化草案、前端任务摘要展示、任务步骤详情入口、失败任务人工重试边界提示、CDP 文本质量诊断、按 search_run 隔离岗位池、真实岗位一键导入、简历关键词推荐、薪资候选增强、详情页 JD/薪资补全回归、DOCX 模板保存、全简历可改写协议和模板化一页 PDF 下载已经具备。

真实平台能力仍限定在“用户启动 CDP 浏览器并登录平台后，系统可用关键词/城市控制搜索页并只读提取当前可见岗位”。系统不会自动登录、不会绕过验证码、不会保存 Cookie/密码、不会未经确认投递或发送招呼语，也不会在同步时静默覆盖用户手工维护的投递状态。

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
  - `POST /api/platform-jobs/search`
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
- 阶段 5D：任务详情接口与前端详情入口。
  - 新增 `GET /api/orchestrator/tasks/{task_id}`，返回指定 Orchestrator 任务及步骤详情，任务不存在时返回 404。
  - Agent 状态区域的最近编排任务摘要旁新增“查看步骤/收起”入口。
  - 前端点击“查看步骤”时读取任务详情接口，并展开 Agent、状态、步骤名和错误摘要。
  - 当前仍不做任务重试、任务恢复执行或自动继续失败任务。
- 阶段 5E：CDP 抽取文本质量修复。
  - `BrowserExtractionDiagnostics` 新增 `text_quality_warnings`。
  - CDP 抽取会识别 `□`、`�`、私用区字符和异常问号等污染文本。
  - 污染的城市/薪资字段会隐藏为“城市未展示/薪资未展示”，标题和描述都不可读的候选会被丢弃。
- 阶段 5F：真实搜索任务与岗位池隔离。
  - `JobPosting` 和 `GET /api/jobs` 返回 `search_run_id`。
  - `GET /api/jobs?search_run_id={id}` 只返回指定搜索任务的岗位。
  - 前端创建搜索任务后只刷新本次 run 的岗位，避免旧 demo 结果混入。
- 阶段 5G：前端一键导入真实岗位。
  - 默认搜索模式改为 `browser_cdp`。
  - 只读提取成功后显示“导入这批真实岗位到岗位池”按钮。
  - 导入按钮复用 `POST /api/search-runs` 的 `browser_cdp` 入库路径，不写 demo fallback。
- 阶段 5H：简历解析后自动推荐搜索关键词。
  - `ResumeParserAgent` 在 `profile` 中返回 `suggested_keywords` 和 `suggested_city`。
  - 前端上传简历成功后，在用户未手动改过搜索框时自动填入推荐关键词和城市。
  - 推荐逻辑为本地规则，不调用 LLM。
- 阶段 5I/5J：岗位定制简历 PDF 初版。
  - 曾新增 `GET /api/tailored-resumes/{id}/pdf` 和前端下载入口。
  - 初版 reportlab 重排式 PDF 已被 5N 的 DOCX 模板化一页 PDF 替代。
- 阶段 5K：薪资提取增强。
  - 新增 `SalaryExtractor`，从薪资选择器、属性文本、整张岗位卡片文本和脚本候选中提取可信薪资。
  - 支持 `15-25K`、`200-300/天`、`薪资面议`、`13薪/14薪` 等常见格式。
  - 污染薪资不再刷屏显示逐条 `hid polluted salary`，无法可信解析时统一显示“薪资读取失败”。
- 阶段 5L：保存原始简历模板。
  - `POST /api/resumes` 会保存 DOCX 原始 bytes、文件类型和模板可用状态。
  - 仅 DOCX 支持模板化生成；PDF/TXT 或旧数据会返回“请重新上传 DOCX 简历以保留模板”。
  - SQLite 老库启动时会自动补充模板相关列。
- 阶段 5M：项目部分定制协议。
  - `ApplicationWriterAgent` 输出 `project_rewrite + greeting + risk_flags`，兼容旧 `resume_text` 字段。
  - 该阶段的“只改项目经历”协议已被 5R 的全简历可改写协议替代；当前不再要求简历只能改项目经历。
  - `ReviewAgent` 会检查定制内容是否新增原简历不存在的公司、学校、技能或项目事实。
- 阶段 5N：模板 DOCX 注入与一页 PDF 导出。
  - 新增 `DocxProjectTemplateService`，定位项目段落并只替换项目文字，保留图片、页边距、样式和非项目文字。
  - `TailoredResumePdfService` 改为 DOCX 模板注入后导出 PDF，优先 Windows Word COM，备用 LibreOffice。
  - 导出后使用 `pypdf` 校验页数；超过 1 页时压缩项目段落，仍超过则返回需人工精简提示。
  - 前端人审区显示“模板化 PDF：可下载/需重新上传 DOCX/缺少转换器”，并展示项目段落改写。
- 阶段 5O：CDP 控制网页搜索。
  - 新增 `POST /api/platform-jobs/search`，接收平台、关键词、城市和 limit。
  - `browser_cdp` 搜索任务会优先调用 `search_and_extract()`，先控制已登录平台页输入/跳转搜索，再提取岗位。
  - 搜索控制只限搜索和读取，不自动投递、不自动发招呼语。
- 阶段 5P：薪资显示二次修复。
  - CDP 薪资候选增加相邻节点、父节点和页面脚本薪资片段。
  - 前端候选预览和岗位池无可信薪资时统一显示“薪资读取失败”。
- 阶段 5Q：诊断区精简与岗位详情弹窗。
  - CDP 提取诊断默认只展示标签页、WebSocket、候选卡片、成功提取四项。
  - 文本质量和 selector 命中信息折叠到“查看诊断详情”。
  - 岗位行新增“查看要求”按钮，右侧弹窗展示完整 JD、薪资、链接、匹配原因和风险/缺口。
- 阶段 5R：全简历可改写协议。
  - `TailoredResume` 新增 `resume_rewrite`，旧 `project_rewrite` 继续兼容。
  - LLM prompt 改为锁定身份信息和教育经历，允许基于原简历事实改写技能、项目、实习、经历描述、自我评价和摘要。
  - `ReviewAgent` 会检查 `resume_rewrite`，防止模型新增原简历不存在的技能、公司、学校或项目事实。
- 阶段 5S：模板 DOCX 替换范围升级。
  - 模板服务改为保留身份信息和教育经历，只替换教育经历后的可编辑正文。
  - PDF 生成优先使用 `resume_rewrite`，仍保留 `project_rewrite` 和 `resume_text` 兜底。
  - 图片 media、页边距和样式继续保留，一页限制仍只压缩可编辑正文。
- 阶段 5T-hotfix：真实搜索结果质量修复。
  - BOSS 搜索 URL 增加常用城市 code 映射，上海会使用 `101020100`，避免沿用杭州等当前页面城市。
  - `POST /api/platform-jobs/search` 会按请求城市过滤明显不匹配的岗位，未知城市/未展示城市保留。
  - CDP 抽取脚本会用登录态 `fetch` 尝试读取岗位详情页，列表卡片文本只作为兜底。
  - 污染标题包含 `□/�/私用区字符` 的岗位会直接丢弃，不再进入岗位池或预览列表。
  - 前端“只读提取岗位”改为“按关键词搜索并提取”，预览和创建搜索任务使用同一搜索控制路径。
- 阶段 5U：失败任务重试边界。
  - Orchestrator 任务详情新增 `retry_suggestion`，失败任务会返回人工重试建议、失败原因和安全边界。
  - 当前只展示“可人工重试/禁止自动重试”，不会自动恢复任务、不会自动投递、不会自动发送招呼语。
  - 前端 Agent 状态区展开“查看步骤”后会显示重试边界说明和下一步人工操作建议。
- 阶段 5V：真实平台回归样例与详情页选择器校验。
  - 新增脱敏回归样例：列表卡片只有残缺文本和失败薪资时，后端优先采用详情页 `detail_description` 和 `detail_salary_candidates`。
  - CDP 详情页脚本会从更多 BOSS/实习僧详情选择器、包含“职位描述/岗位职责/任职要求”等关键词的节点、详情页薪资节点和正文中收集 JD 与薪资候选。
  - 薪资提取修复了 `250-350元/天` 被截成 `250-350元` 的优先级问题。
- 阶段 5W：真实平台空详情/低质量结果的前端提示与人工补全入口。
  - 新增 `getJobDetailQuality()`，前端会判断岗位 JD 是否为空、是否只像列表卡片摘要。
  - 岗位详情弹窗在低质量 JD 时显示“详情未补全”的原因和操作提示。
  - 弹窗内提供“打开原岗位 / 刷新会话 / 重新提取”入口，方便用户在登录平台页面补全后回到工作台重试提取。
- 阶段 5W-hotfix：BOSS 候选卡片为 0 的搜索页兼容。
  - BOSS 搜索 URL 改为当前页面形态 `/web/geek/jobs`，避免仍跳到旧 `/web/geek/job` 路径。
  - CDP 抽取脚本会等待 React 岗位卡片/岗位链接渲染，最多轮询约 3 秒后再扫描。
  - BOSS 候选选择器增加 `job-card/job-list/search-job/ka=search_list` 等兜底，降低“标签页已检测但候选 0”的概率。
- 阶段 5X：低质量 JD 后端诊断原因结构化。
  - `ExtractedJobCandidate` 和 `JobPosting` 新增 `detail_status` / `detail_reason`。
  - CDP 抽取会返回 `detail_fetched`、`detail_blocked`、`card_only`、`low_quality` 等详情补全状态和中文原因。
  - SQLite `jobs` 表新库直接创建详情状态列，老库启动时自动补列；真实岗位导入后仍保留详情诊断原因。
  - 前端详情质量判断优先使用后端结构化原因，只有旧数据缺字段时才回退到文本长度判断。
- 阶段 5Y：真实平台岗位详情刷新单岗位入口。
  - 新增 `POST /api/jobs/{job_id}/refresh-detail`，可对单个已入库岗位重新读取平台详情页。
  - 后端会用当前 CDP 浏览器里已登录的平台标签页读取该岗位 URL，只更新 `salary`、`description`、`detail_status`、`detail_reason`，不重新导入整页岗位。
  - 前端岗位详情弹窗新增“刷新当前岗位详情”按钮，刷新成功后只替换当前岗位卡片和弹窗内容。
- 阶段 5Z：单岗位详情刷新可观察性与真实页面回归加固。
  - 单岗位详情刷新已接入 Orchestrator，任务名为 `job.detail.refresh`。
  - 刷新开始、成功、失败都会写入 `JobSearchAgent` 事件；失败时保留错误原因，供前端 Agent 状态区展示。
  - 新增详情页 HTML 脱敏回归样例，覆盖从详情 DOM 中提取标题、公司、城市、薪资、完整 JD 和 `detail_fetched` 状态。
- 阶段 6A-1：岗位详情人工补全与重新匹配后端接口。
  - 新增 `PATCH /api/jobs/{job_id}/manual-detail`，允许提交人工补全后的 JD 和备注。
  - 后端会根据岗位所属 `search_run_id` 找到原简历，更新 `description/detail_status/detail_reason` 并重新计算 `match_json`。
  - 人工补全流程已接入 Orchestrator，任务名为 `job.detail.manual_update`，并写入 `JobMatchAgent` running/success/failed 步骤。
- 阶段 6A-2：岗位详情人工补全前端接入。
  - 前端 API 客户端新增 `updateJobManualDetail()`，调用 `PATCH /api/jobs/{job_id}/manual-detail`。
  - 岗位详情弹窗新增“人工补全 / 修正 JD”文本框、补全备注和“保存并重新匹配”按钮。
  - 保存成功后会更新当前岗位卡片、详情弹窗、匹配分，并刷新 Agent/Orchestrator 事件。
- 阶段 6B：真实平台字段质量回归样例扩展。
  - 新增 BOSS 类真实页面脱敏回归样例，覆盖标题占位符污染、城市字段污染和薪资候选补全。
  - 标题中 `口` 占位符密度过高的岗位会被视为污染结果并丢弃，不再进入预览或岗位池。
  - 城市字段不可读时，会从标题、描述、详情文本和薪资候选文本中推断常见城市；薪资继续优先使用可信候选。
- 阶段 6C：实习僧字段质量回归样例扩展。
  - 新增实习僧脱敏回归样例，覆盖未知公司、标题占位符污染、城市污染、薪资候选补全和详情 JD 优先。
  - CDP 抽取脚本新增 `company_candidates`，从公司 selector、属性文本和整张岗位卡片中带回公司候选。
  - 当平台字段只给出“未知公司/公司未展示”时，后端会从候选卡片文本中推断可信公司名；已有可信公司不会被覆盖。
- 阶段 6D：补全 JD 后材料生成端到端回归。
  - `POST /api/jobs/{job_id}/tailor` 会阻止 `card_only/detail_blocked/low_quality` 岗位直接生成材料，返回 409 并提示先补全 JD。
  - 低质量 JD 被拦截时会写入 `ApplicationWriterAgent` failed 步骤和 Orchestrator 失败任务，前端 Agent 状态区可看到原因。
  - 新增端到端回归：人工补全 JD 后再生成材料，Fake LLM 会断言收到的是补全后的完整 JD，而不是列表卡片摘要。
- 阶段 6E：前端材料生成低质量 JD 阻断提示。
  - 前端 API helper 新增 `getTailorBlockedMessage()`，识别 409 低质量 JD 阻断并保留后端可读原因。
  - 点击低质量岗位的“生成材料”后，顶部错误条提示详情不完整，人审材料区显示“生成已暂停：需要先补全 JD”。
  - 人审材料区新增“查看/补全岗位要求”入口，打开当前岗位详情弹窗；刷新详情或人工补全成功后会清除该岗位阻断提示。
- 阶段 6F-hotfix：DeepSeek 接入可见化与项目限制文案清理。
  - 前端新增“模型 / API”面板，可读取和保存 `/api/model-config`，并提供 DeepSeek 预设：`deepseek-v4-pro`、`https://api.deepseek.com`、`DEEPSEEK_API_KEY`。
  - 后端默认模型配置在检测到 `DEEPSEEK_API_KEY` 环境变量时，会自动启用 OpenAI-compatible DeepSeek 路由；未检测到 key 时仍保持本地/估算安全状态。
  - 模板化 PDF 错误提示从“未找到项目经历段落/精简项目段落”改为“可编辑简历正文”，避免暗示简历只能改项目经历。
- 阶段 6G：补全 JD 后前端一键重试生成材料。
  - 新增前端判断：只有岗位详情状态为 `manual_filled` 或 `detail_fetched`、当前没有材料且没有阻断提示时，人审材料区才展示“重新生成材料”入口。
  - 用户从“生成已暂停：需要先补全 JD”进入详情弹窗并完成刷新/人工补全后，可以直接在人审材料区重新调用 `ApplicationWriterAgent` 生成简历改写和招呼语。
  - 该入口复用现有 `handleTailor()`，不会自动投递、不会自动打招呼，也不会绕过后端低质量 JD 拦截。
- 阶段 6H：材料区展示模型调用状态与 DeepSeek 路由。
  - 人审材料区新增“模型调用状态”，展示本次材料的 `review.llm.status`、provider/model、ApplicationWriterAgent 路由和 ReviewAgent 路由。
  - 外部模型成功时显示“外部模型已调用”；模型失败回退时显示“模型失败，已本地回退”和错误摘要；本地规则生成时显示未调用外部模型原因。
  - 当前 token/成本展示使用 `ApplicationWriterAgent` 累计 usage 摘要；单次材料级 token/成本仍需后端在下一阶段写入 `review.llm`。
- 阶段 6I：单次材料级模型 usage 写入 `review.llm`。
  - 材料生成成功或失败回退时，后端会把本次 `prompt_tokens`、`completion_tokens`、`total_tokens`、`cost_usd`、`duration_ms`、`usage_status`、`usage_estimated` 写入 `review.llm`。
  - 前端“模型调用状态”优先显示本次材料的精确 token/费用/耗时；旧材料缺少这些字段时仍回退显示 `ApplicationWriterAgent` 累计 usage。
  - 该阶段只补充可观察元数据，不改变模型调用、计费算法、事实审核或本地回退策略。
- 阶段 6J-1：DeepSeek / OpenAI-compatible 连接自检后端接口。
  - 新增 `POST /api/model-config/test`，读取当前模型配置并发起最小 `/chat/completions` 连接自检。
  - 成功时返回 `status=success`、provider、model、duration_ms、api_key_configured 和成功消息。
  - 失败时返回 `status=failed`、provider、model、api_key_configured 和脱敏错误；真实 API key 不进入响应。
- 阶段 6J-2：模型 / API 面板接入“测试模型连接”按钮。
  - 前端 API client 新增 `testModelConfigConnection()`，调用 `POST /api/model-config/test`。
  - 模型 / API 面板新增“测试模型连接”按钮，展示连接成功/失败、provider/model、耗时、Key 是否配置和脱敏错误。
  - DeepSeek 前端预设从 `deepseek-chat` 改为用户指定的 `v4pro`；当前只在前端预设生效，后端默认模型和外部 `.env` 自动加载留到下一阶段。
  - 已安全检查 `D:\code\tourism-opinion-agent\.env`，仅检测到 `DEEPSEEK_API_KEY` 变量；未输出、未复制、未写入真实 key。
- 阶段 6J-3：外部 `.env` 自动加载与后端默认 v4pro。
  - 后端模型配置会优先读取系统环境变量，其次读取 `AGENT_BUSINESS_ENV_FILE` 指向的 `.env`，最后兜底尝试用户提供的 `D:\code\tourism-opinion-agent\.env`。
  - `GET /api/model-config` 在检测到 `DEEPSEEK_API_KEY` 时默认返回 OpenAI-compatible、`deepseek-v4-pro`、`https://api.deepseek.com`，并标记 `api_key_configured=true`。
  - LLM 实际请求和模型连接自检也会通过同样规则读取 API key；真实 key 不写入数据库、文档或响应。

## 未完成

- “模型自动选择”已有最小策略路由，但尚未实现多模型池、按成本/失败率自动切换、按 Agent 配置不同模型。
- 多 Agent 当前是模块拆分，不是可并行调度运行时。
- `JobSearchAgent` 尚未拆成独立任务级 Agent；Orchestrator 已有最小骨架、任务摘要持久化和失败任务人工重试提示，但尚未实现自动重试、并行调度或任务恢复执行。
- `EventStreamService` 目前是进程内最小事件缓存，尚未持久化，也不是 SSE/WebSocket 实时推送。
- 浏览器自动化已支持 CDP 搜索控制和只读提取，但不做自动投递、自动打招呼、验证码处理或账号登录。
- 已有脱敏真实平台回归样例，但还没有持续维护的 BOSS/实习僧页面快照库；DOM、状态关键词和详情页结构仍需在用户登录后的真实页面上继续校验。
- 没有完整数据库迁移系统、外键约束、并发保护、审计日志和密钥管理。
- 模板化 PDF 目前只支持 DOCX 源模板；PDF 简历无法可靠保留图片和排版后只改可编辑正文。

## 风险

- BOSS/实习僧页面 DOM、搜索框、城市控件、字体混淆和文案随时可能变化，当前搜索控制和薪资增强只能提高真实数据命中率，不能保证每页都能稳定读到结果和薪资。
- 详情页读取依赖平台允许同源登录态 `fetch`；如果平台接口风控或详情页结构变化，弹窗仍会回退到列表卡片文本并提示打开原岗位。
- 用户如果未登录、页面停在验证码/风控页、结果为空页，系统只能返回诊断，不能绕过平台限制。
- LLM 输出仍需要 `ReviewAgent` 审核，模型可能返回不合规 JSON 或尝试虚构经历，因此保留本地回退。
- 模板化 PDF 导出依赖本机 Microsoft Word 或 LibreOffice；两者都不可用时接口会返回缺少转换器。
- 一页 PDF 限制只会压缩可编辑正文，不会修改身份信息、教育经历、图片或整体模板；如果模板本身过长，仍需要人工精简。
- Git 远程仓库已配置为 `https://github.com/PrinceSquirrel/find-work.git`，`main` 已成功推送并跟踪 `origin/main`；后续 push 仍依赖本机 GitHub 凭据可用。
- 文档和代码中不得写入真实 API Key、Cookie、密码或平台隐私数据。

## 下一步任务

建议进入 6K：多模型池与按 Agent 选择模型的最小配置。

目标：在当前单模型配置基础上增加最小模型池配置，让 `ApplicationWriterAgent`、`JobMatchAgent`、`ReviewAgent` 可以选择不同模型/本地规则，并保留默认低 token 策略。

预计文件控制在 3-5 个：

- `backend/app/services/model_router_service.py`
- `backend/app/storage.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

浏览器中应该看到：暂不改变前端；后端先具备按 Agent 路由不同模型的能力，后续再接前端配置页面。

## 后续候选任务

- 6K：多模型池与按 Agent 选择模型的最小配置。
- 6L：模型调用失败率和成本维度的路由策略。
- 6M：真实平台页面快照库与选择器回归样例继续扩展。

## 6I 原计划记录

- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `docs/CODEX_STATUS.md`

浏览器中应该看到：材料生成成功后，人审材料区显示本次生成的精确 token、费用、耗时和模型状态；失败回退时也能看到失败 usage 状态与错误摘要。

## 最近修改文件

当前主要修改文件包括：

- `backend/app/storage.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/types.ts`
- `docs/CODEX_STATUS.md`

- `backend/app/main.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `docs/CODEX_STATUS.md`

- `backend/app/services/model_router_service.py`
- `backend/app/services/event_stream_service.py`
- `backend/app/services/orchestrator_service.py`
- `backend/app/services/browser_job_extractor_service.py`
- `backend/app/services/pdf_service.py`
- `backend/app/services/job_application_service.py`
- `backend/app/services/llm_client_service.py`
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/app/agents/application_writer.py`
- `backend/app/agents/resume_parser.py`
- `backend/app/agents/resume_tailor.py`
- `backend/app/agents/review.py`
- `backend/app/schemas.py`
- `backend/requirements.txt`
- `backend/tests/test_agents.py`
- `backend/tests/test_api_flow.py`
- `backend/tests/test_template_resume_pdf_service.py`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/types.ts`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `docs/CODEX_STATUS.md`

## 最近验证

- 6J-3 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_default_model_config_loads_deepseek_key_from_external_env_file backend\tests\test_api_flow.py::test_model_connection_uses_deepseek_key_from_external_env_file -q`：按预期失败，暴露后端尚未从外部 `.env` 识别 key，默认模型仍为 `deepseek-chat`。
- 6J-3 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_default_model_config_loads_deepseek_key_from_external_env_file backend\tests\test_api_flow.py::test_model_connection_uses_deepseek_key_from_external_env_file -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "model_config or model_connection or tailor_uses_enabled or routes_application_writer or falls_back_locally" -q`：通过，9 个模型配置/连接/材料生成相关测试。
  - `python -m pytest -q`：通过，59 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，20 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6J-2 红灯验证：
  - `npm test -- --run src/lib/api.test.ts`：按预期失败，暴露缺少 `api.testModelConfigConnection()`。
- 6J-2 绿灯验证：
  - `npm test -- --run src/lib/api.test.ts`：通过，8 个前端 API 测试。
  - `npm test -- --run`：通过，20 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，57 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6J-1 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_model_config_connection_test_returns_sanitized_success backend\tests\test_api_flow.py::test_model_config_connection_test_returns_sanitized_failure -q`：按预期失败，暴露 `main` 尚未暴露 `OpenAICompatibleClient` 和 `/api/model-config/test` 路由。
- 6J-1 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_model_config_connection_test_returns_sanitized_success backend\tests\test_api_flow.py::test_model_config_connection_test_returns_sanitized_failure -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "model_config or tailor_uses_enabled or routes_application_writer or falls_back_locally" -q`：通过，7 个模型配置/材料生成相关测试。
  - `npm test -- --run`：通过，19 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，57 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6I 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_tailor_uses_enabled_openai_compatible_model_and_records_usage -q`：按预期失败，暴露 `review.llm` 缺少 `prompt_tokens` 等本次 usage 字段。
  - `npm test -- --run src/lib/dashboard.test.ts`：按预期失败，暴露前端仍优先显示 `ApplicationWriterAgent` 累计 usage。
- 6I 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_tailor_uses_enabled_openai_compatible_model_and_records_usage -q`：通过。
  - `npm test -- --run src/lib/dashboard.test.ts`：通过，12 个前端 dashboard 测试。
  - `npm test -- --run`：通过，19 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，55 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6H 红灯验证：
  - `npm test -- --run src/lib/dashboard.test.ts`：按预期失败，暴露缺少 `buildTailorModelSummary()`。
- 6H 绿灯验证：
  - `npm test -- --run src/lib/dashboard.test.ts`：通过，12 个前端 dashboard 测试。
  - `npm test -- --run`：通过，19 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，55 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6G 红灯验证：
  - `npm test -- --run src/lib/dashboard.test.ts`：按预期失败，暴露缺少 `shouldShowTailorRetryAction()`。
- 6G 绿灯验证：
  - `npm test -- --run src/lib/dashboard.test.ts`：通过，11 个前端 dashboard 测试。
  - `npm test -- --run`：通过，18 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，55 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6F-hotfix 红灯验证：
  - `npm test -- --run src/lib/api.test.ts`：按预期失败，暴露前端 API 客户端缺少 `getModelConfig()` / `updateModelConfig()`。
  - `python -m pytest backend\tests\test_template_resume_pdf_service.py::test_docx_template_missing_editable_body_error_is_not_project_only -q`：按预期失败，暴露模板化 PDF 错误仍写“项目经历段落”。
  - `python -m pytest backend\tests\test_api_flow.py::test_default_model_config_uses_deepseek_when_key_env_is_available -q`：按预期失败，暴露默认模型配置仍为 `local`。
- 6F-hotfix 绿灯验证：
  - `npm test -- --run src/lib/api.test.ts`：通过，7 个前端 API 测试。
  - `python -m pytest backend\tests\test_template_resume_pdf_service.py::test_docx_template_missing_editable_body_error_is_not_project_only -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py::test_default_model_config_uses_deepseek_when_key_env_is_available -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "model_config or tailor_uses_enabled or routes_application_writer or falls_back_locally" -q`：通过，5 个模型配置/材料生成相关测试。
  - `python -m pytest backend\tests\test_template_resume_pdf_service.py -q`：通过，3 个模板化 PDF 测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，17 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，55 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- 6E 红灯验证：
  - `npm test -- --run src/lib/api.test.ts`：按预期失败，暴露 `getTailorBlockedMessage is not a function`。
- 6E 绿灯验证：
  - `npm test -- --run src/lib/api.test.ts`：通过，6 个前端 API 测试。
  - `npm test -- --run`：通过，16 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，53 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6D 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_tailor_blocks_low_quality_jd_then_uses_manual_detail_for_llm -q`：按预期失败，暴露 `card_only` 岗位仍能直接生成材料。
- 6D 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_tailor_blocks_low_quality_jd_then_uses_manual_detail_for_llm -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "tailor or manual_job_detail or agent_events" -q`：通过，8 个材料生成/人工补全/Agent 事件相关测试。
  - `python -m pytest -q`：通过，53 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6C 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_shixiseng_extraction_recovers_company_salary_and_detail_from_candidates -q`：按预期失败，暴露 CDP 抽取脚本缺少 `company_candidates`。
- 6C 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_shixiseng_extraction_recovers_company_salary_and_detail_from_candidates -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or platform_job_search or detail_refresh_html" -q`：通过，9 个 CDP 抽取/搜索/详情 HTML 相关测试。
  - `python -m pytest -q`：通过，52 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6B 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_drops_placeholder_titles_and_infers_city_salary -q`：按预期失败，暴露标题占位符污染未被丢弃，且城市字段污染时没有从岗位文本推断城市。
- 6B 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_drops_placeholder_titles_and_infers_city_salary -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or platform_job_search or detail_refresh_html" -q`：通过，9 个 CDP 抽取/搜索/详情 HTML 相关测试。
  - `python -m pytest -q`：通过，51 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 6A-2 红灯验证：
  - `npm test -- --run src/lib/api.test.ts`：按预期失败，暴露 `api.updateJobManualDetail is not a function`。
- 6A-2 绿灯验证：
  - `npm test -- --run src/lib/api.test.ts`：通过，5 个前端 API 测试。
  - `npm test -- --run`：通过，15 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，50 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- 6A-1 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_manual_job_detail_update_recalculates_match_and_records_agent_event -q`：按预期失败，暴露 `PATCH /api/jobs/{job_id}/manual-detail` 路由不存在。
- 6A-1 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_manual_job_detail_update_recalculates_match_and_records_agent_event -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp backend\tests\test_api_flow.py::test_single_job_detail_refresh_failure_records_agent_event backend\tests\test_api_flow.py::test_manual_job_detail_update_recalculates_match_and_records_agent_event -q`：通过。
  - `python -m pytest -q`：通过，50 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5Z 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp backend\tests\test_api_flow.py::test_single_job_detail_refresh_failure_records_agent_event backend\tests\test_api_flow.py::test_detail_refresh_html_regression_extracts_requirements_and_salary -q`：按预期失败，暴露详情刷新未写入 Orchestrator/Agent 事件，且缺少详情 HTML 归一化方法。
- 5Z 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp backend\tests\test_api_flow.py::test_single_job_detail_refresh_failure_records_agent_event backend\tests\test_api_flow.py::test_detail_refresh_html_regression_extracts_requirements_and_salary -q`：通过。
  - `python -m pytest -q`：通过，49 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，14 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
- 5Y 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp -q`：按预期失败，暴露 `POST /api/jobs/{job_id}/refresh-detail` 路由不存在。
  - `npm test -- --run src/lib/api.test.ts`：按预期失败，暴露前端 API 客户端缺少 `refreshJobDetail()`。
- 5Y 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_single_job_detail_can_be_refreshed_from_browser_cdp -q`：通过。
  - `npm test -- --run src/lib/api.test.ts`：通过，4 个前端 API 测试。
  - `python -m pytest -q`：通过，47 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，14 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
- 5X 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_detail_page_requirements_and_salary backend\tests\test_api_flow.py::test_browser_cdp_search_mode_saves_extracted_jobs_without_demo_fallback -q`：按预期失败，暴露提取候选和导入岗位池后都缺少 `detail_status/detail_reason`。
- 5X 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_detail_page_requirements_and_salary backend\tests\test_api_flow.py::test_browser_cdp_search_mode_saves_extracted_jobs_without_demo_fallback -q`：通过。
  - `npm test -- --run`：通过，13 个前端测试。
  - `python -m pytest -q`：通过，46 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5W 红灯验证：
  - `npm test -- --run`：按预期失败，暴露缺少 `getJobDetailQuality()`，岗位详情弹窗无法区分空 JD、列表卡片摘要和完整 JD。
- 5W 绿灯验证：
  - `npm test -- --run`：通过，12 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `python -m pytest -q`：通过，45 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5W-hotfix 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_boss_browser_script_targets_jobs_page_and_waits_for_rendered_cards -q`：按预期失败，暴露 BOSS 搜索 URL 仍是 `/web/geek/job` 且抽取脚本没有等待岗位卡片渲染。
- 5W-hotfix 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_boss_browser_script_targets_jobs_page_and_waits_for_rendered_cards -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or platform_job_search or boss_browser_script" -q`：通过，8 个 CDP 抽取/搜索相关测试。
- 5V 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_detail_page_requirements_and_salary -q`：按预期失败，暴露 CDP 详情页脚本缺少 `detail_salary_candidates`，后端也未优先采用 `detail_description`。
- 5V 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_detail_page_requirements_and_salary -q`：通过。
  - `python -m pytest backend\tests\test_api_flow.py -k "platform_job_extraction or platform_job_search" -q`：通过，7 个 CDP 抽取/搜索相关测试。
  - `python -m pytest -q`：通过，45 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，11 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5U 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_failed_orchestrator_task_detail_includes_manual_retry_boundary -q`：按预期失败，暴露任务详情缺少 `retry_suggestion`。
- 5U 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_failed_orchestrator_task_detail_includes_manual_retry_boundary -q`：通过。
  - `python -m pytest -q`：通过，44 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，11 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5E-5J 绿灯验证：
  - `python -m pytest -q`：通过，34 个后端测试；存在 reportlab 自身的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，10 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5K-5N 绿灯验证：
  - `python -m pytest -q`：通过，39 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，10 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
- 5O-5T 绿灯验证：
  - `python -m pytest -q`：通过，43 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，11 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5T-hotfix 绿灯验证：
  - `python -m pytest -q`：通过，43 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
  - `npm test -- --run`：通过，11 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
  - `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 5D 红灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_orchestrator_task_detail_endpoint_returns_steps -q`：按预期失败，暴露任务详情路由不存在。
- 5D 绿灯验证：
  - `python -m pytest backend\tests\test_api_flow.py::test_orchestrator_task_detail_endpoint_returns_steps -q`：通过。
  - `npm test -- --run`：通过，8 个前端测试。
  - `npm run lint`：通过。
  - `npm run build`：通过。
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

## 6J-3：DeepSeek v4pro 外部 env 接入收口

### 当前真实状态
- 后端默认会先读进程环境变量，再读 `AGENT_BUSINESS_ENV_FILE` 指向的 `.env`，未配置时兜底读取 `D:\code\tourism-opinion-agent\.env`。
- 当前外部 `.env` 已检测到 `DEEPSEEK_API_KEY` 变量名，未输出、未写入、未保存真实 key。
- 默认模型已改为 DeepSeek v4pro 的官方 API 模型名 `deepseek-v4-pro`；兼容用户输入别名 `v4pro`，保存时会规范化。
- 前端“模型 / API”面板默认预设为 `https://api.deepseek.com` + `deepseek-v4-pro` + `DEEPSEEK_API_KEY`，并提供“测试模型连接”按钮。

### 已完成
- `POST /api/model-config/test` 可以真实调用当前模型配置并返回脱敏成功/失败结果。
- `ApplicationWriterAgent` 已可在模型启用且 key 存在时调用 OpenAI-compatible API 生成简历改写和招呼语；失败时仍保留本地回退和错误可观察性。
- 测试默认隔离真实外部 `.env`，避免全量单元测试误连真实 DeepSeek。

### 未完成
- 当前真实网络冒烟显示 key 和模型配置已识别，但 `deepseek-v4-pro` 调用在 20 秒受控超时内返回 `TimeoutError`，需要在本机网络/API 可用后再次点击前端“测试模型连接”确认。
- 尚未做多模型池/不同 Agent 自动选择模型的完整 UI，仅完成单配置和最小路由。

### 风险
- DeepSeek v4pro 响应可能较慢，默认 timeout 暂设为 90000ms；网络不稳定时前端测试按钮会等待较久。
- 外部 `.env` 当前只有 `DEEPSEEK_API_KEY`，base URL 和模型名使用项目默认值。

### 下一步任务
- 6K：模型池与 Agent 路由 UI，支持为 ApplicationWriterAgent / JobMatchAgent 分别选择模型，并在前端显示本次材料是模型生成还是本地回退。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.test.ts`
- `docs/CODEX_STATUS.md`

### 验证结果
- `python -m pytest backend\tests\test_api_flow.py::test_default_model_config_loads_deepseek_key_from_external_env_file backend\tests\test_api_flow.py::test_model_connection_uses_deepseek_key_from_external_env_file backend\tests\test_api_flow.py::test_default_model_config_uses_deepseek_when_key_env_is_available -q`：通过。
- `python -m pytest -q`：通过，59 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run src/lib/api.test.ts`：通过，8 个前端 API 测试。
- `npm test -- --run`：通过，20 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `git diff --check`：无空白错误，仅 Windows 行尾转换提示。

## 6L：LLM Prompt 集中管理

### 当前真实状态
- DeepSeek/OpenAI-compatible 调用链路已经存在，`ApplicationWriterAgent` 会通过 Agent 专属模型路由调用配置的模型；未配置或调用失败时仍会本地回退并记录 usage。
- `ApplicationWriterAgent` 的提示词已集中到 `LLMPromptService`，不再散落在 LLM client 请求代码中。
- 当前简历改写协议不是“只改项目经历”：Prompt 明确锁定身份信息和教育经历，允许基于原简历事实改写技能、项目、实习、经历描述、自我评价、摘要等简历正文。

### 已完成
- 新增 `LLMPromptService`，集中管理材料生成和岗位匹配的 system/user prompt。
- `OpenAICompatibleClient` 支持注入 prompt 服务，方便后续为 DeepSeek 单独调优提示词和测试。
- 保留 `_prompt()` / `_job_match_prompt()` 兼容薄包装，避免已有调用点和测试立刻破坏。
- 新增测试覆盖 ApplicationWriter prompt 的锁定范围、JobMatch prompt 的评分边界，以及 client 是否真正使用注入 prompt。

### 未完成
- 尚未做真实 DeepSeek 长文本材料生成质量调优；下一步需要结合用户真实简历和岗位 JD 做受控冒烟。
- 前端模型配置仍要求用户把 API Key 放在后端环境变量中，不会在浏览器里保存真实 key。

### 风险
- Prompt 已允许改写非身份/教育正文，但 ReviewAgent 仍会拦截新增学校、公司、项目事实、证书或技能；如果原简历文本解析缺失，模型可用事实会偏少。
- 如果 Agent 路由仍处于 `estimation_only` 或没有配置 `DEEPSEEK_API_KEY`，前端会看到本地回退材料，看起来不像真实 AI 输出。

### 下一步任务
- 6M：增加“DeepSeek API 已配置/未配置”的材料生成前提示，并在材料区更醒目标出模型生成或本地回退。
- 6N：继续修复真实岗位详情、薪资读取和城市搜索命中问题。

### 最近修改文件
- `backend/app/services/llm_prompt_service.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_llm_prompt_service.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_llm_prompt_service.py -q` 按预期失败，暴露 `app.services.llm_prompt_service` 尚不存在。
- 绿灯：`python -m pytest backend\tests\test_llm_prompt_service.py backend\tests\test_agents.py::test_llm_prompt_locks_identity_and_education_while_rewriting_resume_body -q` 通过。
- `python -m pytest -q`：通过，后端全量测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run`：通过，22 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。

## 6M：材料区明确 DeepSeek/API 调用状态

### 当前真实状态
- 人审材料区会更明确区分“DeepSeek/API 已调用”“未接入模型，当前本地规则生成”和“模型调用失败，当前本地回退”。
- 如果材料不是外部模型输出，界面会提示这不是 DeepSeek/AI 模型输出，并引导用户到“模型 / API”面板启用 Agent 路由、在后端环境变量中配置 API Key。
- 如果外部模型调用失败，界面会提示检查 API Key、base_url、模型名或网络后重新生成。

### 已完成
- `buildTailorModelSummary()` 增加 `setupHint`，用于展示模型配置/失败处理提示。
- 成功状态文案从泛化的“外部模型已调用”改成更直观的“DeepSeek/API 已调用”。
- 前端人审材料区展示 `setupHint`，避免本地规则材料被误认为真实 AI 生成。
- 新增前端测试覆盖成功、本地未接入、模型失败三种文案。

### 未完成
- 尚未在点击“生成材料”之前阻止未配置模型；当前仍允许生成本地兜底材料。
- 尚未做真实 DeepSeek 长文本生成质量评估。

### 风险
- `DeepSeek/API 已调用` 表示通过 OpenAI-compatible 路由成功调用外部模型；如果用户把路由改成非 DeepSeek 兼容模型，文案仍按当前 DeepSeek 优先产品目标展示。

### 下一步任务
- 6N：继续修复真实平台城市命中、岗位详情/JD 空白和薪资读取失败问题。

### 最近修改文件
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`npm test -- --run src/lib/dashboard.test.ts` 按预期失败，暴露材料摘要仍显示“外部模型已调用”且没有配置提示。
- 绿灯：同一条前端定向测试通过，13 个 dashboard 测试通过。
- `npm test -- --run`：通过，22 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：通过，后端全量测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。

## 6N-1：岗位筛选表不残留历史抓取数据

### 当前真实状态
- 前端启动或刷新工作台时，不再把 `/api/jobs` 返回的历史全量岗位直接显示到岗位筛选表。
- 没有当前搜索任务时，岗位筛选表保持为空，避免停留在之前抓到过的数据。
- 创建新搜索任务时，会立即清空旧岗位、旧选中岗位、旧详情弹窗和旧材料状态；搜索成功后只展示本次 `search_run_id` 对应岗位。

### 已完成
- 新增 `filterJobsForActiveSearchRun()`，明确只有当前 run 的岗位可以进入岗位池。
- `refreshWorkspace()` 使用该过滤逻辑，启动时不再展示历史全量岗位。
- `createSearchRunFromCurrentForm()` 在搜索开始前清空旧岗位和 job-scoped 状态，搜索成功后继续只读取本次 run。
- 新增前端测试覆盖“没有当前 run 时岗位池为空；有当前 run 时只保留该 run 岗位”。

### 未完成
- 后端 `/api/jobs` 不带 `search_run_id` 仍保留历史全量查询能力；当前先由前端隔离展示，后续可增加“latest/current run”专用接口。
- 真实 BOSS/实习僧站内投递尚未实现；当前仍只是前端/后端记录投递。
- 简历跨刷新持久化恢复和 CDP 浏览器会话复用还未在本阶段处理。

### 风险
- 如果用户希望刷新页面后恢复“刚刚那一次搜索任务”的岗位，还需要持久化 `lastRun.id` 或新增后端 current workspace 状态。

### 下一步任务
- 6N-2：持久化最近上传简历和最近搜索任务，让刷新页面后能恢复用户自己的当前工作状态，而不是历史全量数据。
- 6O：设计并实现真实平台投递的安全边界：先打开目标岗位并进入平台原生投递/沟通界面，用户确认后再记录真实投递结果。
- 6P：CDP 浏览器会话复用，已启动且可连接时不重复启动新浏览器。

### 最近修改文件
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`npm test -- --run src/lib/dashboard.test.ts` 按预期失败，暴露 `filterJobsForActiveSearchRun is not a function`。
- 绿灯：同一条前端定向测试通过，14 个 dashboard 测试通过。
- `npm test -- --run`：通过，23 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：通过，后端全量测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。

## 6K-5：前端展示模型生成/规则兜底和实际路由模型

### 当前真实状态
- 人审材料区已经能展示 `ApplicationWriterAgent` 的模型调用状态，包括外部模型成功、本地规则生成、模型失败后本地回退、实际 provider/model、路由模式、token、成本和错误摘要。
- 岗位筛选表上方新增 `JobMatchAgent` 匹配来源状态，能显示匹配分来自模型评分、模型失败后规则兜底，或本地规则生成。
- `JobMatchAgent` 状态会解析后端事件输出中的 `route` 和 `usage_status`，显示实际模型名、token 和成本。

### 已完成
- 新增 `buildJobMatchModelSummary()`，从 `/api/agent-events` 的 `JobMatchAgent` 最新事件生成前端展示摘要。
- 岗位筛选表新增一条紧凑状态栏：`JobMatchAgent：匹配分由模型评分 / 模型评分失败，已规则兜底 / 匹配分由本地规则生成`。
- 新增前端测试覆盖 `JobMatchAgent` 模型路由摘要解析。

### 未完成
- 单个岗位行还没有逐条标记“该岗位分数来自模型覆盖还是规则保留”；当前显示的是最近一次匹配任务的整体来源。

### 风险
- 该显示依赖后端事件的 `output_summary` 包含 `route=...; usage_status=...`；旧历史任务或旧数据没有这些字段时，会显示为本地规则/等待评分。

### 下一步任务
- 6L：把 LLM prompt 从 client 代码中拆出到集中管理文件，符合 Agent 项目规则，并便于后续调优 DeepSeek 提示词。

### 最近修改文件
- `frontend/src/lib/dashboard.ts`
- `frontend/src/lib/dashboard.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`npm test -- --run src/lib/dashboard.test.ts` 按预期失败，暴露 `buildJobMatchModelSummary is not a function`。
- 绿灯：同一条前端定向测试通过，新增摘要能显示 `deepseek-v4-flash`、`150 tokens / $0.0000` 和 `匹配分由模型评分`。
- `npm test -- --run`：通过，22 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：通过，后端全量测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `git diff --check`：无空白错误，仅 Windows 行尾转换提示。

## 6K-4：JobMatchAgent 可选便宜模型批量评分

### 当前真实状态
- `JobMatchAgent` 已支持读取专属模型路由；当前如果路由启用、非估算模式且 API key 环境变量可用，会用 OpenAI-compatible 便宜模型对一批岗位做匹配评分。
- 搜索任务仍会先执行本地规则评分作为基础结果；模型评分成功时，用模型返回的 `score/hit_reasons/gap_reasons/recommendation` 覆盖对应岗位的匹配结果。
- 模型评分失败时，搜索任务不会失败，会保留本地规则匹配结果，并写入一条 `JobMatchAgent` failed usage 记录。
- 未配置 `JobMatchAgent` 路由时，行为保持原来的本地规则评分和本地 token 估算。

### 已完成
- `ModelRouterService` 支持 `JobMatchAgent` 使用启用的 Agent 专属模型路由。
- `OpenAICompatibleClient.score_job_matches()` 新增批量岗位评分调用，要求模型只返回结构化 JSON，不生成简历或招呼语。
- `JobApplicationService` 的 demo 搜索和 `browser_cdp` 入库路径都复用 `_score_jobs()`，避免每个岗位单独调用模型。
- `JobMatchAgent` 的真实模型 usage 会按路由价格记录 token、成本、耗时和模型名。
- 新增回归测试覆盖 `JobMatchAgent -> deepseek-v4-flash` 路由实际参与搜索任务评分和 usage 入库。

### 未完成
- 前端岗位列表暂未显式标注“该匹配分来自模型还是规则”；当前只能通过 Agent 状态区和成本看板观察 `JobMatchAgent` usage。
- 暂未给 `JobMatchAgent` 增加模型失败时的前端专门提示，只保证后端 usage/status 可观察且岗位分数有规则兜底。

### 风险
- 第一版模型评分 prompt 截断单个 JD 到约 1600 字，极长 JD 可能只能基于摘要评分。
- 模型 JSON 如果缺少某个岗位 index，会保留该岗位规则分数，不会阻断整批搜索任务。

### 下一步任务
- 6K-5：前端在岗位匹配/材料区明确展示“模型生成 / 本地回退”和实际使用的 Agent 路由模型。
- 后续可继续拆出 Prompt 文件，避免 LLM prompt 长期散落在 client 代码中。

### 最近修改文件
- `backend/app/services/model_router_service.py`
- `backend/app/services/llm_client_service.py`
- `backend/app/services/job_application_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_search_run_uses_job_match_agent_model_route_for_batch_scoring -q` 按预期失败，暴露搜索任务未使用 `JobMatchAgent` 模型路由。
- 绿灯：同一条定向测试通过，岗位匹配分来自 `deepseek-v4-flash` Fake LLM，`llm_usage` 入库模型为 `deepseek-v4-flash`，token 为 `100/50`，成本为 `0.00004`。
- `python -m pytest backend\tests\test_api_flow.py::test_search_run_uses_job_match_agent_model_route_for_batch_scoring backend\tests\test_api_flow.py::test_tailor_uses_application_writer_agent_model_route_over_global_config backend\tests\test_api_flow.py::test_agent_model_routes_can_be_saved_per_agent -q`：通过。
- `python -m pytest -q`：通过，后端全量测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run`：通过，21 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `git diff --check`：无空白错误，仅 Windows 行尾转换提示。
- 真实外部 `.env` 脱敏冒烟：配置识别成功，`DEEPSEEK_API_KEY` 已配置，模型为 `deepseek-v4-pro`；20 秒受控连接测试返回 `LLM request failed: TimeoutError`。

## 6J-4：DeepSeek v4pro 真实连接修复

### 当前真实状态
- 已对比 `D:\code\tourism-opinion-agent\llm_client.py`：该项目使用 `base_url="https://api.deepseek.com"` 和 `DEEPSEEK_API_KEY`。
- `/models` 脱敏诊断确认当前 key 可访问 `deepseek-v4-pro` 和 `deepseek-v4-flash`。
- 直接 `curl` 调用 `https://api.deepseek.com/chat/completions` + `deepseek-v4-pro` 可在约 1 秒内返回 200。
- 当前项目后端 `/api/model-config/test` 已用真实外部 `.env` 验证成功：`provider=openai-compatible`，`model=deepseek-v4-pro`，`base_url=https://api.deepseek.com`，`api_key_configured=true`，返回 `model connection ok`。

### 已完成
- 后端默认 DeepSeek base URL 改为 `https://api.deepseek.com`，与用户给出的 tourism 项目保持一致。
- `OpenAICompatibleClient` 的 chat 请求增加 `Accept: application/json` 和稳定 `User-Agent: agent-business/0.1`，修复 Python `urllib` 对该网关偶发超时的问题。
- 前端 DeepSeek v4pro 预设同步为 `https://api.deepseek.com`，避免用户点击预设后写回旧 `/v1` 地址。

### 未完成
- 尚未完成多模型池 UI；当前仍是单模型配置 + Agent 最小路由。

### 风险
- `deepseek-v4-pro` 有 reasoning 输出，极短 `max_tokens` 可能只返回 `reasoning_content` 而正文为空；正式材料生成需要保留较大的输出 token。
- 如果用户已经在本地 SQLite 保存过旧 `/v1` 配置，前端点击 DeepSeek v4pro 预设并保存即可覆盖。

### 下一步任务
- 6K：模型池与 Agent 路由 UI，支持为 ApplicationWriterAgent / JobMatchAgent 分别选择模型，并在前端显示本次材料是模型生成还是本地回退。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/services/llm_client_service.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.test.ts`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_default_model_config_uses_deepseek_when_key_env_is_available backend\tests\test_api_flow.py::test_default_model_config_loads_deepseek_key_from_external_env_file backend\tests\test_api_flow.py::test_openai_compatible_client_sends_stable_user_agent -q` 按预期失败，暴露默认 base URL 仍为 `/v1` 且缺少稳定 User-Agent。
- 绿灯：同一组后端定向测试通过。
- 真实外部 `.env` 脱敏冒烟：`POST /api/model-config/test` 成功，`duration_ms=1874`，未输出真实 key。
- 真实材料生成脱敏冒烟：临时简历 + demo 岗位调用 `POST /api/jobs/{id}/tailor` 成功，`ApplicationWriterAgent` 使用 `deepseek-v4-pro`，`usage_status=success`，`total_tokens=1522`，返回 `resume_rewrite` 和招呼语，未输出真实 key。

## 6K-1：Agent 模型路由后端配置

### 当前真实状态
- 已新增后端模型路由配置接口，允许为不同 Agent 保存不同模型配置。
- 当前支持的 Agent 路由范围为 `ApplicationWriterAgent` 和 `JobMatchAgent`。
- `ApplicationWriterAgent` 默认沿用全局 DeepSeek 配置；`JobMatchAgent` 默认保持本地规则/估算，后续可在 UI 中改成便宜模型。

### 已完成
- 新增 `GET /api/model-routes`，返回每个可配置 Agent 的当前模型路由。
- 新增 `PUT /api/model-routes/{agent_name}`，保存单个 Agent 的 OpenAI-compatible 模型配置。
- SQLite 新增 `agent_model_routes` 表，按 `agent_name` 持久化 provider、model、base_url、API key 环境变量、启用状态、超时和价格参数。
- 保存模型时继续兼容 `v4pro -> deepseek-v4-pro`、`v4flash -> deepseek-v4-flash`，并且只返回 `api_key_configured`，不泄露真实 key。

### 未完成
- 前端尚未展示“按 Agent 选择模型”的 UI。
- `JobMatchAgent` 尚未真正按路由调用便宜模型；当前只是先把后端配置能力落库。

### 风险
- 已有全局 `/api/model-config` 仍然存在；6K-2 需要在前端解释“全局默认配置”和“Agent 路由配置”的关系，避免用户误以为只改全局配置就等于改了所有 Agent。

### 下一步任务
- 6K-2：前端模型路由面板，显示 `ApplicationWriterAgent` / `JobMatchAgent` 当前模型、启用状态和是否已配置 key，并允许保存。
- 6K-3：让 `ModelRouterService` 优先读取 Agent 专属路由，`JobMatchAgent` 可选择便宜模型或本地规则。

### 最近修改文件
- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_agent_model_routes_can_be_saved_per_agent backend\tests\test_api_flow.py::test_agent_model_route_rejects_unknown_agent -q` 按预期失败，暴露 `/api/model-routes` 不存在。
- 绿灯：同一组后端定向测试通过。
- `python -m pytest -q`：通过，62 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run`：通过，20 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。

## 6K-2：前端 Agent 模型路由面板

### 当前真实状态
- 前端已接入 `GET /api/model-routes` 和 `PUT /api/model-routes/{agent_name}`。
- “模型 / API”面板底部新增“Agent 模型路由”区域，可分别查看和保存 `ApplicationWriterAgent` 与 `JobMatchAgent` 的模型配置。
- UI 提供 `ApplicationWriterAgent -> DeepSeek v4pro`、`JobMatchAgent -> DeepSeek v4flash` 预设，便于后续把写作和匹配拆成不同成本模型。

### 已完成
- 新增前端类型 `AgentModelRoute` / `AgentModelRoutesResponse`。
- 新增 API client 方法 `getModelRoutes()` 和 `updateModelRoute()`。
- 工作台启动时会读取后端模型路由，并为每个 Agent 生成可编辑草稿。
- 用户可在浏览器里修改单个 Agent 的模型、API 地址、Key 环境变量、启用状态和是否调用模型，并单独保存。

### 未完成
- `ModelRouterService` 尚未真正优先读取 Agent 专属路由；当前 UI 保存后的配置已落库，但运行时仍主要使用全局模型配置。
- `JobMatchAgent` 尚未实际调用便宜模型批量评分。

### 风险
- 这一步没有引入新的视觉组件库；使用现有表单/面板样式，后续如果模型路由增加到更多 Agent，可能需要更紧凑的表格化编辑。

### 下一步任务
- 6K-3：让 `ModelRouterService` 优先读取 Agent 专属路由，并把 `ApplicationWriterAgent` 的实际调用切到专属路由。
- 6K-4：为 `JobMatchAgent` 增加可选便宜模型批量评分，保留本地规则兜底。

### 最近修改文件
- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`npm test -- --run src/lib/api.test.ts` 按预期失败，暴露 `api.getModelRoutes is not a function`。
- 绿灯：`npm test -- --run src/lib/api.test.ts` 通过，9 个前端 API 测试。
- `npm test -- --run`：通过，21 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `python -m pytest -q`：通过，62 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。

## 6K-3：ApplicationWriterAgent 运行时使用专属模型路由

### 当前真实状态
- `ApplicationWriterAgent` 生成人审材料时已经优先读取 `agent_model_routes` 中保存的专属模型配置，不再只使用全局 `/api/model-config`。
- 当前已验证：全局模型为 `deepseek-chat`，`ApplicationWriterAgent` 路由为 `deepseek-v4-flash` 时，材料生成实际传入 LLM client 的模型是 `deepseek-v4-flash`。
- LLM usage 入库会使用 Agent 路由里的输入/输出单价计算成本，未知模型不再因为缺少内置价目表而记为 0 成本。

### 已完成
- `SQLiteStore.get_agent_model_route()` 可按 Agent 名称读取单个专属路由，未保存时返回默认路由。
- `JobApplicationService._write_application_materials()` 改为使用 `ApplicationWriterAgent` 专属路由配置。
- `MetricsService.record_llm_usage()` 支持本次调用传入价格覆盖，材料生成会把路由价格传入计费逻辑。
- 新增回归测试覆盖“专属 Agent 路由优先于全局模型配置”以及路由价格入库计费。

### 未完成
- `JobMatchAgent` 仍未接入便宜模型批量评分，当前还是规则匹配为主。
- `ReviewAgent` 仍固定本地规则审核，不消耗外部模型 token。

### 风险
- 前端可保存多个 Agent 路由，但当前只有 `ApplicationWriterAgent` 在运行时真正使用专属路由。
- 如果用户没有在路由里填写价格，usage 成本仍会按 0 记录；后续可补默认 DeepSeek v4pro/v4flash 价格提示。

### 下一步任务
- 6K-4：为 `JobMatchAgent` 增加可选便宜模型批量评分，保留规则过滤和本地兜底。
- 6K-5：前端在材料区明确展示“模型生成 / 本地回退”和实际使用的 Agent 路由模型。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/services/model_router_service.py`
- `backend/app/services/job_application_service.py`
- `backend/app/services/metrics_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_tailor_uses_application_writer_agent_model_route_over_global_config -q` 按预期失败，先暴露运行时仍用全局 `deepseek-chat`；修正模型路由后又暴露 `deepseek-v4-flash` 成本仍为 0。
- 绿灯：同一条定向测试通过，`llm_usage` 入库模型为 `deepseek-v4-flash`，token 为 `80/40`，成本为 `0.00008`。
- `python -m pytest backend\tests\test_api_flow.py::test_tailor_uses_application_writer_agent_model_route_over_global_config backend\tests\test_api_flow.py::test_tailor_uses_enabled_openai_compatible_model_and_records_usage -q`：通过。
- `python -m pytest -q`：通过，63 个后端测试；测试辅助 PDF 仍触发 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run`：通过，21 个前端测试。
- `npm run lint`：通过。
- `npm run build`：通过。
- `git diff --check`：无空白错误，仅 Windows 行尾转换提示。

## 6N-6：收紧旧本地投递接口

### 当前真实状态
- 旧的 `POST /api/jobs/{job_id}/apply-record` 已不再允许普通 HTTP 调用创建本地投递记录。
- 直接调用旧接口会返回 `409`，提示必须使用 `POST /api/jobs/{job_id}/platform-apply`，由平台确认后再写入投递表。
- 后端测试中需要历史投递记录的场景改为内部 fixture 方式创建，不再通过公开旧接口绕过平台确认。
- 端到端主流程测试已改为走 `/platform-apply`，并用 Fake CDP 确认结果覆盖“平台确认后才入库”。

### 已完成
- `main.py` 中旧 `/apply-record` 路由改为拒绝本地-only 记录。
- `_create_demo_application()` 测试夹具改为内部 service 创建，避免公开 API 绕过平台确认。
- `test_full_resume_to_application_flow` 改为调用 `/platform-apply`。
- 新增回归测试覆盖：普通旧接口调用返回 `409`，且 applications 列表保持为空。

### 未完成
- 仍需在真实 BOSS/实习僧浏览器账号里做端到端验收，确认平台弹窗、简历选择、验证码、二次确认时的返回提示足够清楚。
- 投递结果表还没有单独展示“平台确认来源 / 点击证据 / 失败原因”列。

### 风险
- `JobApplicationService.create_application()` 仍作为内部方法存在，供测试夹具和未来数据迁移使用；公开用户路径已经不再直接暴露它。
- 如果第三方直接依赖旧 `/apply-record`，现在会得到 `409`，需要改用 `/platform-apply`。

### 下一步任务
- 6N-7：真实浏览器端到端验收 BOSS/实习僧平台投递动作，针对实际弹窗补充提示。
- 6N-8：投递结果表显示平台确认来源、点击证据和未确认失败原因。

### 最近修改文件
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_legacy_apply_record_endpoint_rejects_local_only_application_records -q` 先按预期失败，旧接口返回 `201`，暴露仍能本地-only 入库。
- 绿灯：旧接口拒绝测试和完整主流程测试通过。
- 投递相关回归：`python -m pytest backend\tests\test_api_flow.py::test_platform_apply_creates_application_only_after_platform_confirmation backend\tests\test_api_flow.py::test_platform_apply_does_not_create_application_without_platform_confirmation backend\tests\test_api_flow.py::test_status_endpoint_rejects_illegal_application_transition backend\tests\test_api_flow.py::test_application_sync_returns_read_only_proposals_without_overwriting_status backend\tests\test_api_flow.py::test_application_sync_reports_missing_cdp_without_updating_status -q` 通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 在 `frontend/` 目录通过，25 tests。
- `npm run lint` 在 `frontend/` 目录通过。
- `npm run build` 在 `frontend/` 目录通过。
- `git diff --check` 通过；仅有 Windows 行尾转换提示。

## 6N-5：平台确认后才写入投递记录

### 当前真实状态
- 新增 `POST /api/jobs/{job_id}/platform-apply`，用于通过 CDP 打开真实 BOSS/实习僧岗位页并尝试点击平台原生“立即沟通 / 投递 / 申请”等入口。
- 后端只有在平台脚本返回 `confirmed=true` 时才调用 `store.create_application()` 写入投递结果表。
- 如果平台页面没有找到投递/沟通入口、需要登录/验证码/安全验证、或点击后没有出现已投递/已沟通/聊天面板等确认信号，接口返回 `409`，且不会新增 application 记录。
- 前端“记录投递/确认后记录投递”已切换为调用 `/api/jobs/{id}/platform-apply`；按钮文案改为“平台投递 / 确认后在平台投递 / 平台已确认投递”。

### 已完成
- `BrowserJobExtractorService.apply_to_job()`：复用 CDP 平台标签页，打开目标岗位 URL，执行平台投递点击脚本，并返回结构化确认结果。
- `JobApplicationService.apply_to_platform()`：根据平台确认结果决定是否创建投递记录。
- FastAPI 新增 `/api/jobs/{job_id}/platform-apply`，平台未确认时返回 `409`。
- 前端 API client 新增 `applyToPlatform()`，`handleApply()` 已从旧本地记录接口切换到平台确认接口。
- 新增后端测试覆盖“平台确认才入库”和“未确认不入库”；新增前端 API 测试覆盖新 endpoint。

### 未完成
- 旧的 `/api/jobs/{job_id}/apply-record` 仍保留，主要为了历史测试和兼容；后续应改成仅内部/测试使用，或要求明确的人工状态来源。
- 真实平台点击脚本还没有在用户当前 BOSS/实习僧账号上做人工端到端验收；如果平台弹出简历选择、验证码、登录失效或二次确认，接口会拒绝入库并提示原因。
- 暂未自动填写招呼语或发送消息；当前只做“用户确认后点击平台原生入口并确认状态”。

### 风险
- BOSS/实习僧 DOM 和按钮文案可能变化；脚本基于当前可见按钮文本和常见确认信号判断。
- 点击“立即沟通”在不同账号状态下可能打开聊天、弹出简历选择或要求安全验证；只有出现确认信号才会入库。
- 为了安全，不绕过验证码、不保存账号密码/Cookie、不自动处理平台二次确认弹窗。

### 下一步任务
- 6N-6：在真实浏览器里做一次 BOSS/实习僧端到端验收，针对实际弹窗补充“需要用户手动完成最后一步”的前端提示。
- 6N-7：收紧旧 `/apply-record` 本地接口，避免普通前端路径绕过平台确认。
- 6N-8：投递结果表增加“平台确认来源/失败原因”展示，让用户能看出每条记录是否来自真实平台确认。

### 最近修改文件
- `backend/app/services/browser_job_extractor_service.py`
- `backend/app/services/job_application_service.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_platform_apply_creates_application_only_after_platform_confirmation backend\tests\test_api_flow.py::test_platform_apply_does_not_create_application_without_platform_confirmation -q` 先按预期失败，状态为 404，暴露平台确认投递接口尚不存在。
- 绿灯：同一组后端定向测试通过。
- 红灯：`npm test -- --run src/lib/api.test.ts -t applyToPlatform` 先按预期失败，暴露 `api.applyToPlatform is not a function`。
- 绿灯：同一条前端 API 测试通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 在 `frontend/` 目录通过，25 tests。
- `npm run lint` 在 `frontend/` 目录通过。
- `npm run build` 在 `frontend/` 目录通过。
- `git diff --check` 通过；仅有 Windows 行尾转换提示。

## 6N-4：CDP 浏览器会话复用

### 当前真实状态
- `POST /api/browser/launch-cdp` 现在会先检查已有 `BROWSER_CDP_URL` 和默认 `127.0.0.1:9222` 是否可访问 `/json`。
- 如果现有 CDP 浏览器已经可连接，后端返回 `status=reused`，不会再次启动 Edge/Chrome，也不会再新开一组 BOSS/实习僧窗口。
- 前端现有启动按钮会直接展示后端返回的复用提示；用户仍需要在复用的浏览器里保持 BOSS/实习僧登录状态并刷新会话。

### 已完成
- `CdpBrowserLauncher.launch()` 增加启动前 CDP 探测。
- 已支持优先复用环境变量里的 CDP 地址，其次复用默认 9222 端口。
- 新增回归测试覆盖：已有 CDP 可连接时不会调用浏览器查找/启动逻辑。

### 未完成
- 真实投递动作尚未实现；当前仍不会自动点击 BOSS/实习僧的投递或沟通按钮。
- 投递结果表还没有做到只在平台确认投递后写入真实投递状态。
- 如果现有 CDP 浏览器没有打开招聘平台标签页，仍需要用户登录并刷新会话。

### 风险
- CDP 端口可连接不等于用户已经登录招聘平台；搜索和投递前仍要依赖平台标签页检测。
- 如果其他程序占用了 9222 且返回兼容 `/json`，启动器会把它当作可复用浏览器。

### 下一步任务
- 6N-5：真实投递安全边界最小实现：打开目标岗位、定位平台原生投递/沟通入口、用户确认后再执行点击并写入投递记录。
- 6N-6：投递结果表只保存平台确认过的真实投递状态，并保留失败/未确认原因。

### 最近修改文件
- `backend/app/services/platform_session_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_cdp_browser_launcher_reuses_existing_session_without_starting_process -q` 按预期失败，暴露启动器会先查找浏览器而不是复用现有 CDP。
- 绿灯：`python -m pytest backend\tests\test_api_flow.py::test_cdp_browser_launcher_reuses_existing_session_without_starting_process backend\tests\test_api_flow.py::test_platform_sessions_report_missing_cdp_configuration backend\tests\test_api_flow.py::test_platform_sessions_detect_open_recruitment_tabs -q` 通过。
- `python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- `npm test -- --run` 在 `frontend/` 目录通过，24 tests。
- `npm run lint` 在 `frontend/` 目录通过。
- `npm run build` 在 `frontend/` 目录通过。
- `git diff --check` 通过；仅有 Windows 行尾转换提示。

## 6N-3：最近上传简历刷新后恢复

### 当前真实状态
- 上传简历后，后端 SQLite 已经持久化 `ResumeDraft`；本阶段新增只读接口让前端启动时取回最近一份简历。
- 前端刷新页面后会调用 `GET /api/resumes/latest`，如果后端已有简历，会恢复简历卡片、简历 ID、摘要，并继续使用该简历创建搜索任务和生成材料。
- 如果还没有上传过简历，接口返回 `null`，前端保持原来的“还没有简历”空状态。

### 已完成
- 新增 `SQLiteStore.get_latest_resume()`，按 `created_at DESC, id DESC` 读取最新简历。
- 新增 `GET /api/resumes/latest`。
- 前端 API client 新增 `getLatestResume()`。
- 前端 `refreshWorkspace()` 初始化时同步读取最近简历，并在搜索框未被用户手动改过时复用简历推荐关键词和城市。
- 新增后端回归测试覆盖：重新创建 FastAPI app 后仍能从同一个 SQLite 文件恢复最新简历。
- 新增前端 API 测试覆盖：`getLatestResume()` 请求 `/api/resumes/latest`。

### 未完成
- 真实投递动作尚未实现，当前仍不自动点击 BOSS/实习僧投递按钮。
- 投递结果表还没有做到只保存真实平台回读状态。
- CDP 会话复用/避免重复启动还未在本阶段处理。

### 风险
- 当前只恢复“最近一份简历”，本地单用户足够；后续如果做多简历管理，需要增加简历列表和选择器。
- `docs/CODEX_STATUS.md` 历史内容已有编码显示异常，本阶段继续只追加状态，没有重写全文件。

### 下一步任务
- 6N-4：CDP 会话复用与前端状态同步，避免反复启动浏览器。
- 6N-5：真实投递安全边界设计与最小实现：打开岗位、定位投递按钮、用户确认后执行点击，并只在平台确认后写入投递记录。

### 最近修改文件
- `backend/app/storage.py`
- `backend/app/main.py`
- `backend/tests/test_api_flow.py`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/App.tsx`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_latest_resume_endpoint_recovers_after_app_restart -q` 先失败，状态为 404。
- 绿灯：同一条后端测试已通过。
- 红灯：`npm test -- --run src/lib/api.test.ts -t getLatestResume` 先失败，暴露 `api.getLatestResume is not a function`。
- 绿灯：同一条前端测试已通过。
- 定向后端：`python -m pytest backend\tests\test_api_flow.py::test_latest_resume_endpoint_recovers_after_app_restart backend\tests\test_api_flow.py::test_docx_resume_upload_preserves_original_template_bytes -q` 通过。
- 前端 API：`npm test -- --run src/lib/api.test.ts` 通过，10 tests。
- 前端 build：`npm run build` 通过。
- 全量后端：`python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- 全量前端：`npm test -- --run` 通过，24 tests。
- 前端 lint：`npm run lint` 通过。
- 空白检查：`git diff --check` 通过；仅有 Windows 行尾转换提示。

## 6N-2：BOSS 真实岗位抽取数量与薪资修复

### 当前真实状态
- 当前后端 BOSS CDP 抽取已能识别真实列表卡片，避免把“职位搜索 / BOSS直聘APP / 工作区域”等导航或搜索部件当成岗位。
- 当前本机 CDP 只读冒烟结果：BOSS 页面候选卡片 107 个，成功返回前 5 个真实岗位，包含 `Python`、`agent开发实习生`、`全栈研发工程师实习生` 等。
- BOSS 私有字体薪资已在后端清洗层解码，当前冒烟可显示 `150-250元/天`、`290-300元/天`、`150-200元/天`。

### 已完成
- `BrowserJobExtractorService` 增加 BOSS 私有数字解码，薪资候选和描述统一转成可读数字。
- BOSS 抽取脚本增加 `.boss-name`、`.boss-info .boss-name`、`.company-location`，减少公司/城市误抽。
- 后端归一化阶段丢弃 BOSS 搜索框、导航、APP 引导等非岗位候选。
- BOSS 详情页如果只返回加载壳、脚本或风控页面，不再标记为 `detail_fetched`，会回退到列表卡片并标记为 `card_only/low_quality`。
- 新增回归测试覆盖：BOSS 私有薪资字体、真实公司/城市选择器、非岗位候选丢弃、加载壳详情降级。

### 未完成
- 真实投递动作尚未实现，当前仍不自动点击 BOSS/实习僧投递按钮。
- 投递结果表还没有做到“只保存真实平台回读状态”，仍需要后续接真实同步和人工确认。
- 上传简历跨刷新持久化还未在本阶段处理。
- CDP 会话复用/避免重复启动还未在本阶段处理。

### 风险
- BOSS 页面 DOM 和私有字体映射可能继续变化；当前映射来自 2026-07-03 本机页面实测。
- 详情页 fetch 在平台风控或登录态不完整时仍可能只能返回列表卡片摘要，前端详情弹窗会显示 `low_quality/card_only` 状态。
- `docs/CODEX_STATUS.md` 历史内容已有编码显示异常，本阶段只追加状态，没有重写全文件。

### 下一步任务
- 6N-3：修复上传简历刷新后丢失，确保最近简历从后端恢复。
- 6N-4：设计真实投递边界，先实现“打开岗位并定位投递按钮 + 人工确认后点击”的安全流程。
- 6N-5：CDP 会话复用与前端状态同步，避免反复启动浏览器。

### 最近修改文件
- `backend/app/services/browser_job_extractor_service.py`
- `backend/tests/test_api_flow.py`
- `docs/CODEX_STATUS.md`

### 验证结果
- 红灯：`python -m pytest backend\tests\test_api_flow.py::test_boss_extraction_recovers_live_card_salary_company_and_drops_search_widgets -q` 先失败，暴露 BOSS 选择器和薪资解码缺失。
- 绿灯：同一条测试已通过。
- 相关回归：`python -m pytest backend\tests\test_api_flow.py::test_boss_extraction_recovers_live_card_salary_company_and_drops_search_widgets backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_valid_salary_candidates_over_polluted_salary backend\tests\test_api_flow.py::test_platform_job_extraction_prefers_detail_page_requirements_and_salary -q` 通过。
- 全量后端：`python -m pytest -q` 通过；仅有 reportlab 的 Python 3.14 deprecation warning。
- 空白检查：`git diff --check` 通过；仅有 Windows 行尾转换提示。
- 本机 CDP 冒烟：`BROWSER_CDP_URL=127.0.0.1:9222` 下 BOSS 抽取返回 `boss success 107 5`，前 5 条均为真实岗位且薪资可读。
