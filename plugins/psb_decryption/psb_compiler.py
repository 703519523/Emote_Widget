"""
PSB Compiler - 完整的 PSB 文件编译器
基于 FreeMote.PsBuild/PsbCompiler.cs 和 FreeMote.Psb/Psb.cs 实现

负责：
1. 收集 Names、Strings、Resources（Collect）
2. 序列化对象树（Pack）
3. 组装完整 PSB 文件（Build）
"""

import io
import struct
from typing import Dict, List, Any, Tuple, Set
from .psb_types import PsbType, PsbDouble, get_size, zip_number_bytes, write_psb_array, calculate_adler32


class PsbCompiler:
    """PSB 编译器 - 将 Python 对象树编译为 PSB 二进制格式"""

    def __init__(self, version: int = 3):
        self.version = version
        self.names: List[str] = []
        self.name_to_index: Dict[str, int] = {}
        self.strings: List[str] = []
        self.string_to_index: Dict[str, int] = {}
        self.resources: List[bytes] = []
        self.extra_resources: List[bytes] = []
        self.optimize = True

    def compile(self, obj: Any, merge_strings: bool = True, merge_resources: bool = False,
                optimize: bool = True) -> bytes:
        """
        编译对象树为 PSB 二进制数据

        Args:
            obj: 要编译的根对象（通常是 dict）
            merge_strings: 是否合并相同的字符串
            merge_resources: 是否合并相同的资源数据

        Returns:
            PSB 二进制数据
        """
        # 1. 收集所有 Names、Strings、Resources
        self._collect(obj, merge_strings, merge_resources)

        # 2. 构建 PSB
        self.optimize = optimize
        return self._build(obj)

    def _collect(self, obj: Any, merge_strings: bool, merge_resources: bool):
        """收集所有需要的 Names、Strings、Resources"""
        self.names.clear()
        self.name_to_index.clear()
        self.strings.clear()
        self.string_to_index.clear()
        self.resources.clear()
        self.extra_resources.clear()

        name_set: Set[str] = set()
        name_usages: Dict[str, int] = {}
        string_usages: Dict[str, int] = {}
        string_list: List[Tuple[str, int]] = []  # (value, original_index)
        resource_map: Dict[bytes, int] = {} if merge_resources else None

        def travel_collect(o: Any, depth: int = 0) -> Any:
            """遍历对象树收集数据"""
            if o is None:
                return None
            elif isinstance(o, bool):
                return o
            elif isinstance(o, (int, float)):
                return o
            elif isinstance(o, str):
                # 收集字符串
                if merge_strings:
                    if o not in self.string_to_index:
                        idx = len(self.strings)
                        self.strings.append(o)
                        self.string_to_index[o] = idx
                        string_usages[o] = 0
                    else:
                        string_usages[o] += 1
                else:
                    if o not in self.string_to_index:
                        idx = len(string_list)
                        string_list.append((o, idx))
                        self.string_to_index[o] = idx
                return o
            elif isinstance(o, bytes):
                # 收集资源
                if merge_resources and resource_map is not None:
                    if o in resource_map:
                        return ('resource', resource_map[o])
                    else:
                        idx = len(self.resources)
                        self.resources.append(o)
                        resource_map[o] = idx
                        return ('resource', idx)
                else:
                    idx = len(self.resources)
                    self.resources.append(o)
                    return ('resource', idx)
            elif isinstance(o, list):
                # 遍历列表
                for item in o:
                    travel_collect(item, depth + 1)
                return o
            elif isinstance(o, dict):
                # 收集字典的键（Names）并遍历值
                if '_type' in o and o['_type'] == 'resource':
                    # 特殊标记：资源引用
                    idx = int(o.get('index', 0))
                    is_extra = bool(o.get('is_extra', False))
                    data = o.get('data')
                    target = self.extra_resources if is_extra else self.resources
                    if data is not None:
                        if merge_resources and resource_map is not None:
                            if data in resource_map:
                                return ('resource', resource_map[data])
                            else:
                                if idx >= len(target):
                                    # 扩展资源列表
                                    target.extend([b''] * (idx - len(target) + 1))
                                target[idx] = data
                                resource_map[data] = idx
                                return ('resource', idx)
                        else:
                            if idx >= len(target):
                                target.extend([b''] * (idx - len(target) + 1))
                            target[idx] = data
                            return ('resource', idx)
                    return ('resource', idx)

                for key, value in o.items():
                    # 收集键名
                    if not key.startswith('_'):  # 跳过内部标记
                        name_set.add(key)
                        if key in name_usages:
                            name_usages[key] += 1
                        else:
                            name_usages[key] = 0
                    # 遍历值
                    travel_collect(value, depth + 1)
                return o
            else:
                # 未知类型，尝试作为字符串处理
                return travel_collect(str(o), depth)

        # 执行收集
        travel_collect(obj)

        # 构建 Names 列表（排序以匹配 C# 行为）
        # String.CompareOrdinal compares UTF-16 code units, not Unicode code
        # points or UTF-8 bytes. Big-endian UTF-16 bytes preserve that order.
        if merge_strings and merge_resources:
            # PsbCompiler.Compile calls Merge(true), whose Collect(...,
            # sortString:false) orders names by descending occurrence count.
            # LINQ OrderByDescending is stable, preserving first traversal
            # order for equal counts.
            self.names = sorted(name_usages, key=lambda s: -name_usages[s])
        else:
            self.names = sorted(
                name_set, key=lambda s: s.encode('utf-16-be', errors='surrogatepass')
            )
        self.name_to_index = {name: idx for idx, name in enumerate(self.names)}

        if merge_strings and merge_resources:
            self.strings.sort(key=lambda s: -string_usages[s])
            self.string_to_index = {
                value: index for index, value in enumerate(self.strings)
            }

        # Debug: 打印收集统计
        print(f"[Compiler] Collected: {len(self.names)} names, {len(self.strings)} strings, {len(self.resources)} resources")
        if self.resources:
            total_size = sum(len(r) for r in self.resources)
            print(f"[Compiler] Total resource size: {total_size} bytes, avg: {total_size//len(self.resources)} bytes")

        # 如果不合并字符串，需要从 string_list 重建
        if not merge_strings:
            self.strings = [s for s, _ in string_list]

    def _build(self, obj: Any) -> bytes:
        """构建完整的 PSB 二进制文件"""
        output = io.BytesIO()

        # C# PsbHeader.GetHeaderLength(): v2=40, v3=44, v4=56.
        # 注意：HeaderLength 本身是 +8 的字段，不能把 Names offset 写到这里。
        header_len = 40 if self.version <= 2 else (44 if self.version == 3 else 56)
        output.write(b'\x00' * header_len)

        # 1. 编译 Names 区块
        offset_names = output.tell()
        self._write_names(output)
        print(f"[Build] Names: {offset_names} -> {output.tell()} ({output.tell() - offset_names} bytes)")

        # 2. 编译 Entries 区块（对象树）
        offset_entries = output.tell()
        self._pack(output, obj)
        print(f"[Build] Entries: {offset_entries} -> {output.tell()} ({output.tell() - offset_entries} bytes)")

        # 3. 编译 Strings 区块
        offset_strings = output.tell()
        offset_strings_data = self._write_strings(output)
        print(f"[Build] Strings: {offset_strings} -> {output.tell()} ({output.tell() - offset_strings} bytes)")
        print(f"[Build] Strings Data starts at: {offset_strings_data}")

        # 4. 编译 Resources 区块
        # C# ToStream writes the v4 extra offset/length arrays even when the
        # list is empty.  Leaving these header fields at zero makes the
        # loader fall back to Dullahan and mis-detect the regular chunk area.
        if self.version >= 4:
            offset_extra_chunk_offsets, offset_extra_chunk_lengths, offset_extra_chunk_data = \
                self._write_resources(output, self.extra_resources)
        else:
            offset_extra_chunk_offsets = 0
            offset_extra_chunk_lengths = 0
            offset_extra_chunk_data = 0

        offset_chunk_offsets, offset_chunk_lengths, offset_chunk_data = \
            self._write_resources(output, self.resources)
        print(f"[Build] Resources - Offsets: {offset_chunk_offsets}, Lengths: {offset_chunk_lengths}, Data: {offset_chunk_data}")
        print(f"[Build] Total file size: {output.tell()}")

        # 5. 写入 Header
        self._write_header(
            output, header_len, offset_names, offset_strings, offset_strings_data,
            offset_entries, offset_chunk_offsets, offset_chunk_lengths, offset_chunk_data,
            offset_extra_chunk_offsets, offset_extra_chunk_lengths, offset_extra_chunk_data
        )

        return output.getvalue()

    def _write_names(self, output: io.BytesIO):
        """Write the v1 name table or the v2+ UTF-8 trie name table."""
        if self.version == 1:
            # PSBv1: 直接写字符串
            offsets = []
            names_data = io.BytesIO()
            for name in self.names:
                offsets.append(names_data.tell())
                names_data.write(name.encode('utf-8'))
                names_data.write(b'\x00')

            # 写入 offsets array
            output.write(write_psb_array(offsets))
            # In v1 HeaderLength points to the offsets array while
            # OffsetNames points to the following zero-terminated key data.
            self._v1_offset_names = output.tell()
            # 写入 names data
            output.write(names_data.getvalue())
        else:
            names_data, tree, offsets = self._build_name_trie(self.names, getattr(self, 'optimize', True))
            output.write(write_psb_array(offsets))
            output.write(write_psb_array(tree))
            output.write(write_psb_array(names_data))

    @staticmethod
    def _build_name_trie(
        names: List[str], optimize: bool = False, _select_layout: bool = True
    ) -> Tuple[List[int], List[int], List[int]]:
        """Port PrefixTree.Build(..., optimize:false) from the C# library.

        The PSB trie stores UTF-8 bytes (not Unicode code points).  Index 0 is
        the root.  ``tree[id]`` stores the parent id and ``offsets[id]`` is
        the base used to recover a byte as ``id - offsets[parent]``.
        """
        # PrefixTree.Build in C# builds both allocators in OptimizeMode and
        # selects whichever has the smaller serialized representation.
        if optimize and _select_layout:
            optimized = PsbCompiler._build_name_trie(names, True, False)
            legacy = PsbCompiler._build_name_trie(names, False, False)

            def serialized_size(layout: Tuple[List[int], List[int], List[int]]) -> int:
                name_ids, tree_values, offset_values = layout
                return sum(len(write_psb_array(values)) for values in (
                    offset_values, tree_values, name_ids
                ))

            return optimized if serialized_size(optimized) <= serialized_size(legacy) else legacy

        class Node:
            __slots__ = ("char", "parent", "children", "begin", "id")

            def __init__(self, char: int = 0, parent: "Node | None" = None):
                self.char = char
                self.parent = parent
                self.children: Dict[int, "Node"] = {}
                self.begin = 0
                self.id = 0

        root = Node()
        # InsertTree: each name ends with a zero terminal node.
        for value in names:
            node = root
            for byte in value.encode("utf-8") + b"\x00":
                node = node.children.setdefault(byte, Node(byte, node))

        tree: List[int] = [0]
        offsets: List[int] = [1]
        results: Dict[str, int] = {}

        def set_value(values: List[int], index: int, value: int) -> None:
            if index >= len(values):
                values.extend([0] * (index + 1 - len(values)))
            values[index] = value

        def node_string(node: Node) -> str:
            data: List[int] = []
            cur = node.parent
            while cur is not None and cur.parent is not None:
                data.append(cur.char)
                cur = cur.parent
            data.reverse()
            return bytes(data).decode("utf-8")

        def make_tree(node: Node) -> None:
            if node.parent is root:
                node.id = node.char + offsets[0]
            else:
                node.id = node.char - min(node.parent.children) + node.parent.begin
            set_value(tree, node.id, node.parent.id)

        # This is the occupancy allocator from PrefixTree.BuildOptimized in
        # the C# implementation.  It deliberately processes children in
        # byte order and probes the first free range, so the resulting arrays
        # are deterministic and compatible with the runtime.
        occupancy: List[bool] = [True]
        first_vacant = 1

        def expand(index: int) -> None:
            while len(occupancy) <= index:
                occupancy.append(False)
            while len(tree) <= index:
                tree.append(0)

        def mark(index: int) -> None:
            expand(index)
            occupancy[index] = True

        def optimized_branch(node: Node) -> None:
            nonlocal first_vacant
            children = sorted(node.children.values(), key=lambda n: n.char)
            if not children:
                return
            minimum = children[0].char
            rel = [child.char - minimum for child in children]
            candidate = max(first_vacant, minimum + 1)
            while True:
                conflict = False
                for delta in rel:
                    pos = candidate + delta
                    if pos < len(occupancy) and occupancy[pos]:
                        conflict = True
                        break
                if not conflict:
                    break
                candidate += 1
            for child, delta in zip(children, rel):
                child.id = candidate + delta
                mark(child.id)
                set_value(tree, child.id, node.id)
                if child.char == 0:
                    index = names.index(node_string(child))
                    set_value(offsets, child.id, index)
                    results[node_string(child)] = child.id
            set_value(offsets, node.id, candidate - minimum)
            first_vacant = 1
            while first_vacant < len(occupancy) and occupancy[first_vacant]:
                first_vacant += 1
            for child in children:
                if child.char != 0:
                    optimized_branch(child)

        def make_offset(node: Node) -> None:
            if node.char == 0:
                set_value(offsets, node.id, names.index(node_string(node)))
                return
            if not node.children:
                return
            chars = sorted(node.children)
            minimum, maximum = chars[0], chars[-1]
            position = len(tree)
            if position <= maximum or position <= minimum:
                set_value(tree, maximum, 0)
                position = len(tree)
            node.begin = position
            set_value(tree, position + maximum - minimum, 0)
            set_value(offsets, node.id, position - minimum)

        def branch(node: Node) -> None:
            children = sorted(node.children.values(), key=lambda n: n.char)
            for child in children:
                make_tree(child)
            for child in children:
                make_offset(child)
            for child in children:
                branch(child)
            for child in children:
                if child.char == 0:
                    results[node_string(child)] = child.id

        if optimize:
            optimized_branch(root)
        else:
            branch(root)
        return [results[name] for name in names], tree, offsets

    def _write_strings(self, output: io.BytesIO) -> int:
        """写入 Strings 区块，返回 strings data 的起始位置"""
        offsets = []
        strings_data = io.BytesIO()

        if getattr(self, 'optimize', False):
            # C# orders by descending character count and stores every string
            # as a suffix of an already written longer string when possible.
            written: Dict[str, Tuple[int, bytes]] = {}
            ordered = sorted(self.strings, key=lambda s: len(s), reverse=True)
            offsets = [0] * len(self.strings)
            for value in ordered:
                raw = value.encode('utf-8') + b'\x00'
                found = None
                for previous, (base, previous_raw) in written.items():
                    if len(previous_raw) >= len(raw) and previous_raw.endswith(raw):
                        found = base + len(previous_raw) - len(raw)
                        break
                index = self.string_to_index[value]
                if found is None:
                    found = strings_data.tell()
                    strings_data.write(raw)
                    written[value] = (found, raw)
                offsets[index] = found
        else:
            for s in self.strings:
                offsets.append(strings_data.tell())
                strings_data.write(s.encode('utf-8'))
                strings_data.write(b'\x00')

        # 写入 offsets array
        output.write(write_psb_array(offsets))

        # 记录 strings data 起始位置
        offset_strings_data = output.tell()

        # 写入 strings data
        output.write(strings_data.getvalue())

        return offset_strings_data

    def _write_resources(self, output: io.BytesIO, resources: List[bytes]) -> Tuple[int, int, int]:
        """
        写入 Resources 区块

        Returns:
            (offset_chunk_offsets, offset_chunk_lengths, offset_chunk_data)
        """
        # 收集资源的偏移和长度
        offsets = []
        lengths = []
        resources_data = io.BytesIO()

        for res in resources:
            offsets.append(resources_data.tell())
            lengths.append(len(res))
            resources_data.write(res)

        # 写入 offsets array
        offset_chunk_offsets = output.tell()
        output.write(write_psb_array(offsets))

        # 写入 lengths array
        offset_chunk_lengths = output.tell()
        output.write(write_psb_array(lengths))

        # FreeMote's optimized compiler enables PsbDataStructureAlign and
        # aligns the beginning of each resource-data block to 16 bytes.  This
        # applies to the empty v4 extra-resource block as well.
        padding = (-output.tell()) % 16
        if padding:
            output.write(b'\x00' * padding)

        # 写入 resources data
        offset_chunk_data = output.tell()
        output.write(resources_data.getvalue())

        return offset_chunk_offsets, offset_chunk_lengths, offset_chunk_data

    def _pack(self, output: io.BytesIO, obj: Any):
        """序列化对象树为二进制（Pack 方法）"""
        if obj is None:
            # Null
            output.write(bytes([PsbType.NULL]))
        elif isinstance(obj, bool):
            # Bool
            output.write(bytes([PsbType.TRUE if obj else PsbType.FALSE]))
        elif isinstance(obj, int):
            # Number (int/long)
            self._write_number(output, obj)
        elif isinstance(obj, float):
            # Number (float/double)
            self._write_float(output, obj)
        elif isinstance(obj, str):
            # String
            self._write_string(output, obj)
        elif isinstance(obj, bytes):
            # Resource (shouldn't reach here after collect)
            # 在 collect 阶段应该已经转换为 ('resource', idx)
            # 如果到达这里，说明是新资源，添加到资源列表
            idx = len(self.resources)
            self.resources.append(obj)
            self._write_resource(output, idx, False)
        elif isinstance(obj, tuple) and len(obj) == 2 and obj[0] == 'resource':
            # Resource reference
            self._write_resource(output, int(obj[1]), False)
        elif isinstance(obj, list):
            # List
            self._write_list(output, obj)
        elif isinstance(obj, dict):
            # Dictionary or Resource reference
            if '_type' in obj and obj['_type'] == 'resource':
                idx = int(obj.get('index', 0))
                is_extra = bool(obj.get('is_extra', False))
                self._write_resource(output, idx, is_extra)
            else:
                self._write_dict(output, obj)
        else:
            # 未知类型，写入 null
            output.write(bytes([PsbType.NULL]))

    def _write_number(self, output: io.BytesIO, value: int):
        """写入整数"""
        if value == 0:
            output.write(bytes([PsbType.NUMBER_N0]))
            return

        # Preserve the sign bit in the compact two's-complement payload.
        size = self._get_signed_size(value)
        type_byte = PsbType.NUMBER_N0 + size
        output.write(bytes([type_byte]))

        if size > 0:
            data = value.to_bytes(size, byteorder='little', signed=True)
            output.write(data)

    @staticmethod
    def _get_signed_size(value: int) -> int:
        for size in range(1, 9):
            minimum = -(1 << (size * 8 - 1))
            maximum = (1 << (size * 8 - 1)) - 1
            if minimum <= value <= maximum:
                return size
        raise OverflowError(f"PSB signed integer is outside Int64 range: {value}")

    def _write_float(self, output: io.BytesIO, value: float):
        """写入浮点数"""
        if isinstance(value, PsbDouble):
            output.write(bytes([PsbType.DOUBLE]))
            output.write(struct.pack('<d', value))
            return
        # C# emits Float0 only for an exact IEEE zero. Tiny non-zero values
        # in motion control points must retain their Float payload.
        if value == 0.0:
            output.write(bytes([PsbType.FLOAT_0]))
        else:
            # 使用 float (4 bytes)
            output.write(bytes([PsbType.FLOAT]))
            output.write(struct.pack('<f', value))

    def _write_string(self, output: io.BytesIO, value: str):
        """写入字符串引用"""
        if value not in self.string_to_index:
            # 字符串不在表中，添加它
            idx = len(self.strings)
            self.strings.append(value)
            self.string_to_index[value] = idx
        else:
            idx = self.string_to_index[value]

        size = get_size(idx)
        type_byte = PsbType.STRING_N1 + size - 1
        output.write(bytes([type_byte]))
        data = zip_number_bytes(idx, size)
        output.write(data)

    def _write_resource(self, output: io.BytesIO, index: int, is_extra: bool):
        """写入资源引用"""
        size = get_size(index)
        if is_extra:
            type_byte = PsbType.EXTRA_CHUNK_N1 + size - 1
        else:
            type_byte = PsbType.RESOURCE_N1 + size - 1
        output.write(bytes([type_byte]))
        data = zip_number_bytes(index, size)
        output.write(data)

    def _write_list(self, output: io.BytesIO, items: List[Any]):
        """写入列表（List/Collection）"""
        output.write(bytes([PsbType.LIST]))

        # 收集所有子对象
        offsets = []
        items_data = io.BytesIO()

        null_offset = true_offset = false_offset = None
        number_offsets: Dict[Tuple[type, Any], int] = {}
        string_offsets: Dict[str, int] = {}
        resource_offsets: Dict[Tuple[int, bool], int] = {}
        object_seen: Dict[bytes, int] = {}
        for item in items:
            start = items_data.tell()
            self._pack(items_data, item)
            end = items_data.tell()
            raw = items_data.getvalue()[start:end]
            reuse = None
            cache = None
            cache_key: Any = None
            if getattr(self, 'optimize', False):
                if item is None:
                    reuse, cache, cache_key = null_offset, 'null', None
                elif isinstance(item, bool):
                    reuse, cache, cache_key = (true_offset if item else false_offset), 'bool', item
                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                    cache, cache_key = 'number', (type(item), item)
                    reuse = number_offsets.get(cache_key)
                elif isinstance(item, str):
                    cache, cache_key = 'string', item
                    reuse = string_offsets.get(item)
                elif isinstance(item, dict) and item.get('_type') == 'resource':
                    cache = 'resource'
                    cache_key = (int(item.get('index', 0)), bool(item.get('is_extra', False)))
                    reuse = resource_offsets.get(cache_key)
                else:
                    cache, cache_key = 'object', raw
                    reuse = object_seen.get(raw)
            if reuse is not None:
                items_data.seek(start)
                items_data.truncate()
                offsets.append(reuse)
            else:
                offsets.append(start)
                if getattr(self, 'optimize', False):
                    if cache == 'null':
                        null_offset = start
                    elif cache == 'bool':
                        if cache_key:
                            true_offset = start
                        else:
                            false_offset = start
                    elif cache == 'number':
                        number_offsets[cache_key] = start
                    elif cache == 'string':
                        string_offsets[cache_key] = start
                    elif cache == 'resource':
                        resource_offsets[cache_key] = start
                    elif cache == 'object':
                        object_seen[raw] = start

        # 写入 offsets array
        output.write(write_psb_array(offsets))

        # 写入 items data
        output.write(items_data.getvalue())

    def _write_dict(self, output: io.BytesIO, obj: Dict[str, Any]):
        """写入字典（Objects/Dictionary）"""
        if self.version == 1:
            self._write_dict_v1(output, obj)
            return

        output.write(bytes([PsbType.OBJECTS]))

        sorted_keys = [k for k in obj.keys() if not k.startswith('_')]
        if getattr(self, 'optimize', False):
            self._dotnet_introsort(sorted_keys, lambda k: self._write_priority(obj[k]))
        else:
            sorted_keys.sort()

        # 收集 name indexes
        name_indexes = []
        for key in sorted_keys:
            if key in self.name_to_index:
                name_indexes.append(self.name_to_index[key])
            else:
                # 键不在 names 表中，添加它
                idx = len(self.names)
                self.names.append(key)
                self.name_to_index[key] = idx
                name_indexes.append(idx)

        # 收集所有值的偏移
        offsets = []
        values_data = io.BytesIO()

        seen: Dict[bytes, int] = {}
        for key in sorted_keys:
            start = values_data.tell()
            self._pack(values_data, obj[key])
            end = values_data.tell()
            raw = values_data.getvalue()[start:end]
            if getattr(self, 'optimize', False) and raw in seen:
                values_data.seek(start)
                values_data.truncate()
                offsets.append(seen[raw])
            else:
                offsets.append(start)
                if getattr(self, 'optimize', False):
                    seen[raw] = start

        # C# writes values in optimization-priority order, but then sorts the
        # (name index, value offset) pairs by name index for runtime binary
        # search.  Only the value-data layout retains the priority ordering.
        pairs = sorted(zip(name_indexes, offsets), key=lambda pair: pair[0])
        name_indexes = [pair[0] for pair in pairs]
        offsets = [pair[1] for pair in pairs]

        # 写入 name indexes array
        output.write(write_psb_array(name_indexes))

        # 写入 offsets array
        output.write(write_psb_array(offsets))

        # 写入 values data
        output.write(values_data.getvalue())

    def _write_dict_v1(self, output: io.BytesIO, obj: Dict[str, Any]) -> None:
        """Match PSB v1 SaveObjectsV1: offset array + key/value records."""
        output.write(bytes([PsbType.OBJECTS]))
        keys = [key for key in obj if not key.startswith('_')]
        # OptimizeMode makes PsbObjectOrderByKey irrelevant in modern
        # SaveObjects, but SaveObjectsV1 only observes PsbObjectOrderByKey,
        # whose default is true.
        keys.sort(key=lambda s: s.encode('utf-16-be', errors='surrogatepass'))

        offsets: List[int] = []
        records = io.BytesIO()
        for key in keys:
            offsets.append(records.tell())
            index = self.name_to_index[key]
            size = get_size(index)
            records.write(bytes([0x11 + size - 1]))  # KeyNameN1..N4
            records.write(zip_number_bytes(index, size))
            self._pack(records, obj[key])
        output.write(write_psb_array(offsets))
        output.write(records.getvalue())

    def _write_priority(self, value: Any) -> int:
        if value is None:
            return 0
        if value is True or value is False:
            return 1
        if isinstance(value, int) and value == 0:
            return 2
        if isinstance(value, int):
            size = self._get_signed_size(value)
            return 3 if size == 1 else (4 if size == 2 else 10)
        if isinstance(value, float):
            return 4 if value == 0.0 and not isinstance(value, PsbDouble) else 10
        if isinstance(value, str):
            index = self.string_to_index[value]
            return 4 if get_size(index) == 1 else (5 if get_size(index) == 2 else 10)
        if isinstance(value, dict) and value.get('_type') == 'resource':
            return 4 if get_size(int(value.get('index', 0))) == 1 else 10
        return 10

    @staticmethod
    def _dotnet_introsort(items: List[Any], key) -> None:
        """Match .NET Framework ArraySortHelper<T>.IntrospectiveSort.

        SaveObjects uses List<T>.Sort with a comparator that returns zero for
        equal priorities. The runtime sort is intentionally unstable, so a
        stable Python sort changes value-data order and object-byte reuse.
        """
        if len(items) < 2:
            return

        def compare(left: Any, right: Any) -> int:
            return key(left) - key(right)

        def swap(i: int, j: int) -> None:
            if i != j:
                items[i], items[j] = items[j], items[i]

        def swap_if_greater(i: int, j: int) -> None:
            if i != j and compare(items[i], items[j]) > 0:
                swap(i, j)

        def down_heap(index: int, size: int, base: int) -> None:
            value = items[base + index - 1]
            while index <= size // 2:
                child = 2 * index
                if child < size and compare(items[base + child - 1], items[base + child]) < 0:
                    child += 1
                if compare(value, items[base + child - 1]) >= 0:
                    break
                items[base + index - 1] = items[base + child - 1]
                index = child
            items[base + index - 1] = value

        def heap_sort(lo: int, hi: int) -> None:
            size = hi - lo + 1
            for index in range(size // 2, 0, -1):
                down_heap(index, size, lo)
            for index in range(size, 1, -1):
                swap(lo, lo + index - 1)
                down_heap(1, index - 1, lo)

        def insertion_sort(lo: int, hi: int) -> None:
            for index in range(lo, hi):
                current = index + 1
                value = items[current]
                while current > lo and compare(value, items[current - 1]) < 0:
                    items[current] = items[current - 1]
                    current -= 1
                items[current] = value

        def floor_log2_plus_one(length: int) -> int:
            result = 0
            while length >= 1:
                result += 1
                length //= 2
            return result

        def intro_sort(lo: int, hi: int, depth_limit: int) -> None:
            while hi > lo:
                partition_size = hi - lo + 1
                if partition_size <= 16:
                    if partition_size == 1:
                        return
                    if partition_size == 2:
                        swap_if_greater(lo, hi)
                        return
                    if partition_size == 3:
                        swap_if_greater(lo, hi - 1)
                        swap_if_greater(lo, hi)
                        swap_if_greater(hi - 1, hi)
                        return
                    insertion_sort(lo, hi)
                    return
                if depth_limit == 0:
                    heap_sort(lo, hi)
                    return
                depth_limit -= 1
                middle = lo + (hi - lo) // 2
                swap_if_greater(lo, middle)
                swap_if_greater(lo, hi)
                swap_if_greater(middle, hi)
                pivot = items[middle]
                swap(middle, hi - 1)
                left, right = lo, hi - 1
                while True:
                    left += 1
                    while compare(items[left], pivot) < 0:
                        left += 1
                    right -= 1
                    while compare(pivot, items[right]) < 0:
                        right -= 1
                    if left >= right:
                        break
                    swap(left, right)
                swap(left, hi - 1)
                intro_sort(left + 1, hi, depth_limit)
                hi = left - 1

        intro_sort(0, len(items) - 1, 2 * floor_log2_plus_one(len(items)))

    def _write_header(
        self, output: io.BytesIO, header_len: int,
        offset_names: int, offset_strings: int, offset_strings_data: int,
        offset_entries: int, offset_chunk_offsets: int, offset_chunk_lengths: int,
        offset_chunk_data: int, offset_extra_chunk_offsets: int,
        offset_extra_chunk_lengths: int, offset_extra_chunk_data: int
    ):
        """写入 PSB Header"""
        output.seek(0)

        # Layout is identical to FreeMote.Psb/PsbHeader.ToBytes():
        # signature, version, header-encrypt, header-length, seven offsets,
        # checksum (v3+), then three extra offsets (v4+).
        output.write(b'PSB\x00')

        # Version
        output.write(struct.pack('<H', self.version))

        # Flags (0 = unencrypted)
        output.write(struct.pack('<H', 0))

        # HeaderLength (+8), then offsets (+12 ... +36).
        output.write(struct.pack('<I', header_len))
        output.write(struct.pack(
            '<I', getattr(self, '_v1_offset_names', offset_names)
            if self.version == 1 else offset_names
        ))
        output.write(struct.pack('<I', offset_strings))
        output.write(struct.pack('<I', offset_strings_data))
        output.write(struct.pack('<I', offset_chunk_offsets))
        output.write(struct.pack('<I', offset_chunk_lengths))
        output.write(struct.pack('<I', offset_chunk_data))
        output.write(struct.pack('<I', offset_entries))

        if self.version >= 4:
            output.seek(44)
            output.write(struct.pack('<I', offset_extra_chunk_offsets))
            output.write(struct.pack('<I', offset_extra_chunk_lengths))
            output.write(struct.pack('<I', offset_extra_chunk_data))

        # Checksum is written at +40 for v3/v4. C# UpdateChecksum computes
        # HeaderLength..OffsetEntries (+8..+39), followed by the v4 extra
        # offsets (+44..+55). The extra offsets must be present before this
        # calculation; otherwise every v4 file gets a wrong checksum.
        if self.version >= 3:
            checksum_data = bytearray()
            output.seek(8)
            checksum_data.extend(output.read(32))
            if self.version >= 4:
                output.seek(44)
                checksum_data.extend(output.read(12))
            checksum = calculate_adler32(bytes(checksum_data))
            output.seek(40)
            output.write(struct.pack('<I', checksum))
