import logging
import sys

def setup_logging():
    """配置全局日志记录器。"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # 设置默认日志级别
    if logger.hasHandlers():
        logger.handlers.clear()
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

# 每个主要模块创建独立的 logger，以获得更清晰的日志来源
emote_widget_logger = logging.getLogger("EmoteWidget")
bound_params_logger = logging.getLogger("BoundParams")
tester_logger = logging.getLogger("Tester")
plugin_logger = logging.getLogger("Plugins")

# 在模块加载时自动配置日志
setup_logging()