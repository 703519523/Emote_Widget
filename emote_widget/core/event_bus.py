"""
全局事件总线系统。

用于发布生命周期事件和业务通知，插件可以订阅这些事件。
事件是单向的、广播式的，不改变数据流。

示例事件：
- "model.loaded" - 模型加载完成
- "player.ready" - 播放器就绪
- "animation.play" - 开始播放动画
- "parameter.changed" - 参数值改变
"""

from typing import Callable, Dict, List, Any, Optional
from PySide6.QtCore import QObject, Signal
import logging

logger = logging.getLogger("EmoteWidget.EventBus")


class EventBus(QObject):
    """
    全局事件总线。
    
    采用单例模式，全局唯一实例。
    支持事件订阅、取消订阅和触发。
    """
    
    _instance: Optional['EventBus'] = None
    
    # Qt Signal 用于跨线程安全传递事件
    _event_signal = Signal(str, object)
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        super().__init__()
        self._listeners: Dict[str, List[Callable]] = {}
        self._initialized = True
        
        # 连接内部 Signal 到分发逻辑
        self._event_signal.connect(self._dispatch_event)
    
    def on(self, event: str, callback: Callable[[Any], None]) -> None:
        """
        订阅事件。
        
        Args:
            event: 事件名称（如 "model.loaded"）
            callback: 回调函数，接收事件数据
        
        示例:
            >>> event_bus.on("model.loaded", lambda data: print(f"Model: {data['path']}"))
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        logger.debug(f"订阅事件: {event} (共 {len(self._listeners[event])} 个监听器)")
    
    def emit(self, event: str, data: Any = None) -> None:
        """
        触发事件。
        
        Args:
            event: 事件名称
            data: 事件数据（可选）
        
        示例:
            >>> event_bus.emit("model.loaded", {"path": "chara.psb", "size": 1024})
        """
        logger.debug(f"触发事件: {event} (数据: {type(data).__name__ if data else 'None'})")
        # 通过 Signal 触发，确保线程安全
        self._event_signal.emit(event, data)
    
    def _dispatch_event(self, event: str, data: Any) -> None:
        """内部分发逻辑，在主线程执行"""
        for callback in self._listeners.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"事件处理器执行失败: {event}, 错误: {e}", exc_info=True)
    
    def off(self, event: str, callback: Callable) -> None:
        """
        取消订阅事件。
        
        Args:
            event: 事件名称
            callback: 要移除的回调函数
        """
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
                logger.debug(f"取消订阅: {event}")
            except ValueError:
                logger.warning(f"尝试移除不存在的监听器: {event}")
    
    def clear(self, event: Optional[str] = None) -> None:
        """
        清空监听器。
        
        Args:
            event: 如果指定，只清空该事件的监听器；否则清空所有
        """
        if event:
            self._listeners.pop(event, None)
        else:
            self._listeners.clear()


# 全局单例
event_bus = EventBus()
