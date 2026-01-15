"""
SmartCanvas - 高性能图像查看组件
用于遥感软件的样本查看和推理可视化，支持大图加载和 Mask 叠加。
"""

import os
from enum import Enum, auto
from typing import Optional, Tuple, List
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap, QWheelEvent, QMouseEvent, QPen, QColor, QPainter
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem
)


class LayerType(Enum):
    """图层类型枚举"""
    BASE = auto()   # 原始影像
    GT = auto()     # Ground Truth 标签
    PRED = auto()   # 推理预测结果


# VOC 标签调色板
VOC_PALETTE: List[Tuple[int, int, int]] = [
    (0, 0, 0),        # 0: 背景 - 黑色
    (128, 0, 0),      # 1: 深红
    (0, 128, 0),      # 2: 深绿
    (128, 128, 0),    # 3: 橄榄
    (0, 0, 128),      # 4: 深蓝
    (128, 0, 128),    # 5: 紫色
    (0, 128, 128),    # 6: 青色
    (128, 128, 128),  # 7: 灰色
    (64, 0, 0),       # 8: 暗红
    (192, 0, 0),      # 9: 红色
    (64, 128, 0),     # 10: 黄绿
    (192, 128, 0),    # 11: 橙色
    (64, 0, 128),     # 12: 紫罗兰
    (192, 0, 128),    # 13: 粉红
    (64, 128, 128),   # 14: 浅青
    (192, 128, 128),  # 15: 浅粉
    (0, 64, 0),       # 16: 深绿2
    (128, 64, 0),     # 17: 棕色
    (0, 192, 0),      # 18: 亮绿
    (128, 192, 0),    # 19: 黄绿2
    (0, 64, 128),     # 20: 钢蓝
    (255, 255, 255),  # 21+: 白色（边界/忽略）
]


class ClippedPixmapItem(QGraphicsPixmapItem):
    """支持裁剪的图像项（用于卷帘对比）"""
    
    def __init__(self, pixmap: QPixmap = None, parent=None):
        super().__init__(pixmap, parent)
        self._clip_rect: Optional[QRectF] = None
    
    def set_clip_rect(self, rect: QRectF) -> None:
        """设置裁剪区域"""
        self._clip_rect = rect
        self.update()
    
    def clear_clip(self) -> None:
        """清除裁剪"""
        self._clip_rect = None
        self.update()
    
    def paint(self, painter: QPainter, option, widget=None) -> None:
        if self._clip_rect:
            painter.setClipRect(self._clip_rect)
        super().paint(painter, option, widget)


class SwipeLineItem(QGraphicsLineItem):
    """卷帘分割线"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        pen = QPen(QColor(255, 255, 0), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setZValue(100)


def _imread_unicode(path: str, flags: int = cv2.IMREAD_UNCHANGED) -> Optional[np.ndarray]:
    """
    支持中文路径的图像读取
    
    Args:
        path: 图像路径（支持中文）
        flags: OpenCV 读取标志
    
    Returns:
        图像数组，失败返回 None
    """
    try:
        with open(path, 'rb') as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
        return cv2.imdecode(data, flags)
    except Exception as e:
        print(f"⚠️ 读取图像失败: {path}, 错误: {e}")
        return None


class SmartCanvas(QGraphicsView):
    """
    高性能图像查看组件
    
    Features:
    - 三层架构: Base(原图), GT(标签), Pred(预测)
    - 大图自动降采样显示，坐标保持原图对齐
    - 支持透明度控制、图层显隐、缩放平移
    - 卷帘对比功能
    - 兼容 ImageViewer 接口
    """
    
    # 信号：鼠标位置变化时发出 (原图坐标)
    mouse_position_changed = Signal(int, int)
    
    # 显示缓存的最大尺寸
    MAX_DISPLAY_SIZE = 2000
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 场景
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        
        # 图层 Items (使用 ClippedPixmapItem 支持卷帘)
        self._layer_base: Optional[ClippedPixmapItem] = None
        self._layer_gt: Optional[ClippedPixmapItem] = None
        self._layer_pred: Optional[ClippedPixmapItem] = None
        
        # 原始尺寸记录 (用于坐标映射)
        self._original_size: Tuple[int, int] = (0, 0)  # (width, height)
        self._scale_factor: float = 1.0
        
        # 透明度 (0.0 ~ 1.0)
        self._overlay_opacity: float = 0.7
        
        # 图层可见性
        self._show_base: bool = True
        self._show_gt: bool = True
        self._show_pred: bool = True
        
        # 卷帘对比
        self._swipe_enabled: bool = False
        self._swipe_position: int = 50  # 百分比 0-100
        self._swipe_line: Optional[SwipeLineItem] = None
        
        # 当前文件路径
        self._current_image_path: Optional[str] = None
        self._current_label_path: Optional[str] = None
        
        # 配置视图
        self._setup_view()
    
    def _setup_view(self) -> None:
        """配置视图属性"""
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)

    # ==================== 文件加载接口 (兼容 ImageViewer) ====================
    
    def load_sample(self, image_path: str, label_path: Optional[str] = None) -> bool:
        """
        加载样本（影像 + 可选的标签）
        
        Args:
            image_path: 影像文件路径
            label_path: 标签文件路径（可选）
        
        Returns:
            是否加载成功
        """
        self.clear()
        success = self.load_image(image_path)
        if label_path:
            self.load_label(label_path)
        return success
    
    def load_image(self, image_path: str) -> bool:
        """加载影像文件"""
        if not os.path.exists(image_path):
            print(f"⚠️ 影像文件不存在: {image_path}")
            return False
        
        # 使用支持中文路径的方法加载
        image_np = _imread_unicode(image_path, cv2.IMREAD_UNCHANGED)
        if image_np is None:
            print(f"⚠️ 无法加载影像: {image_path}")
            return False
        
        # 处理多通道图像
        if image_np.ndim == 2:
            pass  # 灰度图
        elif image_np.shape[2] == 4:
            image_np = cv2.cvtColor(image_np, cv2.COLOR_BGRA2BGR)
        
        self._current_image_path = image_path
        
        # 清空并重新加载
        self._clear_layers()
        
        h, w = image_np.shape[:2]
        self._original_size = (w, h)
        
        # 计算缩放因子
        max_dim = max(w, h)
        self._scale_factor = max_dim / self.MAX_DISPLAY_SIZE if max_dim > self.MAX_DISPLAY_SIZE else 1.0
        
        # 创建基础图层
        self._layer_base = self._create_layer_item(image_np, is_mask=False)
        self._scene.addItem(self._layer_base)
        self._layer_base.setZValue(0)
        self._layer_base.setVisible(self._show_base)
        
        # 设置场景范围并适应视图
        self._scene.setSceneRect(0, 0, w, h)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        
        print(f"✅ 已加载影像: {image_path}")
        return True
    
    def load_label(self, label_path: str) -> bool:
        """加载标签影像（自动应用伪彩色）"""
        if not os.path.exists(label_path):
            print(f"⚠️ 标签文件不存在: {label_path}")
            return False
        
        # 使用支持中文路径的方法加载（灰度模式）
        label_np = _imread_unicode(label_path, cv2.IMREAD_GRAYSCALE)
        if label_np is None:
            print(f"⚠️ 无法加载标签: {label_path}")
            return False
        
        self._current_label_path = label_path
        
        # 应用 VOC 调色板
        colored_label = self._apply_voc_colormap(label_np)
        
        # 移除旧的 GT 图层
        if self._layer_gt:
            self._scene.removeItem(self._layer_gt)
        
        # 创建 GT 图层
        self._layer_gt = self._create_layer_item(colored_label, is_mask=True)
        self._scene.addItem(self._layer_gt)
        self._layer_gt.setZValue(1)
        self._layer_gt.setOpacity(self._overlay_opacity)
        self._layer_gt.setVisible(self._show_gt)
        
        # 如果卷帘模式开启，更新裁剪
        if self._swipe_enabled:
            self._update_swipe_clip()
        
        print(f"✅ 已加载标签（伪彩色）: {label_path}")
        return True
    
    def _apply_voc_colormap(self, label_np: np.ndarray) -> np.ndarray:
        """
        将灰度标签转换为 VOC 伪彩色 RGBA
        
        Args:
            label_np: 灰度标签 (H, W)，像素值为类别索引
        
        Returns:
            RGBA 图像 (H, W, 4)
        """
        h, w = label_np.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        
        for class_idx in range(len(VOC_PALETTE)):
            mask = label_np == class_idx
            if not np.any(mask):
                continue
            r, g, b = VOC_PALETTE[class_idx]
            rgba[mask, 0] = r
            rgba[mask, 1] = g
            rgba[mask, 2] = b
            # 背景类透明，其他不透明
            rgba[mask, 3] = 0 if class_idx == 0 else 255
        
        # 处理超出调色板范围的类别
        out_of_range = label_np >= len(VOC_PALETTE)
        if np.any(out_of_range):
            rgba[out_of_range] = [255, 255, 255, 255]
        
        return rgba

    # ==================== Numpy 数据加载接口 ====================
    
    def load_data(
        self,
        image_np: np.ndarray,
        gt_mask_np: Optional[np.ndarray] = None,
        pred_mask_np: Optional[np.ndarray] = None
    ) -> None:
        """
        加载 Numpy 图像数据
        
        Args:
            image_np: 原始图像 (H, W, C) BGR 或 (H, W) 灰度
            gt_mask_np: Ground Truth 标签 (H, W) 或 (H, W, C)
            pred_mask_np: 预测结果 (H, W) 或 (H, W, C)
        """
        self._clear_layers()
        
        h, w = image_np.shape[:2]
        self._original_size = (w, h)
        
        max_dim = max(w, h)
        self._scale_factor = max_dim / self.MAX_DISPLAY_SIZE if max_dim > self.MAX_DISPLAY_SIZE else 1.0
        
        # 加载基础图层
        self._layer_base = self._create_layer_item(image_np, is_mask=False)
        self._scene.addItem(self._layer_base)
        self._layer_base.setZValue(0)
        self._layer_base.setVisible(self._show_base)
        
        # 加载 GT 图层
        if gt_mask_np is not None:
            # 如果是灰度 mask，应用调色板
            if gt_mask_np.ndim == 2:
                gt_mask_np = self._apply_voc_colormap(gt_mask_np)
            self._layer_gt = self._create_layer_item(gt_mask_np, is_mask=True)
            self._scene.addItem(self._layer_gt)
            self._layer_gt.setZValue(1)
            self._layer_gt.setOpacity(self._overlay_opacity)
            self._layer_gt.setVisible(self._show_gt)
        
        # 加载 Pred 图层
        if pred_mask_np is not None:
            if pred_mask_np.ndim == 2:
                pred_mask_np = self._apply_voc_colormap(pred_mask_np)
            self._layer_pred = self._create_layer_item(pred_mask_np, is_mask=True)
            self._scene.addItem(self._layer_pred)
            self._layer_pred.setZValue(2)
            self._layer_pred.setOpacity(self._overlay_opacity)
            self._layer_pred.setVisible(self._show_pred)
        
        self._scene.setSceneRect(0, 0, w, h)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def _create_layer_item(
        self,
        data_np: np.ndarray,
        is_mask: bool = False
    ) -> ClippedPixmapItem:
        """创建图层 Item"""
        h, w = data_np.shape[:2]
        
        # 降采样
        if self._scale_factor > 1.0:
            new_w = int(w / self._scale_factor)
            new_h = int(h / self._scale_factor)
            interp = cv2.INTER_NEAREST if is_mask else cv2.INTER_AREA
            display_data = cv2.resize(data_np, (new_w, new_h), interpolation=interp)
        else:
            display_data = data_np
        
        pixmap = self._numpy_to_pixmap(display_data, is_mask)
        
        item = ClippedPixmapItem(pixmap)
        item.setScale(self._scale_factor)
        item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        
        return item
    
    def _numpy_to_pixmap(self, data_np: np.ndarray, is_mask: bool = False) -> QPixmap:
        """高效地将 Numpy 数组转换为 QPixmap"""
        h, w = data_np.shape[:2]
        
        if data_np.ndim == 2:
            if is_mask:
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                rgba[..., :3] = data_np[..., np.newaxis]
                rgba[..., 3] = (data_np > 0).astype(np.uint8) * 255
                data_np = rgba
            else:
                data_np = cv2.cvtColor(data_np, cv2.COLOR_GRAY2RGB)
        elif data_np.ndim == 3:
            channels = data_np.shape[2]
            if channels == 3:
                if is_mask:
                    rgba = np.zeros((h, w, 4), dtype=np.uint8)
                    rgba[..., :3] = cv2.cvtColor(data_np, cv2.COLOR_BGR2RGB)
                    rgba[..., 3] = (np.any(data_np > 0, axis=2)).astype(np.uint8) * 255
                    data_np = rgba
                else:
                    data_np = cv2.cvtColor(data_np, cv2.COLOR_BGR2RGB)
            elif channels == 4:
                # 已经是 RGBA，只需确保顺序正确
                if not is_mask:
                    data_np = cv2.cvtColor(data_np, cv2.COLOR_BGRA2RGBA)
        
        if not data_np.flags['C_CONTIGUOUS']:
            data_np = np.ascontiguousarray(data_np)
        
        h, w = data_np.shape[:2]
        if data_np.ndim == 3 and data_np.shape[2] == 4:
            fmt = QImage.Format.Format_RGBA8888
            bytes_per_line = w * 4
        else:
            fmt = QImage.Format.Format_RGB888
            bytes_per_line = w * 3
        
        qimage = QImage(data_np.data, w, h, bytes_per_line, fmt)
        return QPixmap.fromImage(qimage.copy())
    
    def _clear_layers(self) -> None:
        """清空所有图层"""
        self._scene.clear()
        self._layer_base = None
        self._layer_gt = None
        self._layer_pred = None
        self._swipe_line = None

    # ==================== 图层控制 ====================
    
    def set_overlay_opacity(self, value: float) -> None:
        """设置叠加层透明度 (0.0 ~ 1.0)"""
        self._overlay_opacity = max(0.0, min(1.0, value))
        if not self._swipe_enabled:
            if self._layer_gt:
                self._layer_gt.setOpacity(self._overlay_opacity)
            if self._layer_pred:
                self._layer_pred.setOpacity(self._overlay_opacity)
    
    def set_label_opacity(self, opacity: int) -> None:
        """设置标签透明度 (0-100)，兼容 ImageViewer 接口"""
        self.set_overlay_opacity(opacity / 100.0)
    
    def set_layer_visible(self, layer_type: LayerType, visible: bool) -> None:
        """设置图层可见性"""
        layer = self._get_layer(layer_type)
        if layer:
            layer.setVisible(visible)
        # 更新内部状态
        if layer_type == LayerType.BASE:
            self._show_base = visible
        elif layer_type == LayerType.GT:
            self._show_gt = visible
        elif layer_type == LayerType.PRED:
            self._show_pred = visible
    
    def set_image_visible(self, visible: bool) -> None:
        """设置影像可见性，兼容 ImageViewer 接口"""
        self.set_layer_visible(LayerType.BASE, visible)
    
    def set_label_visible(self, visible: bool) -> None:
        """设置标签可见性，兼容 ImageViewer 接口"""
        self.set_layer_visible(LayerType.GT, visible)
    
    def is_layer_visible(self, layer_type: LayerType) -> bool:
        """获取图层可见性"""
        layer = self._get_layer(layer_type)
        return layer.isVisible() if layer else False
    
    def _get_layer(self, layer_type: LayerType) -> Optional[ClippedPixmapItem]:
        """根据类型获取图层"""
        mapping = {
            LayerType.BASE: self._layer_base,
            LayerType.GT: self._layer_gt,
            LayerType.PRED: self._layer_pred,
        }
        return mapping.get(layer_type)
    
    # ==================== 卷帘对比 ====================
    
    def set_swipe_enabled(self, enabled: bool) -> None:
        """启用/禁用卷帘对比模式"""
        self._swipe_enabled = enabled
        
        if enabled:
            # 启用卷帘：标签不透明，显示两个图层
            if self._layer_gt:
                self._layer_gt.setOpacity(1.0)
                self._layer_gt.setVisible(True)
            if self._layer_base:
                self._layer_base.setVisible(True)
            self._update_swipe_clip()
        else:
            # 禁用卷帘：清除裁剪，恢复透明度和可见性
            if self._layer_base:
                self._layer_base.clear_clip()
            if self._layer_gt:
                self._layer_gt.clear_clip()
                self._layer_gt.setOpacity(self._overlay_opacity)
            if self._swipe_line:
                self._scene.removeItem(self._swipe_line)
                self._swipe_line = None
            # 恢复可见性
            if self._layer_base:
                self._layer_base.setVisible(self._show_base)
            if self._layer_gt:
                self._layer_gt.setVisible(self._show_gt)
    
    def set_swipe_position(self, position: int) -> None:
        """设置卷帘位置 (0-100)"""
        self._swipe_position = max(0, min(100, position))
        if self._swipe_enabled:
            self._update_swipe_clip()
    
    def _update_swipe_clip(self) -> None:
        """更新卷帘裁剪区域"""
        if not self._layer_gt:
            return
        
        w, h = self._original_size
        if w == 0 or h == 0:
            return
        
        split_x = w * self._swipe_position / 100.0
        
        # 底图完整显示
        if self._layer_base:
            self._layer_base.clear_clip()
        
        # 标签只显示分割线右侧
        right_rect = QRectF(split_x, 0, w - split_x, h)
        self._layer_gt.set_clip_rect(right_rect)
        
        # 更新分割线
        if not self._swipe_line:
            self._swipe_line = SwipeLineItem()
            self._scene.addItem(self._swipe_line)
        self._swipe_line.setLine(split_x, 0, split_x, h)

    # ==================== 交互事件 ====================
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """鼠标滚轮缩放"""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1 / zoom_factor, 1 / zoom_factor)
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动时发出原图坐标"""
        super().mouseMoveEvent(event)
        scene_pos = self.mapToScene(event.position().toPoint())
        x, y = int(scene_pos.x()), int(scene_pos.y())
        w, h = self._original_size
        if 0 <= x < w and 0 <= y < h:
            self.mouse_position_changed.emit(x, y)
    
    # ==================== 便捷方法 ====================
    
    def fit_to_view(self) -> None:
        """适应视图大小"""
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def fit_to_window(self) -> None:
        """适应窗口，兼容 ImageViewer 接口"""
        self.fit_to_view()
    
    def zoom_in(self) -> None:
        """放大"""
        self.scale(1.2, 1.2)
    
    def zoom_out(self) -> None:
        """缩小"""
        self.scale(1 / 1.2, 1 / 1.2)
    
    def reset_zoom(self) -> None:
        """重置缩放为 1:1"""
        self.resetTransform()
    
    def get_original_size(self) -> Tuple[int, int]:
        """获取原图尺寸 (width, height)"""
        return self._original_size
    
    def update_gt_mask(self, mask_np: np.ndarray) -> None:
        """更新 GT 图层"""
        if self._layer_gt:
            self._scene.removeItem(self._layer_gt)
        
        if mask_np.ndim == 2:
            mask_np = self._apply_voc_colormap(mask_np)
        
        self._layer_gt = self._create_layer_item(mask_np, is_mask=True)
        self._scene.addItem(self._layer_gt)
        self._layer_gt.setZValue(1)
        self._layer_gt.setOpacity(self._overlay_opacity)
        self._layer_gt.setVisible(self._show_gt)
    
    def update_pred_mask(self, mask_np: np.ndarray) -> None:
        """更新 Pred 图层"""
        if self._layer_pred:
            self._scene.removeItem(self._layer_pred)
        
        if mask_np.ndim == 2:
            mask_np = self._apply_voc_colormap(mask_np)
        
        self._layer_pred = self._create_layer_item(mask_np, is_mask=True)
        self._scene.addItem(self._layer_pred)
        self._layer_pred.setZValue(2)
        self._layer_pred.setOpacity(self._overlay_opacity)
        self._layer_pred.setVisible(self._show_pred)
    
    def clear(self) -> None:
        """清空画布"""
        self._clear_layers()
        self._original_size = (0, 0)
        self._scale_factor = 1.0
        self._current_image_path = None
        self._current_label_path = None
