import logging
import sys

# Logger 定义

#主业务逻辑 (Controller, Widget, PythonBridge)
emote_widget_logger = logging.getLogger("EmoteWidget.Core")

#参数绑定与自省 (BoundParams)
bound_params_logger = logging.getLogger("EmoteWidget.BoundParams")

#插件系统 (PluginSystem, PluginLoader)
plugin_logger = logging.getLogger("EmoteWidget.Plugins")

#音频处理 (AudioUtils, LipSyncThread)
audio_logger = logging.getLogger("EmoteWidget.Audio")

#文件与路径 (Paths, SchemeHandler)
file_logger = logging.getLogger("EmoteWidget.FileIO")

#适配器注册 (AdapterRegistry)
adapter_logger = logging.getLogger("EmoteWidget.Adapter")

#资源管理 (ResourceManager)
resource_logger = logging.getLogger("EmoteWidget.Resource")


def setup_logging(level: int = logging.INFO):
    """
    配置库内部的默认日志行为。
    注意：为了不干扰使用者的全局 logging 配置，只给 EmoteWidget 父节点添加 Handler。
    """
    base_logger = logging.getLogger("EmoteWidget")
    base_logger.setLevel(level)
    
    if not base_logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)-20s - [%(levelname)s] - %(message)s',
            datefmt='%H:%M:%S'
        )
        stream_handler.setFormatter(formatter)
        base_logger.addHandler(stream_handler)
        base_logger.propagate = False

setup_logging()