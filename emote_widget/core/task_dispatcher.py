"""
EmoteWidget 任务调度模块。

本模块提供了一个集中的异步任务分发器 `EmoteTaskDispatcher`，
旨在统一管理 SDK 内部的耗时操作，如音频分析、网络请求、文件 I/O 等。

设计目标 (Design Goals):
    1. **避免卡顿**: 所有的计算密集型或 I/O 密集型任务都应通过 Dispatcher 分发到后台线程池执行，
       确保主 UI 线程（无论是 Qt 还是 QML）始终保持流畅。
    2. **资源隔离**: 通过分离 I/O 线程池和计算线程池，防止大量网络请求阻塞了关键的计算任务。
    3. **防抖与节流**: 提供 `TaskThrottle` 机制，防止短时间内的高频调用（如鼠标移动事件）导致任务堆积。
    4. **信号驱动**: 利用 Qt 的信号槽机制，在任务完成时安全地将结果传回主线程。
"""

import time
import threading
from enum import Enum, auto
from typing import Callable, Dict, Any, Optional, Set
from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, Slot

from emote_widget.utils.logger import emote_widget_logger as logger
from emote_widget.utils.logger import worker_logger

class TaskType(Enum):
    """
    任务类型枚举。
    
    Attributes:
        IO_BOUND: I/O 密集型任务（如文件读写、网络请求）。通常不受全局解释器锁 (GIL) 影响，可以高并发。
        COMPUTE_BOUND: 计算密集型任务（如图像处理、音频分析）。受 CPU 核心数限制，应避免过高并发。
    """
    IO_BOUND = auto()
    COMPUTE_BOUND = auto()

class TaskThrottle:
    """
    [节流器] 简单的请求节流机制。
    
    用途:
        用于限制特定 key 的任务提交频率。
        例如，防止鼠标移动事件频繁触发昂贵的寻路计算。
    """
    def __init__(self, limit_ms: int = 500) -> None:
        """
        初始化节流器。
        
        Args:
            limit_ms (int): 两次任务之间的最小间隔时间（毫秒）。
        """
        self.limit_ms: int = limit_ms
        self.last_requests: Dict[str, float] = {}
        self._lock: threading.Lock = threading.Lock()

    def should_proceed(self, key: str) -> bool:
        """
        检查是否允许执行当前任务。
        
        Args:
            key (str): 任务的唯一标识符（节流键）。
            
        Returns:
            bool: True 表示可以通过（并更新时间戳），False 表示应被拦截。
        """
        with self._lock:
            now = time.time() * 1000
            last = self.last_requests.get(key, 0.0)
            if now - last < self.limit_ms:
                return False
            self.last_requests[key] = now
            return True

class WorkerSignals(QObject):
    """
    [Worker 信号集] 定义 Worker 线程发出的信号。
    
    必须继承自 QObject 才能定义 Signal。
    QRunnable 本身不是 QObject，所以需要一个独立的信号持有者。
    """
    finished = Signal()
    """任务结束信号 (无论成功或失败都会触发)。"""
    
    error = Signal(Exception)
    """任务发生异常时的信号。参数: (exception_object)"""
    
    result = Signal(object)
    """任务成功完成时的结果信号。参数: (return_value)"""

class Worker(QRunnable):
    """
    [通用工作单元] 包装一个 Python 函数以在 QThreadPool 中运行。
    
    特性:
        - 自动处理异常捕获和信号发射。
        - 兼容 Qt 的线程模型。
        - 拥有独立的 logger 实例。
    """
    def __init__(self, task_name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """
        初始化 Worker。
        
        Args:
            task_name (str): 任务名称，用于生成 logger。
            fn (Callable): 要执行的目标函数。
            *args, **kwargs: 传递给 fn 的参数。
        """
        super().__init__()
        self.task_name = task_name
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # 为每个 Worker 分配独立的 Logger (实际上是 worker_logger 的子节点)
        self.logger = worker_logger.getChild(task_name)

    @Slot()
    def run(self) -> None:
        """
        [线程入口] 执行任务逻辑。
        此方法由 QThreadPool 的线程池自动调用。
        """
        try:
            self.logger.debug(f"Task started: {self.task_name}")
            result = self.fn(*self.args, **self.kwargs)
            self.logger.debug(f"Task completed: {self.task_name}")
            self.signals.result.emit(result)
        except Exception as e:
            self.logger.error(f"Task failed: {e}", exc_info=True)
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()

class EmoteTaskDispatcher(QObject):
    """
    [中央任务调度器] 负责管理 SDK 内的所有异步操作。
    
    实现模式:
        单例模式 (Singleton): 确保全局只有一个调度器实例，统一管理线程池资源。
        
    核心组件:
        - **IO Pool**: 用于高并发 I/O 操作 (默认 8 线程)。
        - **Compute Pool**: 用于序列化计算操作 (默认 1 线程)，避免抢占 UI 渲染资源。
        - **Throttle**: 内置节流器。
    """
    _instance: Optional['EmoteTaskDispatcher'] = None
    
    task_started = Signal(str)
    """任务开始信号。参数: (task_name)"""
    
    task_finished = Signal(str)
    """任务结束信号。参数: (task_name)"""

    def __new__(cls, *args: Any, **kwargs: Any) -> 'EmoteTaskDispatcher':
        if cls._instance is None:
            cls._instance = super(EmoteTaskDispatcher, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 单例初始化保护
        if hasattr(self, '_initialized') and self._initialized:
            return
        super().__init__()
        self._initialized = True
        
        self.io_pool = QThreadPool()
        # I/O 密集型任务可以使用较多的线程
        self.io_pool.setMaxThreadCount(8)
        
        self.compute_pool = QThreadPool()
        # 计算密集型任务建议串行执行，避免瞬间 CPU 占用过高导致掉帧
        self.compute_pool.setMaxThreadCount(1) 
        
        self.throttle = TaskThrottle()
        
        # 强引用集合：防止 Worker 在执行期间被 Python GC 回收导致信号断开
        # 这是一个常见的 PySide/PyQt 陷阱。
        self._active_workers: Set[Worker] = set()

    def dispatch(self, 
                 task_name: str, 
                 task_func: Callable[..., Any], 
                 on_success: Optional[Callable[[Any], None]] = None, 
                 on_error: Optional[Callable[[Exception], None]] = None, 
                 task_type: TaskType = TaskType.IO_BOUND, 
                 priority: int = 0,
                 throttle_key: Optional[str] = None,
                 *args: Any,
                 **kwargs: Any) -> None:
        """
        分发一个异步任务。
        
        Args:
            task_name (str): 任务名称 (用于日志和调试)。
            task_func (Callable): 要执行的函数。
            on_success (Callable, optional): 成功回调函数 `(result) -> None`。将在主线程执行。
            on_error (Callable, optional): 失败回调函数 `(exception) -> None`。将在主线程执行。
            task_type (TaskType): 任务类型 (IO_BOUND 或 COMPUTE_BOUND)。决定使用哪个线程池。
            priority (int): 任务优先级。数值越高越优先执行。
            throttle_key (str, optional): 节流键。如果指定，将对此键应用节流策略。
            *args, **kwargs: 传递给 task_func 的参数。
        """
        
        if throttle_key and not self.throttle.should_proceed(throttle_key):
            logger.debug(f"Task '{task_name}' throttled (key: {throttle_key}).")
            return

        worker = Worker(task_name, task_func, *args, **kwargs)
        # 设置 AutoDelete=True 让 Qt 在 run() 结束后自动 delete C++ 对象
        # 但我们仍然需要在 Python 侧保持引用，直到信号发射完毕
        worker.setAutoDelete(True) 
        
        if on_success:
            worker.signals.result.connect(on_success)
        
        if on_error:
            worker.signals.error.connect(on_error)
            
        # 内部闭包：任务完成后的清理工作
        def cleanup() -> None:
            self.task_finished.emit(task_name)
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(cleanup)
        
        # 加入活跃集合，防止 GC
        self._active_workers.add(worker)
        self.task_started.emit(task_name)
        
        if task_type == TaskType.IO_BOUND:
            self.io_pool.start(worker, priority)
        else:
            self.compute_pool.start(worker, priority)

    def cleanup(self) -> None:
        """
        清理资源。
        等待所有线程完成 (最多等待 1000ms)，防止程序退出时崩溃。
        """
        logger.info("TaskDispatcher: 等待后台任务结束...")
        self.io_pool.waitForDone(1000)
        self.compute_pool.waitForDone(1000)
