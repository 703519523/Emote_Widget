"""
EmoteWidget QML 适配器模块。

本模块实现了 `IViewAdapter` 接口的 QML 版本。
由于 PySide6 的 QML 集成 (Shiboken) 与传统的 C++ QWidget 有很大差异，
本模块需要处理更复杂的跨线程调用和对象生命周期管理。

关键差异：
    1. **延迟绑定**: QML 组件初始化时 Adapter 可能还没关联到具体的 View。
    2. **对象销毁**: QML 对象的生命周期由 QML 引擎管理，Python 端必须小心处理野指针。
    3. **JS 执行**: 必须通过 `QMetaObject.invokeMethod` 动态调用 QML 侧的 `runJavaScript`。
"""

from typing import Optional, cast, List, Any
from PySide6.QtCore import QObject, Qt, QRect
from PySide6.QtGui import QRegion
from PySide6.QtQuick import QQuickItem

# 引入接口和日志
from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.utils.logger import adapter_logger as logger
class QmlAdapter(IViewAdapter):
    """
    [QML 适配器] 实现 IViewAdapter 接口，桥接 Controller 与 QML WebEngineView。
    
    设计难点:
        QML 的 `WebEngineView` 不是 Python 可直接导入的类 (在 PySide6 中没有直接对应的 Python Wrapper)。
        因此，我们必须将其作为通用的 `QObject` 或 `QQuickItem` 来操作，
        所有方法调用（如 runJavaScript）都需要通过 Qt 元对象系统动态反射。
    """
    
    def __init__(self, qml_item: Optional[QObject] = None) -> None:
        """
        初始化适配器。
        
        Args:
            qml_item (QObject, optional): 关联的 QML WebEngineView 对象。
                                        通常初始为 None，稍后通过 `set_view` 绑定。
        """
        self._item = qml_item
        self._bridge_object: Optional[QObject] = None
        self._bridge_name: Optional[str] = None
        
        if self._item:
            self._init_view()

    def set_view(self, qml_item: QObject) -> None:
        """
        [生命周期] 绑定或更新关联的 QML Item。
        
        当 QML 组件实例化完成 (`Component.onCompleted`) 时，应调用此方法
        将自身实例传递给 Adapter。
        """
        if not qml_item:
            logger.warning("QmlAdapter: set_view received None")
            return
        
        self._item = qml_item
        self._init_view()
        logger.info(f"QmlAdapter: View 已绑定: {self._item}")

    def _init_view(self) -> None:
        """内部初始化逻辑：设置属性、连接销毁信号。"""
        if not self._item: return

        # 设置默认背景透明
        self._item.setProperty("backgroundColor", "transparent")
        
        # [关键] 监听对象销毁信号
        # QML 对象可能随时被引擎回收（例如切换页面），必须防止 Python 持有悬空指针
        if hasattr(self._item, 'destroyed'):
            self._item.destroyed.connect(self._on_item_destroyed)

    def _on_item_destroyed(self) -> None:
        """[生命周期] QML 对象销毁时的回调。"""
        logger.warning("QmlAdapter: 关联的 QML Item 已销毁，正在断开连接...")
        self._item = None

    @property
    def bridge_object(self) -> Optional[QObject]:
        """[属性] 获取已注册的 Python Bridge 对象。"""
        return self._bridge_object

    def run_javascript(self, script: str) -> None:
        """
        [实现接口] 在 QML WebEngineView 中执行 JavaScript。
        
        单一策略：直接调用 QML Wrapper 的 runJavaScript(script, None)。
        说明：
        - 避免 Python 回调函数转换为 QJSValue 导致的 Shiboken 警告。
        - 明确且可控，失败时打印完整错误日志。
        """
        if not self._item:
            logger.debug("QML Adapter: View尚未绑定，忽略JS执行。")
            return

        if not hasattr(self._item, "runJavaScript"):
            logger.error("QML Adapter: 目标 QML Item 不支持 runJavaScript 方法。")
            return
        try:
            cast(Any, self._item).runJavaScript(script, None)
        except Exception as e:
            logger.error(f"QML Adapter: JS执行失败: {e}")
            logger.error(f"脚本内容片段: {script[:200]}...")

    def register_python_bridge(self, bridge_obj: QObject, name: str) -> None:
        """
        [实现接口] 注册 Python Bridge 对象。
        
        注意：QML 的 WebChannel 注册机制与 C++ 不同。
        这里我们主要是缓存 Bridge 对象，实际的注册过程通常由 QML 侧的
        `EmoteWidgetQml.registerWebChannel` 辅助完成。
        """
        bridge_obj.setObjectName(name)
        
        # 保存引用，防止被 GC
        self._bridge_object = bridge_obj
        self._bridge_name = name
        logger.info(f"QML Adapter: Bridge 对象已注册: name='{name}', id={id(bridge_obj)}")

    def set_window_transparent(self, transparent: bool) -> None:
        """
        [实现接口] 设置 QML 顶层窗口的透明穿透属性。
        
        需要获取 `QQuickItem.window()` 才能操作顶层窗口。
        """
        if not self._item:
            return

        # 强转为 QQuickItem 以获取 window() 方法
        quick_item = cast(QQuickItem, self._item)
        window = quick_item.window()
        
        if not window:
            logger.warning("QML Adapter: 无法获取顶层窗口，透明设置失败。")
            return

        if transparent:
            # 透明背景 + 无边框
            window.setColor(Qt.GlobalColor.transparent)
            flags = window.flags() | Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)
        else:
            # 白色背景 + 有边框
            window.setColor(Qt.GlobalColor.white)
            flags = window.flags() & ~Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)

    def set_mouse_pass_through(self, enable: bool) -> None:
        """[实现接口] 暂未实现。QML 的全窗穿透通常需要在 Window 声明中设置。"""
        if enable:
            logger.warning("QML Adapter: set_mouse_pass_through 尚未完全实现，请在 QML 侧配合处理。")
    
    def set_render_mask(self, rects: Optional[List[List[int]]]) -> None:
        """
        [实现接口] 设置 QML 窗口的异形遮罩。
        
        原理与 Qt Adapter 类似，都是操作顶层 Window 的 Mask。
        """
        if not self._item:
            return
        
        quick_item = cast(QQuickItem, self._item)
        window = quick_item.window()
        if not window:
            return

        if not rects:
            window.setMask(QRegion())
            return
            
        region = QRegion()
        for x, y, w, h in rects:
            # 同样向外膨胀2像素
            region += QRect(int(x), int(y), int(w), int(h)).adjusted(-2, -2, 2, 2)
        
        window.setMask(region)

    def get_ui_object(self) -> Optional[QObject]:
        """[实现接口] 返回关联的 QML Item。"""
        return self._item
