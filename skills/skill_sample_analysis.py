# -*- coding: utf-8 -*-
"""
---
name: skill_sample_analysis
description: >
  遥感数据集样本全能质检分析工具。
  一次 I/O 完成文件存在检查、损坏检测、尺寸匹配、通道/位深校验、
  类别分布统计、噪点检测和无数据覆盖率检测。
  不依赖任何特定模型架构或 GUI 框架，可在独立进程中使用。
parameters:
  analyze_sample_fully:
    args: tuple - (sample_id, dataset_type, image_path, label_path)
    returns: >
      dict - 分析结果，包含 sample_id, dataset, status('ok'|'warning'|'error'),
      issues(问题列表), stats(统计数据)
returns:
  ISSUE_* 常量: str - 问题类型标识
  LEVEL_* 常量: str - 问题级别
  ISSUE_LEVELS: dict - 问题类型到级别的映射
  NOISE_AREA_THRESHOLD: int - 噪点检测面积阈值
  NODATA_COVERAGE_THRESHOLD: float - 无数据覆盖率阈值
  VALID_CLASS_IDS: set - 有效类别 ID 范围
  analyze_sample_fully: callable
---
"""

import os
import numpy as np


# ============== 问题类型常量 ==============
ISSUE_FILE_MISSING = "file_missing"
ISSUE_CORRUPT_FILE = "corrupt_file"
ISSUE_DIMENSION_MISMATCH = "dimension_mismatch"
ISSUE_CHANNEL_MISMATCH = "channel_mismatch"
ISSUE_INVALID_CLASS_ID = "invalid_class_id"
ISSUE_DTYPE_MISMATCH = "dtype_mismatch"
ISSUE_EMPTY_MASK = "empty_mask"
ISSUE_NOISE_ARTIFACT = "noise_artifact"
ISSUE_HIGH_NODATA_COVERAGE = "high_nodata_coverage"

# 问题级别
LEVEL_FATAL = "fatal"
LEVEL_WARNING = "warning"

# 问题级别映射
ISSUE_LEVELS = {
    ISSUE_FILE_MISSING: LEVEL_FATAL,
    ISSUE_CORRUPT_FILE: LEVEL_FATAL,
    ISSUE_DIMENSION_MISMATCH: LEVEL_FATAL,
    ISSUE_CHANNEL_MISMATCH: LEVEL_FATAL,
    ISSUE_INVALID_CLASS_ID: LEVEL_FATAL,
    ISSUE_DTYPE_MISMATCH: LEVEL_FATAL,
    ISSUE_EMPTY_MASK: LEVEL_WARNING,
    ISSUE_NOISE_ARTIFACT: LEVEL_WARNING,
    ISSUE_HIGH_NODATA_COVERAGE: LEVEL_WARNING,
}

# 噪点检测阈值（像素）
NOISE_AREA_THRESHOLD = 5

# 无数据区域覆盖率阈值
NODATA_COVERAGE_THRESHOLD = 0.8  # 80%

# 有效类别ID范围（默认 0-255，可配置）
VALID_CLASS_IDS = set(range(256))


def analyze_sample_fully(args):
    """
    全能分析函数：一次 I/O，完成统计 + 质检。

    Args:
        args (tuple): (sample_id, dataset_type, image_path, label_path)

    Returns:
        dict: 分析结果，包含：
            - sample_id: 样本ID
            - dataset: 数据集类型
            - status: 'ok' | 'warning' | 'error'
            - issues: 问题列表
            - stats: 统计数据（仅当 status != 'error' 时有效）
    """
    import cv2

    sample_id, dataset_type, image_path, label_path = args

    result = {
        'sample_id': sample_id,
        'dataset': dataset_type,
        'image_path': image_path,
        'label_path': label_path,
        'status': 'ok',
        'issues': [],
        'stats': None
    }

    # --- 检查 1: 文件是否存在 (Fatal) ---
    if not image_path or not os.path.exists(image_path):
        result['status'] = 'error'
        result['issues'].append(ISSUE_FILE_MISSING)
        return result

    if not label_path or not os.path.exists(label_path):
        result['status'] = 'error'
        result['issues'].append(ISSUE_FILE_MISSING)
        return result

    try:
        # --- 读取文件 (I/O 瓶颈所在) ---
        # 使用 np.fromfile + cv2.imdecode 支持中文路径
        img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        mask = cv2.imdecode(np.fromfile(label_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

        # --- 检查 2: 文件损坏 (Fatal) ---
        if img is None:
            result['status'] = 'error'
            result['issues'].append(ISSUE_CORRUPT_FILE)
            return result

        if mask is None:
            result['status'] = 'error'
            result['issues'].append(ISSUE_CORRUPT_FILE)
            return result

        # --- 检查 3: 尺寸匹配 (Fatal) ---
        img_h, img_w = img.shape[:2]
        mask_h, mask_w = mask.shape[:2] if len(mask.shape) >= 2 else (0, 0)

        if (img_h, img_w) != (mask_h, mask_w):
            result['status'] = 'error'
            result['issues'].append(ISSUE_DIMENSION_MISMATCH)
            # 尺寸不对，统计数据不可信，停止后续计算
            result['stats'] = {
                'width': img_w,
                'height': img_h,
                'mask_width': mask_w,
                'mask_height': mask_h,
                'total_pixels': 0,
                'class_pixels': {},
                'class_ratios': {},
                'classes_present': []
            }
            return result

        # --- 检查 4: 通道数异常 (Fatal) ---
        img_channels = img.shape[2] if len(img.shape) == 3 else 1
        mask_channels = mask.shape[2] if len(mask.shape) == 3 else 1

        # 图像应为 3 通道 (RGB) 或 4 通道 (RGBA)，标签应为单通道
        if img_channels not in [1, 3, 4]:
            result['status'] = 'error'
            result['issues'].append(ISSUE_CHANNEL_MISMATCH)

        if mask_channels != 1:
            # 标签不是单通道，尝试取第一通道继续处理，但记录警告
            if result['status'] == 'ok':
                result['status'] = 'error'
            result['issues'].append(ISSUE_CHANNEL_MISMATCH)

        # --- 检查 5: 位深错误 (Fatal) ---
        # 标签应为 8-bit (uint8)，图像通常为 8-bit 或 16-bit
        if mask.dtype != np.uint8:
            if result['status'] == 'ok':
                result['status'] = 'error'
            result['issues'].append(ISSUE_DTYPE_MISMATCH)

        # 如果有严重错误，停止后续计算
        if result['status'] == 'error':
            result['stats'] = {
                'width': img_w,
                'height': img_h,
                'total_pixels': 0,
                'class_pixels': {},
                'class_ratios': {},
                'classes_present': []
            }
            return result

        # =========================================
        # 到这里，说明文件是物理健康的，开始统计 + 质量分析
        # =========================================

        # 确保 mask 是单通道
        if len(mask.shape) == 3:
            mask = mask[:, :, 0]

        # --- 统计逻辑 ---
        total_pixels = mask.size
        unique_classes, counts = np.unique(mask, return_counts=True)

        class_pixels = {}
        class_ratios = {}
        has_valid_foreground = False

        for cls_id, count in zip(unique_classes, counts):
            cls_key = str(int(cls_id))
            class_pixels[cls_key] = int(count)
            ratio = float(count / total_pixels)
            class_ratios[cls_key] = ratio

            # 检查是否有前景类（非背景类 0）
            if cls_id != 0:
                has_valid_foreground = True

        # --- 检查 6: 存在定义外的类别ID (Fatal) ---
        # 检查是否有超出有效范围的类别ID（如 255 通常是忽略类）
        invalid_ids = [int(cls_id) for cls_id in unique_classes if int(cls_id) not in VALID_CLASS_IDS]
        if invalid_ids:
            result['status'] = 'error'
            result['issues'].append(ISSUE_INVALID_CLASS_ID)
        result['stats'] = {
            'width': img_w,
            'height': img_h,
            'total_pixels': total_pixels,
            'class_pixels': class_pixels,
            'class_ratios': class_ratios,
            'classes_present': [str(int(k)) for k in unique_classes]
        }

        # --- 检查 7: 质量警告 (Warning) ---

        # A. 空标签检查 (Empty Mask) - 全为背景类
        if not has_valid_foreground:
            if result['status'] == 'ok':
                result['status'] = 'warning'
            result['issues'].append(ISSUE_EMPTY_MASK)

        # B. 噪点检查 (Noise Check) - 极小连通域
        if has_valid_foreground:
            try:
                # 创建前景掩码（非背景类）
                foreground_mask = (mask > 0).astype(np.uint8)
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
                    foreground_mask, connectivity=4
                )

                # stats[:, 4] 是面积，忽略背景(index 0)
                if num_labels > 1:
                    areas = stats[1:, cv2.CC_STAT_AREA]
                    min_area = np.min(areas)

                    if min_area < NOISE_AREA_THRESHOLD:
                        if result['status'] == 'ok':
                            result['status'] = 'warning'
                        result['issues'].append(ISSUE_NOISE_ARTIFACT)
            except Exception:
                # 噪点检测失败不影响主流程
                pass

        # C. 高无数据覆盖率检查 (High Nodata Coverage) - 黑边/无数据区域 > 80%
        try:
            # 检查图像中的黑色/无数据区域
            if len(img.shape) == 3:
                # 彩色图像：所有通道都为 0 视为无数据
                nodata_mask = np.all(img == 0, axis=2)
            else:
                # 灰度图像
                nodata_mask = (img == 0)

            nodata_ratio = np.sum(nodata_mask) / total_pixels
            if nodata_ratio > NODATA_COVERAGE_THRESHOLD:
                if result['status'] == 'ok':
                    result['status'] = 'warning'
                result['issues'].append(ISSUE_HIGH_NODATA_COVERAGE)
        except Exception:
            # 无数据检测失败不影响主流程
            pass

    except Exception as e:
        result['status'] = 'error'
        result['issues'].append(f"exception: {str(e)}")

    return result
