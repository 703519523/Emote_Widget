# EmoteWidget

一个基于 PySide6 的、功能完备的动态角色显示组件，用于加载和控制 [FreeMote (E-mote)](https://github.com/UlyssesWu/FreeMote) (尤其是一些galgame中解包出来的) 模型。它提供了一套高级、纯粹的 Python API，将所有与底层 Web 引擎和 JavaScript 的复杂交互完全封装，让开发者可以轻松地将交互式 2D 角色集成到桌面应用中。

![image](https://github.com/user-attachments/assets/c8fd531b-3327-4b5c-8317-9de2432823a9)

## ✨ 核心功能

*   **高级 Python SDK**: 提供简单易用的 Python 方法（如 `play()`, `set_scale()`）来控制角色，无需编写任何 JavaScript。
*   **智能模型加载**: 自动解包 `.psb` 模型文件，生成并缓存参数映射表 (`.map.json`)，极大简化了模型适配过程。
*   **强大的动画控制**: 支持主时间轴动画和可叠加的差分动画（如表情），可控制动画速度、平滑过渡，并能随时重置角色状态。
*   **自适应口型同步**: 内置基于双指数移动平均（Dual EMA）算法的口型同步系统，能够根据实时音频流（或音频文件）自适应音量大小，实现流畅自然的口型动画。
*   **可扩展插件系统**: 能够自动扫描并加载 `plugins` 目录下的所有插件，方便开发者扩展新功能（如 TTS、AI 对话集成等）。
*   **丰富的视觉特效**: 支持位置/缩放/旋转变换、全局透明度、灰度、顶点染色、背景图更换等多种视觉效果。
*   **物理与环境模拟**: 支持调整头发、配件的物理摆动幅度，并可模拟全局风力效果。
*   **内置交互**: 开箱即用地支持鼠标拖动、滚轮缩放和视线跟随。
*   **完整的测试平台**: 提供一个功能齐全的图形化测试工具 `Tester.py`，允许用户无需编写代码即可探索和调试所有功能。

## 🚀 快速开始：使用测试平台

项目附带一个强大的交互式测试平台 `Tester.py`，是了解和调试所有功能的最佳方式。

**1. 准备环境**

确保你已安装所需的 Python 库：
```bash
pip install PySide6 numpy soundfile sounddevice
```

**2. 运行测试平台**

直接运行 `Tester.py` 文件：
```bash
python Tester.py
```

**3. 探索功能**

测试平台提供了一个带标签页的界面，让你可以：
*   **基本**: 动态加载和切换不同的 `.psb` 模型和背景图片。
*   **变换/动画/外观/物理**: 通过滑块实时控制角色的缩放、旋转、动画速度、透明度、物理摆动和风力等。
*   **绑定**: 实时查看和修改模型的底层变量绑定，调整参数范围、分类和特殊用途标签，并可将修改**保存到缓存**，极大简化了新模型的适配工作。
*   **交互**: 测试鼠标拖动、滚轮缩放、视线跟随，以及从 `.wav` 文件启动的口型同步。
*   **高级**: 测试差分动画、对话框系统，并能查询模型内部的详细数据。
*   **插件**: 查看所有已加载的插件，并与其UI进行交互。

---

### ⚠️ 关于项目开发的说明 (A Note on Development)

这个项目是在一名独立开发者在三个多星期的时间内，从概念构思到功能完备的快速迭代成果。

为了实现如此高的开发效率，本项目在开发过程中大量借助了 **AI 辅助编程工具**。其中，Python 后端代码的格式化、部分通用功能的实现，以及**全部的前端 HTML/JavaScript 代码**，均由 AI 生成初始框架，再进行逻辑修复、功能整合和最终调试。

**重点：**
*   **后端优先**: 本项目的核心与重心在于提供一个功能强大、API 友好的 **Python SDK (`EmoteWidget`)**。
*   **前端作为功能演示**: 由于我并非一名前端开发者，配套的 `pyside_webview.html` 及其 JavaScript 代码应被视为一个**功能性的实现原型 (Proof-of-Concept)**。它能够完整地驱动模型并展示所有功能，但在代码结构上可能较为粗糙（例如，存在较多全局变量），并可能包含一些未知的边界情况或错误。

我选择公开这些信息，是为了让所有使用者和潜在的贡献者对项目的现状有一个清晰的认识。非常欢迎任何形式的贡献，特别是对于前端代码的重构、优化和改进！

---

## 👨‍💻 在你的项目中使用 (Programmatic Usage)

如果你想将 `EmoteWidget` 集成到你自己的 PySide6 应用中，用法也非常简单。

```python
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from emote_widget import EmoteWidget

class MyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My App with EmoteWidget")
        self.resize(800, 600)

        # 1. 实例化 EmoteWidget
        self.emote_widget = EmoteWidget(self)
        self.setCentralWidget(self.emote_widget)

        # 2. 连接信号，在网页和模型准备好后执行操作
        self.emote_widget.load_finished.connect(self.on_page_loaded)
        self.emote_widget.player_ready.connect(self.on_player_ready)

    def on_page_loaded(self):
        """当内部网页加载完毕后，加载一个模型"""
        print("Page loaded, loading model...")
        # 模型文件 "chara.psb" 应放置在 "web_frontend/models/" 目录下
        self.emote_widget.load_model("chara.psb")

    def on_player_ready(self, available_animations):
        """当模型准备就绪后，控制角色行为"""
        print(f"Model ready! Animations: {available_animations}")
        
        # 3. 调用 API 控制角色
        self.emote_widget.play("idle_01")
        self.emote_widget.set_scale(0.8, duration_ms=500)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyApp()
    window.show()
    sys.exit(app.exec())
```

## 📂 项目结构

```
.
├── Emote_Widget.py # 主 SDK 组件
├── Tester.py # 功能测试与演示平台
├── BoundParams.py # 模型参数解包与缓存模块
├── logger_config.py # 日志配置
├── requirements.txt # Python 依赖项列表
│
├── web_frontend/ # 存放所有前端资源
│ ├── pyside_webview.html # 核心 HTML 页面，用于渲染模型
│ ├── models/ # 存放 .psb 模型文件 (例如 chara.psb)
│ ├── driver/ # JavaScript 驱动 (已合并到html中)
│ │ ├ emoteplayer.js # 此为 [Freemote-SDK](https://github.com/Project-AZUSA/FreeMote-SDK) 提供的模型渲染API
│ │ └ FreeMoteDriver.js # 此为 [Freemote-SDK](https://github.com/Project-AZUSA/FreeMote-SDK) 提供的模型渲染核心
│ ├── dialogs/ # 对话框皮肤 (例如 default.html)
│ │ └ default.html # 默认对话框
│ └── backgrounds/ # 背景图片 (例如 bg.png)
│
├── plugins/ # 插件目录
│ ├── plugin_interface.py # 所有插件必须继承的接口
│ └── debug_tools/ # 示例插件：调试工具
│   └ main.py # 插件入口
│
└── tools/ # 存放第三方命令行工具
  ├── lib
  └── PsbDecompile.exe # FreeMote 解包工具，由 BoundParams.py 自动调用
```

## 📜 许可证 (License)

本项目根据 **[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)** 进行许可。

这意味着：
*   **署名 (BY)**: 你必须在你的项目中致谢本项目及相关依赖。
*   **非商业性使用 (NC)**: 你的项目**不能**用于任何商业目的。
*   **相同方式共享 (SA)**: 如果你修改或基于此项目创作了衍生作品，你必须以相同的许可证分发你的作品。

## 🙏 致谢 (Acknowledgements)

本项目依赖于以下优秀的开源项目，并因此受到其 `CC BY-NC-SA 4.0` 许可证的约束。感谢原作者的辛勤工作！

*   **[FreeMote-SDK](https://github.com/Project-AZUSA/FreeMote-SDK)**
*   **[FreeMote](https://github.com/UlyssesWu/FreeMote)**
