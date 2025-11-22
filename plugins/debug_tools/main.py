# plugins/debug_tools/main.py
from plugins.plugin_interface import IEmotePlugin
from PySide6.QtWidgets import QWidget

class DebugToolsPlugin(IEmotePlugin):
    """
    一个简单的示例插件，提供一些调试功能。
    """
    def get_name(self) -> str:
        return "debug" # 插件的访问名将是 widget.plugins.debug
    
    def get_description(self) -> str:
        return "示例插件" # 插件的访问名将是 widget.plugins.debug

    def initialize(self, widget):
        super().initialize(widget)
        print(f"[{self.get_name()}] 插件已初始化！")
        
        # 示例：连接到一个 widget 信号
        self.widget.player_ready.connect(self._on_player_ready)

    def cleanup(self):
        print(f"[{self.get_name()}] 插件正在清理...")
        # 如果有连接信号，在这里断开
        if self.widget:
            self.widget.player_ready.disconnect(self._on_player_ready)

    def _on_player_ready(self, timelines):
        print(f"[{self.get_name()}] 截获到 player_ready 信号！模型有 {len(timelines)} 个动画。")

    # --- 这个插件新增的、可供外部调用的方法 ---
    def print_widget_size(self):
        """打印 EmoteWidget 当前的尺寸。"""
        if self.widget:
            print(f"[{self.get_name()}] EmoteWidget 当前尺寸: {self.widget.size().width()}x{self.widget.size().height()}")

    def get_ui_widget(self):
        win=QWidget()
        win.setFixedSize(100,100)
        return win
        