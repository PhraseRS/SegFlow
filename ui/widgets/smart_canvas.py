"""
SmartCanvas - 高性能图像查看组件
核心渲染引擎，支持大图动态LOD加载、多图层叠加、交互控制。
优化版：后台线程加载 + LOD缓存 + 渐进式显示
"""

import os
import numpy as np
import cv2
from typing import Optional, Tuple, Dict, Any, List
from enum import Enum, auto
from collections import OrderedDict

from PySide6.QtCore import Qt, Signal, QRectF, QThread, QObject, QTimer, QPointF, QMutex, QMutexLocker
from PySide6.QtGui import QImage, QPixmap, QWheelEvent, QMouseEvent, QPen, QColor, QPainter, QAction, QPalette, QTransform
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem,
    QMenu, QMessageBox, QProgressDialog, QApplication
)

try:
    import rasterio
    from rasterio.transform import Affine
    from rasterio.enums import Resampling
    from rasterio.windows import Window
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    Affine = None
    Resampling = None
    Window = None

# ==================== 辅助类与枚举 ====================

class InteractiveMode(Enum):
    """交互模式枚举"""
    NORMAL = auto()
    PAN = auto()
    DRAW = auto()


class LODCache:
    """LOD级别缓存 (LRU策略)"""
    
    def __init__(self, max_size: int = 4):
        self._cache: OrderedDict[int, Tuple[QPixmap, float, Tuple[int, int]]] = OrderedDict()
        self._max_size = max_size
        self._mutex = QMutex()
    
    def get(self, level: int) -> Optional[Tuple[QPixmap, float, Tuple[int, int]]]:
        """获取缓存，命中时移到末尾(最近使用)"""
        with QMutexLocker(self._mutex):
            if level in self._cache:
                self._cache.move_to_end(level)
                return self._cache[level]
            return None
    
    def put(self, level: int, pixmap: QPixmap, scale: float, offset: Tuple[int, int]):
        """存入缓存"""
        with QMutexLocker(self._mutex):
            if level in self._cache:
                self._cache.move_to_end(level)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # 移除最旧的
                self._cache[level] = (pixmap, scale, offset)
    
    def clear(self):
        """清空缓存"""
        with QMutexLocker(self._mutex):
            self._cache.clear()
    
    def has(self, level: int) -> bool:
        with QMutexLocker(self._mutex):
            return level in self._cache


class ImageLoaderWorker(QObject):
    """后台图像加载工作器"""
    finished = Signal(int, int, object, float, tuple)  # z_value, level, pixmap, scale, offset
    
    def __init__(self):
        super().__init__()
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def load(self, z_value: int, path: str, level: int, apply_colormap: bool):
        """执行加载"""
        if self._cancelled:
            return
        
        try:
            data, scale, offset = DynamicImageReader.read_at_level(path, level)
            
            if self._cancelled or data is None:
                return
            
            # 应用伪彩色
            if apply_colormap and data.ndim == 2:
                data = self._apply_voc_colormap(data)
            
            # 转换为 QPixmap
            pixmap = self._numpy_to_pixmap(data)
            
            if not self._cancelled:
                self.finished.emit(z_value, level, pixmap, scale, offset)
                
        except Exception as e:
            print(f"⚠️ 后台加载失败: {e}")
    
    def _apply_voc_colormap(self, label_np: np.ndarray) -> np.ndarray:
        h, w = label_np.shape
        bgra = np.zeros((h, w, 4), dtype=np.uint8)
        for i, color in enumerate(VOC_PALETTE_BGR):
            if i >= len(VOC_PALETTE_BGR):
                break
            mask = label_np == i
            if np.any(mask):
                bgra[mask, :3] = color
                bgra[mask, 3] = 0 if i == 0 else 255
        return bgra
    
    def _numpy_to_pixmap(self, img_np: np.ndarray) -> QPixmap:
        h, w = img_np.shape[:2]
        if img_np.ndim == 2:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2RGB)
        elif img_np.shape[2] == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
        elif img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGRA2RGBA)
        
        if not img_np.flags['C_CONTIGUOUS']:
            img_np = np.ascontiguousarray(img_np)
        
        if img_np.shape[2] == 4:
            fmt = QImage.Format.Format_RGBA8888
            bpl = w * 4
        else:
            fmt = QImage.Format.Format_RGB888
            bpl = w * 3
        
        qimg = QImage(img_np.data, w, h, bpl, fmt)
        return QPixmap.fromImage(qimg.copy())


class ImageLoaderThread(QThread):
    """后台加载线程"""
    finished = Signal(int, int, object, float, tuple)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = ImageLoaderWorker()
        self._worker.finished.connect(self.finished)
        self._tasks = []
        self._mutex = QMutex()
        self._running = True
    
    def add_task(self, z_value: int, path: str, level: int, apply_colormap: bool):
        with QMutexLocker(self._mutex):
            # 替换相同z_value的任务
            self._tasks = [(z, p, l, c) for z, p, l, c in self._tasks if z != z_value]
            self._tasks.append((z_value, path, level, apply_colormap))
    
    def run(self):
        while self._running:
            task = None
            with QMutexLocker(self._mutex):
                if self._tasks:
                    task = self._tasks.pop(0)
            
            if task:
                z_value, path, level, apply_colormap = task
                self._worker.load(z_value, path, level, apply_colormap)
            else:
                self.msleep(50)
    
    def stop(self):
        self._running = False
        self._worker.cancel()
        self.wait()


class ImageLayerInfo:
    """图层元数据信息"""
    def __init__(self, path: str, z_value: int = 0, opacity: float = 1.0, apply_colormap: bool = False):
        self.path = path
        self.z_value = z_value
        self.opacity = opacity
        self.apply_colormap = apply_colormap
        
        self.width = 0
        self.height = 0
        self.count = 1
        self.has_pyramid = False
        self.overviews = []
        
        self.item: Optional[QGraphicsPixmapItem] = None
        self.current_level = 0
        self.cache = LODCache(max_size=4)
        self.loading_level = 0  # 正在加载的级别
        
        self._load_metadata()
    
    def _load_metadata(self):
        if not os.path.exists(self.path):
            return
        
        if HAS_RASTERIO:
            try:
                with rasterio.open(self.path) as src:
                    self.width = src.width
                    self.height = src.height
                    self.count = src.count
                    self.overviews = src.overviews(1) if src.count >= 1 else []
                    self.has_pyramid = len(self.overviews) > 0
            except Exception as e:
                self._load_metadata_opencv()
        else:
            self._load_metadata_opencv()
    
    def _load_metadata_opencv(self):
        try:
            with open(self.path, 'rb') as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if img is not None:
                self.height, self.width = img.shape[:2]
                self.count = 1 if img.ndim == 2 else img.shape[2]
        except:
            pass


class DynamicImageReader:
    """动态图像读取器"""
    
    LOD_LEVELS = [
        (0.03125, 32),
        (0.0625, 16),
        (0.125, 8),
        (0.25, 4),
        (0.5, 2),
        (1.0, 1),
    ]
    
    @staticmethod
    def get_required_level(view_scale: float) -> int:
        for threshold, level in DynamicImageReader.LOD_LEVELS:
            if view_scale <= threshold:
                return level
        return 1
    
    @staticmethod
    def read_at_level(
        path: str, 
        level: int, 
        viewport_rect: Optional[QRectF] = None
    ) -> Tuple[Optional[np.ndarray], float, Tuple[int, int]]:
        if not os.path.exists(path):
            return None, 1.0, (0, 0)
        
        if not HAS_RASTERIO:
            return DynamicImageReader._read_with_opencv(path, level)
        
        try:
            with rasterio.open(path) as src:
                actual_level = DynamicImageReader._get_best_level(src, level)
                out_h = max(1, src.height // actual_level)
                out_w = max(1, src.width // actual_level)
                data = DynamicImageReader._read_full(src, out_h, out_w)
                return data, 1.0 / actual_level, (0, 0)
        except Exception as e:
            return DynamicImageReader._read_with_opencv(path, level)
    
    @staticmethod
    def _get_best_level(src, requested_level: int) -> int:
        overviews = src.overviews(1) if src.count >= 1 else []
        if not overviews:
            return requested_level
        best = 1
        for ov_level in overviews:
            if ov_level <= requested_level:
                best = ov_level
            else:
                break
        return best
    
    @staticmethod
    def _read_full(src, out_h: int, out_w: int) -> np.ndarray:
        # 使用 nearest 进行快速读取
        resample = Resampling.nearest if out_h * out_w > 2000 * 2000 else Resampling.bilinear
        
        if src.count == 1:
            data = src.read(1, out_shape=(out_h, out_w), resampling=resample)
        elif src.count >= 3:
            r = src.read(1, out_shape=(out_h, out_w), resampling=resample)
            g = src.read(2, out_shape=(out_h, out_w), resampling=resample)
            b = src.read(3, out_shape=(out_h, out_w), resampling=resample)
            data = cv2.merge([b, g, r])
        else:
            data = src.read(1, out_shape=(out_h, out_w), resampling=resample)
        return data
    
    @staticmethod
    def _read_with_opencv(path: str, level: int) -> Tuple[Optional[np.ndarray], float, Tuple[int, int]]:
        try:
            with open(path, 'rb') as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if img is None:
                return None, 1.0, (0, 0)
            if level > 1:
                h, w = img.shape[:2]
                new_h, new_w = max(1, h // level), max(1, w // level)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return img, 1.0 / level, (0, 0)
        except:
            return None, 1.0, (0, 0)


# VOC 标签调色板 (BGR)
VOC_PALETTE_BGR = [
    (0, 0, 0), (0, 0, 128), (0, 128, 0), (0, 128, 128),
    (128, 0, 0), (128, 0, 128), (128, 128, 0), (128, 128, 128),
    (0, 0, 64), (0, 0, 192), (0, 128, 64), (0, 128, 192),
    (128, 0, 64), (128, 0, 192), (128, 128, 64), (128, 128, 192),
    (0, 64, 0), (0, 64, 128), (0, 192, 0), (0, 192, 128),
    (128, 64, 0), (255, 255, 255),
]


class SmartCanvas(QGraphicsView):
    """高性能图像查看器 - 优化版"""
    
    mouse_position_changed = Signal(int, int)
    lod_changed = Signal(int)
    
    # 防抖延迟
    LOD_UPDATE_DELAY_ZOOM = 200    # 缩放后延迟
    LOD_UPDATE_DELAY_PAN = 350     # 拖动后延迟
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._scene = QGraphicsScene(self)
        self._scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.setScene(self._scene)
        
        self._setup_view()
        self._interactive_mode = InteractiveMode.NORMAL
        
        self._layers: Dict[int, ImageLayerInfo] = {}
        self._current_lod_level = 0
        
        # 防抖定时器
        self._lod_update_timer = QTimer(self)
        self._lod_update_timer.setSingleShot(True)
        self._lod_update_timer.timeout.connect(self._update_lod)
        self._current_delay = self.LOD_UPDATE_DELAY_ZOOM
        
        # 后台加载线程
        self._loader_thread = ImageLoaderThread(self)
        self._loader_thread.finished.connect(self._on_layer_loaded)
        self._loader_thread.start()
        
        # 交互状态
        self._is_panning = False
        
    def _setup_view(self):
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self._update_background_from_palette()
        
        # 禁用视口缓存提升性能
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)

    def load_image_layer(
        self, path: str, pos: Tuple[int, int] = (0, 0), 
        z_value: int = 0, opacity: float = 1.0, apply_colormap: bool = False
    ) -> Optional[QGraphicsPixmapItem]:
        if not os.path.exists(path):
            return None
        
        layer_info = ImageLayerInfo(path, z_value, opacity, apply_colormap)
        if layer_info.width == 0:
            return None
        
        if z_value in self._layers:
            old = self._layers[z_value]
            if old.item:
                self._scene.removeItem(old.item)
            old.cache.clear()
        
        self._layers[z_value] = layer_info
        
        # 快速初始加载 (低分辨率)
        initial_level = self._calculate_initial_level(layer_info)
        self._load_layer_sync(layer_info, initial_level)
        self._update_scene_rect()
        
        return layer_info.item

    def load_layer_from_numpy(
        self, img_np: np.ndarray, pos: Tuple[int, int] = (0, 0),
        z_value: int = 0, opacity: float = 1.0, apply_colormap: bool = False
    ) -> Optional[QGraphicsPixmapItem]:
        if apply_colormap and img_np.ndim == 2:
            img_np = self._apply_voc_colormap(img_np)
        return self._create_and_add_item(img_np, 1.0, pos, z_value, opacity)

    def clear_all(self):
        # 清理缓存
        for layer in self._layers.values():
            layer.cache.clear()
        self._scene.clear()
        self._layers.clear()
        self._current_lod_level = 0

    def set_interactive_mode(self, mode: str):
        if mode == 'pan':
            self._interactive_mode = InteractiveMode.PAN
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        elif mode == 'draw':
            self._interactive_mode = InteractiveMode.DRAW
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self._interactive_mode = InteractiveMode.NORMAL
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def fit_to_view(self):
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def zoom_in(self, *args):
        self.scale(1.2, 1.2)
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def zoom_out(self, *args):
        self.scale(1 / 1.2, 1 / 1.2)
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def fit_to_window(self, *args):
        self.fit_to_view()

    def get_current_lod_level(self) -> int:
        return self._current_lod_level

    # ========== Compatibility ==========
    
    def load_sample(self, image_path: str, label_path: Optional[str] = None) -> bool:
        self.clear_all()
        base_item = self.load_image_layer(image_path, z_value=0)
        if not base_item:
            return False
        if label_path:
            self.load_image_layer(label_path, z_value=1, opacity=0.7, apply_colormap=True)
        self.fit_to_view()
        return True
        
    def load_label(self, label_path: str) -> bool:
        return self.load_image_layer(label_path, z_value=1, opacity=0.7, apply_colormap=True) is not None

    def load_data(self, image_np: np.ndarray, gt_mask_np=None, pred_mask_np=None):
        self.clear_all()
        self.load_layer_from_numpy(image_np, z_value=0)
        if gt_mask_np is not None:
            self.load_layer_from_numpy(gt_mask_np, z_value=1, opacity=0.7, apply_colormap=True)
        if pred_mask_np is not None:
            self.load_layer_from_numpy(pred_mask_np, z_value=2, opacity=0.7, apply_colormap=True)
        self.fit_to_view()

    # ========== LOD ==========
    
    def _calculate_initial_level(self, layer_info: ImageLayerInfo) -> int:
        max_dim = max(layer_info.width, layer_info.height)
        if max_dim > 16000:
            return 16
        elif max_dim > 8000:
            return 8
        elif max_dim > 4000:
            return 4
        elif max_dim > 2000:
            return 2
        return 1
    
    def _get_view_scale(self) -> float:
        return self.transform().m11()
    
    def _schedule_lod_update(self, delay: int):
        self._current_delay = delay
        self._lod_update_timer.start(delay)
    
    def _update_lod(self):
        if not self._layers or self._is_panning:
            return
        
        view_scale = self._get_view_scale()
        required_level = DynamicImageReader.get_required_level(view_scale)
        
        if required_level == self._current_lod_level:
            return
        
        self._current_lod_level = required_level
        
        for z_value, layer_info in self._layers.items():
            # 检查缓存
            cached = layer_info.cache.get(required_level)
            if cached:
                pixmap, scale, offset = cached
                self._apply_pixmap(layer_info, pixmap, scale, offset, required_level)
            else:
                # 后台加载
                if layer_info.loading_level != required_level:
                    layer_info.loading_level = required_level
                    self._loader_thread.add_task(
                        z_value, layer_info.path, required_level, layer_info.apply_colormap
                    )
        
        self.lod_changed.emit(required_level)
    
    def _on_layer_loaded(self, z_value: int, level: int, pixmap: QPixmap, scale: float, offset: tuple):
        """后台加载完成回调"""
        if z_value not in self._layers:
            return
        
        layer_info = self._layers[z_value]
        
        # 存入缓存
        layer_info.cache.put(level, pixmap, scale, offset)
        layer_info.loading_level = 0
        
        # 如果仍是当前需要的级别，应用
        if level == self._current_lod_level or layer_info.current_level == 0:
            self._apply_pixmap(layer_info, pixmap, scale, offset, level)
    
    def _apply_pixmap(self, layer_info: ImageLayerInfo, pixmap: QPixmap, scale: float, offset: tuple, level: int):
        """应用 Pixmap 到图层"""
        if layer_info.item is None:
            layer_info.item = QGraphicsPixmapItem(pixmap)
            layer_info.item.setZValue(layer_info.z_value)
            layer_info.item.setOpacity(layer_info.opacity)
            self._scene.addItem(layer_info.item)
        else:
            layer_info.item.setPixmap(pixmap)
        
        layer_info.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        layer_info.item.setScale(1.0 / scale if scale > 0 and scale < 1.0 else 1.0)
        layer_info.item.setPos(offset[0], offset[1])
        layer_info.current_level = level
    
    def _load_layer_sync(self, layer_info: ImageLayerInfo, level: int):
        """同步加载 (初始加载用)"""
        data, scale, offset = DynamicImageReader.read_at_level(layer_info.path, level)
        if data is None:
            return
        
        if layer_info.apply_colormap and data.ndim == 2:
            data = self._apply_voc_colormap(data)
        
        pixmap = self._numpy_to_pixmap(data)
        layer_info.cache.put(level, pixmap, scale, offset)
        self._apply_pixmap(layer_info, pixmap, scale, offset, level)

    def _update_scene_rect(self):
        if not self._layers:
            return
        max_w = max(l.width for l in self._layers.values())
        max_h = max(l.height for l in self._layers.values())
        if max_w > 0 and max_h > 0:
            self._scene.setSceneRect(0, 0, max_w, max_h)

    # ========== Utils ==========
    
    def _create_and_add_item(self, img_np, scale, pos, z_value, opacity):
        pixmap = self._numpy_to_pixmap(img_np)
        item = QGraphicsPixmapItem(pixmap)
        item.setZValue(z_value)
        item.setOpacity(opacity)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        if scale > 0 and scale < 1.0:
            item.setScale(1.0 / scale)
        item.setPos(pos[0], pos[1])
        self._scene.addItem(item)
        self._scene.setSceneRect(self._scene.itemsBoundingRect())
        return item

    def _apply_voc_colormap(self, label_np: np.ndarray) -> np.ndarray:
        h, w = label_np.shape
        bgra = np.zeros((h, w, 4), dtype=np.uint8)
        for i, color in enumerate(VOC_PALETTE_BGR):
            if i >= len(VOC_PALETTE_BGR):
                break
            mask = label_np == i
            if np.any(mask):
                bgra[mask, :3] = color
                bgra[mask, 3] = 0 if i == 0 else 255
        return bgra

    def _numpy_to_pixmap(self, img_np: np.ndarray) -> QPixmap:
        h, w = img_np.shape[:2]
        if img_np.ndim == 2:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2RGB)
        elif img_np.shape[2] == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
        elif img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGRA2RGBA)
        
        if not img_np.flags['C_CONTIGUOUS']:
            img_np = np.ascontiguousarray(img_np)
        
        if img_np.shape[2] == 4:
            fmt, bpl = QImage.Format.Format_RGBA8888, w * 4
        else:
            fmt, bpl = QImage.Format.Format_RGB888, w * 3
        
        qimg = QImage(img_np.data, w, h, bpl, fmt)
        return QPixmap.fromImage(qimg.copy())

    # ========== Events ==========
    
    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        sp = self.mapToScene(event.pos())
        self.mouse_position_changed.emit(int(sp.x()), int(sp.y()))
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._schedule_lod_update(self.LOD_UPDATE_DELAY_PAN)
        super().mouseReleaseEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)
    
    def _update_background_from_palette(self):
        palette = QApplication.palette()
        self.setBackgroundBrush(palette.color(QPalette.ColorRole.Window))
    
    def closeEvent(self, event):
        self._loader_thread.stop()
        super().closeEvent(event)
