# 插件系统 v2 架构设计与实施指南

## 📋 目录

1. [设计目标](#设计目标)
2. [核心机制](#核心机制)
3. [架构设计](#架构设计)
4. [实施计划](#实施计划)
5. [API 参考](#api-参考)
6. [插件开发指南](#插件开发指南)
7. [集成点清单](#集成点清单)

---

## 设计目标

### 当前问题

现有插件系统功能受限：
- ❌ 只能调用有限的 Controller API
- ❌ 无法干预核心数据流
- ❌ 无法在执行流程中注入逻辑
- ❌ 插件能力不足以实现复杂功能

### 目标

实现 **Minecraft Mod 级别**的插件扩展能力：
- ✅ 插件可监听任意生命周期事件
- ✅ 插件可干预和修改数据流
- ✅ 插件可在关键位置注入逻辑
- ✅ 保持向后兼容性

---

## 核心机制

### 1. EventBus（事件总线）

**用途**：生命周期事件和业务通知

**特点**：
- 单向广播，松耦合
- 不改变数据流，仅通知
- 线程安全（基于 Qt Signal）

**适用场景**：
- 监听模型加载完成
- 监听播放器就绪
- 监听动画播放/完成
- 监听参数改变

**示例**：
```python
from emote_widget.core.event_bus import event_bus

# 订阅事件
event_bus.on("model.loaded", lambda data: print(f"模型已加载: {data['path']}"))

# 触发事件
event_bus.emit("model.loaded", {"path": "chara.psb", "size": 1024})
```

### 2. Middleware（中间件链）

**用途**：数据流水线干预

**特点**：
- 可检查、修改、替换数据
- 责任链模式，按顺序执行
- 可中断流水线

**适用场景**：
- PSB 解密
- 参数验证和转换
- 资源预处理
- 数据格式转换

**示例**：
```python
from emote_widget.core.middleware import Middleware, MiddlewareManager

class DecryptionMiddleware(Middleware):
    def process(self, data, next):
        if self._is_encrypted(data["path"]):
            data["path"] = self._decrypt(data["path"])
        return next(data)

# 注册中间件
chain = MiddlewareManager.get_chain("psb.normalize")
chain.use(DecryptionMiddleware())
```

### 3. Monkey Patch（隐藏功能）

**用途**：高级用户暴力替换函数

**特点**：
- 直接替换任意函数
- 风险高，不写入文档
- 仅供高级用户使用

**示例**：
```python
import emote_widget.utils.model_normalizer as normalizer

original_func = normalizer.normalize_model_path

def patched_func(path, **kwargs):
    print(f"[Patch] Intercepting: {path}")
    return original_func(path, **kwargs)

normalizer.normalize_model_path = patched_func
```

---

## 架构设计

### 系统层次

```
┌─────────────────────────────────────┐
│          Plugin Layer               │ ← 插件开发者
├─────────────────────────────────────┤
│   EventBus    │    Middleware       │ ← 插件系统 v2
├─────────────────────────────────────┤
│        Controller & Utils           │ ← 核心代码
├─────────────────────────────────────┤
│      Qt WebEngine & JavaScript      │ ← 渲染层
└─────────────────────────────────────┘
```

### 数据流示例

**模型加载流程（集成事件和中间件）**：

```
Controller.load_model("model.psb")
    ↓
event_bus.emit("model.before_load", {...})  ← 事件1
    ↓
paths.resolve_resource_url()
    ↓
model_normalizer.normalize_model_path()
    ↓
MiddlewareManager.get_chain("psb.normalize").execute(data)  ← 中间件链
    ├→ Middleware 1: 日志记录
    ├→ Middleware 2: 解密
    ├→ Middleware 3: 平台转换
    └→ 返回处理后的数据
    ↓
加载到 WebEngine
    ↓
event_bus.emit("model.loaded", {...})  ← 事件2
    ↓
event_bus.emit("player.ready", {...})  ← 事件3
```

---

## 实施计划

### Phase 1: 基础设施 ✅（已完成）

**文件**：
- ✅ `emote_widget/core/event_bus.py`
- ✅ `emote_widget/core/middleware.py`
- ✅ `examples/plugin_system_v2_example.py`

**功能**：
- ✅ EventBus 单例实现
- ✅ Middleware 责任链实现
- ✅ 使用示例文档

### Phase 2: 核心集成 🚧（进行中）

#### 输入边界约定

- 核心模型加载器在没有扩展插件时只接受 raw/pure `PSB\0`。
- Shell 脱壳、加密解密、平台适配等属于插件能力，不应重新耦合回核心。
- 插件通过 `psb.normalize` Middleware 提供 `normalized_data`，再由核心完成结构校验和缓存。
- 当前参考扩展：`plugins/psb_decryption/`，负责 Shell、XorShift128 和 Win→EMS 适配。

#### 2.1 Controller 事件集成

**文件**：`emote_widget/core/controller.py`

**事件触发点**：

| 事件名 | 触发时机 | 数据 |
|--------|---------|------|
| `model.before_load` | 开始加载模型 | `{"path": str}` |
| `model.loaded` | 模型加载完成 | `{"path": str, "info": dict}` |
| `player.ready` | 播放器初始化完成 | `{"timelines": list, "parameters": list}` |
| `animation.play` | 开始播放动画 | `{"name": str, "timeline": str}` |
| `animation.complete` | 动画播放完成 | `{"name": str, "duration": float}` |
| `parameter.changed` | 参数值改变 | `{"name": str, "value": float}` |
| `controller.cleanup` | 控制器清理 | `{}` |

**实施步骤**：
1. 在 `controller.py` 顶部导入 `event_bus`
2. 在对应方法中添加 `event_bus.emit()` 调用
3. 确保数据格式一致

#### 2.2 数据流中间件集成

**中间件链清单**：

| 链名称 | 用途 | 集成位置 |
|--------|------|---------|
| `psb.normalize` | PSB 处理流水线 | `model_normalizer.py::normalize_model_path()` |
| `parameter.transform` | 参数转换 | `controller.py::set_parameter()` |
| `resource.preprocess` | 资源预处理 | `paths.py::resolve_resource_url()` |

**实施步骤（以 `psb.normalize` 为例）**：

1. 在 `model_normalizer.py` 导入 `MiddlewareManager`
2. 修改 `normalize_model_path()` 函数：
   ```python
   def normalize_model_path(path: StrPath, **kwargs) -> Path:
       chain = MiddlewareManager.get_chain("psb.normalize")
       
       # 构造上下文
       context = {
           "path": Path(path).resolve(),
           "kwargs": kwargs,
           "shell": None,
           "spec": None,
           "normalized_path": None
       }
       
       # 执行中间件链
       result = chain.execute(context)
       
       # 如果中间件链为空或没有处理，执行默认逻辑
       if result.get("normalized_path") is None:
           result = _default_normalize_logic(context)
       
       return result["normalized_path"]
   ```
3. 提取默认逻辑到 `_default_normalize_logic()` 函数

#### 2.3 插件接口更新

**文件**：`emote_widget/core/plugin_interface.py`

**添加便捷属性**：
```python
from .event_bus import event_bus
from .middleware import MiddlewareManager

class IEmotePlugin(ABC):
    controller: EmoteController
    logger: logging.Logger
    
    @property
    def events(self):
        """便捷访问全局事件总线"""
        return event_bus
    
    @property
    def middleware(self):
        """便捷访问中间件管理器"""
        return MiddlewareManager
    
    # ... 其他方法
```

### Phase 3: 文档更新 📚

- [ ] 更新 `docs/ARCHITECTURE.md`
- [ ] 编写插件开发教程
- [ ] 更新 README.md 插件说明
- [ ] 编写迁移指南

### Phase 4: 测试 🧪

- [ ] 单元测试：EventBus 功能
- [ ] 单元测试：Middleware 链执行
- [ ] 集成测试：实际插件场景
- [ ] 回归测试：现有插件兼容性

### PSB 解密插件迁移状态

- ✅ 解密实现位于 `plugins/psb_decryption/psb_crypto.py`
- ✅ `PsbDecryptionPlugin` 在初始化时注册 `psb.normalize` 中间件
- ✅ 核心 `psb_converter` 不再直接导入解密模块
- ✅ 普通模型不依赖解密插件；加密模型按需启用插件
- ✅ 已用 PSZ v4 样本验证插件链路可生成规范化缓存

---

## API 参考

### EventBus API

```python
from emote_widget.core.event_bus import event_bus

# 订阅事件
event_bus.on(event: str, callback: Callable) -> None

# 触发事件
event_bus.emit(event: str, data: Any = None) -> None

# 取消订阅
event_bus.off(event: str, callback: Callable) -> None

# 清空监听器
event_bus.clear(event: Optional[str] = None) -> None
```

### Middleware API

```python
from emote_widget.core.middleware import Middleware, MiddlewareManager

# 定义中间件
class MyMiddleware(Middleware):
    def process(self, data: Any, next: Callable) -> Any:
        # 处理逻辑
        return next(data)

# 获取中间件链
chain = MiddlewareManager.get_chain(name: str) -> MiddlewareChain

# 注册中间件
chain.use(middleware: Middleware) -> None

# 执行中间件链
result = chain.execute(data: Any) -> Any

# 清空中间件链
MiddlewareManager.clear_chain(name: str) -> None
MiddlewareManager.clear_all() -> None
```

### 插件接口 API

```python
class IEmotePlugin(ABC):
    controller: EmoteController
    logger: logging.Logger
    events: EventBus  # v2 新增
    middleware: MiddlewareManager  # v2 新增
    
    @abstractmethod
    def get_name(self) -> str:
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        pass
    
    @abstractmethod
    def initialize(self):
        """在这里注册事件和中间件"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理资源"""
        pass
```

### 插件启用状态与热重载 API

插件 ID 使用扫描阶段的**模块名**：单文件插件 `plugins/foo.py` 对应 `foo`，包插件
`plugins/foo/__init__.py` 也对应 `foo`。未记录状态的插件默认启用；禁用列表持久化到
插件目录的 `.plugin_state.json`，扫描阶段会在导入和实例化之前跳过禁用模块。

```python
# 仅持久化状态，默认在下次启动时生效
controller.set_plugin_enabled("psb_decryption", False)
controller.is_plugin_enabled("psb_decryption")  # False

# 显式热重载，使最新状态立即生效
accepted = controller.reload_plugins()
```

`reload_plugins()` 是异步操作：它会调用所有当前插件的 `cleanup()`，清空运行时插件
访问器，重新扫描并启动后台加载线程。若插件加载线程仍在运行，该调用返回 `False`，
不会清理当前插件；成功接受请求时返回 `True`。调用方可继续监听
`plugins_load_finished` 获知新一轮初始化完成。

状态变更会广播 `plugin.state_changed`，重载开始会广播 `plugins.reload_started`。
插件若要安全支持热重载，必须在 `cleanup()` 中精确撤销自身的事件订阅、中间件、
线程、定时器和 Monkey patch。

---

## 插件开发指南

### 基础插件模板

```python
from emote_widget.core.plugin_interface import IEmotePlugin
from emote_widget.core.middleware import Middleware

class MyPlugin(IEmotePlugin):
    def get_name(self) -> str:
        return "my_plugin"
    
    def get_description(self) -> str:
        return "我的插件示例"
    
    def initialize(self):
        # 1. 监听事件
        self.events.on("model.loaded", self.on_model_loaded)
        
        # 2. 注册中间件
        chain = self.middleware.get_chain("psb.normalize")
        chain.use(MyMiddleware())
        
        self.logger.info("插件已初始化")
    
    def on_model_loaded(self, data):
        self.logger.info(f"模型已加载: {data['path']}")
    
    def cleanup(self):
        # 清理资源
        self.events.off("model.loaded", self.on_model_loaded)
        self.middleware.clear_chain("psb.normalize")

class MyMiddleware(Middleware):
    def process(self, data, next):
        # 处理数据
        self.logger.debug(f"处理数据: {data}")
        return next(data)
```

### 最佳实践

1. **事件订阅**
   - 在 `initialize()` 中订阅
   - 在 `cleanup()` 中取消订阅
   - 使用实例方法而非 lambda

2. **中间件注册**
   - 考虑执行顺序
   - 处理异常，避免中断流水线
   - 必须调用 `next(data)` 继续流水线

3. **日志记录**
   - 使用 `self.logger` 而非 `print()`
   - 记录关键操作和错误
   - 避免过多日志输出

4. **资源清理**
   - 必须实现 `cleanup()` 方法
   - 清理所有订阅和中间件
   - 释放文件句柄和线程

---

## 集成点清单

### 事件触发点（Controller）

```python
# emote_widget/core/controller.py

def load_model(self, path: str):
    event_bus.emit("model.before_load", {"path": path})
    # ... 加载逻辑
    event_bus.emit("model.loaded", {"path": path, "info": info})

def _on_player_ready(self, timelines):
    # ... 原有逻辑
    event_bus.emit("player.ready", {
        "timelines": timelines,
        "parameters": self._cached_parameters
    })

def play(self, name: str):
    event_bus.emit("animation.play", {"name": name})
    # ... 播放逻辑

def set_parameter(self, name: str, value: float):
    # ... 设置逻辑
    event_bus.emit("parameter.changed", {"name": name, "value": value})

def cleanup(self):
    event_bus.emit("controller.cleanup", {})
    # ... 清理逻辑
```

### 中间件调用点

#### PSB 处理流水线

```python
# emote_widget/utils/model_normalizer.py

def normalize_model_path(path: StrPath, **kwargs) -> Path:
    source = Path(path).resolve()
    
    # 检查是否为 raw PSB
    if detect_shell(source.read_bytes()) == "raw":
        return source
    
    # 执行中间件链
    chain = MiddlewareManager.get_chain("psb.normalize")
    context = {
        "source_path": source,
        "cache_root": kwargs.get("cache_root", ".emote_cache/normalized_models"),
        "normalized_data": None,
        "summary": None
    }
    
    result = chain.execute(context)
    
    # 如果中间件未处理，执行默认逻辑
    if result["normalized_data"] is None:
        result = _execute_default_normalization(result)
    
    # 写入缓存
    return _write_to_cache(result)
```

#### 参数转换流水线

```python
# emote_widget/core/controller.py

def set_parameter(self, name: str, value: float):
    # 执行参数转换中间件
    chain = MiddlewareManager.get_chain("parameter.transform")
    context = {
        "name": name,
        "value": value,
        "transformed_value": value
    }
    
    result = chain.execute(context)
    final_value = result["transformed_value"]
    
    # 设置参数
    self._safe_run(f"window.emoteplayer.set_parameter('{name}', {final_value})")
    
    # 触发事件
    event_bus.emit("parameter.changed", {"name": name, "value": final_value})
```

---

## 总结

### 插件能力对比

| 能力 | v1（旧版） | v2（新版） |
|------|-----------|-----------|
| 调用 API | ✅ | ✅ |
| 监听信号 | ⚠️ 有限 | ✅ 完整 |
| 干预数据流 | ❌ | ✅ 中间件 |
| 注入逻辑 | ❌ | ✅ 事件+中间件 |
| 替换函数 | ❌ | ⚠️ Monkey Patch |

### 下一步

1. ✅ 阅读本文档
2. 🚧 按照 Phase 2 集成事件和中间件
3. 📚 更新相关文档
4. 🧪 编写测试
5. 🚀 发布 v2

---

**文档版本**: 1.0  
**更新时间**: 2026-07-22  
**维护者**: EmoteWidget Team


## 当前 PSB 能力边界

核心规范化器只解析 `PSB\0` 开头的 pure/raw PSB，并负责结构校验、checksum 校验和 spec 验证。LZ4、PSZ、MDF、PSP LZSS 等包装格式的检测与脱壳，以及解密和平台适配，均由 `plugins/psb_decryption/` 提供；未启用该插件时，包装输入会被拒绝。PSP shell 按 FreeMote 规则检查 offset 5 的 `PSB` 特征，并使用 4096-byte 滑动窗口解包。插件初始化时保存自己的 middleware 实例，清理时只移除自身注册，不会清空其他插件的 `psb.normalize` 中间件。

当前插件内的 EMS 适配器同时支持 Win 的 RGBA8 纹理和 KrKr 的 RL 压缩纹理。新版实现同步了完整 `PsbCompiler`：Win 路径会保留普通/额外资源索引空间，仅对纹理描述符引用的 regular RGBA8/RL resource 执行 BGRA→RGBA 通道转换后完整重编译，FlattenArray 等 extra resources 原样保留；KrKr 路径会解压 RL、交换 BGRA 通道、按 C# FreeMote 的 FIFO/MaxOneAxis 规则重新打包图集、展开时间轴并重写 motion 纹理引用，最后重建 v2/v3/v4 PSB header、offset 与 checksum 后输出 `spec=ems`。编译器当前为纯 Python 实现，行为兼容优先，性能敏感部分后续可由 Rust 后端替换。解密算法仍由插件中的独立 crypto 模块负责，适配失败不会被伪装成路径错误。

插件包含可选的 PyO3 原生后端及其 `native-src/` Cargo workspace。当前 native capability 仅为 `psp_lzss_unpack`：Windows x64 随附 `abi3-py310` 扩展，PSP LZSS 会优先直接写入 CPython 最终 `bytes`；扩展缺失、ABI 不兼容或加载失败时自动回退纯 Python，且可通过 `_native.load_error()` 诊断。`PsbCompiler` 仍为纯 Python实现，不能把 PSP 解包加速描述为 Rust PSB 编译器。
