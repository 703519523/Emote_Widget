from typing import Any, Callable, List, TYPE_CHECKING, cast
import logging

if TYPE_CHECKING:
    from emote_widget.core.controller import EmoteController

logger = logging.getLogger(__name__)

class ControllerProxy:
    """
    [安全代理]
    
    作用：
    1. 拦截对私有属性（_开头）的访问。
    2. 仅暴露公共业务 API 给用户。
    3. 配合 Type Hinting 实现安全的 IDE 补全体验。
    """
    _impl: 'EmoteController'
    
    def __init__(self, controller: 'EmoteController'):
        # 保存真实控制器的引用
        # 使用 super().__setattr__ 防止递归调用自身的 __setattr__
        super().__setattr__('_impl', controller)

    def __getattr__(self, name: str) -> Any:
        """当用户访问 proxy.xxx 时触发"""
        
        # 1. 禁止访问下划线开头的私有成员
        if name.startswith('_'):
            raise AttributeError(f"Access denied: '{name}' is private.")

        # 2. 获取真实属性
        if not hasattr(self._impl, name):
            raise AttributeError(f"'{type(self._impl).__name__}' has no attribute '{name}'")
            
        attr = getattr(self._impl, name)
        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        """禁止外部修改 Controller 的属性 (转发设置)"""
        setattr(self._impl, name, value)

    def __dir__(self) -> List[str]:
        """定制 dir() 结果，过滤掉私有属性"""
        all_attrs = dir(self._impl)
        return [x for x in all_attrs if not x.startswith('_')]


class PoisonPillProxy:
    """
    [故障隔离代理]
    
    当插件初始化失败时，系统将分配此代理给插件。
    它会静默拦截所有方法调用并记录警告，防止故障插件破坏系统稳定性。
    """
    def __init__(self, plugin_name: str):
        self._plugin_name = plugin_name

    def __getattr__(self, name: str) -> Any:
        # 允许 Python 魔术方法
        if name.startswith('__'):
            raise AttributeError(name)
            
        def dummy_sink(*args: Any, **kwargs: Any) -> None:
            logger.warning(f"[Security/Isolation] Plugin '{self._plugin_name}' attempted to call 'controller.{name}' after failure. Action blocked.")
            return None
        return dummy_sink

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_plugin_name":
            super().__setattr__(name, value)
            return
        logger.warning(f"[Security/Isolation] Plugin '{self._plugin_name}' attempted to set 'controller.{name}' after failure. Action blocked.")


class SandboxProxy:
    """
    [沙盒事务代理]
    
    用于插件初始化阶段。它不会立即执行操作，而是将所有方法调用
    和信号连接存入队列。只有当 initialize() 成功返回后，
    才会通过 commit() 方法应用这些操作。
    """
    def __init__(self, controller: 'EmoteController'):
        self._real_controller = controller
        self._call_queue: List[Callable[[], None]] = []
        self._signal_queue: List[Callable[[], None]] = []
    
    def commit(self) -> None:
        """提交事务：按顺序回放暂存的指令（先连接信号，后调用方法）。"""
        # 1. 回放信号连接
        for action in self._signal_queue:
            try:
                action()
            except Exception as e:
                logger.error(f"Sandbox commit error (signal): {e}")
        
        # 2. 回放方法调用
        for action in self._call_queue:
            try:
                action()
            except Exception as e:
                logger.error(f"Sandbox commit error (method): {e}")
                
        self._signal_queue.clear()
        self._call_queue.clear()

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(f"Access denied: '{name}' is private.")
            
        if not hasattr(self._real_controller, name):
            raise AttributeError(f"'{type(self._real_controller).__name__}' has no attribute '{name}'")
            
        real_attr = getattr(self._real_controller, name)
        
        # 识别信号 (Duck typing: 检查是否有 connect 方法)
        if hasattr(real_attr, 'connect') and callable(real_attr.connect):
            return self._SignalInterceptor(self, real_attr)
            
        # 识别方法
        if callable(real_attr):
            return self._MethodInterceptor(self, real_attr)
            
        # 属性访问 (允许读取)
        return real_attr

    class _SignalInterceptor:
        def __init__(self, proxy: 'SandboxProxy', real_signal: Any):
            self._proxy = proxy
            self._real_signal = real_signal
            
        def connect(self, *args: Any, **kwargs: Any) -> None:
            def deferred() -> None:
                self._real_signal.connect(*args, **kwargs)
            self._proxy._signal_queue.append(deferred)

    class _MethodInterceptor:
        def __init__(self, proxy: 'SandboxProxy', real_method: Callable[..., Any]):
            self._proxy = proxy
            self._real_method = real_method
            
        def __call__(self, *args: Any, **kwargs: Any) -> None:
            def deferred() -> None:
                self._real_method(*args, **kwargs)
            self._proxy._call_queue.append(deferred)
            return None
