import os
from functools import lru_cache
from PySide6.QtCore import QUrl
from .logger import file_logger as logger

# 动态计算包内 web_frontend 的绝对路径
# 结构: emote_widget/utils/paths.py -> (up) -> emote_widget/ -> (down) -> web_frontend
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_FRONTEND_ROOT = os.path.join(_BASE_DIR, 'web_frontend')

@lru_cache(maxsize=128)
def resolve_resource_url(path_or_name: str | None, internal_subfolder: str) -> str | None:
    """
    将路径转换为 emote:// 协议的 URL。
    支持绝对路径和相对路径自动补全。
    """
    if not path_or_name:
        return None

    final_path = None

    # 1. 检查是否为绝对路径
    if os.path.exists(path_or_name):
        final_path = os.path.abspath(path_or_name)
    else:
        # 2. 检查内部默认目录
        internal_path = os.path.join(WEB_FRONTEND_ROOT, internal_subfolder, path_or_name)
        if os.path.exists(internal_path):
            final_path = internal_path
    
    if final_path:
        # 转换为 emote:// 协议
        # 格式: emote://resource/<path>
        # QUrl.fromLocalFile 生成 file:///C:/...
        # 把 'file://' 替换成 'emote://resource'
        
        # 使用 QUrl 处理路径转义 (空格 -> %20)
        u = QUrl.fromLocalFile(final_path)
        u.setScheme("emote")
        # 这里的 host 设置为 'resource' 只是为了让 URL 看起来规范 (emote://resource/C:/...)
        # SchemeHandler 那边会忽略 host，直接读 path
        # 但要注意 Windows 盘符问题，Qt 的 path() 会处理好
        return u.toString()

    logger.warning(f"资源未找到: {path_or_name}")
    return None