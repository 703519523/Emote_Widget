<p>
    简体中文 | <a href="docs/README_EN.md">English</a>
</p>

# EmoteWidget

一个基于 PySide6 的、功能完备的动态角色显示组件 SDK，用于加载和控制 [FreeMote (E-mote)](https://github.com/UlyssesWu/FreeMote) 模型。

它采用 **Controller-Adapter (控制器-适配器)** 架构，实现了业务逻辑与 UI 框架的彻底解耦。不仅提供开箱即用的 Qt Widgets 组件，还同时支持 **Qt Quick (QML)**，并允许通过插件扩展支持其他 GUI 框架。

<img width="1924" height="1397" alt="image" src="https://github.com/user-attachments/assets/167df9b6-325e-458e-aa48-fd870f5e1bc6" />

## ✨ 核心功能

*   **多框架支持**: 开箱即支持 `QtWidgets` 和 `QtQuick (QML)`，一套逻辑，多端运行。
*   **Controller-Adapter 架构**: 核心逻辑封装在纯 Python 控制器中，UI 层通过适配器接口交互，结构清晰，极易扩展。
*   **安全沙箱**: 引入自定义 `emote://` 协议加载本地资源，无需关闭浏览器的安全策略 (CORS)，解决了跨域和资源加载的痛点。
*   **异步通信机制**: 采用基于 Promise 的 JS-Python 握手流程，杜绝通信时序导致的 Race Condition，加载更稳健。
*   **高级 Python SDK**: 提供简单易用的 Python 方法（如 `play()`, `set_scale()`）控制角色，无需编写任何 JavaScript。
*   **自适应口型同步**: 内置基于双指数移动平均（Dual EMA）算法的口型同步线程，支持实时音频流或文件驱动。
*   **插件化扩展**: 强大的插件系统 (`plugins/`)，支持扩展功能或注册新的 UI 适配器。
*   **内置交互与特效**: 支持鼠标拖动、视线跟随、透明窗口穿透、背景更换、灰度/染色特效等。

## 💻 配置要求

*   **操作系统**: Windows 10/11, macOS 11+, Linux
*   **Python版本**: 3.10+
*   **依赖**: 
    *   `PySide6` (必需)
    *   `numpy` (用于口型分析)
    *   `soundfile`, `sounddevice` (用于音频播放与流处理)

## 🚀 快速开始：运行测试平台

项目重构后提供了一个全新的 `run_tests.py`，它是了解 SDK 功能的最佳入口。

**1. 安装依赖**
```bash
pip install -r requirements.txt
```

**2. 运行测试**
```bash
python run_tests.py
```

测试平台包含：
*   **UI 交互**: 实时调整变换、动画、物理参数。
*   **参数绑定调试**: 查看模型内部变量，实时修改绑定并保存到缓存。
*   **插件管理**: 查看已加载插件及其 UI。
*   **嵌入式终端**: 内置 Python 控制台，方便直接调用 `controller` 进行调试。

---

## 👨‍💻 集成指南 (Integration)

### 场景 1: 使用 PySide6 Widgets (经典模式)

最简单的用法，使用封装好的 `EmoteWidget` 类。

```python
import sys
from PySide6.QtWidgets import QApplication
# 直接导入封装好的 Widget
from emote_widget import EmoteWidget

app = QApplication(sys.argv)

# 1. 实例化
widget = EmoteWidget()
widget.show()

# 2. 加载模型 (支持绝对路径或包内相对路径)
# 默认模型目录: emote_widget/web_frontend/models/
widget.load_model("chara.psb")

# 3. 监听信号
widget.player_ready.connect(lambda: widget.play("Hello"))

sys.exit(app.exec())
```

### 场景 2: 使用 Qt Quick / QML (高级模式)

通过 `create_emote_widget` 工厂函数和 `QmlAdapter` 实现。

**Python 端:**
```python
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from emote_widget import create_emote_widget

QtWebEngineQuick.initialize() # 必须初始化
engine = QQmlApplicationEngine()
engine.load("main.qml")

# 1. 找到 QML 中的 WebEngineView 对象
root = engine.rootObjects()[0]
qml_item = root.findChild(object, "emoteView")

# 2. 创建控制器 (指定 adapter="qml")
# 返回 (ui_handle, controller)
_, controller = create_emote_widget(adapter_name="qml", qml_item=qml_item)

# 3. 使用 controller 控制逻辑
controller.load_model("chara.psb")
```

**QML 端 (`main.qml`):**
```qml
import QtQuick 2.15
import QtWebEngine 1.10

Window {
    visible: true
    width: 800; height: 600

    WebEngineView {
        objectName: "emoteView" // Python 通过这个名字查找
        anchors.fill: parent
        backgroundColor: "transparent"
        
        // 必须使用 emote:// 协议加载主页
        url: "emote://pyside_webview.html"
    }
}
```

### 场景 3: 自定义适配器 (Custom Adapter)

如果你想支持 Tkinter 或 CEF Python，只需编写一个 Adapter 插件。

```python
# plugins/my_adapter.py
from emote_widget import AdapterRegistry
from emote_widget.core.adapter_interface import IViewAdapter

@AdapterRegistry.register("my_driver")
class MyAdapter(IViewAdapter):
    def run_javascript(self, script: str):
        # 实现你的 JS 执行逻辑
        pass
    # ... 实现其他接口
```
调用：`create_emote_widget(adapter_name="my_driver")`

---

## 📂 项目结构 (New Structure)

重构后的项目采用了标准的 Python Package 结构：

```
.
├── run_tests.py              # [入口] 功能测试平台
├── requirements.txt          # 依赖列表
├── LICENSE                   # 许可协议
│
├── emote_widget/             # [核心包]
│   ├── __init__.py           # 包入口，注册协议与工厂函数
│   │
│   ├── core/                 # [业务核心] (纯 Python，无 UI 依赖)
│   │   ├── controller.py     # 核心控制器 (大脑)
│   │   ├── adapter_interface.py # 适配器接口定义
│   │   ├── resource_manager.py  # 生命周期管理
│   │   ├── scheme_handler.py    # 自定义协议与安全处理
│   │   └── ...
│   │
│   ├── ui/                   # [UI 实现]
│   │   ├── adapters/         # 各种 UI 框架的适配器 (Widget, QML)
│   │   ├── views/            # 封装好的外观类 (Facade)
│   │   └── common/           # 通用 UI 组件 (如调试监视器)
│   │
│   ├── utils/                # [工具集] (路径解析、日志、音频)
│   ├── config/               # [配置] 默认配置文件
│   │
│   └── web_frontend/         # [前端资源] (打包在包内)
│       ├── pyside_webview.html # 核心 HTML
│       ├── driver/           # FreeMote JS SDK
│       ├── models/           # 默认模型目录
│       └── ...
│
└── plugins/                  # [用户插件] 用户自定义扩展目录
```

---

## ⚠️ 关于开发的说明

本项目由独立开发者维护。核心 Python SDK (`EmoteController`) 经过了深度重构，具备极高的稳定性和扩展性。

前端部分 (`pyside_webview.html` & JS) 主要作为功能实现的载体，虽然功能完备，但仍有优化空间。项目大量使用了 AI 辅助编程来加速开发，特别是前端逻辑和部分样板代码。我们欢迎社区贡献代码，进一步完善前端交互或添加新的 Adapter。

---

## 📜 许可证 & 致谢

本项目基于 **CC BY-NC-SA 4.0** 许可。

特别致谢以下项目：
*   **[FreeMote-SDK](https://github.com/Project-AZUSA/FreeMote-SDK)** & **[FreeMote](https://github.com/UlyssesWu/FreeMote)** by UlyssesWu