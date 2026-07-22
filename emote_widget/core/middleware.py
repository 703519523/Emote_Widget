"""
中间件系统。

用于在数据处理流水线中注入自定义逻辑，插件可以检查、修改或替换数据。
中间件按注册顺序依次执行，每个中间件决定是否调用下一个。

典型用途：
- PSB 解密
- 数据格式转换
- 参数验证
- 资源预处理
"""

from typing import Callable, Any, Dict, List
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("EmoteWidget.Middleware")


class Middleware(ABC):
    """
    中间件基类。
    
    所有中间件必须继承此类并实现 process 方法。
    """
    
    @abstractmethod
    def process(self, data: Any, next: Callable[[Any], Any]) -> Any:
        """
        处理数据。
        
        Args:
            data: 输入数据（可以是任意类型）
            next: 调用下一个中间件的函数
        
        Returns:
            处理后的数据
        
        注意：
            - 必须调用 next(data) 才能继续流水线
            - 可以修改 data 后再调用 next
            - 可以直接返回结果而不调用 next（中断流水线）
        
        示例:
            >>> def process(self, data, next):
            >>>     data["processed"] = True  # 修改数据
            >>>     return next(data)         # 继续流水线
        """
        pass


class MiddlewareChain:
    """
    中间件链。
    
    管理一组中间件的顺序执行。
    """
    
    def __init__(self, name: str):
        self.name = name
        self._middlewares: List[Middleware] = []
    
    def use(self, middleware: Middleware) -> None:
        """
        注册中间件。
        
        Args:
            middleware: 中间件实例
        """
        self._middlewares.append(middleware)
        logger.debug(f"[{self.name}] 注册中间件: {middleware.__class__.__name__} (共 {len(self._middlewares)} 个)")
    
    def execute(self, data: Any) -> Any:
        """
        执行中间件链。
        
        Args:
            data: 初始数据
        
        Returns:
            经过所有中间件处理后的数据
        """
        logger.debug(f"[{self.name}] 开始执行中间件链 (共 {len(self._middlewares)} 个中间件)")
        
        def create_next(index: int) -> Callable:
            if index >= len(self._middlewares):
                # 最后一个中间件，直接返回数据
                return lambda d: d
            
            def next_func(d: Any) -> Any:
                middleware = self._middlewares[index]
                try:
                    result = middleware.process(d, create_next(index + 1))
                    logger.debug(f"[{self.name}] 中间件 {middleware.__class__.__name__} 执行成功")
                    return result
                except Exception as e:
                    logger.error(f"[{self.name}] 中间件 {middleware.__class__.__name__} 执行失败: {e}", exc_info=True)
                    raise
            
            return next_func
        
        return create_next(0)(data)
    
    def clear(self) -> None:
        """清空所有中间件"""
        self._middlewares.clear()
        logger.debug(f"[{self.name}] 清空中间件链")


class MiddlewareManager:
    """
    全局中间件管理器。
    
    管理多个命名的中间件链，插件可以向指定链注册中间件。
    """
    
    _chains: Dict[str, MiddlewareChain] = {}
    
    @classmethod
    def get_chain(cls, name: str) -> MiddlewareChain:
        """
        获取或创建命名的中间件链。
        
        Args:
            name: 中间件链名称（如 "psb.normalize", "parameter.transform"）
        
        Returns:
            中间件链实例
        """
        if name not in cls._chains:
            cls._chains[name] = MiddlewareChain(name)
            logger.info(f"创建中间件链: {name}")
        return cls._chains[name]
    
    @classmethod
    def clear_chain(cls, name: str) -> None:
        """清空指定的中间件链"""
        if name in cls._chains:
            cls._chains[name].clear()
    
    @classmethod
    def clear_all(cls) -> None:
        """清空所有中间件链"""
        for chain in cls._chains.values():
            chain.clear()
        cls._chains.clear()
