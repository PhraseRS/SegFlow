# -*- coding: utf-8 -*-
"""
MMSegmentation 配置文件解析器
用于从配置文件中提取模型信息、类别和调色板
"""

import os
import re
from typing import Dict, List, Optional, Any


def parse_mmseg_config(config_path: str) -> Dict[str, Any]:
    """
    解析 MMSegmentation 配置文件
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        dict: 包含以下字段的字典
            - model_name: 模型名称
            - model_type: 模型类型（如 EncoderDecoder）
            - backbone: 骨干网络类型
            - num_classes: 类别数量
            - classes: 类别名称列表
            - palette: 调色板（RGB颜色列表）
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    config_info = {
        'model_name': os.path.splitext(os.path.basename(config_path))[0],
        'model_type': None,
        'backbone': None,
        'num_classes': None,
        'classes': None,
        'palette': None
    }
    
    # 提取模型类型
    model_type_match = re.search(r"model\s*=\s*dict\s*\(\s*type\s*=\s*['\"](\w+)['\"]", content)
    if model_type_match:
        config_info['model_type'] = model_type_match.group(1)
    
    # 提取骨干网络类型
    backbone_match = re.search(r"backbone\s*=\s*dict\s*\(\s*type\s*=\s*['\"](\w+)['\"]", content)
    if backbone_match:
        config_info['backbone'] = backbone_match.group(1)
    
    # 提取类别数量
    num_classes_match = re.search(r"num_classes\s*=\s*(\d+)", content)
    if num_classes_match:
        config_info['num_classes'] = int(num_classes_match.group(1))
    
    # 提取类别列表 (CLASSES)
    classes = _extract_list(content, 'CLASSES')
    if classes:
        config_info['classes'] = classes
    else:
        # 尝试其他常见变量名
        for var_name in ['classes', 'class_names', 'CLASSES']:
            classes = _extract_list(content, var_name)
            if classes:
                config_info['classes'] = classes
                break
    
    # 提取调色板 (PALETTE)
    palette = _extract_palette(content)
    if palette:
        config_info['palette'] = palette
    
    return config_info


def _extract_list(content: str, var_name: str) -> Optional[List[str]]:
    """
    从配置内容中提取列表变量
    
    Args:
        content: 配置文件内容
        var_name: 变量名
    
    Returns:
        list: 提取的列表，如果未找到则返回 None
    """
    # 匹配 VAR_NAME = ['item1', 'item2', ...] 或 VAR_NAME = ('item1', 'item2', ...)
    pattern = rf"{var_name}\s*=\s*[\[\(](.*?)[\]\)]"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return None
    
    list_content = match.group(1)
    
    # 提取字符串项
    items = re.findall(r"['\"]([^'\"]+)['\"]", list_content)
    
    return items if items else None


def _extract_palette(content: str) -> Optional[List[List[int]]]:
    """
    从配置内容中提取调色板
    
    Args:
        content: 配置文件内容
    
    Returns:
        list: RGB颜色列表，如 [[128, 0, 0], [0, 128, 0], ...]
    """
    # 匹配 PALETTE = [[r, g, b], ...] 或 palette = [[r, g, b], ...]
    for var_name in ['PALETTE', 'palette']:
        pattern = rf"{var_name}\s*=\s*\[(.*?)\](?:\s*\n|\s*$|\s*#)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            palette_content = match.group(1)
            
            # 提取所有 [r, g, b] 格式的颜色
            colors = re.findall(r"\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]", palette_content)
            
            if colors:
                return [[int(r), int(g), int(b)] for r, g, b in colors]
    
    return None


def get_model_display_name(config_info: Dict[str, Any]) -> str:
    """
    生成模型的显示名称
    
    Args:
        config_info: parse_mmseg_config 返回的配置信息
    
    Returns:
        str: 格式化的模型显示名称
    """
    parts = []
    
    if config_info.get('model_type'):
        parts.append(config_info['model_type'])
    
    if config_info.get('backbone'):
        parts.append(config_info['backbone'])
    
    if not parts:
        return config_info.get('model_name', 'Unknown Model')
    
    return ' + '.join(parts)
