# EmoteWidget 损坏模型优雅拒绝与健康检查修复计划

## 1. 目标

模型加载必须成为一个有明确状态、可取消、可失败、可恢复的事务。

成功模型继续维持现有行为。结构损坏或运行时不兼容的模型在进入 WASM 前尽量被拒绝；进入 WASM 后才暴露的问题必须通过结构化失败信号返回 Python，不得继续执行 timeline、变量、自省、resize 或插件命令。

对于结构合法但内容可疑的模型，例如没有 timeline、纹理为空、纹理完全透明或几乎没有有效像素，应发出“疑似损坏”警告，但默认不把所有此类情况都当成硬错误，以免误伤静态模型和稀疏 atlas。

## 2. 日志所反映的当前问题

### 2.1 raw PSB 绕过严格验证

`emote_widget/utils/model_normalizer.py` 在检测到文件以 `PSB\0` 开头后直接返回原路径，没有调用 `PsbNormalizer.normalize_data()` 或完整 `PsbReader.parse()`。

结果是：只要签名正确，内部对象、资源引用、纹理长度或资源内容即使已经损坏，也会直接交给 WASM。

### 2.2 模型切换没有进入 LOADING 状态

`EmoteController.load_model()` 目前没有在加载新模型前执行以下操作：

- 将 `_player_is_ready` 设为 false；
- 标记当前加载请求 ID；
- 清理旧模型命令队列；
- 终止或回收旧的 pending queries；
- 禁止插件在新模型就绪前操作 timeline；
- 启动加载超时计时器。

因此，从一个成功模型切换到损坏模型时，控制器仍然认为 player 已就绪。插件和 UI 会继续立即执行 `set_diff_timeline` 等指令。

### 2.3 JS 加载失败只有日志，没有 load failure 协议

`core_renderer.js` 的 `loadNewModel()` catch 分支调用 `handleJsError()`，随后把 `window.emotePlayer` 设为 null。

Python 只收到普通 `on_js_error(message, stack)`，无法知道：

- 哪一个模型请求失败；
- 失败发生在创建 canvas、初始化 runtime、下载数据还是解析模型阶段；
- 当前 player 是否还能继续使用；
- 是否需要重载 Web 页面；
- 是否应撤销 UI 和插件状态。

### 2.4 失败后发生连锁空引用

加载失败后，timeline/UI/plugin 指令继续执行，形成：

- `Cannot set properties of null (setting 'diffTimelineSlot1')`；
- `Cannot set properties of null (setting 'diffTimelineSlot2')`；
- resize 继续调用已经 abort 的 Emscripten runtime；
- 同一个根错误被重复记录多次，掩盖首个有效错误。

### 2.5 Emscripten abort 可能污染整个 runtime

日志中的 `abort()` 和 `abort(22)` 不一定只损坏当前 player 对象。Emscripten Module 进入 abort 状态后，创建新的 `EmotePlayer` 也可能继续失败。因此不能只执行 `window.emotePlayer = null`，必须区分可恢复异常与 runtime fatal abort。

## 3. 总体架构

引入四层防护：

1. 文件和 PSB 结构预检；
2. 内容健康检查；
3. 有请求 ID 的 JS/Python 加载事务；
4. WASM fatal 后的 renderer 恢复。

每次模型加载生成唯一 `load_id`，所有成功、失败、超时和异步查询都必须携带该 ID。过期回调直接忽略。

建议定义以下控制器状态：

- IDLE：没有模型；
- VALIDATING：Python 正在预检；
- LOADING：JS/WASM 正在加载；
- INTROSPECTING：模型对象已创建，正在查询变量和运行时健康；
- READY：允许模型命令；
- FAILED：当前加载已失败，拒绝模型命令；
- RECOVERING：Web renderer 正在重新初始化。

不要再使用单个 `_player_is_ready` 同时表达页面就绪、模型加载中、模型加载失败和模型已就绪。

## 4. 第一阶段：加载前 PSB 预检

### 4.1 新建独立健康检查模块

建议文件：

`emote_widget/utils/model_health.py`

建议数据结构：

- `ModelHealthSeverity`: info、warning、error；
- `ModelHealthIssue`: code、severity、message、path、details；
- `ModelHealthReport`: accepted、issues、summary、parsed；
- `ModelValidationError`: 携带稳定错误码和用户可读消息。

健康检查模块只负责解析和判断，不直接弹窗，也不依赖具体 UI。

### 4.2 raw PSB 也必须完整解析

修改 `model_normalizer.py`：

- raw `PSB\0` 不再直接 return；
- 始终执行一次 `PsbReader(data, load_resource_data=False).parse()`；
- 校验 header、offset、array、name、string、entry、resource 范围和 checksum；
- 只有完整结构解析成功后，raw PSB 才可以保留原路径；
- wrapped/converted PSB 在写入缓存前和写入后各验证一次，避免转换器输出损坏文件进入缓存。

### 4.3 硬拒绝条件

以下情况直接拒绝，不进入 WASM：

- 不是可支持的 PSB 或 shell；
- header、offset、array、name trie、string 或 object tree 截断/越界；
- v3/v4 checksum 明确不匹配；
- root 不是可识别对象；
- regular/extra resource offset 和 length 数量不一致；
- 任意资源范围超出文件；
- 被纹理描述符引用的资源索引不存在；
- 被纹理引用的资源长度为 0；
- width/height 非正数或超过安全上限；
- 未压缩 RGBA8 纹理长度不等于 width × height × 4；
- 当前 EMS renderer 明确不支持的 spec/texture layout，且没有可靠转换路径；
- 文件、资源数量、递归深度、纹理尺寸超过配置的防资源耗尽上限。

错误应使用稳定 code，例如：

- PSB_PARSE_FAILED；
- CHECKSUM_MISMATCH；
- RESOURCE_OUT_OF_RANGE；
- TEXTURE_RESOURCE_MISSING；
- TEXTURE_SIZE_MISMATCH；
- UNSUPPORTED_RENDER_LAYOUT；
- MODEL_LIMIT_EXCEEDED。

### 4.4 软警告条件

以下情况默认允许加载，但发送“疑似损坏/不完整”报告：

- motion 模型没有可识别的 motion/timeline 结构；
- 没有变量定义；
- 没有任何纹理描述符；
- 存在未被引用的空资源；
- atlas 纹理完全透明；
- atlas 只有极少量非透明像素；
- 纹理内容全部相同或几乎没有信息量；
- metadata、object、source 等常见区块缺失，但不违反基础格式；
- runtime 所需字段存在可疑值，但无法仅靠静态分析确认损坏。

软警告不能伪装成成功日志，应通过专用 `model.health_warning` 事件和信号传递。

## 5. 纹理健康检查设计

### 5.1 只对可解释格式做像素判断

仅当纹理明确为未压缩 RGBA8/BGRA8，或已有可靠解码器时，才判断 alpha 和颜色内容。

对 RL、DXT、BC7、ASTC 等压缩数据，如果当前检查器不能可靠解码，只记录“像素健康检查已跳过”，不能把压缩字节中的零误判为透明像素。

### 5.2 避免稀疏 atlas 误报

Emote atlas 大面积透明可能是正常现象，因此“透明比例高”不能单独作为损坏结论。

建议规则：

- `alpha_max == 0`：高可信度警告“纹理完全透明”；
- 非透明像素数小于绝对阈值，例如 16 或 64：警告“纹理近乎为空”；
- 非透明覆盖率极低且 alpha 总能量极低：警告；
- 只有透明率高、但仍存在大量有效像素：仅记录统计，不警告；
- 资源长度为 0 或尺寸不匹配：硬错误，不是软警告。

### 5.3 性能策略

- 直接使用 PSB 原始 bytes/memoryview，不复制整张 atlas；
- 大纹理均匀抽样，最多检查约 65536 个像素；
- 对可疑结果再做一次完整 alpha 扫描确认；
- 报告 alpha max、有效像素数、采样覆盖率和是否完整扫描；
- 检查结果按文件 SHA-256 缓存。

## 6. 第二阶段：加载事务与状态隔离

### 6.1 Controller 加载开始时必须原子重置

`EmoteController.load_model()` 在任何路径解析和 JS 调用前：

- 生成新的 `load_id`；
- 状态切到 VALIDATING；
- `_player_is_ready = False`；
- 禁止 `_safe_run` 把普通模型命令无限排队；
- 清空上一次模型的命令队列；
- 将所有 pending query 回调以 `None`/取消状态结束；
- 清空 variable map、mouth param 和当前 runtime metadata；
- 记录 previous_model 和 requested_model，但不要提前把 requested_model 宣布为 current；
- 发出 `model.load_started`。

只有最终 READY 后，才更新 `current_model_filename`。

### 6.2 区分可排队命令和模型命令

当前 `_safe_run` 在未就绪时无条件排队，会让旧插件动作落到新模型上。

建议：

- 页面初始化命令可排队；
- 用户/插件的 timeline、variable、transform 命令在 VALIDATING、LOADING、FAILED、RECOVERING 状态下直接拒绝并返回 false；
- 如确实需要“加载后执行”，命令必须绑定同一个 `load_id`，模型切换后自动丢弃；
- 队列冲刷时每条命令再次校验 load_id 和 player 非 null。

### 6.3 超时

开始 JS 加载后启动单次 QTimer：

- 默认 15 秒，可配置；
- 收到对应 load_id 的 success/failure 后取消；
- 超时触发 MODEL_LOAD_TIMEOUT；
- 过期 JS 回调不改变当前状态。

## 7. 第三阶段：JS/Python 结构化加载协议

### 7.1 Bridge 新增槽和信号

`PythonApiBridge` 新增：

- `on_model_load_succeeded(load_id, health_json)`；
- `on_model_load_failed(load_id, code, message, stack, fatal)`；

普通 `on_js_error` 继续用于非加载期错误，但不能再承担模型事务结果回传。

### 7.2 loadNewModel 接收 load_id

接口改为：

`loadNewModel(modelUrl, loadId)`

成功时回传 load_id 和运行时基础信息；失败时回传：

- LOAD_FETCH_FAILED；
- PLAYER_CREATE_FAILED；
- RUNTIME_INITIALIZE_FAILED；
- MODEL_PARSE_FAILED；
- WASM_ABORT；
- UNKNOWN_LOAD_ERROR。

### 7.3 JS catch 必须完整清理

失败时：

- 禁止调用 player_ready；
- 解除旧 listener；
- 停止 model-specific timer/animation callback；
- 将 `emotePlayer` 安全置空；
- 设置 `window.modelLoadState = 'failed'`；
- resize、mask sampler、interaction handler 首先检查 player 和 runtime 状态；
- 只上报一次首要失败，后续同源错误降级或抑制。

### 7.4 防止 null 连锁错误

所有直接访问 `window.emotePlayer` 的 JS 入口增加统一 guard：

`requireReadyPlayer(operationName)`

如果 player 不可用，返回 false，不抛 TypeError，不调用 WASM。

Python `_safe_run` 也要在非 READY 状态拒绝模型操作，从两端共同防护。

## 8. 第四阶段：WASM abort 后恢复

### 8.1 区分普通加载失败和 fatal abort

以下特征视为 fatal：

- 错误消息含 `abort()` 或 `abort(number)`；
- Emscripten Module 的 ABORT 状态已置位；
- 初始化、framebuffer resize 等核心导出函数抛出 abort；
- player 重建探针失败。

普通模型解析失败只回到 FAILED；fatal abort 进入 RECOVERING。

### 8.2 renderer 重载接口

在 `IViewAdapter` 增加可选 `reload_renderer()`：

- Qt Adapter：调用 WebEngine page reload 或重新 setUrl；
- QML Adapter：通过 QML wrapper 重载内部 WebView；
- 无实现的 adapter 返回 false，并提示需要重启视图。

重载过程中：

- 不自动重试造成 abort 的同一个模型；
- 等页面和 QWebChannel 重新就绪；
- 恢复背景、画质和非模型 UI 设置；
- 状态回到 IDLE；
- 用户可以选择其他模型继续加载。

这比仅设置 `window.emotePlayer = null` 更可靠，因为 Emscripten runtime 本身可能已经不可复用。

## 9. 第五阶段：运行时健康探针

静态预检无法确认所有语义问题，因此 player 创建成功后，在发出最终 READY 前执行轻量探针。

建议检查：

- `mainTimelineLabels` 是否存在及数量；
- diff timelines 是否可查询；
- variables 是否可查询；
- chara bounds 是否有限且宽高为正；
- playerId/initialized 是否有效；
- 连续两帧渲染是否成功；
- 可选 framebuffer alpha 抽样是否完全透明。

结果分级：

- player 未 initialized、bounds 为 NaN、渲染调用 abort：加载失败；
- timeline 为 0：疑似损坏警告，默认允许静态模型；
- variables 为 0：警告；
- framebuffer 连续多帧完全透明：警告；
- 静态纹理和 framebuffer 都完全透明：提升为高可信度警告；
- 用户配置 strict mode 时，可把指定 warning 升级为拒绝。

最终顺序应改为：

JS 模型数据加载成功 -> 运行时健康探针 -> Python introspection -> READY -> 发出 player_ready。

不能在模型对象刚创建时就把 `_player_is_ready` 设为 true。

## 10. 用户提示与事件

核心 SDK 不直接依赖 QMessageBox。新增信号和事件：

- `model_load_started(path, load_id)`；
- `model_health_warning(path, issues)`；
- `model_load_failed(path, code, message, recoverable)`；
- `model_load_succeeded(path, report)`；
- `renderer_recovery_started()`；
- `renderer_recovered(success)`。

Qt/QML 示例应用订阅这些信号：

- 硬错误：弹出一次明确提示，“模型已拒绝加载，应用仍可继续使用”；
- 软警告：显示“模型疑似不完整”，列出没有 timeline、纹理完全透明等原因，并允许继续；
- fatal abort：提示“渲染器正在恢复”，恢复后允许选择其他模型；
- 清空旧 timeline、diff timeline 和参数面板，禁止旧控件继续发送命令。

日志必须首先记录一个根错误，随后记录一次状态转换，避免同一失败刷出大量 null 错误。

## 11. 插件隔离

插件是日志中 diffTimelineSlot 连锁错误的重要来源。

计划：

- Controller 非 READY 时，所有模型操作返回 false；
- event bus 发出 `model.load_failed` 后，behavior plugin 清空当前 animation state；
- 新模型开始加载时发出 `model.unloading`；
- 插件只在匹配 load_id 的 `player.ready` 后恢复驱动；
- 旧模型 timer/callback 必须取消；
- 插件错误不能改变 Controller 的加载状态。

## 12. 测试计划

### 12.1 Python 单元测试

- raw PSB signature 正确但 header 截断；
- checksum mismatch；
- resource offset 越界；
- texture resource index 不存在；
- texture length 为 0；
- RGBA8 长度与尺寸不符；
- root 缺少 object/source；
- 无 timeline；
- 无 variables；
- 全透明纹理；
- 稀疏但有效 atlas，不应误报为完全透明；
- 压缩纹理跳过 alpha 判断；
- 大 atlas 使用抽样而非完整复制。

### 12.2 Controller 状态机测试

- READY -> load bad model -> FAILED；
- FAILED 状态的 timeline 命令被拒绝且不排队；
- 新 load 清除旧 pending queries；
- 过期 success/failure 回调被忽略；
- timeout 只触发一次；
- failure 后不发 player_ready；
- warning 模型仍可进入 READY；
- current_model 只在成功后切换；
- 插件 timer 不会操作失败 player。

### 12.3 JS 测试

- promiseLoadDataFromURL reject；
- EmotePlayer constructor throw；
- Emscripten abort；
- catch 后不再触发 resize/WASM 调用；
- failure 回调含正确 load_id；
- null player guard 不抛 TypeError；
- 同一错误只上报一次。

### 12.4 集成测试

按顺序加载：

1. 正常模型；
2. 结构损坏模型；
3. 正常模型；
4. 无 timeline 模型；
5. 全透明模型；
6. 会触发 WASM abort 的模型；
7. renderer 恢复后再次加载正常模型。

成功标准：应用进程不退出、无 null 连锁刷屏、UI 状态与当前模型一致、损坏模型只产生一次明确提示、fatal 后可恢复加载其他模型。

## 13. 推荐实施顺序

### ✅ P0：先阻止连锁异常（已完成 - 2026-07-23）

1. ✅ Controller 引入加载状态和 load_id；
2. ✅ load 开始立即设为非 READY 并清队列；
3. ✅ 非 READY 时模型命令直接拒绝；
4. ✅ Bridge 增加结构化 load failure；
5. ✅ JS null guard；
6. ✅ UI 收到失败后清空模型相关控件。

P0 完成后，即使预检还不完善，损坏模型也不会继续产生 diffTimelineSlot 连锁错误。

**实施文件**:
- `emote_widget/core/controller.py`: 状态机(_model_state)、load_id、命令拒绝逻辑
- `emote_widget/core/python_api_bridge.py`: 结构化加载结果信号(model_load_succeeded/failed)
- `emote_widget/web_frontend/js/core_renderer.js`: requireReadyPlayer guard、fatal 检测

### ✅ P1：加载前硬预检（已完成 - 2026-07-23）

1. ✅ raw PSB 也执行完整 parse；
2. ✅ 检查资源范围和纹理引用；
3. ✅ 校验未压缩纹理尺寸；
4. ✅ 添加安全上限（16384x16384）；
5. ✅ 输出稳定错误码。

**实施文件**:
- `emote_widget/utils/model_health.py`: 完整健康检查逻辑（179行）
- `emote_widget/utils/model_normalizer.py`: raw PSB 验证集成（第38行）
- `emote_widget/utils/paths.py`: 健康报告传递机制

### ⏳ P2：疑似损坏警告（部分完成 - 2026-07-23）

1. ✅ timeline/variable/source 检查（已实施）；
2. ✅ 全透明/近空纹理检查（零拷贝alpha扫描已实施）；
3. ⏸️ 运行时 bounds 和 framebuffer 探针（JS基础设施就绪，待详细探针）；
4. ⏸️ UI warning 展示和 strict mode（信号就绪，待UI组件）。

**已完成**: 静态健康警告（NO_TIMELINE_DATA, NO_VARIABLE_DATA, TEXTURE_FULLY_TRANSPARENT等）
**待完成**: 运行时探针详细逻辑、示例应用UI组件

### ⏸️ P3：fatal runtime 自动恢复（基础设施就绪 - 2026-07-23）

1. ✅ abort 分类（JS fatal正则检测已实施）；
2. ⏸️ adapter reload_renderer（接口预留，待实现）；
3. ⏸️ QWebChannel 重连（recovering状态支持，待连接逻辑）；
4. ⏸️ 恢复非模型设置；
5. ⏸️ 完整集成测试（待真实损坏模型）。

**已完成**: fatal检测、recovering状态
**待完成**: reload_renderer在各adapter的实现、完整恢复流程

## 14. 不建议的做法

- 不要只在 Python 日志里捕获 `Unknown error occurred`；
- 不要在 catch 后只把 `emotePlayer` 设为 null；
- 不要把所有未就绪命令无条件排队；
- 不要把“没有 timeline”一律视为硬损坏；
- 不要仅凭压缩纹理原始字节判断透明度；
- 不要在核心 SDK 内强制弹 QMessageBox；
- 不要自动重试刚刚使 WASM abort 的同一文件；
- 不要在加载开始时提前覆盖 `current_model_filename`。

## 15. 最终验收标准

- 损坏 PSB 尽量在 WASM 前被明确拒绝；
- JS/WASM 加载失败会产生单次、结构化、可定位的错误；
- 失败模型不会触发 player_ready、自省或 UI 填充；
- timeline、变量和插件命令不会访问 null player；
- 无 timeline、空纹理、全透明/近空纹理产生分级警告；
- 稀疏但有效的 atlas 不被简单透明率规则误杀；
- fatal abort 后 renderer 可恢复，应用可继续加载其他模型；
- 正常模型加载行为和性能没有明显退化；
- 所有状态转换、错误码和健康报告均有自动化测试。
