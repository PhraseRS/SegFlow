# -*- coding: utf-8 -*-
"""
推理可视化渲染组件 (Inference Visualization Widget)
用于渲染和显示语义分割推理结果
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
import numpy as np
from typing import List, Optional
import os

from core.mask_renderer import MaskRenderer


class InferenceVisualizationWidget(QWidget):
    """
    推理可视化渲染组件
    负责渲染小图和大图的推理结果
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = MaskRenderer()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 图像显示标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)

        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)

    def render(self, image: np.ndarray, mask: np.ndarray,
               classes: List[str], palette: List[List[int]],
               alpha: float = 0.5):
        """
        渲染小图推理结果

        Args:
            image: 原始图像 (H, W, 3) RGB格式
            mask: 分割掩码 (H, W) 类别索引
            classes: 类别名称列表
            palette: 调色板 [[R,G,B], ...]
            alpha: 叠加透明度
        """
        try:
            # 更新渲染器配置
            self.renderer.num_classes = len(classes)
            self.renderer.palette = {i: color for i, color in enumerate(palette)}
            self.renderer.alpha = alpha

            # 渲染叠加图像
            overlay = self.renderer.render_overlay_with_legend(
                image=image,
                mask=mask,
                class_names=classes
            )

            # 转换为QPixmap并显示
            self._display_image(overlay)

        except Exception as e:
            self.image_label.setText(f"渲染失败: {str(e)}")

    def render_large_image(self, image_path: str, mask_path: str,
                          classes: List[str], palette: List[List[int]],
                          alpha: float = 0.5, tile_size: int = 512):
        """
        渲染大图推理结果（分块加载）

        Args:
            image_path: 原始图像路径
            mask_path: 分割掩码路径（GeoTIFF）
            classes: 类别名称列表
            palette: 调色板
            alpha: 叠加透明度
            tile_size: 分块大小
        """
        try:
            from osgeo import gdal

            # 打开图像和掩码
            image_ds = gdal.Open(image_path)
            mask_ds = gdal.Open(mask_path)

            if not image_ds or not mask_ds:
                self.image_label.setText("无法打开图像或掩码文件")
                return

            # 读取中心区域作为预览
            width = image_ds.RasterXSize
            height = image_ds.RasterYSize

            # 计算预览区域（中心512x512）
            preview_size = min(tile_size, width, height)
            x_offset = (width - preview_size) // 2
            y_offset = (height - preview_size) // 2

            # 读取图像数据
            image_tile = np.zeros((preview_size, preview_size, 3), dtype=np.uint8)
            for i in range(3):
                band = image_ds.GetRasterBand(i + 1)
                image_tile[:, :, i] = band.ReadAsArray(x_offset, y_offset, preview_size, preview_size)

            # 读取掩码数据
            mask_band = mask_ds.GetRasterBand(1)
            mask_tile = mask_band.ReadAsArray(x_offset, y_offset, preview_size, preview_size)

            # 更新渲染器配置
            self.renderer.num_classes = len(classes)
            self.renderer.palette = {i: color for i, color in enumerate(palette)}
            self.renderer.alpha = alpha

            # 渲染叠加图像
            overlay = self.renderer.render_overlay_with_legend(
                image=image_tile,
                mask=mask_tile,
                class_names=classes
            )

            # 显示
            self._display_image(overlay)

            # 关闭数据集
            image_ds = None
            mask_ds = None

        except Exception as e:
            self.image_label.setText(f"大图渲染失败: {str(e)}")

    def clear(self):
        """清空显示"""
        self.image_label.clear()
        self.image_label.setText("暂无可视化结果")

    def _display_image(self, image: np.ndarray):
        """
        将numpy数组转换为QPixmap并显示

        Args:
            image: RGB图像数组 (H, W, 3)
        """
        height, width, channel = image.shape
        bytes_per_line = 3 * width

        # 转换为QImage
        q_image = QImage(
            image.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )

        # 转换为QPixmap
        pixmap = QPixmap.fromImage(q_image)

        # 显示（限制最大显示尺寸）
        max_display_size = 800
        if width > max_display_size or height > max_display_size:
            pixmap = pixmap.scaled(
                max_display_size,
                max_display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        self.image_label.setPixmap(pixmap)
