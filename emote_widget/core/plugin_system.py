import sys
import os
import importlib
import logging
from PySide6.QtCore import QObject, Signal, Slot
from typing import Dict, List, ValuesView
from emote_widget.utils.logger import plugin_logger as logger
from .plugin_interface import IEmotePlugin

class PluginAccessor:
    """提供类似 widget.plugins.pluginname 的访问方式"""
    def __init__(self) -> None:
        self._plugins: Dict[str, IEmotePlugin] = {}

    def register(self, plugin: IEmotePlugin) -> None:
        name = plugin.get_name()
        if not name.isidentifier():
            logger.error(f"插件名无效: {name}")
            return
        self._plugins[name] = plugin

    def get(self, name: str) -> IEmotePlugin | None:
        return self._plugins.get(name)

    def get_all(self) -> ValuesView[IEmotePlugin]:
        return self._plugins.values()
    
    def cleanup_all(self) -> None:
        for p in self._plugins.values():
            try: p.cleanup()
            except: pass
    
    def __getattr__(self, name: str) -> IEmotePlugin:
        plugin = self.get(name)
        if plugin is None:
            raise AttributeError(f"未找到插件: '{name}'")
        return plugin

class PluginLoaderWorker(QObject):
    """独立的插件加载逻辑"""
    progress_updated = Signal(float, str)
    log_message = Signal(str, bool)
    finished = Signal(list)

    def __init__(self, plugin_dir: str) -> None:
        super().__init__()
        self._modules_to_load: List[str] = []
        self._plugin_dir: str = plugin_dir

    def scan_for_plugin_modules(self) -> None:
        if self._plugin_dir not in sys.path:
            sys.path.insert(0, self._plugin_dir)
            logger.debug(f"已将插件目录加入 sys.path")

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

                # Case A: 单文件插件
                if is_file and filename.endswith(".py"):
                    if filename.startswith("__"):
                        logger.debug(f"  [忽略] 系统/接口文件: {filename}")
                        continue
                    module_name = filename[:-3]
                    logger.info(f"  [命中] 单文件插件: {module_name}")

                # Case B: 包插件 (文件夹)
                elif is_dir:
                    if filename.startswith("__") or filename.startswith("."):
                        logger.debug(f"  [忽略] 隐藏目录: {filename}")
                        continue
                    
                    init_path = os.path.join(filepath, "__init__.py")
                    has_init = os.path.exists(init_path)
                    
                    if has_init:
                        module_name = filename
                        logger.info(f"  [命中] 包插件: {module_name} (包含 __init__.py)")
                    else:
                        logger.warning(f"  [跳过] 文件夹 '{filename}' 缺少 __init__.py，无法作为包加载")
                else:
                    logger.debug(f"  [忽略] 未知类型: {filename}")
                
                # 加入列表
                if module_name:
                    if module_name not in self._modules_to_load:
                        self._modules_to_load.append(module_name)
                    else:
                        logger.warning(f"  [重复] 插件 '{module_name}' 已在列表中")

            logger.info(f"扫描结束，待加载模块列表: {self._modules_to_load}")
        except Exception as e:
            logger.error(f"扫描插件时发生异常: {e}", exc_info=True)


    @Slot()
    def run_loading(self) -> None:
        total = len(self._modules_to_load)
        loaded_instances: List[IEmotePlugin] = []
        
        if total == 0:
            self.finished.emit([])
            return
            
        for i, mod_name in enumerate(self._modules_to_load):
            self.progress_updated.emit((i+1)/total, f"正在加载: {mod_name}")
            try:
                module = importlib.import_module(mod_name)

                found_in_module = False
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type):           
                        is_sub = issubclass(item, IEmotePlugin)
                        is_self = item is IEmotePlugin
                        logger.info(f"  发现类 '{item_name}': 继承检测={is_sub}, 是否基类本身={is_self}")
                        if is_sub and not is_self:
                            instance = item()
                            # 为插件创建专属logger
                            instance.logger = logging.getLogger(f"EmoteWidget.Plugins.{instance.get_name()}")
                            loaded_instances.append(instance)
                            self.log_message.emit(f"已加载: {instance.get_name()}", False)
                            found_in_module = True
                
                if not found_in_module:
                    logger.warning(f"模块 '{mod_name}' 中未发现有效的 IEmotePlugin 子类。请检查 __init__.py 是否暴露了该类。")

            except Exception as e:
                self.log_message.emit(f"加载失败 {mod_name}: {e}", True)
                logger.error(f"插件加载错误 {mod_name}: {e}", exc_info=True)
                
        self.finished.emit(loaded_instances)