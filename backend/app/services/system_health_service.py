from __future__ import annotations

import os
import shutil

from app.schemas import SystemHealthCheck, SystemHealthResponse
from app.services.platform_session_service import PlatformSessionService
from app.storage import SQLiteStore


class SystemHealthService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def inspect(self) -> SystemHealthResponse:
        checks = [
            self._backend_check(),
            self._database_check(),
            *self._browser_checks(),
            self._model_check(),
            self._pdf_converter_check(),
            self._ocr_check(),
        ]
        return SystemHealthResponse(status=self._overall_status(checks), checks=checks)

    def _backend_check(self) -> SystemHealthCheck:
        return SystemHealthCheck(
            id="backend",
            label="后端运行",
            status="green",
            summary="FastAPI 服务正在响应",
            next_action="可以继续上传简历、搜索岗位或检查其他状态",
        )

    def _database_check(self) -> SystemHealthCheck:
        try:
            with self.store._connect() as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as exc:
            return SystemHealthCheck(
                id="database",
                label="数据库",
                status="red",
                summary="数据库不可用",
                detail=type(exc).__name__,
                next_action="检查 data 目录权限或重新启动后端",
            )
        return SystemHealthCheck(
            id="database",
            label="数据库",
            status="green",
            summary="SQLite 可以读写",
            next_action="无需处理",
            metadata={"path": str(self.store.db_path)},
        )

    def _browser_checks(self) -> list[SystemHealthCheck]:
        sessions = PlatformSessionService().inspect()
        cdp_check = SystemHealthCheck(
            id="cdp_browser",
            label="CDP 浏览器",
            status="green" if sessions.browser_connected else "yellow",
            summary="已连接本机浏览器" if sessions.browser_connected else "未连接 CDP 浏览器",
            detail=sessions.error,
            next_action="可以刷新平台会话" if sessions.browser_connected else "点击“启动 CDP 浏览器”并登录招聘平台",
            metadata={"cdp_url": sessions.cdp_url or ""},
        )
        detected = [session.platform for session in sessions.sessions if session.state == "tab_detected"]
        missing = [session.platform for session in sessions.sessions if session.state != "tab_detected"]
        if not sessions.browser_connected:
            platform_status = "yellow"
            summary = "需要先连接浏览器"
            next_action = "启动 CDP 浏览器后打开 BOSS/实习僧页面"
        elif missing:
            platform_status = "yellow"
            summary = f"已检测 {len(detected)} 个平台标签页，仍需打开：{', '.join(missing)}"
            next_action = "在 CDP 浏览器中打开缺失平台页面后刷新会话"
        else:
            platform_status = "green"
            summary = "BOSS/实习僧标签页均已检测"
            next_action = "可以执行真实搜索或刷新岗位详情"
        return [
            cdp_check,
            SystemHealthCheck(
                id="platform_sessions",
                label="平台会话",
                status=platform_status,
                summary=summary,
                next_action=next_action,
                metadata={
                    "detected": detected,
                    "missing": missing,
                    "sessions": [
                        {
                            "platform": session.platform,
                            "state": session.state,
                            "detected_url": session.detected_url or "",
                        }
                        for session in sessions.sessions
                    ],
                },
            ),
        ]

    def _model_check(self) -> SystemHealthCheck:
        config = self.store.get_model_config()
        metadata = {
            "provider": config.provider,
            "model": config.model,
            "enabled": config.enabled,
            "estimation_only": config.estimation_only,
            "api_key_configured": config.api_key_configured,
            "api_key_masked": config.api_key_masked,
        }
        if config.enabled and not config.estimation_only and config.api_key_configured:
            return SystemHealthCheck(
                id="model",
                label="模型连接",
                status="green",
                summary=f"{config.provider} / {config.model} 已配置 Key",
                next_action="可以点击测试模型连接",
                metadata=metadata,
            )
        if config.enabled and not config.api_key_configured:
            return SystemHealthCheck(
                id="model",
                label="模型连接",
                status="red",
                summary="已启用真实模型，但还没有 API Key",
                next_action="在模型 / API 区域填入真实 Key 并保存",
                metadata=metadata,
            )
        return SystemHealthCheck(
            id="model",
            label="模型连接",
            status="yellow",
            summary="当前使用本地规则或估算模式",
            next_action="如需 AI 改写，请配置 DeepSeek 或 OpenAI-compatible API Key",
            metadata=metadata,
        )

    def _pdf_converter_check(self) -> SystemHealthCheck:
        has_word_com = os.name == "nt" and self._can_import("win32com.client")
        libreoffice = shutil.which("soffice") or shutil.which("libreoffice")
        if has_word_com or libreoffice:
            return SystemHealthCheck(
                id="pdf_converter",
                label="PDF 转换器",
                status="green",
                summary="已检测到 DOCX 转 PDF 能力",
                next_action="可以下载模板化一页 PDF",
                metadata={"word_com": has_word_com, "libreoffice": bool(libreoffice)},
            )
        return SystemHealthCheck(
            id="pdf_converter",
            label="PDF 转换器",
            status="yellow",
            summary="未检测到 Word COM 或 LibreOffice",
            next_action="安装 Microsoft Word 或 LibreOffice 后再导出模板化 PDF",
            metadata={"word_com": False, "libreoffice": False},
        )

    def _ocr_check(self) -> SystemHealthCheck:
        has_ocr = self._can_import("PIL.Image") and self._can_import("pytesseract")
        if has_ocr:
            return SystemHealthCheck(
                id="ocr",
                label="OCR 能力",
                status="green",
                summary="已检测到图片简历 OCR 依赖",
                next_action="可尝试上传图片简历自动识别",
            )
        return SystemHealthCheck(
            id="ocr",
            label="OCR 能力",
            status="yellow",
            summary="未检测到完整 OCR 依赖",
            next_action="上传图片或扫描 PDF 后，可手动补全文字",
        )

    def _can_import(self, module_name: str) -> bool:
        try:
            __import__(module_name)
        except Exception:
            return False
        return True

    def _overall_status(self, checks: list[SystemHealthCheck]) -> str:
        statuses = {check.status for check in checks}
        if "red" in statuses:
            return "red"
        if "yellow" in statuses:
            return "yellow"
        return "green"
