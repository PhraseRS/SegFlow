# -*- coding: utf-8 -*-
"""
掩膜渲染器 (Mask Renderer)
负责将语义分割的灰度索引图转换为彩色可视化结果
"""

import numpy as np
import cv2
from typing import Dict, Optional, Tuple


class MaskRenderer:
    """
    掩膜渲染器类
    将单通道的类别索引图转换为彩色RGB图像,并支持与原图混合
    """

    def __init__(self, num_classes: int = 6, palette: Optional[Dict[int, list]] = None, alpha: float = 0.5):
        """
        初始化掩膜渲染器

        Args:
            num_classes: 类别数量
            palette: 调色板字典 {class_id: [R, G, B], ...}
            alpha: 透明度 0.0-1.0
        """
        self.num_classes = num_classes
        self.palette = palette if palette is not None else self._get_default_palette()
        self.alpha = np.clip(alpha, 0.0, 1.0)

    def _get_default_palette(self) -> Dict[int, list]:
        """
        获取默认调色板
        使用常见的遥感分类配色方案

        Returns:
            调色板字典
        """
        default_colors = [
            [0, 0, 0],       # 0: 背景 - 黑色
            [255, 0, 0],     # 1: 建筑 - 红色
            [0, 255, 0],     # 2: 道路 - 绿色
            [0, 0, 255],     # 3: 水体 - 蓝色
            [255, 255, 0],   # 4: 植被 - 黄色
            [255, 0, 255],   # 5: 其他 - 紫色
        ]

        palette = {}
        for i in range(self.num_classes):
            if i < len(default_colors):
                palette[i] = default_colors[i]
            else:
                # 超出预定义颜色,生成随机颜色
                palette[i] = [
                    int(np.random.randint(0, 256)),
                    int(np.random.randint(0, 256)),
                    int(np.random.randint(0, 256))
                ]

        return palette

    def set_palette(self, palette: Dict[int, list]):
        """
        更新调色板

        Args:
            palette: 新的调色板字典 {class_id: [R, G, B], ...}
        """
        self.palette = palette

    def set_alpha(self, alpha: float):
        """
        设置透明度

        Args:
            alpha: 透明度值 0.0-1.0
        """
        self.alpha = np.clip(alpha, 0.0, 1.0)

    def get_palette(self) -> Dict[int, list]:
        """获取当前调色板"""
        return self.palette.copy()

    def get_alpha(self) -> float:
        """获取当前透明度"""
        return self.alpha

    def apply_palette(self, mask: np.ndarray) -> np.ndarray:
        """
        将单通道索引图转换为RGB彩色图

        Args:
            mask: (H, W) 灰度索引图,值为类别ID

        Returns:
            colored_mask: (H, W, 3) RGB彩色图
        """
        if mask.ndim != 2:
            raise ValueError(f"mask必须是2D数组,当前维度: {mask.ndim}")

        h, w = mask.shape
        colored_mask = np.zeros((h, w, 3), dtype=np.uint8)

        # 遍历调色板,为每个类别着色
        for class_id, color in self.palette.items():
            colored_mask[mask == class_id] = color

        return colored_mask

    def blend_with_image(self, image: np.ndarray, colored_mask: np.ndarray, alpha: Optional[float] = None) -> np.ndarray:
        """
        将彩色掩膜与原图混合

        Args:
            image: (H, W, 3) 原始RGB图像
            colored_mask: (H, W, 3) 彩色掩膜
            alpha: 可选的透明度值,如果不提供则使用self.alpha

        Returns:
            blended: (H, W, 3) 混合后的图像
        """
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"image必须是3通道RGB图像,当前形状: {image.shape}")

        if colored_mask.ndim != 3 or colored_mask.shape[2] != 3:
            raise ValueError(f"colored_mask必须是3通道RGB图像,当前形状: {colored_mask.shape}")

        # 确保尺寸一致
        if image.shape[:2] != colored_mask.shape[:2]:
            colored_mask = cv2.resize(colored_mask, (image.shape[1], image.shape[0]),
                                     interpolation=cv2.INTER_NEAREST)

        # 使用指定的alpha或默认alpha
        blend_alpha = alpha if alpha is not None else self.alpha
        blend_alpha = np.clip(blend_alpha, 0.0, 1.0)

        # Alpha混合: result = image * (1-alpha) + mask * alpha
        blended = cv2.addWeighted(image, 1 - blend_alpha, colored_mask, blend_alpha, 0)

        return blended

    def render(self, image: np.ndarray, mask: np.ndarray,
               palette: Optional[Dict[int, list]] = None,
               alpha: Optional[float] = None) -> np.ndarray:
        """
        一步完成渲染: 索引图 → 彩色掩膜 → 混合

        Args:
            image: (H, W, 3) 原始RGB图像
            mask: (H, W) 灰度索引图
            palette: 可选的调色板,如果不提供则使用self.palette
            alpha: 可选的透明度,如果不提供则使用self.alpha

        Returns:
            result: (H, W, 3) 最终渲染结果
        """
        # 临时更新调色板(如果提供)
        original_palette = None
        if palette is not None:
            original_palette = self.palette
            self.palette = palette

        try:
            # 步骤1: 应用调色板
            colored_mask = self.apply_palette(mask)

            # 步骤2: 混合
            result = self.blend_with_image(image, colored_mask, alpha)

            return result

        finally:
            # 恢复原调色板
            if original_palette is not None:
                self.palette = original_palette

    def render_mask_only(self, mask: np.ndarray,
                         palette: Optional[Dict[int, list]] = None) -> np.ndarray:
        """
        仅渲染掩膜为彩色图,不与原图混合

        Args:
            mask: (H, W) 灰度索引图
            palette: 可选的调色板,如果不提供则使用self.palette

        Returns:
            colored_mask: (H, W, 3) RGB彩色图
        """
        # 临时更新调色板(如果提供)
        original_palette = None
        if palette is not None:
            original_palette = self.palette
            self.palette = palette

        try:
            colored_mask = self.apply_palette(mask)
            return colored_mask

        finally:
            # 恢复原调色板
            if original_palette is not None:
                self.palette = original_palette

    @staticmethod
    def create_from_mmseg_palette(mmseg_palette: list, alpha: float = 0.5) -> 'MaskRenderer':
        """
        从MMSegmentation的调色板格式创建渲染器

        Args:
            mmseg_palette: MMSeg格式的调色板 [[R,G,B], [R,G,B], ...]
            alpha: 透明度

        Returns:
            MaskRenderer实例
        """
        palette_dict = {i: color for i, color in enumerate(mmseg_palette)}
        return MaskRenderer(num_classes=len(mmseg_palette), palette=palette_dict, alpha=alpha)
