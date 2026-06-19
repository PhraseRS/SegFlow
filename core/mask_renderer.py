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
            num_classes: Class Count
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
            raise ValueError(f"mask must be 2D array, current dim: {mask.ndim}")

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
            raise ValueError(f"image must be 3 channel RGB, current shape: {image.shape}")

        if colored_mask.ndim != 3 or colored_mask.shape[2] != 3:
            raise ValueError(f"colored_mask must be 3 channel RGB, current shape: {colored_mask.shape}")

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

    def render_overlay_with_legend(self, image: np.ndarray, mask: np.ndarray,
                                    class_names: Optional[list] = None,
                                    palette: Optional[Dict[int, list]] = None,
                                    alpha: Optional[float] = None) -> np.ndarray:
        """
        渲染叠加图像，并在右侧添加图例

        Args:
            image: (H, W, 3) 原始RGB图像
            mask: (H, W) 灰度索引图
            class_names: 类别名称列表，用于绘制图例
            palette: 可选的调色板
            alpha: 可选的透明度

        Returns:
            result: (H, W+legend_width, 3) 包含图例的结果图像
        """
        # 先进行基本渲染
        overlay = self.render(image, mask, palette, alpha)

        # 如果没有类别名称，直接返回叠加图像
        if not class_names:
            return overlay

        # 绘制图例
        return self._add_legend(overlay, class_names)

    def _add_legend(self, image: np.ndarray, class_names: list, 
                    legend_bg_color: tuple = (255, 255, 255),
                    text_color: tuple = (0, 0, 0),
                    font_scale: float = 0.4,
                    thickness: int = 1) -> np.ndarray:
        """
        为图像添加图例

        Args:
            image: (H, W, 3) 输入图像
            class_names: 类别名称列表
            legend_bg_color: 图例背景颜色 (B, G, R)
            text_color: 文本颜色 (B, G, R)
            font_scale: 字体缩放系数
            thickness: 字体厚度

        Returns:
            带图例的图像
        """
        h, w, c = image.shape
        
        # 计算图例宽度（基于最长的类别名称）
        max_name_len = max([len(name) for name in class_names]) if class_names else 5
        legend_width = max(150, int(max_name_len * 8 + 80))
        
        # 计算每个类别行的高度
        line_height = int(font_scale * 30 + 10)
        
        # 创建包含图例的图像
        legend_height = max(h, len(class_names) * line_height + 20)
        result = np.ones((legend_height, w + legend_width, c), dtype=np.uint8) * 255
        
        # 复制原图像到左侧
        result[:h, :w] = image
        
        # 绘制图例背景
        result[:, w:, :] = legend_bg_color
        
        # 绘制图例内容
        y_offset = 10
        for class_id, class_name in enumerate(class_names):
            # 绘制颜色块
            color_block_size = int(line_height * 0.6)
            color = self.palette.get(class_id, [128, 128, 128])
            # OpenCV使用BGR格式，需要反转
            color_bgr = (color[2], color[1], color[0])
            x_start = w + 5
            y_start = y_offset + line_height // 2 - color_block_size // 2
            
            cv2.rectangle(result, 
                         (x_start, y_start),
                         (x_start + color_block_size, y_start + color_block_size),
                         color_bgr, -1)
            
            # 绘制文本
            cv2.putText(result,
                       class_name,
                       (x_start + color_block_size + 5, y_offset + line_height),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       font_scale,
                       text_color,
                       thickness)
            
            y_offset += line_height
        
        return result

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
