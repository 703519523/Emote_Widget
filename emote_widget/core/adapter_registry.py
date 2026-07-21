import importlib
import pkgutil
import os
import sys
from typing import Type, Dict, Callable, TypeVar
from .adapter_interface import IViewAdapter

from emote_widget.utils.logger import adapter_logger as logger

# [新增] 定义一个泛型 T，它必须是 IViewAdapter 的子类(Type)
# 这样不仅解决了 Pylance 报错，还能保留被装饰类的具体类型信息
T = TypeVar('T', bound=Type[IViewAdapter])

class AdapterRegistry:
    """
    视图适配器注册表。
    用于管理和查找不同的 UI 适配器 (如 QtAdapter, TkAdapter, CEFAdapter)。
    """
    _adapters: Dict[str, Type[IViewAdapter]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[T], T]:
        """
        装饰器：注册一个 Adapter 类。
        用法:
            @AdapterRegistry.register("my_custom_adapter")
            class MyAdapter(IViewAdapter): ...
        """
        def decorator(adapter_cls: T) -> T:
            # 1. 安全检查：确保注册的是类，且继承自接口
            # 注意：这里的 isinstance 检查对于静态类型检查器来说是多余的(因为 T 已经约束了)，
            # 但对于运行时防御仍然很有必要。
            if not isinstance(adapter_cls, type) or not issubclass(adapter_cls, IViewAdapter): # pyright: ignore[reportUnnecessaryIsInstance]
                logger.warning(f"注册失败: '{name}' 对应的类必须继承自 IViewAdapter。")
                return adapter_cls
            
            # 2. 注册
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
        安全地扫描指定目录下的 Python 模块，尝试加载其中的 Adapter。
        """
        if not os.path.isdir(plugin_dir):
            return

        logger.info(f"正在扫描适配器插件目录: {plugin_dir}")
        
        # 使用 pkgutil 扫描
        count = 0
        # iter_modules 返回 (finder, name, ispkg)，我们只关心 name
        for _, name, _ in pkgutil.iter_modules([plugin_dir]):
            try:
                # 动态加载模块
                # 方法 A: 简单加载 (仍然需要 sys.path 支持模块内互相引用)
                if plugin_dir not in sys.path:
                    sys.path.append(plugin_dir) # append 比 insert(0) 安全
                
                importlib.import_module(name)
                
                # 注意：import_module 会自动触发模块内的 @register 装饰器
                count += 1
                
            except Exception as e:
                logger.error(f"加载适配器插件 '{name}' 失败: {e}", exc_info=True)
        
        # 清理路径 (保持环境纯净)
        if plugin_dir in sys.path:
            sys.path.remove(plugin_dir)

        if count > 0:
            logger.info(f"扫描完成，尝试导入了 {count} 个模块。")