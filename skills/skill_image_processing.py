# -*- coding: utf-8 -*-
"""
---
name: skill_image_processing
description: >
  遥感/语义分割图像处理工具集。
  包含 VOC 调色板常量、标签图像伪彩色渲染、遥感图像线性拉伸等通用函数。
  不依赖任何特定模型架构，可在缩略图生成、画布渲染等多处复用。
parameters:
  apply_colormap:
    label_image: QImage - 单通道灰度标签图像
    palette: list[tuple] - RGB 调色板，默认使用 VOC_PALETTE
    returns: QImage - ARGB32 格式的伪彩色图像（背景类 alpha=0）
  apply_linear_stretch:
    image: QImage - 输入 RGB 图像
    percent: float - 截断百分比（默认 2%）
    returns: QImage - 拉伸后的 RGB32 图像
returns:
  VOC_PALETTE: list[tuple] - PASCAL VOC 标准 22 色调色板
  apply_colormap: callable
  apply_linear_stretch: callable
---
"""

from PySide6.QtGui import QImage


# ============== VOC 调色板常量 ==============

VOC_PALETTE = [
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (128, 128, 128),
    (64, 0, 0), (192, 0, 0), (64, 128, 0), (192, 128, 0),
    (64, 0, 128), (192, 0, 128), (64, 128, 128), (192, 128, 128),
    (0, 64, 0), (128, 64, 0), (0, 192, 0), (128, 192, 0),
    (0, 64, 128), (255, 255, 255),
]


def apply_colormap(label_image, palette=None):
    """
    将单通道标签图像转换为伪彩色 QImage。

    Args:
        label_image (QImage): 单通道灰度标签图像。
        palette (list[tuple], optional): RGB 调色板。默认使用 VOC_PALETTE。

    Returns:
        QImage: ARGB32 格式的伪彩色图像（背景类 gray==0 时 alpha=0）。
    """
    if palette is None:
        palette = VOC_PALETTE

    width = label_image.width()
    height = label_image.height()
    colored = QImage(width, height, QImage.Format.Format_ARGB32)

    for y in range(height):
        for x in range(width):
            pixel = label_image.pixel(x, y)
            gray = pixel & 0xFF
            if gray < len(palette):
                r, g, b = palette[gray]
            else:
                r, g, b = 255, 255, 255
            alpha = 0 if gray == 0 else 255
            colored.setPixel(x, y, (alpha << 24) | (r << 16) | (g << 8) | b)

    return colored


def apply_linear_stretch(image, percent=2):
    """
    对 QImage 应用线性 percent% 拉伸（遥感影像增强常用）。

    Args:
        image (QImage): 输入 RGB 图像。
        percent (float): 上下截断百分比，默认 2%。

    Returns:
        QImage: 拉伸后的 RGB32 图像；若无法拉伸则返回原图。
    """
    width = image.width()
    height = image.height()

    if image.format() != QImage.Format.Format_RGB32:
        image = image.convertToFormat(QImage.Format.Format_RGB32)

    # 收集像素亮度
    pixels = []
    for y in range(height):
        for x in range(width):
            pixel = image.pixel(x, y)
            r = (pixel >> 16) & 0xFF
            g = (pixel >> 8) & 0xFF
            b = pixel & 0xFF
            luminance = int(0.299 * r + 0.587 * g + 0.114 * b)
            pixels.append(luminance)

    if not pixels:
        return image

    pixels.sort()
    n = len(pixels)
    low_idx = int(n * percent / 100)
    high_idx = int(n * (100 - percent) / 100) - 1

    if low_idx >= high_idx:
        return image

    low_val = pixels[low_idx]
    high_val = pixels[high_idx]

    if high_val <= low_val:
        return image

    result = QImage(width, height, QImage.Format.Format_RGB32)
    scale = 255.0 / (high_val - low_val)

    for y in range(height):
        for x in range(width):
            pixel = image.pixel(x, y)
            r = (pixel >> 16) & 0xFF
            g = (pixel >> 8) & 0xFF
            b = pixel & 0xFF

            r_new = int(max(0, min(255, (r - low_val) * scale)))
            g_new = int(max(0, min(255, (g - low_val) * scale)))
            b_new = int(max(0, min(255, (b - low_val) * scale)))

            result.setPixel(x, y, (255 << 24) | (r_new << 16) | (g_new << 8) | b_new)

    return result
