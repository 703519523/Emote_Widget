import os
from functools import lru_cache
import time
from typing import Dict, List, Tuple
from PySide6.QtCore import QUrl
from .logger import file_logger as logger

# 动态计算包内 web_frontend 的绝对路径
# 结构: emote_widget/utils/paths.py -> (up) -> emote_widget/ -> (down) -> web_frontend
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_FRONTEND_ROOT = os.path.join(_BASE_DIR, 'web_frontend')

# [Security] 允许访问的根目录白名单
ALLOWED_RESOURCE_ROOTS: List[str] = [WEB_FRONTEND_ROOT]

RESOURCE_SEARCH_PATHS: Dict[str, List[str]] = {
    'models': [],
    'backgrounds': [],
    'dialogs': []
}

def register_allowed_path(path: str) -> None:
    """
    注册一个允许被前端访问的根目录。
    这对于安全性至关重要，防止路径穿越攻击。
    """
    abs_path = os.path.abspath(path)
    # 检查是否已经包含在现有白名单中（或者是子目录）
    for root in ALLOWED_RESOURCE_ROOTS:
        if abs_path.startswith(root):
            return 
            
    if abs_path not in ALLOWED_RESOURCE_ROOTS:
        ALLOWED_RESOURCE_ROOTS.append(abs_path)
        logger.info(f"[Security] 注册安全访问路径: {abs_path}")

def is_path_allowed(path: str) -> bool:
    """检查路径是否在允许的白名单内"""
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(root) for root in ALLOWED_RESOURCE_ROOTS)

class _TTLScanCache:
    """Simple TTL cache for directory scanning results."""
    def __init__(self, ttl_seconds: float = 5.0):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, str]]] = {}

    def get(self, key: str) -> Dict[str, str] | None:
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return data
            else:
                del self._cache[key]
        return None

    def set(self, key: str, data: Dict[str, str]):
        self._cache[key] = (time.time(), data)

    def clear(self):
        self._cache.clear()

_scan_cache = _TTLScanCache(ttl_seconds=15.0)

def scan_directory_for_resources(directory_path: str, extensions: Tuple[str, ...], recursive: bool = False, max_depth: int = 1) -> Dict[str, str]:
    """
    高效扫描目录以查找特定扩展名的资源文件。
    
    Args:
        directory_path: 要扫描的目录路径。
        extensions: 允许的文件扩展名元组 (例如: ('.psb', '.html'))。应为小写。
        recursive: 是否递归扫描子目录。
        max_depth: 递归最大深度。

    Returns:
        Dict[str, str]: {文件名: 绝对路径} 的字典。
    """
    # Create a cache key based on arguments
    cache_key = f"{directory_path}|{extensions}|{recursive}|{max_depth}"
    cached = _scan_cache.get(cache_key)
    if cached is not None:
        return cached

    results: Dict[str, str] = {}
    
    if not os.path.exists(directory_path):
        return results

    try:
        # Normalize extensions to lowercase for case-insensitive comparison
        allowed_exts = set(ext.lower() for ext in extensions)

        def _scan(path: str, current_depth: int):
            if current_depth > max_depth:
                return

            try:
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            if entry.is_file():
                                # Check extension
                                name = entry.name
                                ext = os.path.splitext(name)[1].lower()
                                if ext in allowed_exts:
                                    # [Security] Ensure path is allowed?
                                    # logic in controller will call is_path_allowed on result, 
                                    # but we can also just return absolute paths here.
                                    # The requirement says "Make sure every path ... is checked by is_path_allowed" in Controller refactor.
                                    # So we just return raw scan results here.
                                    results[name] = entry.path
                            
                            elif recursive and entry.is_dir() and not entry.name.startswith('.'):
                                # Recurse
                                _scan(entry.path, current_depth + 1)
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, FileNotFoundError) as e:
                logger.warning(f"Error scanning directory {path}: {e}")
                return

        _scan(directory_path, 0)
        
        # Update cache
        _scan_cache.set(cache_key, results)
        
    except Exception as e:
        logger.error(f"Failed to scan directory {directory_path}: {e}")

    return results

def add_resource_directory(category: str, path: str) -> None:
    """
    添加一个资源搜索目录。
    category: 'models', 'backgrounds', 'dialogs'
    """
    if category in RESOURCE_SEARCH_PATHS:
        abs_path = os.path.abspath(path)
        if abs_path not in RESOURCE_SEARCH_PATHS[category]:
            RESOURCE_SEARCH_PATHS[category].insert(0, abs_path) # Insert at beginning to prioritize user paths
            register_allowed_path(abs_path) # 同时注册到安全白名单
            resolve_resource_url.cache_clear()
            _scan_cache.clear() # Clear scan cache when new directory is added
            logger.info(f"添加资源搜索路径 [{category}]: {abs_path}")
    else:
        logger.warning(f"尝试添加未知资源类别 [{category}]: {path}")

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
        # Helper to check directory
        def check_directory(base_path: str) -> str | None:
            # A. 直接拼接检查
            candidate = os.path.join(base_path, path_or_name)
            if os.path.exists(candidate):
                return candidate
            
            # B. 递归扫描查找 (针对子文件夹中的文件)
            # 仅当 path_or_name 是纯文件名时才尝试搜索
            if os.path.basename(path_or_name) == path_or_name:
                ext = os.path.splitext(path_or_name)[1].lower()
                if ext:
                    # 使用 scan_directory_for_resources 利用缓存进行查找
                    # recursive=True, max_depth=1 (保持与 list_available_resources 一致)
                    mapping = scan_directory_for_resources(base_path, (ext,), recursive=True)
                    if path_or_name in mapping:
                        return mapping[path_or_name]
            return None

        # 2. 检查自定义搜索路径
        if internal_subfolder in RESOURCE_SEARCH_PATHS:
            for search_path in RESOURCE_SEARCH_PATHS[internal_subfolder]:
                found = check_directory(search_path)
                if found:
                    final_path = found
                    break
        
        # 3. 检查内部默认目录 (如果没有在自定义路径中找到)
        if not final_path:
            internal_path = os.path.join(WEB_FRONTEND_ROOT, internal_subfolder)
            found = check_directory(internal_path)
            if found:
                final_path = found
    
    if final_path:
        # [Security] 二次校验：确保解析出的绝对路径在白名单内
        if not is_path_allowed(final_path):
            logger.warning(f"[Security] 拦截非法路径访问尝试: {final_path}")
            return None

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
