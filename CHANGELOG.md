# 更新日志

## 2026-07-24 — Plugin System v2 与模型加载稳健性

### 后续更新：freemote-py 插件化

- 将 `freemote-py` 的 PSB builder/compiler/reader、shell、crypto、RLE、DXT 和 EMS 转换核心合并到 `plugins/psb_decryption`。
- 将 `function_parity_matrix.md` 随插件维护，明确已验证、部分验证及缺失能力；不再把渲染后端当作 PSB 插件运行时依赖。
- 保留插件现有 Rust/PyO3 PSP 解包 ABI，并为未来的 PSB 对象打包、字符串表 native 能力增加可选 facade；旧扩展仍可正常回退。
- 明确排除 `backends/`、Windows DLL/PYD、`__pycache__` 和独立开发用 Rust 目录，避免把 dev 产物打入插件。

### 新增

- 新增模型健康检查与结构化加载成功、失败、警告信号。
- 新增插件启用状态持久化、运行时重载入口及 Qt 测试器管理界面。
- 新增 `example` 示例插件，完整演示生命周期、Controller 信号、EventBus、Middleware 与 Qt UI。
- 新增 PSB 解密插件限制文档：`docs/PSB_DECRYPTION_PLUGIN_LIMITATIONS.md`。
- 新增模型加载稳健性设计记录：`docs/model_load_robustness_plan.md`。

### 变更

- 将原 `debug` 示例插件更名为 `example`，并同步代码、测试器与架构文档引用。
- 明确 EventBus 仅用于通知，数据流干预应使用 Middleware。
- 明确说明猴子补丁会破坏模块边界和卸载安全，正式插件中不建议使用。
- core 仅接受并严格验证 pure/raw `PSB\0`；脱壳、解密与 Win/KrKr→EMS 转换由 `psb_decryption` 插件负责。
- Web 前端改为候选 Player 事务：新模型完全就绪后才替换旧 Player，非致命失败恢复旧模型。
- WebAssembly 内存允许增长，以支持较大的模型资源。

### 修复

- 修复模型验证、资源解析或运行时加载失败后旧模型状态丢失的问题。
- 修复过期模型加载回调污染当前状态的问题，并加入 15 秒加载超时。
- 修复 Player 重复销毁、设备引用计数错误及缺失 `EmoteDevice.destroy()` 导致的 native/WebGL 资源释放异常。
- 修复默认对话框主题异步加载完成前被误报为结构无效的问题。
- 修复原 debug 示例插件 Controller 初始化判断反向的问题。

### 测试

- 增加模型健康检查、旧模型恢复、候选 Player 生命周期、设备释放、插件状态与 example 插件回归测试。
- 损坏的边界条件 PSB 继续按预期被严格拒绝，不放宽 core 校验。