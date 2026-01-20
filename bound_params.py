# BoundParams.py
import json
import os
import logging
from logger_config import bound_params_logger as logger

CACHE_DIR = ".emote_cache"
CONFIG_FILE = "config.json"

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

def get_default_map():
    return {}

def _load_semantic_rules():
    """从 config.json 加载规则"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config", CONFIG_FILE)
    
    default_rules = [] # 如果文件不存在
    
    if not os.path.exists(config_path):
        logger.warning(f"配置文件 {config_path} 不存在，将无法进行智能匹配。")
        return default_rules

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("semantic_rules", [])
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}", exc_info=True)
        return default_rules

# 加载规则
SEMANTIC_RULES = _load_semantic_rules()

def analyze_variable_list(raw_variable_list: list) -> dict:
    """
    基于 config.json 的规则进行分析
    """
    # 如果规则为空，尝试重新加载
    global SEMANTIC_RULES
    if not SEMANTIC_RULES:
        SEMANTIC_RULES = _load_semantic_rules()

    logger.info(f"开始分析 {len(raw_variable_list)} 个运行时变量...")
    
    bound_map = {}
    
    for var_info in raw_variable_list:
        var_name = var_info.get('label')
        if not var_name: continue
        
        min_val = var_info.get('minValue', 0.0)
        max_val = var_info.get('maxValue', 0.0)
        frame_list = var_info.get('frameList', [])
        
        # 默认值
        category = "未分类"
        special_usage_list = []
        
        name_lower = var_name.lower()
        
        for rule in SEMANTIC_RULES:
            keywords = rule.get("keywords", [])
            if any(kw in name_lower for kw in keywords):
                category = rule.get("category", "未分类")
                tag = rule.get("tag")
                if tag:
                    special_usage_list.append(tag)
                break

        semantic_frames = {}
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

def get_bound_map(model_path: str) -> dict:
    """兼容性接口 仅读缓存，不解包"""
    if not os.path.exists(model_path):
        return get_default_map()

    model_filename = os.path.basename(model_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(script_dir, CACHE_DIR, f"{model_filename}.map.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                logger.info(f"从缓存加载映射: {model_filename}")
                return json.load(f)
        except Exception:
            pass
    
    logger.info(f"无缓存，将在模型加载后通过运行时自省生成映射: {model_filename}")
    return get_default_map()

def update_cache(model_filename: str, new_map: dict):
    """更新缓存"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir_path = os.path.join(script_dir, CACHE_DIR)
    if not os.path.exists(cache_dir_path):
        os.makedirs(cache_dir_path)
        
    model_filename = os.path.basename(model_filename)
    cache_file = os.path.join(cache_dir_path, f"{model_filename}.map.json")
    
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(new_map, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error("更新缓存失败", exc_info=True)
        return False

load_map_from_cache = get_bound_map
save_map_to_cache = update_cache