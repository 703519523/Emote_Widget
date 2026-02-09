# emote_widget/core/plugin_system.py
import pkgutil
import importlib
from PySide6.QtCore import QObject, Signal, Slot
from emote_widget.utils.logger import emote_widget_logger as logger
from .plugin_interface import IEmotePlugin

class PluginAccessor:
    """提供类似 widget.plugins.pluginname 的访问方式"""
    def __init__(self):
        self._plugins = {}

    def register(self, plugin: IEmotePlugin):
        name = plugin.get_name()
        if not name.isidentifier():
            logger.error(f"插件名无效: {name}")
            return
        self._plugins[name] = plugin

    def get(self, name: str) -> IEmotePlugin | None:
        return self._plugins.get(name)

    def get_all(self):
        return self._plugins.values()
    
    def cleanup_all(self):
        for p in self._plugins.values():
            try: p.cleanup()
            except: pass
    
    def __getattr__(self, name: str):
        plugin = self.get(name)
        if plugin is None:
            raise AttributeError(f"未找到插件: '{name}'")
        return plugin

class PluginLoaderWorker(QObject):
    """独立的插件加载逻辑"""
    progress_updated = Signal(float, str)
    log_message = Signal(str, bool)
    finished = Signal(list)

    def __init__(self, plugin_dir):
        super().__init__()
        self._modules_to_load = []
        self._plugin_dir = plugin_dir

    def scan_for_plugin_modules(self):
        import sys
        if self._plugin_dir not in sys.path:
            sys.path.insert(0, self._plugin_dir)

        try:
            logger.info(f"扫描插件目录: {self._plugin_dir}")
            for _, module_name, _ in pkgutil.walk_packages([self._plugin_dir]):
                # 排除接口文件
                if not module_name.endswith('plugin_interface'):
                    self._modules_to_load.append(module_name)
        except Exception as e:
            logger.error(f"扫描插件失败: {e}")

    @Slot()
    def run_loading(self):
        total = len(self._modules_to_load)
        loaded_instances = []
        
        if total == 0:
            self.finished.emit([])
            return
            
        for i, mod_name in enumerate(self._modules_to_load):
            self.progress_updated.emit((i+1)/total, f"正在加载: {mod_name}")
            try:
                module = importlib.import_module(mod_name)
                # 查找 IEmotePlugin 的子类
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type) and issubclass(item, IEmotePlugin) and item is not IEmotePlugin:
                        instance = item()
                        loaded_instances.append(instance)
                        self.log_message.emit(f"已加载: {instance.get_name()}", False)
            except Exception as e:
                self.log_message.emit(f"加载失败 {mod_name}: {e}", True)
                logger.error(f"插件加载错误 {mod_name}: {e}", exc_info=True)
                
        self.finished.emit(loaded_instances)