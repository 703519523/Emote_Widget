from typing import Any
import os
from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl


# 引入核心组件
from emote_widget.core.controller import EmoteController
from emote_widget.core.scheme_handler import EmoteSchemeHandler
from emote_widget.core.resource_manager import ResourceManager
from emote_widget.ui.adapters.qml_adapter import QmlAdapter
from emote_widget.utils.logger import emote_widget_logger as logger

class EmoteWidgetQml(QObject):
    """
    [QML Facade] QML 专用的后端逻辑封装类。
    
    它充当 ViewModel 的角色，将 Controller 的功能暴露给 QML 引擎。
    
    使用方式:
    1. 在 Python 端实例化此经类。
    2. 在 QML 加载完成后，找到 WebEngineView 的 Item。
    3. 调用 `bind_to_item(item)` 进行绑定。
    4. (可选) 将此对象注册为 QML ContextProperty，以便在 QML 中直接调用 play() 等方法。
    """

    # --- 信号定义 (暴露给 QML) ---
    # 注意：QML 能够自动处理 Python 的 list 和 dict，所以参数类型保持一致即可
    loadFinished = Signal()
    playerReady = Signal(list, arguments=['timelines']) 
    pluginsLoadFinished = Signal()
    characterClicked = Signal()
    characterHovered = Signal()
    
    def __init__(self, parent: QObject | None = None,plugin_path: str | None = None,config_override: dict[str, Any] | None = None):
        super().__init__(parent)
        
        self.resources: ResourceManager = ResourceManager()
        self._plugin_path = plugin_path
        self._config_override = config_override
        
        self.controller = None
        self.adapter = None
        self._qml_item = None
        
        # 预先初始化 Scheme Handler (这是全局或 Profile 级别的，必须尽早)
        # 注意：QML WebEngine 的 Profile 处理可能在 QML 端定义，这里我们先实例化 Handler
        self._scheme_handler = EmoteSchemeHandler()

    @Slot(QObject)
    def bind_to_item(self, qml_webengine_item: QObject):
        """
        [关键步骤] 将此后端逻辑绑定到一个具体的 QML WebEngineView Item 上。
        """
        if not qml_webengine_item:
            logger.error("EmoteWidgetQml: 传入的 QML Item 为空，绑定失败。")
            return

        self._qml_item = qml_webengine_item
        logger.info(f"EmoteWidgetQml: 正在绑定到 QML Item: {self._qml_item}")

        # 1. 尝试安装 Scheme Handler 到该 Item 的 Profile
        # QML WebEngineView 有一个 'profile' 属性
        try:
            profile = self._qml_item.property("profile")
            if profile:
                profile.installUrlSchemeHandler(b"emote", self._scheme_handler)
            else:
                # 如果 QML 没指定 profile，通常使用默认 profile，这里尝试获取默认的
                # 但 PySide6 获取默认 Quick Profile 比较麻烦，通常建议 QML 端显式指定
                logger.warning("EmoteWidgetQml: 未能获取 QML Item 的 profile 属性，SchemeHandler 可能未生效。")
        except Exception as e:
            logger.warning(f"EmoteWidgetQml: 安装 SchemeHandler 时遇到问题 (非致命): {e}")

        # 2. 初始化适配器
        self.adapter = QmlAdapter(self._qml_item)

        # 3. 初始化控制器
        self.controller = EmoteController(
            view_adapter=self.adapter,
            plugin_dir=self._plugin_path,
            config_override=self._config_override
        )
        self.resources.register_cleanup_task(self.controller.cleanup)

        # 4. 连接内部信号转发
        self.controller.load_finished.connect(self.loadFinished)
        self.controller.player_ready.connect(self.playerReady)
        self.controller.plugins_load_finished.connect(self.pluginsLoadFinished)
        self.controller.on_character_clicked.connect(self.characterClicked)
        self.controller.on_character_hovered.connect(self.characterHovered)

        # 5. 加载主页 (计算绝对路径)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        url = QUrl.fromLocalFile(html_path)
        url.setScheme("emote")
        
        # 设置 QML Item 的 url 属性
        self._qml_item.setProperty("url", url.toString())
        logger.info(f"EmoteWidgetQml: 已设置 QML url -> {url.toString()}")

    @Slot()
    def cleanup(self):
        """手动清理资源"""
        self.resources.shutdown()

    @Property(QObject, constant=True)
    def api(self):
        """直接暴露 Controller 给 QML"""
        return self.controller