import os
from functools import lru_cache
from typing import Dict, List
from PySide6.QtCore import QUrl
from .logger import file_logger as logger

# 动态计算包内 web_frontend 的绝对路径
# 结构: emote_widget/utils/paths.py -> (up) -> emote_widget/ -> (down) -> web_frontend
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_FRONTEND_ROOT = os.path.join(_BASE_DIR, 'web_frontend')

RESOURCE_SEARCH_PATHS: Dict[str, List[str]] = {
    'models': [],
    'backgrounds': [],
    'dialogs': []
}

def add_resource_directory(category: str, path: str) -> None:
    """
    添加一个资源搜索目录。
    category: 'models', 'backgrounds', 'dialogs'
    """
    if category in RESOURCE_SEARCH_PATHS:
        abs_path = os.path.abspath(path)
        if abs_path not in RESOURCE_SEARCH_PATHS[category]:
            RESOURCE_SEARCH_PATHS[category].insert(0, abs_path) # Insert at beginning to prioritize user paths
            resolve_resource_url.cache_clear()
            logger.info(f"添加资源搜索路径 [{category}]: {abs_path}")

def getresource_search_paths(category: str) -> List[str]:
    """
    获取指定类别的资源搜索路径列表。
    返回的是列表的副本，以防外部修改影响内部状态。
    """
    return list(RESOURCE_SEARCH_PATHS.get(category, []))

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
        # 2. 检查自定义搜索路径
        if internal_subfolder in RESOURCE_SEARCH_PATHS:
            for search_path in RESOURCE_SEARCH_PATHS[internal_subfolder]:
                candidate = os.path.join(search_path, path_or_name)
                if os.path.exists(candidate):
                    final_path = candidate
                    break
        
        # 3. 检查内部默认目录 (如果没有在自定义路径中找到)
        if not final_path:
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
