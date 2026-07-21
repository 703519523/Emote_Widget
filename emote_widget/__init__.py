from typing import Any
from PySide6.QtWebEngineCore import QWebEngineUrlScheme
from .default_config.default_constants import __version__
from .core.adapter_registry import AdapterRegistry
from .core.controller import EmoteController

from .ui.adapters.qt_adapter import WidgetAdapter

try:
    from .ui.adapters.qml_adapter import QmlAdapter
    AdapterRegistry.register("qml")(QmlAdapter)
except ImportError:
    pass

AdapterRegistry.register("default")(WidgetAdapter)
AdapterRegistry.register("qt")(WidgetAdapter)
from .ui.views.widget_qt import EmoteWidget
from .ui.views.widget_qml import EmoteWidgetQml

def _register_custom_scheme():
    if QWebEngineUrlScheme.schemeByName(b"emote").name() == b"emote":
        return

    scheme = QWebEngineUrlScheme(b"emote")
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme |
        QWebEngineUrlScheme.Flag.LocalScheme |
        QWebEngineUrlScheme.Flag.LocalAccessAllowed |
        QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)

_register_custom_scheme()


def create_emote_widget(adapter_name: str = "default", plugin_dir: str = "./plugins", **kwargs: Any):
    """
    [工厂函数] 创建 EmoteWidget 实例。
    
    参数:
        adapter_name (str): 适配器名称，默认为 "default" (Qt)。
                            你可以将其指向你在 plugins 里定义的自定义 adapter。
        plugin_dir (str): 插件扫描目录。
        **kwargs: 传递给 Adapter 构造函数的参数。
    
    返回:
        (ui_widget, controller): 返回元组。
            ui_widget: 具体的 UI 控件 (如 QWebEngineView)。
            controller: EmoteController 实例。
    """
    # 1. 扫描插件目录 (加载用户自定义 Adapter)
    AdapterRegistry.scan_plugins(plugin_dir)
    
    # 2. 获取 Adapter 类
    AdapterCls = AdapterRegistry.get(adapter_name)
    
    # 3. 实例化 Adapter (这一步通常会创建 UI 控件)
    # 注意：具体的参数取决于 Adapter 的实现，这里简单透传 kwargs
    adapter_instance = AdapterCls(**kwargs)
    
    # 4. 创建 Controller 并绑定
    controller = EmoteController(view_adapter=adapter_instance, plugin_dir=plugin_dir)
    
    # 5. 返回 UI 句柄和控制器
    # 我们约定 Adapter 必须提供一个方法返回真正的 UI 对象，或者它自己就是
    ui_handle = adapter_instance.get_ui_object() if hasattr(adapter_instance, "get_ui_object") else adapter_instance
    
    return ui_handle, controller

__all__ = ["EmoteWidget", "EmoteWidgetQml", "__version__", "create_emote_widget", "AdapterRegistry"]
