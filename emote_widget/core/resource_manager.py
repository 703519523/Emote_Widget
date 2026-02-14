"""
EmoteWidget 资源管理模块。

本模块提供了一个集中式的资源生命周期管理器 `ResourceManager`，用于处理
SDK 运行时产生的各种资源（如附属窗口、后台线程、回调函数等）的清理工作。

设计背景 (Design Context):
    在 GUI 编程中，组件的生命周期往往比较复杂。特别是当 SDK 内部持有了用户创建的
    对象引用，或者用户持有了 SDK 内部对象的引用时，很容易形成“循环引用 (Circular Reference)”。
    如果不小心处理，会导致对象无法被 Python 的垃圾回收器 (GC) 及时回收，进而引发内存泄漏。
    
    本模块通过大量使用 `weakref` (弱引用) 技术，确保 SDK 在管理资源的同时，
    不会强行延长对象的生命周期，从而规避了内存泄漏风险。
"""

import weakref
from typing import Protocol, Callable, Union, Any, List, TypeVar, Optional, cast
from emote_widget.utils.logger import resource_logger as logger

# 定义清理回调函数的类型别名
CleanupCallback = Callable[[], Any]
T = TypeVar('T', bound=CleanupCallback)

class WindowProtocol(Protocol):
    """
    [协议] 定义可被资源管理器管理的窗口对象接口。
    
    任何实现了 `close()` 方法的对象都可以被注册为附属窗口。
    这利用了 Python 的鸭子类型 (Duck Typing) 特性，兼容 Qt 的 QWidget、QWindow，
    甚至其他 UI 框架的窗口对象。
    """
    def close(self) -> Any:
        """
        请求关闭窗口。
        
        Returns:
            Any: 返回值类型不限（通常是 bool），资源管理器不关心返回值。
        """
        ...


class ResourceManager:
    """
    [资源管理器] 负责统一管理 SDK 资源的生命周期。

    核心职责:
        1. **附属窗口管理**: 自动追踪并关闭如“调试监视器”之类的辅助窗口。
        2. **清理任务调度**: 在主组件销毁时，按逆序执行注册的清理回调（如停止线程）。
        3. **防止内存泄漏**: 内部仅持有受管对象的“弱引用”，不干扰 GC 的引用计数。

    Internal Logic (Weak References):
        为了打破潜在的引用循环（例如：Widget -> Controller -> CleanupTask -> Widget），
        本类在存储清理回调时，会智能识别“绑定方法 (Bound Method)”。
        
        如果直接存储 `obj.method`，Python 会创建一个强引用指向 `obj`。
        本类使用 `weakref.WeakMethod` 来包装这些方法，这样 `obj` 就可以在
        不被资源管理器“抓住”的情况下正常销毁。
    """
    
    def __init__(self) -> None:
        """初始化资源管理器。"""
        
        # 使用 WeakSet 存储窗口引用
        # 特性：当窗口对象在外部被销毁（引用计数归零）时，它会自动从这个集合中消失。
        # 这避免了资源管理器持有已销毁对象的“悬空指针”或阻碍对象销毁。
        self._widgets: weakref.WeakSet[WindowProtocol] = weakref.WeakSet()
        
        # 存储清理任务列表
        # 列表元素可能是弱引用封装器，也可能是普通函数。
        self._cleanup_tasks: List[Union[weakref.WeakMethod[CleanupCallback], CleanupCallback]] = []

    def register_window(self, widget: WindowProtocol) -> None:
        """
        注册一个附属窗口 (如监视器、设置面板)。
        
        当调用 `shutdown()` 时，所有在此注册且尚未被销毁的窗口都会收到 `close()` 调用。
        
        Args:
            widget (WindowProtocol): 实现了 close 方法的窗口对象。
        """
        if widget:
            self._widgets.add(widget)

    def register_cleanup_task(self, callback: CleanupCallback) -> None:
        """
        注册一个清理回调函数。
        
        Args:
            callback (Callable): 无参数的可调用对象。通常是 `controller.cleanup`。

        Technical Detail (WeakMethod):
            此方法会检查 `callback` 是否是一个实例的绑定方法 (Bound Method)。
            
            - **如果是绑定方法** (如 `self.controller.cleanup`):
              它隐式包含了对 `self.controller` 的强引用。为了防止循环引用
              (ResourceManager -> callback -> Controller -> ResourceManager)，
              我们使用 `weakref.WeakMethod` 对其进行封装。
              
            - **如果是普通函数** (如 `def my_cleanup()`):
              直接存储，因为普通函数通常不持有状态对象的引用，造成泄漏的风险较小。
        """
        if not callable(callback):
            return

        # 检查是否为绑定方法 (Bound Method)
        # 绑定方法会有 __self__ 属性指向实例，__func__ 指向函数体
        if hasattr(callback, '__self__') and hasattr(callback, '__func__'):
            # 使用 WeakMethod 包装，避免强引用导致 Controller 无法释放
            self._cleanup_tasks.append(weakref.WeakMethod(callback)) # type: ignore
        else:
            # 普通函数或 lambda，直接存储
            self._cleanup_tasks.append(callback)

    def shutdown(self) -> None:
        """
        执行所有注册的清理工作，释放资源。
        通常在主窗口的 `closeEvent` 或应用退出时调用。
        """
        logger.info("ResourceManager: 开始执行资源清理流程...")

        # 1. 关闭所有附属窗口
        # 由于使用 WeakSet，我们遍历的都是当前还“活着”的窗口
        for w in self._widgets:
            try:
                # 双重检查：确保对象仍有效且有关闭方法
                if hasattr(w, 'close'):
                    w.close()
            except RuntimeError:
                # PySide/Qt 对象可能已被 C++ 侧删除 (wrapped C/C++ object has been deleted)
                # 这种情况下 Python 包装器还在，但内部指针已失效，忽略即可。
                pass
            except Exception as e:
                logger.error(f"关闭窗口资源失败: {e}")
        
        # 2. 执行清理回调 (按注册顺序的逆序执行)
        # 后注册的任务通常依赖先注册的任务，所以先清理后注册的 (LIFO)。
        for task_ref in reversed(self._cleanup_tasks):
            try:
                func: Optional[CleanupCallback] = None
                
                # 解包弱引用
                if isinstance(task_ref, weakref.WeakMethod):
                    # 如果对象还存在，WeakMethod() 会返回绑定方法；否则返回 None
                    func = cast(Optional[CleanupCallback], task_ref())
                elif callable(task_ref):
                    func = task_ref
                
                if func is not None:
                    func()
                else:
                    logger.debug("跳过已失效的清理任务 (对象已被回收)。")
                    
            except Exception as e:
                logger.error(f"执行清理任务失败: {e}")
                
        self._cleanup_tasks.clear()
        logger.info("ResourceManager: 清理完成。")
