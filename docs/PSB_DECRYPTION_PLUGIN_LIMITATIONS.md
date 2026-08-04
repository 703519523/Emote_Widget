# PSB 解密插件：当前不足与待改进项

本文档只记录 `plugins/psb_decryption` 的已知限制，供后续维护插件时使用。
这些能力属于插件边界，**不应为了绕过限制而改动 core/raw widget 的 PSB 校验**。

## 1. 支持范围有限

当前中间件主要覆盖：

- PSB shell：PSZ、LZ4、PSP、MDF；
- PSB 解密：插件内置的已知算法和 key 推断路径；
- 平台转换：`win` / `krkr` 到 `ems`；
- 纹理转换：受限的 RGBA8 / RL 资源。

未知 shell、未知加密变体、非预期版本或新的平台资源布局会被拒绝，当前没有通用探测或自动修复能力。

## 2. 解密失败与明文 PSB 的区分仍不够明确

`PsbDecryptionMiddleware.process()` 在 `decrypt_psb()` 抛出 `PsbCryptoError` 时，会把数据继续交给 core normalizer：

```python
except PsbCryptoError:
    return next(data)
```

这对纯明文 PSB 兼容性有帮助，但也会把“未知加密格式、错误 key、损坏文件”延迟到后面的 PSB parser 才失败，日志不够直接。

后续可考虑补充结构化诊断字段，例如：

- `crypto_status`: `not_encrypted` / `decrypted` / `unsupported` / `invalid`；
- 使用过的 shell、版本、key 来源；
- 是否建议用户检查文件损坏，而不是继续尝试 core 解析。

## 3. 损坏输入的资源消耗风险

shell 解包、解密和 PSB 解析之前缺少统一的资源预算策略。恶意或损坏头部可能声明很大的解压长度、资源长度或纹理尺寸。

当前虽然有边界校验，但仍建议增加：

- shell 解压最大输出字节数；
- 单个资源最大长度；
- 纹理宽高与 `width * height * 4` 的溢出/上限校验；
- 总资源内存预算；
- 超限时使用明确的 `RESOURCE_LIMIT_EXCEEDED` 错误码。

## 4. LZ4 依赖处理不统一

LZ4 shell 依赖可选的 Python `lz4` 包；缺少依赖时才在运行期报错。建议在插件初始化或能力探测接口中提前报告：

- 是否有 native PSP backend；
- 是否安装 LZ4；
- 当前可用的 shell 类型。

这样 UI 可以在加载模型前给出清晰提示，而不是等到模型加载时失败。

## 5. Win/KrKr 到 EMS 的转换格式覆盖不足

`ems_adapter.py` 只接受安全可转换的纹理布局，明确拒绝未知 texture type、未知 compression 和无法识别的 texture descriptor。这是安全选择，但当前不足包括：

- 不支持更多压缩格式；
- 不支持所有纹理色彩布局；
- atlas 重编译可能改变资源顺序、边界 padding 或元数据细节；
- 缺少针对每一种平台版本的 golden fixture 回归集。

建议为每一种受支持的 spec / texture layout 增加脱敏 fixture、转换前后摘要和 EMS runtime 加载测试。

## 6. 插件运行时依赖与 native backend 可诊断性不足

插件目前通过包内 `_native` 模块优先使用 native backend，并保留 Python fallback。需要进一步明确：

- native `.pyd` 的 ABI、Python 版本和架构要求；
- native backend 加载失败的具体原因；
- fallback 是否会带来明显性能下降；
- native 与 Python 实现结果一致性的测试方式。

建议将 backend 选择结果写入结构化日志，但不要记录密钥或模型隐私数据。

## 7. 错误恢复边界

插件中间件失败后通常继续执行 core normalizer。对于“明确不是 raw PSB”的数据，继续下游解析会产生二次错误堆栈，增加诊断噪声。

后续可按错误类型区分：

- 明确是纯 raw PSB：允许继续；
- shell 已识别但解包失败：直接返回插件错误；
- 解密结果头部非法：直接返回插件错误；
- 输入损坏：返回可识别的 validation error。

但无论如何，不能为了让流程继续而放宽 core 对纯 raw `PSB\0` 的硬校验。

## 8. 测试覆盖不足

当前测试主要覆盖正常 shell、部分转换和错误回退。仍需补充：

- 截断 shell；
- 声明长度与实际长度不一致；
- 整数溢出和极大尺寸；
- 错误 key / 错误版本；
- 重复资源引用；
- extra resource 与 regular resource 混用；
- 多次初始化/清理插件；
- native backend 与 Python fallback 的一致性；
- 插件失败后下一个正常模型能否继续加载。

## 建议优先级

1. **高优先级**：统一资源预算与极大长度保护；明确解密失败分类；补充损坏输入回归测试。
2. **中优先级**：完善 native/fallback 能力报告和错误上下文。
3. **低优先级**：扩展纹理格式和平台版本支持，并为每类格式建立 golden fixture。
