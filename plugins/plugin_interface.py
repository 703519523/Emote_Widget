from abc import ABC, abstractmethod

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from Emote_Widget import EmoteWidget

class IEmotePlugin(ABC):
    """
    EmoteWidget 插件的抽象基类接口。

    所有插件都必须继承自这个类，并实现其所有抽象方法。
    这确保了插件系统的一致性和可靠性。
    """

    @abstractmethod
    def get_name(self) -> str:
        """
        返回插件的唯一名称。

        这个名称应该是一个有效的 Python 标识符（例如 "tts", "debug_tools"），
        因为它将被用作通过 PluginAccessor 访问插件的属性名。
        
        返回:
            str: 插件的唯一名称。
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        返回插件的其他信息。
        这里可以存放作者信息，插件文档以及其他相关信息。
        
        返回:
            str: 插件的信息。
        """
        pass

    @abstractmethod
    def initialize(self, widget: 'EmoteWidget'):
        """
        插件的初始化入口点。

        当 EmoteWidget 加载此插件时，会调用此方法。
        插件应该在这里执行其所有的初始化逻辑，例如连接信号、
        添加UI元素等。

        参数:
            widget (EmoteWidget):
                EmoteWidget 的主实例。插件可以通过这个实例与主应用交互，
                调用其公共方法，连接其信号。
        """
        self.widget = widget # 存储对主 widget 的引用

    @abstractmethod
    def cleanup(self):
        """
        插件的清理/卸载入口点。

        当应用程序关闭或插件被卸载时调用。
        插件应该在这里释放所有资源，例如断开信号连接、
        关闭文件、停止线程等。
        """
        pass