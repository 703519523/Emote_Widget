# C# / Python 函数级行为一致性矩阵（PSB 解密插件）

本文件随 `plugins/psb_decryption` 发布。插件只打包 PSB/壳/加密/资源转换核心；
渲染后端、Windows DLL/PYD、`__pycache__` 和独立开发构建目录不属于插件运行时。

本文按 C# FreeMote 的函数边界记录 Python 对应实现。状态含义：

- **已验证**：已有 oracle、样本或单元测试证明输入/输出一致。
- **部分验证**：主路径一致，但边界、异常或某些版本尚未覆盖。
- **缺失/差异**：Python 没有对应函数，或已确认行为不同。
- **非目标**：依赖 System.Drawing、插件、Windows 或 MMO 的实现，当前 Python 没有等价运行时。

> 本矩阵只覆盖当前 Python 已实现的 PSB/壳/加密/图像资源转换闭环；不把 C# 全部图像编解码和 MMO 内部函数误报为“已兼容”。

## 1. 编译与 JSON 转换

| C# 函数 | Python 对应 | 输入/输出 | 边界与异常 | 状态 |
|---|---|---|---|---|
| `PsbJsonConverter.ReadJson` | `PsbCompiler._convert_json_values` | JSON 值 -> Python PSB 值 | 深度 256；Int64；非法 scalar | **部分验证**：深度与 Int64 已补齐，非法 `#0x`/resource 语法待测 |
| `PsbJsonConverter.ConvertToken` | `_convert_json_values` + `_collect` | null/bool/int/float/string/list/object -> PSB 表与值 | float32 阈值 `1E-08`、double、资源标记、字符串复用 | **已验证**：现有 120 oracle cases |
| `PsbCompiler.Compile` | `PsbCompiler.compile` | 对象树 -> PSB bytes | v1-v4、optimize、align、资源/字符串合并 | **已验证**：全量 oracle 逐字节通过 |
| `PsbCompiler.Parse` | `PsbReader.parse` | PSB bytes -> 对象树/元数据 | v1-v4、坏 offset、坏数组、checksum | **部分验证**：v1 主路径与关键畸形输入已验证，真实历史文件仍待补 |
| `PsbCompiler.CompileToFile` | 无对应入口 | JSON/resx 路径 -> 文件路径/bytes | `.resx.json` 探测、`.pure/.impure`、Context_FileName、shell | **缺失/差异** |

## 2. PSB Header / Reader

| C# 函数 | Python 对应 | 输入/输出 | 边界与异常 | 状态 |
|---|---|---|---|---|
| `PsbHeader.Load` | `PsbReader._read_header` | bytes -> header | signature、v1-v4、截断、MDF 误判 | **部分验证**：v1-v4 主路径、v1 HeaderLength 纠错已验证 |
| `PsbHeader.GetHeaderLength` | `PsbHeader.expected_length` | version -> 40/44/56 | version <3、=3、>3 | **部分验证**：Python属性对非法版本不单独拒绝 |
| `PsbHeader.UpdateChecksum` | `PsbReader.validate_header_checksum` / compiler header | header -> Adler32 | v3 8 fields；v4 + 3 extra fields | **已验证**：v3/v4 oracle与样本 |
| `PsbHeader.SwitchVersion` | 无对应入口 | header -> header | 仅 v2/v3/v4；是否平移 offset | **缺失** |
| `PsbHeader.ToBytes` | `PsbCompiler._write_header` | fields -> header bytes | v1 HeaderLength 特殊写法 | **部分验证**：compiler与reader v1 主路径已覆盖 |
| `PsbReader._read_array` | C# PSB array reader | array bytes -> values | width 1..8、entry width、截断、超大 count | **部分验证**：v1 关键数组边界已验证 |
| `PsbReader._decode_names` | `PrefixTree.Load` 的 Python内联解码 | trie -> names | 空树、越界、UTF-8 | **部分验证** |
| `PsbReader._unpack` | C# PsbValues unpack | value bytes -> Python值 | null/number/float/double/list/object/resource/未知tag | **部分验证** |

## 3. 加密状态机

| C# 函数 | Python 对应 | 输入/输出 | 边界与异常 | 状态 |
|---|---|---|---|---|
| `PsbStreamContext.Init`/constructor | `PsbStreamContext.__init__` | key -> initial state | uint32 key masking、round/count=0 | **已验证** |
| `PsbStreamContext.Encode` | `PsbStreamContext.encode` | bytes -> XOR bytes + mutated state | 空输入、跨调用、word边界 | **已验证** |
| `PsbStreamContext.FastForward` | `PsbStreamContext.fast_forward` | byte count -> mutated state | C# 是每次右移 1 bit；负数非法 | **已验证**：状态机边界测试 |
| `PsbStreamContext.NextRound` | `PsbStreamContext.next_round` | state -> new uint32 word | 清空当前 word、count 变化 | **已验证**：状态机边界测试 |
| `PsbFile.TestHeaderEncrypted` | `decrypt_psb` header branch | PSB -> encrypted flag | v3/v4 key recovery、坏checksum | **已验证/部分** |
| `PsbFile.TestBodyEncrypted` | `_body_is_encrypted` | bytes/version/offset -> bool | array tag识别、边界末尾 | **部分验证** |

## 4. Shell / RLE

| C# 函数 | Python 对应 | 输入/输出 | 边界与异常 | 状态 |
|---|---|---|---|---|
| `RleCompress.Decompress` | `rle_compress.decompress` | RLE bytes -> raw bytes | align、重复/非重复、截断、actualSize容量语义 | **部分验证**：关键边界已验证；Python 更严格地拒绝截断，C# 可能静默短读 |
| `RleCompress.Compress` | `rle_compress.compress` | raw bytes -> RLE bytes | 空输入、重复上限、尾块不足 align | **部分验证**：关键边界已验证；随机 C# oracle 待补 |
| `MPack.MdfDecompressToStream` | `psb_shell.unwrap_psb` MDF分支 | MDF -> PSB | MDF头、原始长度、坏压缩流 | **部分验证** |
| PSP/LZSS shell | `psb_shell.unwrap_psb` + `_native.unpack_psp` | shell -> raw PSB | frame边界、坏引用、输出长度 | **已验证**：native与fallback parity |
| PSZ/LZ4 shell | `psb_shell.unwrap_psb` | shell -> raw PSB | 截断、依赖缺失、长度不符 | **部分验证** |

## 5. 资源/EMS 转换

| C# 函数族 | Python 对应 | 输入/输出 | 边界与异常 | 状态 |
|---|---|---|---|---|
| `PsbSpecConverter.SwitchSpec` | `adapt_win_psb_to_ems` 的规格转换路径 | PSB tree/resources -> EMS PSB | win/krkr、RGBA/BGRA、RL、资源引用 | **部分验证**：真实样本有覆盖，平台/像素格式不完整 |
| `Krkr2CommonConverter` atlas/timeline | `ems_adapter._convert_krkr_tree_to_ems` 等 | krkr tree -> atlas tree | 空图、超大图、padding、timeline路径 | **部分验证** |
| `DxtUtil.DecompressDxt5` + Win→EMS 通道链 | `dxt_decoder.decompress_dxt5` + `adapt_win_psb_to_ems` | DXT5/BC3 -> RGBA8 resource | alpha 两模式、RGB565、共享资源、非 4 倍数边界 | **已验证**：2048² 真实样本的 Python/C# resource 逐字节一致，SHA-256 `d5d53b...fba96` |
| `DxtUtil.DecompressDxt1/3` | `decompress_dxt1/3` | BC1/BC2 -> RGBA8 | 透明色、4-bit alpha、边缘块 | **部分验证**：算法已移植并有块级测试，尚无 C# 随机 oracle |
| `DxtCodec.Dxt1/3/5Encode` | 无对应 | RGBA/BGRA -> BC1/2/3 | 端点选择、alpha、质量与逐字节输出 | **缺失** |
| `PsbResHelper.LinkExtraResources` | 无完整对应 | resx -> extra resources | flatten arrays、索引空间、相对路径 | **缺失/差异** |
| `PsbResourceJson.ExternalTextures` | `_prepare_root_for_compiler` 部分 | resx external resources -> PSB | 外部图片、插件类型、路径 | **缺失/差异** |

## 6. 已有实现的一致性结论

### 6.1 已达到强一致

- `PsbCompiler.compile`：v1-v4、optimize/align 组合已有 C# compiler oracle，目标用例逐字节一致。
- `PsbStreamContext`：初始化、跨调用 Encode、FastForward、NextRound 状态转换已有边界测试。
- PSP shell：native 与 Python fallback 已做 parity，真实样本解包摘要固定。
- KrKr → EMS：现有真实样本与 C# oracle 整个 PSB 逐字节一致。
- Win RGBA8 → EMS：真实 FlattenArray 样本的主 atlas 与 C# resource 摘要一致，extra resources 保持不变。
- Win DXT5 → EMS：C# 与 Python 输出资源均为 16,777,216 字节且逐字节一致；对象树按值一致。

### 6.2 语义一致但容器字节不一致

DXT5 样本中 Python 与 C# 的对象树值、资源、版本、spec、type、checksum 和数量均一致，但最终 PSB 文件不同：

- Python：17,337,536 字节；
- C#：17,280,928 字节；
- 第一个已确认差异是根对象键的序列化顺序，进而影响 Name/Entry 布局；
- 资源 SHA-256 完全相同，因此不是像素通道或 DXT 解码偏差。

如果要求“播放器语义兼容”，当前结果合格；如果要求“SwitchSpec 输出逐字节复刻”，还需把 C# `PSB.Merge(true)` 的对象排序/重建顺序纳入 oracle。

### 6.3 已知有意差异

- Python Reader/Normalizer 对截断、尾随数据、未知 shell 和不安全 spec 更严格，通常直接拒绝；C# 某些 Stream API 可能短读或依赖插件继续探测。
- Python DXT 解码器要求 payload 长度精确等于块网格大小；C# `BinaryReader` 会在短输入处抛异常，但对尾随字节通常不主动拒绝。严格校验是 canonicalization 的安全策略。
- Python 当前只做解包和规范化，不自动保留原 shell；C# `CompileToFile`/context 支持更多 shell 与文件命名策略。

## 7. TODO 清单

### P0：现有闭环必须补齐的 oracle

- [ ] 给 DXT1/BC1 建立 C# 随机块 oracle，覆盖 `c0 > c1` 与透明 `c0 <= c1` 两种模式。
- [ ] 给 DXT3/BC2 建立 C# 随机块 oracle，覆盖 4-bit alpha 扩展和非 4 倍数尺寸。
- [ ] 将 DXT5 C# 转换纳入自动化 oracle，而不只固定真实样本 resource SHA-256。
- [ ] 对 `RleCompress.Compress/Decompress` 做随机与边界逐字节差分，包括截断和 `actualSize` 行为。
- [ ] 为 PSZ、LZ4、MDF 增加 C# plugin oracle：正常、截断、长度错误、尾随数据、依赖缺失。
- [ ] 补 `_body_is_encrypted` 的 C# 对照样本：仅 Header、仅 Body、Header+Body、误判数组 tag。

### P1：PSB 文件与编译工具能力缺口

- [ ] 实现 `PsbHeader.SwitchVersion` 等价入口，并验证 offset 平移及 v2/v3/v4 checksum。
- [ ] 实现 `PsbFile.Encode/EncodeToBytes/Transfer` 的加密写出、换 key 和 Header/Body position 组合。
- [ ] 实现 `PsbCompiler.CompileToFile` 的 resx 探测、输出命名、shell 保留、Context_FileName 和加密元数据继承。
- [ ] 完整实现 `PsbResourceJson` / `LinkExtraResources`：外部资源、FlattenArray、普通/extra 索引空间、相对路径。
- [ ] 收集真实 PSB v1 历史文件，验证 HeaderLength 修复、NameIndex、对象键和资源表。
- [ ] 判断是否需要复刻 `PSB.Merge(true)` 的对象键顺序，使 DXT5 SwitchSpec 整个 PSB 逐字节一致。

### P2：像素格式与平台转换矩阵

- [ ] DXT1/DXT3 接入 `adapt_win_psb_to_ems`；当前解码函数存在，但 adapter 只接受 RGBA8/DXT5。
- [ ] ASTC 解码（C# `AstcDecoder` / ASTC header）。
- [ ] BC7 解码（C# `Bc7Decoder`）。
- [ ] RGBA4444、RGBA5551、RGBA5650、RGB5A3、A8/L8/A8L8/GA8 等像素格式。
- [ ] PS3 flip、Morton swizzle、PSP/PSV swizzle、RVL tile 和通用 tile/untile。
- [ ] palette/CI4/CI8、palette 像素格式和索引纹理。
- [ ] 验证 win/ems/krkr 之外的 spec 默认像素格式和大小端规则。

### P3：C# 中存在但不属于当前 PSB 核心闭环

- [ ] DXT1/3/5 编码器；除非需要重新压缩回 Win，否则优先级低于解码。
- [ ] MDF/PSZ/LZ4/PSP shell 打包与压缩输出。
- [ ] TLG5/TLG6 图像读写、ASTC/BC7 独立文件工具。
- [ ] System.Drawing 图片导入/导出、缩放、区域复制与图片元数据。
- [ ] 路径辅助、日志、CLI UX 等非格式核心 API。

## 8. 下一轮建议顺序

1. 先扩展 `CompilerOracle` 增加 `dxt-decode` 与 `rle` 子命令，形成小输入、快速、可随机化的差分测试。
2. 把 DXT1/DXT3 接入 EMS adapter，并以 C# resource SHA-256 锁定通道语义。
3. 完成 Shell/RLE/Body encryption 的 P0 oracle。
4. 再做 `CompileToFile`、资源 JSON 和加密写出；这些是从“转换函数”走向完整工具链的关键缺口。
