import importlib
import os
import sys
import logging
from typing import Type, Dict
from .adapter_interface import IViewAdapter

from emote_widget.utils.logger import adapter_logger as logger

class AdapterRegistry:
    """
    视图适配器注册表。
    用于管理和查找不同的 UI 适配器 (如 QtAdapter, TkAdapter, CEFAdapter)。
    """
    _adapters: Dict[str, Type[IViewAdapter]] = {}

    @classmethod
    def register(cls, name: str):
        """
        装饰器：注册一个 Adapter 类。
        用法:
            @AdapterRegistry.register("my_custom_adapter")
            class MyAdapter(IViewAdapter): ...
        """
        def decorator(adapter_cls):
            if not issubclass(adapter_cls, IViewAdapter):
                logger.warning(f"Adapter '{name}' 必须继承自 IViewAdapter")
                return adapter_cls
            
            logger.info(f"注册适配器: {name} -> {adapter_cls.__name__}")
            cls._adapters[name] = adapter_cls
            return adapter_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> Type[IViewAdapter]:
        if name not in cls._adapters:
            available = list(cls._adapters.keys())
            raise ValueError(f"未找到名为 '{name}' 的适配器。可用适配器: {available}")
        return cls._adapters[name]

    @classmethod
    def scan_plugins(cls, plugin_dir: str):
        """
        扫描指定目录下的 Python 文件，尝试加载其中的 Adapter。
        """
        if not os.path.isdir(plugin_dir):
            return

        logger.info(f"正在扫描适配器插件目录: {plugin_dir}")
        
        # 临时将插件目录加入 sys.path
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)

        count = 0
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    # 导入模块会自动触发 @register 装饰器
                    importlib.import_module(module_name)
                    count += 1
                except Exception as e:
                    logger.error(f"加载适配器插件 '{filename}' 失败: {e}")
        
        if count > 0:
            logger.info(f"扫描完成，尝试加载了 {count} 个模块。")