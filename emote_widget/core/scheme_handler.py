import os
import mimetypes
from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtWebEngineCore import QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob
from emote_widget.utils.logger import file_logger as logger

class EmoteSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    自定义协议处理器: emote://
    用于安全地加载本地资源，解决 file:// 协议的 CORS 问题。
    """
    def requestStarted(self, job: QWebEngineUrlRequestJob):
        url = job.requestUrl()
        # url 格式: emote://resource/<path>
        
        file_path = url.path()
        
        if os.name == 'nt' and file_path.startswith('/') and ':' in file_path:
            file_path = file_path[1:]

        file_path = QUrl.fromPercentEncoding(file_path.encode()).strip()
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.error(f"[SchemeHandler] File not found: {file_path}")
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        try:
            file = open(file_path, 'rb')
            content = file.read()
            file.close()
        except Exception as e:
            logger.error(f"[SchemeHandler] Read error: {e}")
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return

        buffer = QBuffer(job)
        buffer.setData(content)
        buffer.open(QIODevice.ReadOnly)
        
        # 设置 CORS 头，允许 JS fetch()
        # 告诉浏览器：这个资源允许被任何页面请求
        job.reply(mime_type.encode('utf-8'), buffer)