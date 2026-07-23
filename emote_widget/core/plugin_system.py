"""
EmoteWidget 插件系统模块。

本模块实现了 EmoteWidget 的插件扩展机制。
插件允许开发者在不修改 SDK 核心代码的情况下，为组件添加新的功能（如聊天机器人集成、行为等）。

架构组成:
    1. **PluginAccessor**: 一个方便的容器类，提供点号访问语法 (widget.plugins.my_plugin)。
    2. **PluginLoaderWorker**: 一个独立的后台线程 Worker，负责扫描和加载插件模块，避免阻塞 UI 主线程。
"""

import sys
import os
import json
import importlib
import logging
from PySide6.QtCore import QObject, Signal, Slot
from typing import Dict, List, ValuesView, Optional
from emote_widget.utils.logger import plugin_logger as logger
from .plugin_interface import IEmotePlugin


class PluginStateStore:
    """持久化插件模块的启用状态；未记录的插件默认启用。"""

    FILENAME = ".plugin_state.json"

    def __init__(self, plugin_dir: str) -> None:
        self._path = os.path.join(plugin_dir, self.FILENAME)

    def _read_disabled(self) -> set[str]:
        if not os.path.exists(self._path):
            return set()
        try:
            with open(self._path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            disabled = payload.get("disabled_plugins", [])
            if not isinstance(disabled, list):
                raise ValueError("disabled_plugins 必须是列表")
            return {name for name in disabled if isinstance(name, str)}
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.error(f"读取插件状态失败，将按全部启用处理: {exc}")
            return set()

    def is_enabled(self, module_name: str) -> bool:
        return module_name not in self._read_disabled()

    def set_enabled(self, module_name: str, enabled: bool) -> None:
        if not module_name or not module_name.isidentifier():
            raise ValueError(f"无效的插件模块名: {module_name!r}")

        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        disabled = self._read_disabled()
        if enabled:
            disabled.discard(module_name)
        else:
            disabled.add(module_name)

        temp_path = f"{self._path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(
                {"disabled_plugins": sorted(disabled)},
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")
        os.replace(temp_path, self._path)

class PluginAccessor:
    """
    [插件访问器] 用于存储和访问已加载的插件实例。
    
    设计目的:
        提供一种直观的语法糖，允许用户通过 `widget.plugins.plugin_name` 的方式访问插件。
        这比 `get_plugin("plugin_name")` 更符合 Pythonic 风格。
    """
    def __init__(self) -> None:
        self._plugins: Dict[str, IEmotePlugin] = {}
        self._is_qml_mode: bool = False

    def set_qml_mode(self, enabled: bool) -> None:
        """设置是否处于 QML 模式。在 QML 模式下，获取插件会返回 SafeProxy。"""
        self._is_qml_mode = enabled

    def register(self, plugin: IEmotePlugin) -> None:
        """
        注册一个插件实例。
        
        Args:
            plugin (IEmotePlugin): 已初始化的插件对象。
        """
        name = plugin.get_name()
        if not name.isidentifier():
            logger.error(f"插件名无效: '{name}'。必须是有效的 Python 标识符。")
            return
        self._plugins[name] = plugin

    def get(self, name: str) -> Optional[IEmotePlugin]:
        """
        获取指定名称的插件。
        
        Returns:
            Optional[IEmotePlugin]: 插件实例，若不存在则返回 None。
        """
        return self._plugins.get(name)

    def get_all(self) -> ValuesView[IEmotePlugin]:
        """获取所有已加载的插件。"""
        return self._plugins.values()
    
    def cleanup_all(self, clear: bool = False) -> None:
        """调用所有插件的 cleanup 方法。"""
        for p in list(self._plugins.values()):
            try: 
                p.cleanup()
            except Exception as e:
                logger.error(f"插件 {p.get_name()} 清理失败: {e}")
        if clear:
            self._plugins.clear()
    
    def __getattr__(self, name: str) -> IEmotePlugin:
        """
        [黑魔法] 动态属性访问。
        
        允许 `plugins.example` 访问名为 "example" 的插件。
        如果插件不存在，抛出 AttributeError。
        """
        plugin = self.get(name)
        if plugin is None:
            raise AttributeError(f"未找到插件: '{name}'")
            
        if self._is_qml_mode:
            # 在 QML 模式下，返回安全的代理对象
            from emote_widget.utils.proxy import create_safe_proxy
            return create_safe_proxy(plugin)
            
        return plugin

class PluginLoaderWorker(QObject):
    """
    [插件加载器] 负责在后台线程中扫描和实例化插件。
    
    职责:
        1. 扫描指定目录下的 .py 文件和包目录。
        2. 动态 import 模块。
        3. 查找模块中继承自 `IEmotePlugin` 的类并实例化。
        4. 通过信号汇报加载进度和日志。
    """
    
    # 信号定义
    progress_updated = Signal(float, str)
    """加载进度信号: (progress 0.0~1.0, current_task_description)"""
    
    log_message = Signal(str, bool)
    """日志信号: (message, is_error)"""
    
    finished = Signal(list)
    """完成信号: (loaded_instances: List[IEmotePlugin])"""

    def __init__(self, plugin_dir: str, state_store: Optional[PluginStateStore] = None) -> None:
        """
        Args:
            plugin_dir (str): 插件根目录的绝对路径。
        """
        super().__init__()
        self._modules_to_load: List[str] = []
        self._plugin_dir: str = plugin_dir
        self._state_store = state_store or PluginStateStore(plugin_dir)

    @property
    def modules_to_load(self) -> tuple[str, ...]:
        """返回本轮扫描所得模块快照。"""
        return tuple(self._modules_to_load)

    def list_plugin_modules(self) -> List[Dict[str, object]]:
        """列出可发现的全部插件模块及其持久化启用状态。"""
        modules: List[str] = []
        if not os.path.isdir(self._plugin_dir):
            return []

        for filename in os.listdir(self._plugin_dir):
            filepath = os.path.join(self._plugin_dir, filename)
            module_name: Optional[str] = None
            if os.path.isfile(filepath) and filename.endswith(".py"):
                if not filename.startswith("__"):
                    module_name = filename[:-3]
            elif os.path.isdir(filepath):
                if not filename.startswith(("__", ".")) and os.path.exists(
                    os.path.join(filepath, "__init__.py")
                ):
                    module_name = filename
            if module_name and module_name not in modules:
                modules.append(module_name)

        return [
            {"module": name, "enabled": self._state_store.is_enabled(name)}
            for name in sorted(modules)
        ]

    def scan_for_plugin_modules(self) -> None:
        """
        [预处理] 扫描插件目录，生成待加载模块列表。
        此步骤通常在主线程执行，因为它很快且只涉及文件系统枚举。
        """
        self._modules_to_load.clear()

        # 将插件目录加入 sys.path，以便可以直接 import 其中的模块
        if self._plugin_dir not in sys.path:
            sys.path.insert(0, self._plugin_dir)
            logger.debug(f"已将插件目录加入 sys.path: {self._plugin_dir}")

        if not os.path.exists(self._plugin_dir):
            logger.error(f"❌ 插件目录不存在! 请检查路径: {self._plugin_dir}")
            return

        try:
            raw_list = os.listdir(self._plugin_dir)
            for filename in raw_list:
                filepath = os.path.join(self._plugin_dir, filename)
                module_name = None
                
                is_file = os.path.isfile(filepath)
                is_dir = os.path.isdir(filepath)

                # Case A: 单文件插件 (plugin.py)
                if is_file and filename.endswith(".py"):
                    if filename.startswith("__"): # 忽略 __init__.py
                        continue
                    module_name = filename[:-3] # 去掉 .py 后缀
                    logger.info(f"  [命中] 单文件插件: {module_name}")

                # Case B: 包插件 (plugin_folder/)
                elif is_dir:
                    if filename.startswith("__") or filename.startswith("."):
                        continue
                    
                    init_path = os.path.join(filepath, "__init__.py")
                    if os.path.exists(init_path):
                        module_name = filename
                        logger.info(f"  [命中] 包插件: {module_name} (包含 __init__.py)")
                    else:
                        logger.warning(f"  [跳过] 文件夹 '{filename}' 缺少 __init__.py，无法作为包加载")
                
                # 加入待加载列表 (去重)
                if module_name and module_name not in self._modules_to_load:
                    if self._state_store.is_enabled(module_name):
                        self._modules_to_load.append(module_name)
                    else:
                        logger.info(f"  [禁用] 跳过插件模块: {module_name}")

            logger.info(f"扫描结束，待加载模块列表: {self._modules_to_load}")
        except Exception as e:
            logger.error(f"扫描插件时发生异常: {e}", exc_info=True)


    @Slot()
    def run_loading(self) -> None:
        """
        [后台任务] 执行具体的 import 和实例化操作。
        此方法应在 QThread 中执行，以免阻塞主线程 UI。
        """
        total = len(self._modules_to_load)
        loaded_instances: List[IEmotePlugin] = []
        
        if total == 0:
            self.finished.emit([])
            return
            
        for i, mod_name in enumerate(self._modules_to_load):
            self.progress_updated.emit((i+1)/total, f"正在加载: {mod_name}")
            try:
    # 动态导入模块
                module = importlib.import_module(mod_name)

                found_in_module = False
                # 遍历模块中的所有属性，寻找 IEmotePlugin 的子类
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type): # 必须是类定义          
                        is_sub = issubclass(item, IEmotePlugin)
                        is_self = item is IEmotePlugin # 排除接口类本身
                        
                        if is_sub and not is_self:
                            logger.info(f"  发现插件类 '{item_name}'")
                            
                            # [Sanitizing] 在实例化之前，确保所有公共方法都是 Slot
                            from emote_widget.utils.proxy import wrap_as_qml_slot
                            import inspect
                            
                            for member_name, member in inspect.getmembers(item):
                                if not member_name.startswith("_") and callable(member):
                                    # 跳过已经有 Slot 标记的
                                    # 注意：必须同时检查 __pyside_signals__ 和 _slots (PySide6 特性)
                                    if getattr(member, "__pyside_signals__", None) or getattr(member, "_slots", None):
                                        continue
                                        
                                    # 包装并替换
                                    # 注意：我们是在类定义上修改，所以这会影响所有实例
                                    wrapped = wrap_as_qml_slot(member)
                                    setattr(item, member_name, wrapped)
                                    # logger.debug(f"    已自动修补 Slot: {member_name}")

                            # 实例化插件
                            instance = item()
                            # 自动注入专属 Logger，方便插件开发者调试
                            instance.logger = logging.getLogger(f"EmoteWidget.Plugins.{instance.get_name()}")
                            
                            loaded_instances.append(instance)
                            self.log_message.emit(f"已加载: {instance.get_name()}", False)
                            found_in_module = True
                            # 每个模块通常只包含一个主要插件类，找到后继续下一个模块?
                            # 暂时不 break，允许一个模块包含多个插件类。
                
                if not found_in_module:
                    logger.warning(f"模块 '{mod_name}' 中未发现有效的 IEmotePlugin 子类。")

            except Exception as e:
                self.log_message.emit(f"加载失败 {mod_name}: {e}", True)
                logger.error(f"插件加载错误 {mod_name}: {e}", exc_info=True)
                
        # 加载完成，返回实例列表
        self.finished.emit(loaded_instances)
