# -*- coding: utf-8 -*-
"""
Inference visualization widget.
"""

from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.mask_renderer import MaskRenderer
from ui.widgets.smart_canvas import DynamicImageReader


class InferenceVisualizationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = MaskRenderer()
        self._cached_image: Optional[np.ndarray] = None
        self._cached_mask: Optional[np.ndarray] = None
        self._cached_source: Optional[Tuple[str, str, int]] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.image_label = QLabel("暂无可视化结果")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)

        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)

    def render(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        classes: Optional[List[str]],
        palette: Optional[List[List[int]]],
        alpha: float = 0.5,
    ):
        self._cached_image = np.asarray(image).copy() if image is not None else None
        self._cached_mask = np.asarray(mask).copy() if mask is not None else None
        self._cached_source = None
        self._render_from_cache(classes, palette, alpha)

    def render_large_image(
        self,
        image_path: str,
        mask_path: str,
        classes: Optional[List[str]],
        palette: Optional[List[List[int]]],
        alpha: float = 0.5,
        tile_size: int = 512,
    ):
        source = (image_path, mask_path, tile_size)
        if self._cached_source == source and self._cached_image is not None and self._cached_mask is not None:
            self._render_from_cache(classes, palette, alpha)
            return

        try:
            image_tile = DynamicImageReader.read_center_preview(image_path, tile_size=tile_size, is_label=False)
            mask_tile = DynamicImageReader.read_center_preview(mask_path, tile_size=tile_size, is_label=True)

            if image_tile is None or mask_tile is None:
                self.image_label.setText(
                    "无法打开图像或掩膜文件\n\n"
                    "请检查当前机器是否正确安装 rasterio/GDAL，并Confirm该 TIFF/GeoTIFF 格式受支持。"
                )
                return

            self._cached_image = np.asarray(image_tile).copy()
            self._cached_mask = np.asarray(mask_tile).copy()
            self._cached_source = source
            self._render_from_cache(classes, palette, alpha)

        except Exception as e:
            self.image_label.setText(f"大图渲染失败: {e}")

    def rerender(
        self,
        classes: Optional[List[str]],
        palette: Optional[List[List[int]]],
        alpha: float = 0.5,
    ):
        self._render_from_cache(classes, palette, alpha)

    def clear(self):
        self._cached_image = None
        self._cached_mask = None
        self._cached_source = None
        self.image_label.clear()
        self.image_label.setText("暂无可视化结果")

    def _render_from_cache(
        self,
        classes: Optional[List[str]],
        palette: Optional[List[List[int]]],
        alpha: float,
    ):
        if self._cached_image is None or self._cached_mask is None:
            self.image_label.setText("暂无可视化结果")
            return

        try:
            class_names, palette_list = self._normalize_metadata(classes, palette, self._cached_mask)
            self.renderer.num_classes = len(class_names)
            self.renderer.set_palette({idx: color for idx, color in enumerate(palette_list)})
            self.renderer.set_alpha(alpha)

            overlay = self.renderer.render_overlay_with_legend(
                image=self._cached_image,
                mask=self._cached_mask,
                class_names=class_names,
            )
            self._display_image(overlay)

        except Exception as e:
            self.image_label.setText(f"渲染失败: {e}")

    def _normalize_metadata(
        self,
        classes: Optional[List[str]],
        palette: Optional[List[List[int]]],
        mask: np.ndarray,
    ) -> Tuple[List[str], List[List[int]]]:
        class_names = []
        for idx, name in enumerate(classes or []):
            class_names.append(str(name) if name is not None else f"Class {idx}")

        palette = list(palette or [])
        mask_class_count = 0
        if mask is not None and np.size(mask) > 0:
            mask_class_count = int(np.max(mask)) + 1

        class_count = max(len(class_names), len(palette), mask_class_count)
        if class_count <= 0:
            return [], []

        if not class_names:
            class_names = [f"Class {idx}" for idx in range(class_count)]
        elif len(class_names) < class_count:
            class_names.extend(f"Class {idx}" for idx in range(len(class_names), class_count))

        fallback_palette = MaskRenderer(num_classes=class_count).get_palette()
        palette_list: List[List[int]] = []
        for idx in range(class_count):
            if idx < len(palette) and isinstance(palette[idx], (list, tuple)) and len(palette[idx]) >= 3:
                palette_list.append([int(palette[idx][0]), int(palette[idx][1]), int(palette[idx][2])])
            else:
                palette_list.append(list(fallback_palette[idx]))

        return class_names, palette_list

    def _display_image(self, image: np.ndarray):
        height, width, _channel = image.shape
        bytes_per_line = 3 * width
        q_image = QImage(image.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        max_display_size = 800
        if width > max_display_size or height > max_display_size:
            pixmap = pixmap.scaled(
                max_display_size,
                max_display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self.image_label.setPixmap(pixmap)
