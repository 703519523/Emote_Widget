"""
EmoteWidget 参数绑定模块。

本模块负责管理模型参数的“语义绑定” (Semantic Binding)。
由于 Emote/Live2D 模型的参数名称通常是混淆的或非标准化的（如 "PARAM_ANGLE_X" vs "ParamAngleX"），
本模块通过配置文件 (`bound_params_config.json`) 中的正则表达式规则，
将底层参数映射到标准化的“特殊用途标签” (Special Usage Tags)。

功能:
    1. **语义分析**: 解析模型的所有参数名，匹配出控制头部、眼睛、嘴巴等的关键参数。
    2. **缓存管理**: 将分析结果缓存到 `.emote_cache` 目录，避免每次加载都重新分析。
    3. **配置加载**: 加载用户定义或默认的匹配规则。
"""

import json
import os
from typing import Dict, List, Tuple, Any, Union, Optional
from .logger import bound_params_logger as logger

# --- 类型定义 ---
# BoundMapItem: 单个参数的绑定信息
BoundMapItem = Dict[str, Union[str, Tuple[float, float], List[str], Dict[float, str]]]
# BoundMap: 参数名 -> 绑定信息的映射表
BoundMap = Dict[str, BoundMapItem]
# SemanticRule: 语义匹配规则
SemanticRule = Dict[str, Union[List[str], str]]

# --- 路径常量 ---
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_ROOT = os.path.dirname(_CURRENT_DIR)
DEFAULT_CONFIG_PATH = os.path.join(_PACKAGE_ROOT, 'default_config', 'bound_params_config.json')

# 缓存目录（相对于当前工作目录）
CACHE_DIR = ".emote_cache"

class SpecialUsage:
    """
    [枚举] 标准化的特殊用途标签。
    用于在代码中引用特定的模型参数，解耦具体参数名。
    """
    HEAD_LR = "HEAD_LR"       # 头部左右旋转 (Yaw)
    HEAD_UD = "HEAD_UD"       # 头部上下旋转 (Pitch)
    EYE_LR = "EYE_LR"         # 眼球左右视线
    EYE_UD = "EYE_UD"         # 眼球上下视线
    EYE_OPEN = "EYE_OPEN"     # 眼睛开合
    MOUTH_OPEN = "MOUTH_OPEN" # 嘴巴开合 (用于 LipSync)
    MOUTH_FORM = "MOUTH_FORM" # 嘴型 (A, I, U, E, O)
    BODY_LR = "BODY_LR"       # 身体左右旋转
    BODY_UD = "BODY_UD"       # 身体上下旋转

def get_default_map() -> BoundMap:
    """获取一个空的绑定映射表。"""
    return {}

# 全局语义规则列表
_semantic_rules: List[SemanticRule] = []

def load_config(config_path: Optional[str] = None) -> None:
    """
    加载语义匹配规则配置文件。
    
    Args:
        config_path (str, optional): 配置文件路径。如果不指定，则加载包内置的默认配置。
    """
    global _semantic_rules
    
    target_path = config_path if config_path else DEFAULT_CONFIG_PATH
    
    if not os.path.exists(target_path):
        if config_path:
            logger.warning(f"用户指定的配置文件不存在: {target_path}，将使用空规则。")
        else:
            # 开发环境下可能找不到默认配置，仅记录信息
            logger.info(f"未找到默认参数配置文件: {target_path}，跳过加载。")
        _semantic_rules = []
        return

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data: Union[List[SemanticRule], Dict[str, List[SemanticRule]]] = json.load(f)
            # 兼容两种格式：直接列表 List[...] 或 字典 {"semantic_rules": [...]}
            if isinstance(data, list):
                _semantic_rules = data
            else:
                _semantic_rules = data.get("semantic_rules", [])
        
        source = "用户自定义" if config_path else "默认"
        logger.info(f"已加载{source}语义规则: {target_path} (包含 {len(_semantic_rules)} 条规则)")
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}", exc_info=True)
        _semantic_rules = []

# 模块加载时自动读取默认配置
load_config()

def analyze_variable_list(raw_variable_list: List[Dict[str, Any]]) -> BoundMap:
    """
    执行参数自省与语义分析。
    
    遍历模型提供的原始变量列表，根据 `_semantic_rules` 中的关键字规则，
    自动识别参数的用途并打上标签 (Tag)。
    
    Args:
        raw_variable_list (List[Dict]): 从 JS 端 `emotePlayer.variableList` 获取的原始数据。
        
    Returns:
        BoundMap: 生成的参数绑定映射表。
    """
    global _semantic_rules

    logger.info(f"开始分析 {len(raw_variable_list)} 个运行时变量...")
    
    bound_map: BoundMap = {}
    
    for var_info in raw_variable_list:
        var_name = var_info.get('label')
        if not var_name: continue
        
        min_val = var_info.get('minValue', 0.0)
        max_val = var_info.get('maxValue', 0.0)
        frame_list = var_info.get('frameList', [])
        
        # 默认属性
        category = "未分类"
        special_usage_list: List[str] = []
        
        name_lower = var_name.lower()
        
        # 遍历规则进行匹配
        for rule in _semantic_rules:
            keywords = rule.get("keywords", [])
            # 只要包含任意一个关键字即视为匹配
            if any(kw in name_lower for kw in keywords):
                category = rule.get("category", "未分类")
                tag = rule.get("tag")
                if tag:
                    if isinstance(tag, list):
                        special_usage_list.extend(tag)
                    else:
                        special_usage_list.append(tag)
                break

        # 处理关键帧标签 (如果存在)
        semantic_frames: Dict[float, str] = {}
        if frame_list:
            for frame in frame_list:
                f_label = frame.get('label')
                f_value = frame.get('value')
                if f_label is not None and f_value is not None:
                    semantic_frames[f_value] = f_label

        # 构建映射条目
        bound_map[var_name] = {
            "name": var_name,
            "range": (float(min_val), float(max_val)),
            "category": category,
            "special_usage": special_usage_list,
            "semantic_frames": semantic_frames 
        }
        
    logger.info(f"变量分析完成，生成了 {len(bound_map)} 个映射条目。")
    return bound_map

def get_bound_map(model_path: str) -> BoundMap:
    """
    获取模型的参数映射表。
    
    策略:
        1. 尝试从磁盘缓存 (`.emote_cache/xxx.map.json`) 加载。
        2. 如果缓存不存在，返回空字典。后续 Controller 会在模型加载完成后
           调用 `analyze_variable_list` 进行实时分析并更新缓存。
    
    Args:
        model_path (str): 模型文件的路径或文件名。
        
    Returns:
        BoundMap: 参数映射表。
    """
    model_filename = os.path.basename(model_path)
    cache_file = os.path.join(os.getcwd(), CACHE_DIR, f"{model_filename}.map.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                logger.info(f"从缓存加载映射: {model_filename}")
                return json.load(f)
        except Exception as e:
            logger.error(f"读取缓存失败: {e}", exc_info=True)
    
    logger.info(f"无缓存，将在模型加载后通过运行时自省生成映射: {model_filename}")
    return get_default_map()

def update_cache(model_filename: str, new_map: BoundMap) -> bool:
    """
    将生成的参数映射表保存到磁盘缓存。
    
    Args:
        model_filename (str): 模型文件名。
        new_map (BoundMap): 要保存的映射数据。
        
    Returns:
        bool: 保存是否成功。
    """
    # 确保使用的是文件名而不是完整路径
    model_filename = os.path.basename(model_filename)
    
    # 确保缓存目录存在
    cache_dir_path = os.path.join(os.getcwd(), CACHE_DIR)
    if not os.path.exists(cache_dir_path):
        try:
            os.makedirs(cache_dir_path)
        except Exception as e:
            logger.error(f"创建缓存目录失败: {e}", exc_info=True)
            return False
            
    cache_file = os.path.join(cache_dir_path, f"{model_filename}.map.json")
    
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(new_map, f, indent=4, ensure_ascii=False)
        return True
    except Exception as exc:
        logger.error(f"更新缓存失败: {exc}", exc_info=True)
        return False

# 导出别名
load_map_from_cache = get_bound_map
save_map_to_cache = update_cache
