<p>
    简体中文 | <a href="docs/README_EN.md">English</a>
</p>

# EmoteWidget

一个基于 PySide6、Qt WebEngine 和 JavaScript 前端的动态角色显示组件 SDK，用于加载和控制 [FreeMote (E-mote)](https://github.com/UlyssesWu/FreeMote) 模型。

它采用 **Controller-Adapter (控制器-适配器)** 架构，实现了业务逻辑与 UI 框架的彻底解耦。不仅提供开箱即用的 Qt Widgets 组件，还同时支持 **Qt Quick (QML)**，并允许通过插件扩展支持其他 GUI 框架。

<img width="1924" height="1397" alt="image" src="https://github.com/user-attachments/assets/167df9b6-325e-458e-aa48-fd870f5e1bc6" />

## ✨ 核心功能

*   **多框架支持**: 开箱即支持 `QtWidgets` 和 `QtQuick (QML)`，一套逻辑，多端运行。
*   **Controller-Adapter 架构**: 核心逻辑封装在纯 Python 控制器中，UI 层通过适配器接口交互，结构清晰，极易扩展。
*   **可扩展 PSB 处理**: 核心自动处理 LZ4/MDF/PSZ 压缩包装和 Win→EMS 平台转换；XorShift128 等可选处理通过插件接入，不耦合核心 SDK。
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
    *   `lz4` (用于读取 LZ4 Frame 包装的 PSB)

## 🧭 先了解当前架构

项目当前的正式架构说明见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，其中区分了 Qt Widgets 和 QML 两条真实调用链、Controller/Adapter 边界、Python-JavaScript 通信以及插件生命周期。

`walkthrough.md` 是项目审查记录，适合了解重构背景和已发现的问题；它不是严格的 API 文档。

## 🚀 快速开始：运行测试平台

当前仓库提供了两个独立的测试入口（位于 `testers/` 目录）：`test_qt.py` 和 `test_qml.py`。

**1. 安装依赖**
```bash
pip install -r requirements.txt
```

**2. 运行测试**
```bash
python testers/test_qt.py
```

Qt 测试平台包含：
*   **UI 交互**: 实时调整变换、动画、物理参数。
*   **参数绑定调试**: 查看模型内部变量，实时修改绑定并保存到缓存。
*   **插件管理**: 查看已加载插件及其 UI。
*   **嵌入式终端**: 内置 Python 控制台，方便直接调用 `controller` 进行调试。

QML 测试平台：

```bash
python testers/test_qml.py
```

QML 界面资源位于 `qml_tester/qml/`，Python 侧后端对象是 `EmoteWidgetQml`。

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

# 2. 加载模型（自动处理压缩/平台转换；可选插件可扩展加密处理）
widget.load_model("chara.psb")

# 3. 监听信号
widget.player_ready.connect(lambda: widget.play("Hello"))

sys.exit(app.exec())
```

### 场景 2: 使用 Qt Quick / QML

QML 场景建议使用 `EmoteWidgetQml`，由 QML 的 WebEngineView 在完成实例化后绑定到 `targetView`。完整可运行示例请看 `test_qml.py` 和 `qml_tester/qml/`。

**Python 端:**
```python
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from emote_widget import EmoteWidgetQml

QtWebEngineQuick.initialize() # 必须初始化
engine = QQmlApplicationEngine()
engine.load("main.qml")

# 创建 QML 后端对象并注入上下文；QML 组件负责 targetView 和 WebChannel 绑定
backend = EmoteWidgetQml()
engine.rootContext().setContextProperty("EmoteBackend", backend)
```

**QML 端 (`main.qml`):**
```qml
import QtQuick 2.15
import QtWebEngine 1.10

Window {
    visible: true
    width: 800; height: 600

    WebEngineView {
        anchors.fill: parent
        backgroundColor: "transparent"

        // 具体的 QML 封装、targetView 和 URL 以 qml_tester/qml 中的实现为准
    }
}
```

### 场景 3: 自定义适配器 (高级扩展)

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
`create_emote_widget()` 是底层 Adapter 工厂，不是 `EmoteWidget` Facade 的替代品。默认 Qt Adapter 需要调用者提供一个已创建的 WebView；如需普通 Qt 集成，优先使用 `EmoteWidget()`。

---

## 📂 项目结构 (New Structure)

重构后的项目采用了标准的 Python Package 结构：

```
.
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
│   ├── default_config/       # [配置] 默认配置文件
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

## 🧪 其他测试入口

```bash
python testers/click_through_test.py
```

该脚本用于专项检查透明窗口和点击穿透。由于 Qt WebEngine 依赖图形环境，测试脚本应在本地桌面环境中运行。

## ⚠️ 关于开发的说明

核心 Python SDK (`EmoteController`) 已完成一轮 Controller-Adapter 重构，但项目仍处于持续整理阶段；请以当前源码、`docs/ARCHITECTURE.md` 和测试入口为准。

前端部分 (`pyside_webview.html` & JS) 主要作为功能实现的载体，虽然功能完备，但仍有优化空间。项目大量使用了 AI 辅助编程来加速开发，特别是前端逻辑和部分样板代码。我们欢迎社区贡献代码，进一步完善前端交互或添加新的 Adapter。

---

## 📜 许可证 & 致谢

本项目基于 **CC BY-NC-SA 4.0** 许可。

特别致谢以下项目：
*   **[FreeMote-SDK](https://github.com/Project-AZUSA/FreeMote-SDK)** & **[FreeMote](https://github.com/UlyssesWu/FreeMote)** by UlyssesWu