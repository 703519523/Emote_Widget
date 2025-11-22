# BoundParams.py
import os
import json
import re
import subprocess
import shutil
import random
import string
import sys

import logging
from logger_config import bound_params_logger as logger

# 定义特殊用途标签的常量，方便代码引用和提示
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
    """返回一个结构完整、包含默认值的变量映射表。"""
    return {
        # --- 头部与视线 ---
        "head_lr": {"name": None, "range": (-30.0, 30.0), "category": "头部", "special_usage": [SpecialUsage.HEAD_LR]},
        "head_ud": {"name": None, "range": (-30.0, 30.0), "category": "头部", "special_usage": [SpecialUsage.HEAD_UD]},
        "head_slant": {"name": None, "range": (-15.0, 15.0), "category": "头部", "special_usage": []},
        "eye_lr": {"name": None, "range": (-1.0, 1.0), "category": "眼睛", "special_usage": [SpecialUsage.EYE_LR]},
        "eye_ud": {"name": None, "range": (-1.0, 1.0), "category": "眼睛", "special_usage": [SpecialUsage.EYE_UD]},
        "eye_open": {"name": None, "range": (0.0, 1.0), "category": "眼睛", "special_usage": [SpecialUsage.EYE_OPEN]},

        # --- 身体 ---
        "body_lr": {"name": None, "range": (-10.0, 10.0), "category": "身体", "special_usage": [SpecialUsage.BODY_LR]},
        "body_ud": {"name": None, "range": (-10.0, 10.0), "category": "身体", "special_usage": [SpecialUsage.BODY_UD]},
        "body_slant": {"name": None, "range": (-10.0, 10.0), "category": "身体", "special_usage": []},
        
        # --- 嘴部 ---
        "mouth_talk": {"name": None, "range": (0.0, 1.0), "category": "嘴部", "special_usage": [SpecialUsage.MOUTH_OPEN]},
        "mouth_shape": {"name": None, "range": (0.0, 1.0), "category": "嘴部", "special_usage": [SpecialUsage.MOUTH_FORM]},
        
        # --- 其他默认映射 ---
        "move_lr": {"name": None, "range": (-100.0, 100.0), "category": "位移", "special_usage": []},
        "move_ud": {"name": None, "range": (-100.0, 100.0), "category": "位移", "special_usage": []},
        "eyebrow_shape": {"name": None, "range": (0.0, 1.0), "category": "眉毛", "special_usage": []},
        "tears": {"name": None, "range": (0.0, 1.0), "category": "表情", "special_usage": []},
        "cheek_blush": {"name": None, "range": (0.0, 1.0), "category": "表情", "special_usage": []},
    }


CACHE_DIR = ".emote_cache"
TOOLS_DIR = "tools"
VARIABLE_PATTERNS = {
    # (正则表达式库保持原样)
    "move_lr": r"^move_LR$", "move_ud": r"^move_UD$", "head_lr": r"^head_LR$", "head_ud": r"^head_UD$",
    "head_slant": r"^head_slant$", "body_lr": r"^body_LR$", "body_ud": r"^body_UD$", "body_slant": r"^body_slant$",
    "eye_lr": r"^face_eye_LR$", "eye_ud": r"^face_eye_UD$", "eye_open": r"^face_eye_open$", "eye_special": r"^face_eye_sp$",
    "pupil_special": r"^face_hitomi_sp$", "eyebrow_shape": r"^face_eyebrow$", "eyebrow_special": r"^face_eyebrow_sp$",
    "mouth_shape": r"^face_mouth$", "mouth_special": r"^face_mouth_sp$", "mouth_talk": r"^face_talk$",
    "tears": r"^face_tears$", "cheek_blush": r"^face_cheek$", "action_special": r"^act_sp$", "action_special_2": r"^act_sp2$",
    "action_special_3": r"^act_sp3$", "bust_lr": r"^bust_LR$", "bust_ud": r"^bust_UD$", "bust_lr_spare": r"^bust_LR_spare$",
    "bust_ud_spare": r"^bust_UD_spare$", "hair_front_lr": r"^hair_LR_front$", "hair_front_middle_lr": r"^hair_LR_M_front$",
    "hair_front_ud": r"^hair_UD_front$", "hair_sidel_lr": r"^hair_LR_sideL$", "hair_sidel_middle_lr": r"^hair_LR_M_sideL$",
    "hair_sidel_ud": r"^hair_UD_sideL$", "hair_sider_lr": r"^hair_LR_sideR$", "hair_sider_middle_lr": r"^hair_LR_M_sideR$",
    "hair_sider_ud": r"^hair_UD_sideR$", "hair_back_lr": r"^hair_LR$", "hair_back_middle_lr": r"^hair_LR_M$",
    "hair_back_ud": r"^hair_UD$", "quake_lr": r"^quake_LR$", "quake_middle_lr": r"^quake_LR_M$", "quake_ud": r"^quake_UD$",
    "quake_lr_spare": r"^quake_LR_spare$", "quake_middle_lr_spare": r"^quake_LR_M_spare$", "quake_ud_spare": r"^quake_UD_spare$",
    "part_a_fade": r"^fade_l?a$", "part_b_fade": r"^fade_l?b$", "part_c_fade": r"^fade_l?c$", "part_d_fade": r"^fade_l?d$",
    "part_e_fade": r"^fade_e$", "part_x_fade": r"^fade_l?x$", "part_y_fade": r"^fade_l?y$", "part_z_fade": r"^fade_l?z$",
    "arm_selector": r"^arm_type$", "vr_lr": r"^vr_LR$", "vr_ud": r"^vr_UD$",
}

def _extract_all_vars_from_data(data):
    vars_found = set()
    def recursive(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("var_lr", "var_ud", "var_lrm", "label") and isinstance(v, str): vars_found.add(v)
                if k == "optionList" and isinstance(v, list):
                    for opt in v:
                        if "label" in opt: vars_found.add(opt["label"])
                recursive(v)
        elif isinstance(obj, list):
            for item in obj: recursive(item)
    recursive(data)
    return list(vars_found)

def _build_map_from_json_file(json_path: str) -> dict:
    """
    从 JSON 文件构建一个符合新规范的、结构完整的变量映射表。
    """
    logger.info(f"正在从 '{os.path.basename(json_path)}' 构建映射表...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"无法读取或解析 JSON 文件: {json_path}", exc_info=True)
        return get_default_map()
    model_vars_found = _extract_all_vars_from_data(data)
    result_map = get_default_map()
    for friendly_name, pattern in VARIABLE_PATTERNS.items():
        regex = re.compile(pattern)
        matched = [v for v in model_vars_found if regex.match(v)]
        if matched:
            if friendly_name in result_map:
                result_map[friendly_name]['name'] = matched[0]
            else:
                result_map[friendly_name] = {
                    "name": matched[0],
                    "range": (-1.0, 1.0),
                    "category": "自动匹配",
                    "special_usage": []
                }
    
    logger.info("映射表构建完成。")
    return result_map


def _run_decompile_in_sandbox(model_path: str) -> str:
    logger.info("进入沙盒解包模式...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tools_path = os.path.join(script_dir, TOOLS_DIR)
    decompiler_exe = os.path.join(tools_path, "PsbDecompile.exe")
    if not os.path.exists(decompiler_exe):
        logger.error(f"找不到解包工具 '{decompiler_exe}'")
        return None

    rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    sandbox_dir = os.path.join(script_dir, f"work_temp_{rand_str}")
    try:
        os.makedirs(sandbox_dir)
    except OSError as e:
        logger.error(f"创建沙盒失败: {sandbox_dir}", exc_info=True)
        return None
        
    try:
        shutil.copy(decompiler_exe, sandbox_dir)
        config_file = f"{decompiler_exe}.config"
        if os.path.exists(config_file): shutil.copy(config_file, sandbox_dir)
        lib_dir_in_tools = os.path.join(tools_path, "lib")
        if os.path.isdir(lib_dir_in_tools): shutil.copytree(lib_dir_in_tools, os.path.join(sandbox_dir, "lib"))
        model_filename_in_sandbox = os.path.basename(model_path)
        shutil.copy(model_path, os.path.join(sandbox_dir, model_filename_in_sandbox))
    except Exception as e:
        logger.error("准备沙盒环境时出错", exc_info=True)
        shutil.rmtree(sandbox_dir)
        return None

    json_path_in_sandbox = None; final_json_path = None
    try:
        original_cwd = os.getcwd()
        os.chdir(sandbox_dir)
        command = [os.path.basename(decompiler_exe), model_filename_in_sandbox]
        logger.info(f"在沙盒中执行命令: {' '.join(command)}")
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=False, 
            encoding=sys.getfilesystemencoding(), 
            errors='ignore'
        )

        model_name_base, _ = os.path.splitext(model_filename_in_sandbox)
        expected_json_filename = f"{model_name_base}.json"

        if result.returncode != 0 or not os.path.exists(expected_json_filename):
            logger.error(f"解包失败! 返回码: {result.returncode}")
            logger.error(f"PsbDecompile.exe 输出:\n--- STDERR ---\n{result.stderr}\n--- STDOUT ---\n{result.stdout}\n--------------")
            json_path_in_sandbox = None
        else:
            json_path_in_sandbox = os.path.join(sandbox_dir, expected_json_filename)
    except Exception as e:
        logger.error("执行 subprocess 时发生异常", exc_info=True)
    finally:
        os.chdir(original_cwd)
        if json_path_in_sandbox and os.path.exists(json_path_in_sandbox):
             final_json_path = os.path.join(os.path.dirname(model_path), os.path.basename(json_path_in_sandbox))
             try:
                 shutil.copy(json_path_in_sandbox, final_json_path)
                 logger.info(f"已将 '{os.path.basename(final_json_path)}' 复制到模型目录。")
             except (IOError, OSError) as e:
                 logger.error(f"复制生成的JSON文件失败: {final_json_path}", exc_info=True)
                 final_json_path = None
        try:
            shutil.rmtree(sandbox_dir)
        except OSError as e:
            logger.warning(f"清理沙盒目录失败: {sandbox_dir}", exc_info=True)
        return final_json_path


def get_bound_map(model_path: str) -> dict:
    """
    获取一个模型文件的变量映射表（新版）。
    优先从缓存加载，否则通过解包和自动绑定生成。
    """
    logger.info(f"开始处理模型: '{os.path.basename(model_path)}'")
    if not os.path.exists(model_path):
        logger.error(f"模型文件不存在 '{model_path}'")
        return get_default_map()

    model_filename = os.path.basename(model_path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir_path = os.path.join(script_dir, CACHE_DIR)
    if not os.path.exists(cache_dir_path): os.makedirs(cache_dir_path)
    cache_file = os.path.join(cache_dir_path, f"{model_filename}.map.json")

    if os.path.exists(cache_file):
        logger.info(f"发现缓存文件，正在加载: '{os.path.basename(cache_file)}'")
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("缓存文件损坏或无法读取，将重新生成。", exc_info=True)
            
    logger.info("未找到或缓存无效，开始生成新的映射表...")

    model_dir = os.path.dirname(model_path)
    model_name, _ = os.path.splitext(model_filename)
    json_path = os.path.join(model_dir, f"{model_name}.json")
    if not os.path.exists(json_path):
        json_path = _run_decompile_in_sandbox(model_path)
    
    if not json_path or not os.path.exists(json_path):
        logger.critical("致命错误: 无法获取 .json 文件，将返回默认映射表。")
        return get_default_map()

    variable_map = _build_map_from_json_file(json_path)
    try:
        os.remove(json_path)
    except OSError:
        logger.warning(f"清理临时JSON文件失败: {json_path}", exc_info=True)
    
    if variable_map:
        update_cache(model_filename, variable_map)
            
    return variable_map

def update_cache(model_filename: str, new_map: dict):
    """
    将用户修改后的变量映射表更新到缓存文件中。
    这是由 EmoteWidget 在用户编辑后调用的。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir_path = os.path.join(script_dir, CACHE_DIR)
    if not os.path.exists(cache_dir_path):
        os.makedirs(cache_dir_path)
        
    cache_file = os.path.join(cache_dir_path, f"{model_filename}.map.json")
    
    logger.info(f"正在更新缓存文件: '{os.path.basename(cache_file)}'")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(new_map, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error("更新缓存失败", exc_info=True)
        return False