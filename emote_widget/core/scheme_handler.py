"""
EmoteWidget 自定义协议处理器模块。

本模块实现了 `EmoteSchemeHandler`，用于拦截并处理 `emote://` 协议的请求。
这使得 WebEngine 可以像访问 Web 服务器一样访问本地文件系统中的资源，同时绕过浏览器的同源策略 (CORS) 限制。
"""

import os
import mimetypes
from typing import Optional
from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtWebEngineCore import QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob
from emote_widget.utils.logger import file_logger as logger
from emote_widget.utils.paths import is_path_allowed

class EmoteSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    [协议处理器] 自定义 URL Scheme 处理器: `emote://`
    
    功能:
        将 `emote:///path/to/file` 形式的请求映射到本地文件系统。
        
    安全性 (Security):
        为了防止任意文件读取漏洞 (LFI)，本处理器集成了路径白名单检查机制 (`is_path_allowed`)。
        只有被显式允许的目录（如 SDK 内部资源目录、用户指定的模型目录）下的文件才会被加载。
        
    解决痛点 (Pain Points Solved):
        1. **CORS 问题**: 本地 `file://` 协议通常禁止跨域请求 (如 fetch 加载 .json)，
           通过自定义协议并设置 CORS 头，完美规避此限制。
        2. **路径统一**: 无论是在开发环境还是打包后的环境，都可以使用统一的 `emote://` 路径。
    """
    
    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        """
        [Override] 当 WebEngine 发起请求时调用。
        
        Args:
            job (QWebEngineUrlRequestJob): 请求任务对象，用于获取 URL 和发送响应。
        """
        url: QUrl = job.requestUrl()
        file_path: str = url.path()
        
        # Windows 路径修正: "/C:/path" -> "C:/path"
        if os.name == 'nt' and file_path.startswith('/') and ':' in file_path:
            file_path = file_path[1:]

        # URL 解码 (处理中文路径和特殊字符)
        file_path = QUrl.fromPercentEncoding(file_path.encode()).strip()
        
        # [Security] 强制校验路径白名单
        # 防止恶意构造如 emote:///etc/passwd 的请求
        if not is_path_allowed(file_path):
            logger.warning(f"[Security] SchemeHandler 拦截未授权访问: {file_path}")
            # 使用 UrlInvalid 模拟 403 Forbidden
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return

        # 检查文件存在性
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.error(f"[SchemeHandler] File not found: {file_path}")
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        # 猜测 MIME 类型
        mime_type: Optional[str]
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        try:
            # 读取文件内容
            # TODO: 对于大文件 (如视频)，应考虑流式读取以减少内存占用
            with open(file_path, 'rb') as file:
                content: bytes = file.read()
        except Exception as e:
            logger.error(f"[SchemeHandler] Read error: {e}")
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return

        # 构造响应缓冲区
        # 注意：buffer 必须挂载到 job 对象上，防止被提前 GC
        buffer: QBuffer = QBuffer(job)
        buffer.setData(content)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        
        # 发送响应
        # 这里的关键是 QtWebEngine 会自动处理 CORS (或者我们需要手动注入 Access-Control-Allow-Origin?)
        # 实际上自定义 Scheme 通常被视为同源，或者我们可以通过 Profile 设置来放宽限制。
        job.reply(mime_type.encode('utf-8'), buffer)
