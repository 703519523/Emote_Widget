import weakref
from typing import Protocol, Callable, Union, Any, List, TypeVar, Optional, cast
from emote_widget.utils.logger import resource_logger as logger

CleanupCallback = Callable[[], Any]
T = TypeVar('T', bound=CleanupCallback)

class WindowProtocol(Protocol):
    """定义窗口对象需要实现的接口"""
    def close(self) -> None:
        """关闭窗口的方法"""
        ...


class ResourceManager:
    """
    资源生命周期管理器。
    负责统一管理附属窗口的关闭和后台任务的清理，避免在 closeEvent 中硬编码。
    """
    def __init__(self):
        # 使用 WeakSet 存储窗口引用
        # 如果窗口已经被用户手动关闭并销毁了，这里会自动移除，不会导致访问已删除对象的崩溃
        self._widgets: weakref.WeakSet[WindowProtocol] = weakref.WeakSet()
        self._cleanup_tasks: List[Union[weakref.WeakMethod[CleanupCallback], CleanupCallback]] = []

    def register_window(self, widget: WindowProtocol) -> None:
        """注册一个附属窗口 (如监视器、设置面板)"""
        if widget:
            self._widgets.add(widget)

    def register_cleanup_task(self, callback: CleanupCallback) -> None:
        """注册一个清理函数 (如 controller.cleanup)"""
        if not callable(callback):
            return

        # 如果是绑定方法 (例如 self.controller.cleanup)，使用 WeakMethod
        if hasattr(callback, '__self__') and hasattr(callback, '__func__'):
            self._cleanup_tasks.append(weakref.WeakMethod(callback))
        else:
            # 普通函数直接存储 (或者也可以用 weakref.ref)
            self._cleanup_tasks.append(callback)

    def shutdown(self) -> None:
        """执行所有清理工作"""
        logger.info("开始清理资源...")

        # 1. 关闭所有附属窗口
        for w in self._widgets:
            try:
                # 检查是否有关闭方法
                if hasattr(w, 'close'):
                    w.close()
            except RuntimeError:
                # 对象可能已被 C++ 侧删除
                pass
            except Exception as e:
                logger.error(f"关闭窗口资源失败: {e}")
        
        # 2. 执行清理回调
        for task_ref in reversed(self._cleanup_tasks):
            try:
                # 如果是 WeakMethod/ref，需要先解引用
                if isinstance(task_ref, (weakref.WeakMethod, weakref.ref)):
                    func = cast(Optional[CleanupCallback], task_ref())
                    if func is not None:
                        func()
                elif callable(task_ref):
                    task_ref()
            except Exception as e:
                logger.error(f"执行清理任务失败: {e}")
                
        self._cleanup_tasks.clear()
        logger.info("清理完成。")