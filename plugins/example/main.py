"""插件系统完整示例。

这个插件只演示公开扩展点，不修改 core，也不依赖插件外部运行时。
猴子补丁（运行时替换其他模块/类的方法）虽然可以临时验证想法，
但会破坏模块边界、增加加载顺序和卸载风险，**不建议在正式插件中使用**。
优先使用 Controller 信号、EventBus 和 Middleware。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QWidget

from emote_widget.core.middleware import Middleware
from emote_widget.core.plugin_interface import IEmotePlugin


class ExampleMiddleware(Middleware):
    """仅观察数据流的示例中间件；不改写模型字节。"""

    def process(self, data: Any, next: Any) -> Any:
        return next(data)


class ExamplePlugin(IEmotePlugin):
    """展示生命周期、信号、事件总线、中间件和 Qt UI 的示例插件。"""

    def __init__(self) -> None:
        super().__init__()
        self._middleware: ExampleMiddleware | None = None
        self._last_model: str | None = None
        self._player_ready_connected = False

    def get_name(self) -> str:
        return "example"

    def get_description(self) -> str:
        return "插件系统完整示例：生命周期、Controller 信号、EventBus、Middleware 和 Qt UI"

    def initialize(self) -> None:
        """初始化时只注册资源；失败会由 Controller 隔离。"""
        if self.controller is None:
            self.logger.warning("示例插件尚未注入 controller，跳过初始化")
            return

        # 1. Controller 信号：适合接收强类型的模型生命周期通知。
        self.controller.player_ready.connect(self.on_player_ready)
        self._player_ready_connected = True

        # 2. EventBus：适合跨模块通知；EventBus 只通知，不干预数据流。
        self.events.on("model.load_failed", self.on_model_load_failed)

        # 3. Middleware：需要参与数据流时使用中间件，而不是 EventBus。
        chain = self.middleware.get_chain("example.observe")
        self._middleware = ExampleMiddleware()
        chain.use(self._middleware)

        self.logger.info("示例插件已初始化：信号、EventBus、中间件和 UI 均可用")

    def cleanup(self) -> None:
        """卸载时对所有自己注册的资源逐项撤销。"""
        if self.controller is not None and self._player_ready_connected:
            try:
                self.controller.player_ready.disconnect(self.on_player_ready)
            except (RuntimeError, TypeError):
                pass
            self._player_ready_connected = False

        self.events.off("model.load_failed", self.on_model_load_failed)
        if self._middleware is not None:
            self.middleware.get_chain("example.observe").remove(self._middleware)
            self._middleware = None
        self.logger.info("示例插件已清理")

    def on_player_ready(self, timelines: list[str]) -> None:
        """Controller 信号回调。"""
        self.logger.info("示例插件收到 player_ready：%d 个 timeline", len(timelines))

    def on_model_load_failed(self, payload: dict[str, Any]) -> None:
        """EventBus 回调。"""
        self._last_model = str(payload.get("path", ""))
        self.logger.info("示例插件观察到模型加载失败：%s", self._last_model)

    def get_ui_widget(self) -> QWidget:
        """提供一个最小 Qt UI；QML 模式会由框架代理公开方法。"""
        return QLabel("ExamplePlugin：请通过信号、事件和中间件扩展，不要使用猴子补丁")

    def print_widget_size(self) -> None:
        """展示如何安全读取宿主 UI；controller 未注入时只记录 warning。"""
        if self.controller is None:
            self.logger.warning("示例插件 controller 尚未初始化")
            return
        try:
            ui_obj = self.controller.view_adapter.get_ui_object()
            if hasattr(ui_obj, "width") and hasattr(ui_obj, "height"):
                self.logger.info("宿主 UI 尺寸：%s x %s", ui_obj.width(), ui_obj.height())
            else:
                self.logger.warning("宿主 UI 对象没有 width/height 方法")
        except (AttributeError, RuntimeError) as exc:
            self.logger.warning("读取宿主 UI 失败：%s", exc)