import json
import os
from typing import Dict, List, Tuple, Any, Union
from .logger import bound_params_logger as logger

# 定义类型别名
BoundMapItem = Dict[str, Union[str, Tuple[float, float], List[str], Dict[float, str]]]
BoundMap = Dict[str, BoundMapItem]
SemanticRule = Dict[str, Union[List[str], str]]

# 包内文件路径
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_ROOT = os.path.dirname(_CURRENT_DIR)
DEFAULT_CONFIG_PATH = os.path.join(_PACKAGE_ROOT, 'default_config', 'bound_params_config.json')

# 缓存目录（相对于工作目录）
CACHE_DIR = ".emote_cache"

class SpecialUsage:
    HEAD_LR = "HEAD_LR"
    HEAD_UD = "HEAD_UD"
    EYE_LR = "EYE_LR"
    EYE_UD = "EYE_UD"
    EYE_OPEN = "EYE_OPEN"
    MOUTH_OPEN = "MOUTH_OPEN"
    MOUTH_FORM = "MOUTH_FORM"
    BODY_LR = "BODY_LR"
    BODY_UD = "BODY_UD"

def get_default_map() -> BoundMap:
    return {}

_semantic_rules: List[SemanticRule] = []

def load_config(config_path: str|None =None) -> None:
    """
    加载语义匹配规则。
    如果不传路径，默认加载包内置的 bound_params_config.json。
    """
    global _semantic_rules
    
    target_path = config_path if config_path else DEFAULT_CONFIG_PATH
    
    if not os.path.exists(target_path):
        if config_path:
            logger.warning(f"用户指定的配置文件不存在: {config_path}，将使用空规则。")
        else:
            # 默认配置不存在 (可能是开发环境缺失)，仅提示
            logger.info(f"未找到默认参数配置文件: {target_path}，跳过。")
        _semantic_rules = []
        return

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data: Union[List[SemanticRule], Dict[str, List[SemanticRule]]] = json.load(f)
            # 兼容两种格式：直接列表 或 {"semantic_rules": [...]}
            if isinstance(data, list):
                _semantic_rules = data
            else:
                _semantic_rules = data.get("semantic_rules", [])
        
        source = "用户自定义" if config_path else "默认"
        logger.info(f"已加载{source}语义规则: {target_path} (包含 {len(_semantic_rules)} 条规则)")
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}", exc_info=True)
        _semantic_rules = []

load_config()

def analyze_variable_list(raw_variable_list: List[Dict[str, Any]]) -> BoundMap:
    """
    基于 config.json 的规则进行分析
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
        
        # 默认值
        category = "未分类"
        special_usage_list: List[str] = []
        
        name_lower = var_name.lower()
        
        for rule in _semantic_rules:
            keywords = rule.get("keywords", [])
            if any(kw in name_lower for kw in keywords):
                category = rule.get("category", "未分类")
                tag = rule.get("tag")
                if tag:
                    if isinstance(tag, list):
                        special_usage_list.extend(tag)
                    else:
                        special_usage_list.append(tag)
                break

        semantic_frames: Dict[float, str] = {}
        if frame_list:
            for frame in frame_list:
                f_label = frame.get('label')
                f_value = frame.get('value')
                if f_label is not None and f_value is not None:
                    semantic_frames[f_value] = f_label

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
    获取模型参数映射。优先从缓存加载，无缓存时返回空映射。
    
    Args:
        model_path: 模型文件路径或文件名
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
    更新参数映射缓存。
    
    Args:
        model_filename: 模型文件名
        new_map: 新的参数映射数据
        
    Returns:
        bool: 更新是否成功
    """
    # 确保使用的是文件名而不是路径
    model_filename = os.path.basename(model_filename)
    
    # 在当前工作目录下创建缓存目录
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

load_map_from_cache = get_bound_map
save_map_to_cache = update_cache