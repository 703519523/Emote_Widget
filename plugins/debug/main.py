"""
EmoteWidget 插件系统示例插件

这是一个示例插件，展示了如何创建一个 EmoteWidget 插件。它演示了:
1. 插件的基本结构和必需方法
2. 如何与 EmoteController 交互
3. 如何连接和处理信号
4. 如何添加自定义功能

插件开发指南:
-------------
1. 必需步骤:
   - 继承 IEmotePlugin 接口
   - 实现所有抽象方法 (get_name, get_description, initialize, cleanup)
   - 在 initialize 中设置必要的状态和连接信号
   - 在 cleanup 中清理资源和断开信号

2. 最佳实践:
   - 为插件类添加清晰的文档字符串
   - 正确处理类型标注
   - 安全地处理controller引用（考虑None的情况）
   - 在cleanup中完整清理所有资源
   - 使用描述性的方法名和变量名

3. 插件生命周期:
   - 构造: __init__ 被调用，此时还不能访问 EmoteController
   - 初始化: initialize 被调用，获得 EmoteController 实例
   - 运行: 插件处于活动状态，可以响应信号和调用方法
   - 清理: cleanup 被调用，需要断开所有信号连接
   - 销毁: 插件实例被删除

4. 提示:
   - 使用 typing 模块添加类型标注
   - 为复杂的方法添加文档字符串
   - 使用 try-except 处理可能的错误
   - 检查 controller 是否为 None
"""

from typing import List
from emote_widget.core.plugin_interface import IEmotePlugin
from PySide6.QtWidgets import QWidget

class DebugToolsPlugin(IEmotePlugin):
    """
    调试工具插件 - 演示插件系统的基本功能

    这个插件提供了一些基本的调试功能，作为插件开发的参考示例。
    它展示了如何:
    1. 实现必需的插件接口方法
    2. 处理 EmoteController 实例
    3. 连接和响应信号
    4. 添加自定义功能方法
    5. 正确进行资源清理

    Attributes:
        controller: 对 EmoteController 实例的引用，用于与主程序交互
    """
    def __init__(self):
        """
        插件构造函数

        注意: 在这个阶段，插件还没有访问 EmoteController 的权限。
        构造函数应该只进行最基本的初始化，不要尝试设置任何依赖于
        controller 的状态。
        """
        super().__init__() # 初始化父类 (如果是 QObject 继承链这很重要)

    def get_name(self) -> str:
        """
        返回插件的唯一标识符名称。

        这个名称会用作插件的访问键，例如 widget.plugins.debug。
        名称应该:
        1. 是有效的 Python 标识符（只包含字母、数字和下划线）
        2. 全小写，使用下划线分隔单词
        3. 简短但描述性强
        4. 在所有插件中唯一

        Returns:
            str: 插件的唯一名称
        """
        return "debug"
    
    def get_description(self) -> str:
        """
        返回插件的人类可读描述。

        这个描述可以包含:
        - 插件的主要功能
        - 版本信息
        - 作者信息
        - 使用说明
        - 其他相关信息

        Returns:
            str: 插件的描述文本
        """
        return "示例调试插件 - 演示插件系统基本功能"

    def initialize(self):
        """
        插件初始化方法，在插件被加载时调用。

        这是插件生命周期中最重要的方法之一。在这里你可以:
        1. 连接需要的信号
        2. 初始化插件的状态
        3. 设置定时器或其他长期运行的功能

        注意：
        此时 self.controller 是一个沙盒代理，操作会被暂存。
        """
        self.logger.info(f"[{self.get_name()}] 插件已初始化！")
        
        # 示例：连接到一个 widget 信号以接收模型加载通知
        # 直接使用 self.controller 访问
        self.controller.player_ready.connect(self.on_player_ready)

    def cleanup(self):
        """
        插件清理方法，在插件被卸载时调用。

        这是插件生命周期中最后的机会来清理资源。你应该:
        1. 断开所有信号连接
        2. 关闭打开的文件
        3. 停止运行的线程
        4. 释放分配的资源
        5. 还原任何对主程序做出的修改

        注意: 即使插件初始化失败，这个方法仍可能被调用，
        所以要注意检查对象是否为None。
        """
        self.logger.info(f"[{self.get_name()}] 插件正在清理...")
        
        # 安全地断开信号连接
        if self.controller:
            self.controller.player_ready.disconnect(self.on_player_ready)

    def on_player_ready(self, timelines: List[str]):
        """
        player_ready 信号的处理函数。

        这个方法演示了如何处理来自 EmoteController 的信号。
        当一个模型成功加载后，这个方法会被调用。

        Args:
            timelines: 模型中所有可用的动画时间轴名称列表
        """
        self.logger.info(f"[{self.get_name()}] 截获到 player_ready 信号！模型有 {len(timelines)} 个动画。")

    # --- 插件特有的公开方法 ---
    def print_widget_size(self):
        """
        打印 EmoteWidget 当前的尺寸。

        这个方法展示了:
        1. 如何添加插件特有的功能
        2. 如何安全地访问 controller 的属性
        3. 如何处理可能的错误

        示例用法:
            widget.plugins.debug.print_widget_size()
        """
        if self.controller:
            self.logger.error("DebugPlugin Error: 控制器未初始化")
            return
            
        try:
            ui_obj = self.controller.view_adapter.get_ui_object()
            
            # 假设这是 Qt 环境，ui_obj 是 QWidget
            if hasattr(ui_obj, "width") and hasattr(ui_obj, "height"):
                self.logger.info(f"DebugPlugin: Widget 尺寸 = {ui_obj.width()} x {ui_obj.height()}")
            else:
                self.logger.error(f"DebugPlugin: UI 对象 {ui_obj} 没有宽高属性")
        except AttributeError as e:
            self.logger.error(f"DebugPlugin Error: 无法访问 UI 属性 - {e}")
    
    def get_ui_widget(self) -> QWidget:
        """
        创建并返回一个示例UI组件。

        这个方法展示了如何为插件创建自定义UI组件。
        插件可以通过这种方式向主程序提供:
        - 控制面板
        - 配置界面
        - 状态显示
        - 其他交互界面

        Returns:
            QWidget: 一个简单的100x100固定大小的窗口部件
        """
        win = QWidget()
        win.setFixedSize(100, 100)
        return win
        