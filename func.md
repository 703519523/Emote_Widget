# EmoteWidget 功能详解

> 本文档详细说明 EmoteWidget SDK 的所有功能模块及其技术实现原理。

## 目录

1. [核心架构](#1-核心架构)
2. [模型加载与自动转换](#2-模型加载与自动转换)
3. [多框架支持](#3-多框架支持)
4. [Python-JavaScript 通信](#4-python-javascript-通信)
5. [渲染与交互](#5-渲染与交互)
6. [高级功能](#6-高级功能)
7. [插件系统](#7-插件系统)
8. [开发工具](#8-开发工具)

---

## 1. 核心架构

### 1.1 Controller-Adapter 模式

**功能说明**：EmoteWidget 采用 Controller-Adapter 架构，将业务逻辑与 UI 框架彻底解耦。

**实现原理**：
- **EmoteController**（`emote_widget/core/controller.py`）：核心控制器，包含所有业务逻辑
- **IViewAdapter**（`emote_widget/core/adapter_interface.py`）：抽象接口，定义 UI 层必须实现的能力
- **具体 Adapter**：`WidgetAdapter`（Qt Widgets）、`QmlAdapter`（Qt Quick）

**技术细节**：
```python
class IViewAdapter(ABC):
    @abstractmethod
    def run_javascript(self, script: str) -> None: pass
    
    @abstractmethod
    def register_python_bridge(self, bridge_obj: Any, name: str) -> None: pass
    
    @abstractmethod
    def set_window_transparent(self, transparent: bool) -> None: pass
    
    @abstractmethod
    def set_render_mask(self, rects: List[List[int]]) -> None: pass
```

Controller 只依赖抽象接口，不知道底层是 QWidget 还是 QML，实现了真正的框架无关。

### 1.2 AdapterRegistry 注册机制

**功能说明**：支持动态注册和切换不同的 UI 适配器。

**实现原理**（`emote_widget/core/adapter_registry.py`）：
```python
class AdapterRegistry:
    _adapters: Dict[str, Type[IViewAdapter]] = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(adapter_cls):
            cls._adapters[name] = adapter_cls
            return adapter_cls
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type[IViewAdapter]:
        return cls._adapters[name]
```

**使用示例**：
```python
@AdapterRegistry.register("my_framework")
class MyAdapter(IViewAdapter):
    # 实现接口方法
    pass

# 使用时
AdapterCls = AdapterRegistry.get("my_framework")
```

### 1.3 资源管理器

**功能说明**：统一管理辅助窗口和清理任务的生命周期。

**实现位置**：`emote_widget/core/resource_manager.py`

**技术细节**：
- 自动跟踪所有创建的辅助窗口（调试器、监视器等）
- 注册清理回调，确保资源正确释放
- 在程序退出时统一执行清理操作

```python
class ResourceManager:
    def register_window(self, widget: WindowProtocol) -> None:
        self._windows.append(widget)
    
    def register_cleanup_task(self, callback: CleanupCallback) -> None:
        self._cleanup_tasks.append(callback)
    
    def shutdown(self) -> None:
        # 关闭所有窗口并执行清理任务
```

---

## 2. 模型加载与自动转换

### 2.1 非 Pure PSB 自动转换（核心新功能）

**功能说明**：用户可直接加载 LZ4/MDF 包装的 Win 平台模型，无需外部工具预转换。

**实现位置**：
- `emote_widget/utils/model_normalizer.py` - 模型规范化入口
- `emote_widget/utils/psb_converter/` - PSB 处理工具集
  - `psb_shell.py` - Shell 检测与脱壳
  - `psb_reader.py` - PSB 结构解析
  - `ems_adapter.py` - Win → EMS 平台适配
  - `normalizer.py` - 完整规范化流程

**技术实现流程**：

```
用户输入: wrapped_model.psb
    ↓
检测 Shell 类型 (detect_shell)
    ↓
LZ4 Frame/MDF 脱壳 (unwrap_psb)
    ↓
解析 PSB 结构 (PsbReader)
    ↓
检查 spec 字段
    ↓ (spec=win)
执行平台适配 (adapt_win_psb_to_ems)
  - 交换纹理 R/B 通道
  - 修改 spec 为 ems
  - 重新计算 checksum
    ↓
写入内容寻址缓存
    ↓
返回缓存路径给 WebEngine
```

**关键代码**（`model_normalizer.py`）：
```python
def normalize_model_path(path: StrPath, *, 
                        cache_root: StrPath = ".emote_cache/normalized_models") -> Path:
    source = Path(path).resolve()
    
    # Raw PSB\0 文件保持原样，兼容已有 spec=ems 模型
    if detect_shell(source.read_bytes()) == "raw":
        return source
    
    # 脱壳
    result = PsbNormalizer(source).normalize_with_summary()
    normalized_data = result.data
    
    # 如果是 Win 平台，自动适配为 EMS
    if result.summary.get("spec") == "win":
        normalized_data = adapt_win_psb_to_ems(normalized_data)
    
    # 内容寻址缓存
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    target = cache_dir / f"{source.stem}.{source_digest}.pure.psb"
    
    if not target.exists() or target.read_bytes() != normalized_data:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(normalized_data)
        os.replace(temporary, target)
    
    return target
```

### 2.2 Win → EMS 平台适配

**功能说明**：将 Win 平台的 RGBA8 纹理模型转换为 EMS 驱动可识别的格式。

**实现位置**：`emote_widget/utils/psb_converter/ems_adapter.py`

**安全边界**：
- ✅ 支持：未压缩 RGBA8 纹理（资源长度 = width × height × 4）
- ❌ 拒绝：DXT 等压缩纹理、资源尺寸不匹配、未知 spec

**技术细节**：

1. **纹理通道转换**：
```python
# 交换 R 和 B 通道（Win BGRA → EMS RGBA）
pixels = converted[start:end]
red = pixels[0::4]
pixels[0::4] = pixels[2::4]  # R ← B
pixels[2::4] = red           # B ← R
```

2. **Spec 字段修改**：
```python
# 在字符串表中找到 "win\0" 并原位替换为 "ems\0"
for offset in reader.string_offsets:
    pos = string_start + offset
    if bytes(converted[pos:pos + 4]) == b"win\0":
        converted[pos:pos + 4] = b"ems\0"
```

3. **Checksum 验证**：
```python
# PSB v3+ 自动重新计算 Adler32 checksum
verified = PsbReader(result).parse()
if verified["spec"] != "ems" or verified["checksum_valid"] is False:
    raise PsbBadFormatError("EMS adaptation failed validation")
```

### 2.3 内容寻址缓存

**功能说明**：转换后的模型缓存在 `.emote_cache/normalized_models/`，避免重复转换。

**缓存策略**：
- 文件名格式：`{原文件名}.{SHA256前16位}.pure.psb`
- 原文件内容变化会导致摘要改变，自动生成新缓存
- 使用原子写入（临时文件 + `os.replace`），避免并发冲突

**测试覆盖**：
- 单元测试：`tests/test_model_normalizer.py::test_real_lz4_win_rgba8_model_is_adapted_for_ems_driver`
- 集成验证：实际 WebEngine + FreeMoteDriver 加载成功

---

## 3. 多框架支持

### 3.1 Qt Widgets 集成

**功能说明**：传统 QWidget 应用的开箱即用组件。

**实现位置**：`emote_widget/ui/views/widget_qt.py`

**使用方式**：
```python
from emote_widget import EmoteWidget

widget = EmoteWidget()
widget.resize(800, 600)
widget.show()
widget.load_model("chara.psb")
```

**技术实现**：
- `EmoteWidget` 继承自 `QWidget`
- 内部创建 `QWebEngineView` 作为渲染容器
- 通过 `WidgetAdapter` 桥接到 `EmoteController`
- 直接暴露 Controller 的信号和方法

### 3.2 Qt Quick/QML 集成

**功能说明**：支持在 QML 应用中嵌入 Emote 角色。

**实现位置**：
- Python: `emote_widget/ui/views/widget_qml.py` (EmoteWidgetQml)
- QML: `qml_tester/qml/` (示例组件)

**使用方式**：

Python 端：
```python
from emote_widget import EmoteWidgetQml

backend = EmoteWidgetQml()
engine.rootContext().setContextProperty("EmoteBackend", backend)
```

QML 端：
```qml
WebEngineView {
    id: webView
    Component.onCompleted: {
        EmoteBackend.targetView = webView
        EmoteBackend.notifyPageLoadFinished(true)
    }
}
```

**技术特点**：
- QML WebEngineView 延迟创建，通过 `targetView` 属性动态绑定
- 使用 `QmlAdapter` 调用 QML 对象的 `runJavaScript` 方法
- 所有信号和方法自动暴露给 QML（通过 `@Property` / `@Signal` / `@Slot`）

### 3.3 自定义框架扩展

**功能说明**：通过插件机制支持任意 GUI 框架（Tkinter、CEF Python 等）。

**实现步骤**：

1. 实现 `IViewAdapter` 接口
2. 使用 `@AdapterRegistry.register()` 注册
3. 通过 `create_emote_widget()` 工厂函数创建

**示例**：
```python
@AdapterRegistry.register("cef")
class CefAdapter(IViewAdapter):
    def run_javascript(self, script: str) -> None:
        self.browser.ExecuteJavascript(script)
    
    def register_python_bridge(self, bridge_obj, name: str) -> None:
        # CEF JavaScript Binding
        pass
    
    # 实现其他接口...

# 使用
ui, controller = create_emote_widget(adapter_name="cef")
```

---

## 4. Python-JavaScript 通信

### 4.1 自定义 emote:// 协议

**功能说明**：通过自定义 URL Scheme 安全加载本地资源，无需禁用 CORS。

**实现位置**：
- 注册：`emote_widget/__init__.py` (`_register_custom_scheme`)
- 处理：`emote_widget/core/scheme_handler.py` (EmoteSchemeHandler)

**技术细节**：
```python
# 协议注册（必须在 QApplication 之前）
scheme = QWebEngineUrlScheme(b"emote")
scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
scheme.setFlags(
    QWebEngineUrlScheme.Flag.SecureScheme |
    QWebEngineUrlScheme.Flag.LocalScheme |
    QWebEngineUrlScheme.Flag.CorsEnabled
)
QWebEngineUrlScheme.registerScheme(scheme)
```

**安全机制**（`emote_widget/utils/paths.py`）：
- 白名单验证：只允许访问已注册的安全路径
- 路径规范化：防止 `../` 等路径遍历攻击
- 自动注册 SDK 内部资源和用户添加的资源目录

### 4.2 QWebChannel 双向通信

**功能说明**：实现 Python 和 JavaScript 之间的双向方法调用。

**实现位置**：`emote_widget/core/python_api_bridge.py`

**通信流程**：

Python → JavaScript：
```python
# Controller 通过 Adapter 执行 JS
controller._safe_run("emoteAPI.play('Hello')")
```

JavaScript → Python：
```javascript
// JS 通过 QWebChannel 调用 Python
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.py_api = channel.objects.py_api;
    py_api.on_player_ready(timelines);
});
```

**暴露的 Python 接口**（通过 `@Slot` 装饰器）：
- `on_player_ready(timelines: List[str])` - 播放器就绪通知
- `receive_query_result(request_id, result_json)` - 异步查询结果
- `js_on_character_click()` - 角色点击事件
- `receive_render_mask_binary(data)` - 遮罩数据传输

### 4.3 异步查询机制

**功能说明**：解决 WebEngine 异步执行导致的结果回传时序问题。

**实现位置**：`emote_widget/core/controller.py` (`_safe_query`)

**技术原理**：
```python
def _safe_query(self, expression: str, callback: Optional[Callable]) -> None:
    request_id = str(uuid.uuid4())
    self._pending_queries[request_id] = callback
    
    js = f'''
        (function() {{
            try {{
                const result = {expression};
                py_api.receive_query_result("{request_id}", JSON.stringify(result));
            }} catch(e) {{
                py_api.receive_query_result("{request_id}", null);
            }}
        }})();
    '''
    self._safe_run(js)

# JS 执行完成后回调
def _handle_query_result(self, request_id: str, result_json: str) -> None:
    callback = self._pending_queries.pop(request_id, None)
    if callback:
        result = json.loads(result_json) if result_json else None
        callback(result)
```

**使用示例**：
```python
def on_timelines_received(timelines):
    print(f"模型有 {len(timelines)} 个动画")

controller.get_main_timelines(callback=on_timelines_received)
```

---

## 5. 渲染与交互

### 5.1 透明窗口与点击穿透

**功能说明**：实现真正的透明背景和像素级点击穿透。

**实现位置**：
- Controller: `emote_widget/core/controller.py` (`set_window_transparent`)
- Adapter: `emote_widget/ui/adapters/qt_adapter.py` (`set_render_mask`)
- 前端: `emote_widget/web_frontend/js/mask_sampler.js`

**技术实现**：

1. **窗口透明**：
```python
# Qt Widgets
self.setAttribute(Qt.WA_TranslucentBackground)
self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

# WebEngine 背景
page.setBackgroundColor(QColor(0, 0, 0, 0))
```

2. **遮罩采样**（前端 JavaScript）：
```javascript
// 在 Canvas 上采样角色非透明区域
const imageData = ctx.getImageData(0, 0, width, height);
const pixels = imageData.data;

for (let i = 3; i < pixels.length; i += 4) {
    if (pixels[i] > alphaThreshold) {
        // 记录不透明像素位置
    }
}

// 合并为矩形并传回 Python
py_api.receive_render_mask_binary(packedData);
```

3. **应用遮罩**（Python）：
```python
def set_render_mask(self, rects: List[List[int]]) -> None:
    region = QRegion()
    for rect in rects:
        x, y, w, h = rect
        region += QRegion(x, y, w, h)
    self.view.setMask(region)
```

### 5.2 视线跟随与鼠标拖动

**功能说明**：角色眼睛跟随鼠标，支持拖动改变位置。

**实现位置**：`emote_widget/web_frontend/pyside_webview.html`

**技术实现**：

视线跟随：
```javascript
document.addEventListener('mousemove', (e) => {
    if (!gazeEnabled) return;
    const dx = e.clientX - centerX;
    const dy = e.clientY - centerY;
    const gazeX = Math.max(-1, Math.min(1, dx / gazeRange));
    const gazeY = Math.max(-1, Math.min(1, dy / gazeRange));
    emoteAPI.setGaze(gazeX, gazeY);
});
```

鼠标拖动：
```javascript
let isDragging = false;
let dragStartX, dragStartY;

characterElement.addEventListener('mousedown', (e) => {
    if (!dragEnabled) return;
    isDragging = true;
    dragStartX = e.clientX - currentX;
    dragStartY = e.clientY - currentY;
});

document.addEventListener('mousemove', (e) => {
    if (isDragging) {
        currentX = e.clientX - dragStartX;
        currentY = e.clientY - dragStartY;
        updateTransform();
    }
});
```

**Python API**：
```python
controller.enable_gaze_control(True)   # 启用视线跟随
controller.enable_drag(True)           # 启用拖动
controller.set_coord(x, y, duration_ms=100)  # 设置位置
```

---

## 6. 高级功能

### 6.1 口型同步（Lip Sync）

**功能说明**：根据音频自动驱动角色嘴型，支持文件和实时流式音频。

**实现位置**：
- 核心线程：`emote_widget/core/lipsync_thread.py` (StreamLipSyncThread)
- 音频工具：`emote_widget/utils/audio_utils.py`
- Controller 接口：`start_lip_sync` / `start_lip_sync_from_file`

**技术原理**：

1. **双指数移动平均（Dual EMA）**：
```python
# 快速响应张嘴
ema_fast = alpha_fast * current_rms + (1 - alpha_fast) * ema_fast
# 缓慢跟随闭嘴
ema_slow = alpha_slow * current_rms + (1 - alpha_slow) * ema_slow

open_ratio = (ema_fast - ema_slow) / threshold
open_ratio = max(0.0, min(1.0, open_ratio))
```

2. **文件播放流程**：
```python
def start_lip_sync_from_file(self, filepath: str) -> None:
    audio_queue = queue.Queue()
    
    # 后台线程：音频文件 → 队列
    audio_thread = threading.Thread(
        target=stream_audio_file,
        args=(filepath, audio_queue)
    )
    audio_thread.start()
    
    # 口型分析线程：队列 → 嘴型系数
    lipsync_thread = StreamLipSyncThread(audio_queue, sample_rate=16000)
    lipsync_thread.mouth_ratio_updated.connect(self._on_mouth_ratio_update)
    lipsync_thread.start()
```

3. **实时控制**：
```python
def _on_mouth_ratio_update(self, open_ratio: float) -> None:
    # 找到嘴型参数（通过语义标签）
    mouth_param = self.find_param_by_usage("mouth_open_y")
    if mouth_param:
        # 线性映射到模型变量范围
        value = mouth_param.min_value + open_ratio * (max_value - min_value)
        self.set_variable(mouth_param.label, value, duration_ms=50)
```

**Python API**：
```python
# 从文件播放并同步
controller.start_lip_sync_from_file("voice.wav")

# 手动停止
controller.stop_lip_sync()

# 自定义流式输入
audio_queue = queue.Queue()
controller.start_lip_sync(audio_queue)
```

### 6.2 参数绑定与自省

**功能说明**：自动分析模型变量并建立语义映射，简化参数控制。

**实现位置**：`emote_widget/utils/bound_params.py`

**语义标签系统**：
```python
class SpecialUsage:
    MOUTH_OPEN_Y = "mouth_open_y"
    EYE_OPEN_LEFT = "eye_open_left"
    EYE_OPEN_RIGHT = "eye_open_right"
    EYEBROW_ANGLE_LEFT = "eyebrow_angle_left"
    # ... 更多预定义标签
```

**自动分析流程**：
```python
def analyze_variable_list(raw_variable_list: List[Dict]) -> BoundMap:
    bound_map = []
    
    for var in raw_variable_list:
        label = var["label"].lower()
        frames = var["frameList"]
        
        # 规则匹配：根据变量名识别语义
        if "口" in label or "mouth" in label:
            if "開" in label or "open" in label:
                usage = SpecialUsage.MOUTH_OPEN_Y
        elif "目" in label or "eye" in label:
            # 根据关键词判断左右、开闭
            pass
        
        bound_map.append(BoundMapItem(
            label=var["label"],
            usage=usage,
            min_value=frames[0]["value"],
            max_value=frames[-1]["value"]
        ))
    
    return bound_map
```

**缓存机制**：
- 首次自省结果缓存到 `.emote_cache/bound_params/{model_name}.json`
- 用户可手动编辑缓存文件调整映射
- 调用 `save_bindings()` 保存当前映射

**使用示例**：
```python
# 通过语义标签查找参数
mouth_param = controller.find_param_by_usage("mouth_open_y")
if mouth_param:
    controller.set_variable(mouth_param.label, 0.8)

# 查看所有可用标签
tags = controller.get_available_special_usage_tags()
```

### 6.3 任务调度器

**功能说明**：统一管理异步任务、线程池和任务信号。

**实现位置**：`emote_widget/core/task_dispatcher.py`

**技术特点**：
- 单例模式，全局共享线程池
- 支持任务成功/失败/进度回调
- 内置节流器，避免高频任务过载
- 自动异常捕获和清理

**使用示例**：
```python
dispatcher = EmoteTaskDispatcher()

def heavy_task(param):
    # 耗时操作
    result = process_data(param)
    return result

def on_success(result):
    print(f"任务完成: {result}")

def on_error(e):
    print(f"任务失败: {e}")

# 调度异步任务
dispatcher.dispatch(
    task_name="data_processing",
    fn=heavy_task,
    args=("input",),
    on_success=on_success,
    on_error=on_error,
    task_type=TaskType.RESOURCE_SCAN
)
```

**节流控制**：
```python
throttle = TaskThrottle(limit_ms=500)

if throttle.should_proceed("resource_scan"):
    # 执行任务
    pass
else:
    # 跳过，距上次执行不足 500ms
    pass
```

---

## 7. 插件系统

### 7.1 插件接口

**功能说明**：允许用户扩展 SDK 功能，注入自定义逻辑。

**实现位置**：`emote_widget/core/plugin_interface.py`

**插件基类**：
```python
class IEmotePlugin(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """插件唯一标识"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """插件描述"""
        pass
    
    @abstractmethod
    def initialize(self):
        """初始化回调，可访问 self.controller"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理回调"""
        pass
```

### 7.2 插件加载机制

**功能说明**：自动扫描 `plugins/` 目录，异步加载插件模块。

**实现位置**：`emote_widget/core/plugin_system.py`

**加载流程**：
```python
class PluginLoaderWorker(QObject):
    def scan_for_plugin_modules(self) -> None:
        for entry in os.listdir(self.plugin_dir):
            path = os.path.join(self.plugin_dir, entry)
            
            if os.path.isfile(path) and entry.endswith(".py"):
                # 单文件插件
                module_name = entry[:-3]
                spec = importlib.util.spec_from_file_location(module_name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._find_plugin_classes(module)
            
            elif os.path.isdir(path) and "__init__.py" in os.listdir(path):
                # 包插件
                package_name = os.path.basename(path)
                spec = importlib.util.spec_from_file_location(
                    package_name, 
                    os.path.join(path, "__init__.py")
                )
                # ... 同样的加载逻辑
```

**插件访问**：
```python
# 通过 Controller 访问插件
controller.plugins.get("behavior_engine")
controller.plugins.behavior_engine  # 属性访问

# QML 安全代理（自动包装为 Slot）
qml_proxy = controller.plugins._qml_proxies["debug"]
```

### 7.3 内置插件示例

#### behavior_engine 插件

**功能**：基于 Perlin Noise 的自主行为引擎。

**实现位置**：`plugins/behavior_engine/main.py`

**技术原理**：
```python
def _behavior_loop(self):
    while self.running:
        t = time.time() * self.config["speed"]
        
        # 使用 Perlin Noise 生成平滑的随机值
        blink_noise = noise.pnoise1(t * 0.5)
        head_x_noise = noise.pnoise1(t * 0.3 + 100)
        head_y_noise = noise.pnoise1(t * 0.3 + 200)
        
        # 映射到模型参数
        if blink_noise > self.config["blink_threshold"]:
            self.trigger_blink()
        
        # 更新头部摆动
        self.controller.set_variable("head_x", head_x_noise)
        self.controller.set_variable("head_y", head_y_noise)
```

#### debug 插件

**功能**：提供调试工具和日志输出。

**实现位置**：`plugins/debug/main.py`

**主要功能**：
- 监听所有 Controller 信号
- 输出详细日志
- 提供调试命令接口

---

## 8. 开发工具

### 8.1 内置 Python 控制台

**功能说明**：在测试平台中提供交互式 Python 终端，直接调用 Controller API。

**实现位置**：`testers/test_qt.py` (EmbeddedTerminal)

**技术实现**：
```python
class EmbeddedTerminal(QWidget):
    def __init__(self, controller):
        self.controller = controller
        self.console = QTextEdit()
        self.input = QLineEdit()
        
        # 创建受限的执行环境
        self.namespace = {
            'controller': controller,
            'np': np,
            'time': time
        }
    
    def execute_command(self, command: str):
        try:
            result = eval(command, self.namespace)
            self.console.append(f">>> {command}\n{result}")
        except:
            try:
                exec(command, self.namespace)
            except Exception as e:
                self.console.append(f"Error: {e}")
```

**使用示例**：
```python
# 在终端中输入
controller.play("Hello")
controller.set_scale(1.5)
controller.get_main_timelines(lambda t: print(len(t)))
```

### 8.2 参数监视器

**功能说明**：实时查看和修改模型变量，保存参数绑定配置。

**实现位置**：`emote_widget/ui/common/variable_monitor.py`

**主要功能**：
- 表格显示所有模型变量
- 拖动滑块实时调整参数值
- 编辑语义标签（SpecialUsage）
- 一键保存到缓存

### 8.3 口型调试窗口

**功能说明**：可视化音频输入和嘴型系数，辅助调试口型同步。

**实现位置**：`emote_widget/ui/common/lipsync_debug.py`

**显示内容**：
- 实时音频波形
- RMS 能量曲线
- 快速/慢速 EMA 曲线
- 最终嘴型开合系数

---

## 总结

EmoteWidget SDK 通过精心设计的架构实现了以下核心能力：

1. **开箱即用**：支持直接加载 LZ4/MDF/Win 平台模型
2. **框架无关**：Controller-Adapter 架构支持任意 GUI 框架
3. **安全可靠**：自定义协议、路径白名单、异步查询机制
4. **功能丰富**：口型同步、参数绑定、插件系统、透明穿透
5. **易于扩展**：清晰的接口定义和插件机制

所有功能都经过实际项目验证，并提供完整的测试平台（`testers/test_qt.py` 和 `testers/test_qml.py`）供开发者参考和测试。

---

**文档版本**: v1.0  
**最后更新**: 2026-07-22  
**维护者**: EmoteWidget 开发团队


