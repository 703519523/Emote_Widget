# EmoteWidget 架构说明

> 本文以当前代码为准，用于帮助重新熟悉项目。它不是 API 参考手册；公开 API 的细节应以源码和示例为准。

## 1. 项目定位

EmoteWidget 是一个基于 PySide6、Qt WebEngine 和 JavaScript 前端的动态角色显示 SDK。Python 负责宿主窗口、业务编排、插件和音频分析；JavaScript 负责 FreeMote/E-mote 播放器和高频渲染逻辑。

当前支持两条宿主路径：

1. **Qt Widgets**：`EmoteWidget`，适合传统 QWidget 应用。
2. **Qt Quick/QML**：`EmoteWidgetQml`，适合 QML 应用，通过属性、信号和槽与 QML 交互。

插件系统 v2 的详细设计、事件目录、中间件调用约定和实施计划见
[`docs/PLUGIN_SYSTEM_V2.md`](PLUGIN_SYSTEM_V2.md)。本文只保留整体架构和真实调用链；
插件扩展点的具体约定以该文档为准。

项目的核心不是某一个窗口类，而是下面这条依赖链：

```text
Qt Facade / QML ViewModel
          ↓
      ViewAdapter
          ↓  (IViewAdapter)
   EmoteController
      ↙      ↓       ↘
  Bridge  Plugins  LipSync/Tasks
          ↓
       Web Frontend
```

这里的“MVVM”是宽泛意义上的分层：`EmoteController` 承担 ViewModel/业务控制器职责，两个 UI 外观类负责宿主框架生命周期，Adapter 负责屏蔽 WebView 差异。

## 2. 目录职责

```text
emote_widget/
├── core/                 跨 UI 的核心业务与基础设施
│   ├── controller.py     EmoteController，统一业务入口
│   ├── adapter_interface.py
│   ├── adapter_registry.py
│   ├── python_api_bridge.py  JS → Python 的 QObject Bridge
│   ├── plugin_system.py
│   ├── task_dispatcher.py
│   ├── scheme_handler.py     emote:// 资源协议
│   ├── resource_manager.py
│   └── lipsync_thread.py
├── ui/
│   ├── adapters/         WidgetAdapter / QmlAdapter
│   ├── views/            EmoteWidget / EmoteWidgetQml
│   └── common/           口型与遮罩调试窗口
├── utils/                路径、日志、代理、音频、参数绑定等工具
├── default_config/       默认配置和版本信息
└── web_frontend/         HTML、CSS、FreeMote 和业务 JS

plugins/                  外部插件目录
testers/test_qt.py        Qt Widgets 全功能测试器
testers/test_qml.py       QML 测试器
qml_tester/qml/           QML 测试器的界面资源
```

## 3. Qt Widgets 路径

推荐入口：

```python
from PySide6.QtWidgets import QApplication
from emote_widget import EmoteWidget

app = QApplication([])
widget = EmoteWidget()
widget.resize(800, 600)
widget.show()
widget.load_model("chara.psb")
app.exec()
```

实际初始化顺序：

1. `EmoteWidget` 创建 `QWebEngineView`。
2. 设置透明背景，并安装 `EmoteSchemeHandler`。
3. 创建 `WidgetAdapter(self)`；Adapter 创建并挂载 `QWebChannel`。
4. 创建 `EmoteController`，Controller 创建 `PythonApiBridge` 并注册为 `py_api`。
5. 加载 `emote_widget/web_frontend/pyside_webview.html`（当前 Qt 路径使用 `file://` 主页面）。
6. 页面加载完成后，Controller 启动插件和前端初始化流程。
7. 外部 API 调用由 Controller 转成 JavaScript；播放器未就绪时暂存到 `_command_queue`。
8. JS 调用 `py_api.on_player_ready()`，Controller 收到后执行积压指令。

`WidgetAdapter` 的职责是把抽象接口映射到 Qt：

| 抽象能力 | Qt 实现 |
|---|---|
| 执行 JS | `QWebEnginePage.runJavaScript()` |
| 注册 Bridge | `QWebChannel.registerObject()` |
| 窗口透明 | QWidget 属性和 Window Flags |
| 点击穿透 | `QRegion` + `QWidget.setMask()` |

## 4. QML 路径

推荐参考实际测试入口 `test_qml.py` 和 `qml_tester/qml/`，不要把 QML 当作一个 Python `QWebEngineView` 子类。

```text
test_qml.py
  └── EmoteWidgetQml(QObject)
        ├── QmlAdapter(None)       # 先创建，后绑定
        ├── EmoteController
        └── QML targetView
              └── QmlAdapter.set_view()
```

QML 的初始化特点：

1. Python 创建 `EmoteWidgetQml`、Adapter 和 Controller。
2. QML WebEngineView 创建完成后，通过 `targetView` 属性交给 ViewModel。
3. `QmlAdapter` 使用 QML 对象的 `runJavaScript` 动态调用 JS。
4. QML WebChannel 创建后调用 `EmoteWidgetQml.registerWebChannel()`，把 Controller 的 Bridge 注册为 `py_api`。
5. QML 通过 `EmoteBackend.api` 调用 Controller，通过 ViewModel 的信号接收事件。
6. `notifyPageLoadFinished()` 通知 Controller 页面状态；早到的 `modelSource` 会延迟到页面成功后加载。

## 5. Python 与 JavaScript 通信

### Python → JavaScript

Controller 只依赖 `IViewAdapter.run_javascript()`：

```text
Controller._safe_run(js)
       ├── WidgetAdapter → page().runJavaScript(js)
       └── QmlAdapter    → QML WebEngineView.runJavaScript(js, None)
```

### JavaScript → Python

前端通过 QWebChannel 获取 `window.py_api`，其对象由 `PythonApiBridge` 提供。Bridge 只暴露显式 `@Slot` 方法，例如：

- `on_player_ready(timelines)`
- `receive_query_result(request_id, result_json)`
- `js_on_character_click()` / `js_on_character_hover()`
- `receive_render_mask_binary(data)`

### 异步查询

Controller 的 `_safe_query()` 生成 UUID 并保存回调：

```text
_safe_query(expression, callback)
  → JS 执行表达式
  → py_api.receive_query_result(uuid, json)
  → Controller 按 UUID 取出 callback
```

这套机制解决了 WebEngine 异步执行和查询结果回传的时序问题。

## 6. 模型加载与命令队列

模型资源通常由 `paths.py` 解析为允许访问的资源 URL。`EmoteSchemeHandler` 负责处理 `emote://` 请求，并配合资源白名单避免任意路径访问。

在 URL 解析阶段，`models/*.psb` 会经过 `emote_widget.utils.model_normalizer`。已有 raw `PSB\0` 文件保持旧 loader 路径，以兼容当前可工作的 `spec=ems` 模型；包装/加密输入则调用控件包内的 `emote_widget.utils.psb_converter`，执行以下流程：

**1. Shell 脱壳** (`psb_shell.py`)
- 支持 LZ4 Frame、MDF、PSZ (zlib) 压缩包装
- 自动检测并解包，输出 raw PSB 字节流

**2. XorShift128 解密** (`psb_crypto.py`)
- 检测 PSB v2/v3/v4 header 的加密标志
- **PSB v3/v4**: 支持自动密钥恢复（通过已知 header 长度反推 XorShift128 的 Key4）
- **PSB v2**: 需要用户提供显式密钥
- 解密后重新计算 Adler32 checksum 确保完整性

**3. 平台适配** (`ems_adapter.py`)
- 检查 PSB 的 `spec` 字段（`win`/`ems`/`krkr` 等）
- 由于网页内置的是 EMS 驱动，`spec=win` 模型需执行平台适配：
  - 仅支持所有纹理均为未压缩 `RGBA8`、资源长度严格等于 `width × height × 4`
  - 交换纹理 R/B 通道（Win BGRA → EMS RGBA）
  - 将对象树 spec 字段从 `"win"` 安全改为 `"ems"`
  - 重新计算并验证 checksum

**4. 缓存写入**
- 通过校验和适配的模型会写入 `.emote_cache/normalized_models/` 缓存
- 使用内容寻址（源文件 SHA256 的前 16 位）确保缓存一致性
- 原始文件永不改写

**安全边界**：
- Checksum 错误、未知 shell、非 `win/ems` spec 会显式拒绝
- DXT 等压缩纹理、不一致的资源尺寸会拒绝平台适配
- 避免把"结构有效但驱动无法加载"的 PSB 交给前端

播放器存在三个不同的就绪概念，阅读代码时不要混为一谈：

- **页面加载完成**：HTML 容器可通信，由 `on_page_load_finished()` 处理。
- **Bridge 就绪**：JS 侧 QWebChannel 已拿到 `py_api`，由 `bridge_manager.js` 的 Promise 管理。
- **Player 就绪**：模型播放器已初始化，JS 调用 `on_player_ready()`。

Controller 在 Player 就绪前缓存控制指令；Player 就绪后按调用顺序执行。这是 SDK 对外 API 可以早于 WebEngine 完成初始化调用的原因。

## 7. 插件、任务和口型同步

### 插件

`PluginLoaderWorker` 在 QThread 中扫描 `plugins/`，导入单文件插件或包含 `__init__.py` 的插件包，寻找 `IEmotePlugin` 子类并实例化。完成后 Controller 注册到 `PluginAccessor`。

```python
controller.plugins.get("debug")
controller.plugins.debug
```

QML 模式下，访问器会返回安全代理；插件公共方法还会被包装为 QML 可调用 Slot。插件清理由 Controller 的 `cleanup()` 统一协调。

### 任务与音频

- `EmoteTaskDispatcher`：统一异步任务、线程池和任务信号。
- `StreamLipSyncThread`：从音频队列读取数据，计算并平滑嘴型系数。
- `audio_utils.py`：负责音频文件到流式队列的转换。
- `ResourceManager`：管理监视器等辅助窗口和退出清理回调。

## 8. 点击穿透遮罩

`mask_sampler.js` 在前端采样角色非透明区域，使用矩形合并降低数据量，再通过 `receive_render_mask_binary()` 或旧 JSON 接口传到 Python。Controller 将数据转换为 `[[x, y, w, h], ...]`，最后交给 Adapter：

- Qt：构造 `QRegion` 并调用 `setMask()`。
- QML：获取顶层 Window 并设置 Mask。

这是前端渲染逻辑和宿主窗口能力的典型跨层功能。

## 9. 当前真实入口

| 目的 | 文件 |
|---|---|
| Qt Widgets 功能测试 | `python testers/test_qt.py` |
| QML 功能测试 | `python testers/test_qml.py` |
| 点击穿透专项测试 | `python testers/click_through_test.py` |
| Qt SDK 组件 | `from emote_widget import EmoteWidget` |
| QML 后端对象 | `from emote_widget import EmoteWidgetQml` |

当前仓库没有 `run_tests.py`；旧 README 中对它的引用已经过时。

## 10. 当前边界与待确认点

1. `create_emote_widget()` 是适配器工厂，不等同于 `EmoteWidget` Facade。默认 `WidgetAdapter` 需要传入已有的 WebView，因此目前不应把无参数工厂调用当作主入口。
2. Qt 主 HTML 当前通过 `file://` 加载，内部资源使用 `emote://`；QML 路径的 URL 组装不同，文档和代码后续应考虑统一。
3. `docs/系统架构.mmd` 主要描述 Qt 初始化流程，不能单独代表完整 QML 架构。
4. `walkthrough.md` 是审查记录；本文是稳定的架构基线。代码变动后应优先更新本文，再同步 README。
