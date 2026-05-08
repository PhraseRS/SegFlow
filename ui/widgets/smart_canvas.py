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

    def load(
        self,
        z_value: int,
        path: str,
        level: int,
        apply_colormap: bool,
        palette: Optional[Any] = None,
    ):
        """执行加载"""
        if self._cancelled:
            return

        try:
            # 对于标签图像 (apply_colormap=True)，使用 nearest 重采样以保留类别索引
            data, scale, offset = DynamicImageReader.read_at_level(path, level, is_label=apply_colormap)

            if self._cancelled or data is None:
                return

            # 应用伪彩色
            if apply_colormap:
                # 如果是 3D 数组，取第一个通道
                if data.ndim == 3:
                    data = data[:, :, 0]
                data = self._apply_voc_colormap(data, palette)

            # 转换为 QPixmap
            pixmap = self._numpy_to_pixmap(data)

            if not self._cancelled:
                self.finished.emit(z_value, level, pixmap, scale, offset)

        except Exception as e:
            print(f"⚠️ 后台加载失败: {e}")

    def _apply_voc_colormap(self, label_np: np.ndarray, palette: Optional[Any] = None) -> np.ndarray:
        return apply_label_colormap(label_np, palette)

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

    def add_task(
        self,
        z_value: int,
        path: str,
        level: int,
        apply_colormap: bool,
        palette: Optional[Any] = None,
    ):
        with QMutexLocker(self._mutex):
            self._tasks = [(z, p, l, c, pal) for z, p, l, c, pal in self._tasks if z != z_value]
            self._tasks.append((z_value, path, level, apply_colormap, palette))

    def run(self):
        while self._running:
            task = None
            with QMutexLocker(self._mutex):
                if self._tasks:
                    task = self._tasks.pop(0)

            if task:
                z_value, path, level, apply_colormap, palette = task
                # 执行任务前再次检查停止标志
                if not self._running:
                    break
                self._worker.load(z_value, path, level, apply_colormap, palette)
            else:
                # 减少等待时间以便更快响应停止请求
                self.msleep(20)

    def stop(self):
        """停止线程"""
        self._running = False
        self._worker.cancel()
        # 清空待处理任务
        with QMutexLocker(self._mutex):
            self._tasks.clear()
        # 等待线程结束 (最多2秒)
        if not self.wait(2000):
            print("⚠️ ImageLoaderThread: 强制终止")
            self.terminate()
            self.wait(1000)


class MetadataLoaderWorker(QObject):
    """后台元数据加载工作器 - 用于异步读取大图像的元数据"""
    finished = Signal(str, int, int, int, list, bool)  # path, width, height, count, overviews, has_pyramid
    error = Signal(str, str)  # path, error_message

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def load(self, path: str):
        """执行元数据加载"""
        if self._cancelled:
            return

        try:
            if not os.path.exists(path):
                self.error.emit(path, f"文件不存在: {path}")
                return

            width, height, count, overviews = 0, 0, 1, []
            has_pyramid = False

            if HAS_RASTERIO:
                try:
                    with rasterio.open(path) as src:
                        width = src.width
                        height = src.height
                        count = src.count
                        overviews = src.overviews(1) if src.count >= 1 else []
                        has_pyramid = len(overviews) > 0
                except Exception as e:
                    # 回退到 OpenCV
                    width, height, count = self._load_metadata_opencv(path)
            else:
                width, height, count = self._load_metadata_opencv(path)

            if not self._cancelled:
                self.finished.emit(path, width, height, count, overviews, has_pyramid)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(path, str(e))

    def _load_metadata_opencv(self, path: str):
        """使用 OpenCV 读取元数据 (回退方案)"""
        try:
            # 只读取头部信息，不完全解码
            with open(path, 'rb') as f:
                # 只读取前 64KB 用于解析头部
                data = np.frombuffer(f.read(65536), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if img is not None:
                h, w = img.shape[:2]
                c = 1 if img.ndim == 2 else img.shape[2]
                return w, h, c
        except:
            pass
        return 0, 0, 1


class MetadataLoaderThread(QThread):
    """后台元数据加载线程"""
    finished = Signal(str, int, int, int, list, bool)
    error = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = MetadataLoaderWorker()
        self._worker.finished.connect(self.finished)
        self._worker.error.connect(self.error)
        self._tasks = []
        self._mutex = QMutex()
        self._running = True

    def add_task(self, path: str):
        with QMutexLocker(self._mutex):
            # 避免重复任务
            if path not in self._tasks:
                self._tasks.append(path)

    def run(self):
        while self._running:
            task = None
            with QMutexLocker(self._mutex):
                if self._tasks:
                    task = self._tasks.pop(0)

            if task:
                self._worker.load(task)
            else:
                self.msleep(50)

    def stop(self):
        """停止线程"""
        self._running = False
        self._worker.cancel()
        with QMutexLocker(self._mutex):
            self._tasks.clear()
        if not self.wait(2000):
            print("⚠️ MetadataLoaderThread: 强制终止")
            self.terminate()
            self.wait(1000)


class ImageLayerInfo:
    """图层元数据信息"""
    def __init__(
        self,
        path: str,
        z_value: int = 0,
        opacity: float = 1.0,
        apply_colormap: bool = False,
        async_load: bool = False,
        palette: Optional[Any] = None,
    ):
        self.path = path
        self.z_value = z_value
        self.opacity = opacity
        self.apply_colormap = apply_colormap
        self.palette = palette

        self.width = 0
        self.height = 0
        self.count = 1
        self.has_pyramid = False
        self.overviews = []

        self.item: Optional[QGraphicsPixmapItem] = None
        self.current_level = 0
        self.cache = LODCache(max_size=4)
        self.loading_level = 0  # 正在加载的级别

        # 异步加载状态
        self.metadata_loaded = False
        self.loading_metadata = False

        # 根据参数决定是否同步加载
        if not async_load:
            self._load_metadata()
            self.metadata_loaded = True

    def set_metadata(self, width: int, height: int, count: int, overviews: list, has_pyramid: bool):
        """设置元数据 (由异步加载器调用)"""
        self.width = width
        self.height = height
        self.count = count
        self.overviews = overviews
        self.has_pyramid = has_pyramid
        self.metadata_loaded = True
        self.loading_metadata = False

    def _load_metadata(self):
        if not os.path.exists(self.path):
            return

        is_tiff = os.path.splitext(self.path)[1].lower() in {'.tif', '.tiff'}

        if HAS_RASTERIO:
            try:
                with rasterio.open(self.path) as src:
                    self.width = src.width
                    self.height = src.height
                    self.count = src.count
                    self.overviews = src.overviews(1) if src.count >= 1 else []
                    self.has_pyramid = len(self.overviews) > 0
                return
            except Exception as e:
                print(f"⚠️ rasterio 元数据读取失败: {self.path} | {e}")
                if is_tiff:
                    return

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

    TIFF_EXTS = {'.tif', '.tiff'}

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
        viewport_rect: Optional[QRectF] = None,
        is_label: bool = False
    ) -> Tuple[Optional[np.ndarray], float, Tuple[int, int]]:
        if not os.path.exists(path):
            return None, 1.0, (0, 0)

        is_tiff = DynamicImageReader._is_tiff(path)
        if not HAS_RASTERIO:
            if is_tiff:
                print(f"⚠️ TIFF 读取失败：当前环境缺少 rasterio 支持 | {path}")
                return None, 1.0, (0, 0)
            return DynamicImageReader._read_with_opencv(path, level, is_label)

        try:
            with rasterio.open(path) as src:
                actual_level = DynamicImageReader._get_best_level(src, level)
                if viewport_rect:
                    return DynamicImageReader._read_viewport(src, actual_level, viewport_rect, is_label)

                out_h = max(1, src.height // actual_level)
                out_w = max(1, src.width // actual_level)
                data = DynamicImageReader._read_full(src, out_h, out_w, is_label)
                return data, 1.0 / actual_level, (0, 0)
        except Exception as e:
            print(f"⚠️ rasterio 图像读取失败: {path} | {e}")
            if is_tiff:
                return None, 1.0, (0, 0)
            return DynamicImageReader._read_with_opencv(path, level, is_label)

    @staticmethod
    def read_center_preview(path: str, tile_size: int = 512, is_label: bool = False) -> Optional[np.ndarray]:
        if not os.path.exists(path) or not HAS_RASTERIO:
            return None

        try:
            with rasterio.open(path) as src:
                preview_size = min(tile_size, src.width, src.height)
                x_offset = max((src.width - preview_size) // 2, 0)
                y_offset = max((src.height - preview_size) // 2, 0)
                viewport = QRectF(x_offset, y_offset, preview_size, preview_size)
                data, _scale, _offset = DynamicImageReader._read_viewport(src, 1, viewport, is_label)
                return data
        except Exception as e:
            print(f"⚠️ 中心预览读取失败: {path} | {e}")
            return None


    @staticmethod
    def _is_tiff(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in DynamicImageReader.TIFF_EXTS

    @staticmethod
    def _read_raster_display_data(src, out_h: int, out_w: int, resample, window=None) -> np.ndarray:
        if src.count <= 0:
            raise ValueError("影像不包含可读取波段")

        read_kwargs = {'out_shape': (out_h, out_w), 'resampling': resample}
        if window is not None:
            read_kwargs['window'] = window

        if src.count == 1:
            band = src.read(1, **read_kwargs)
            try:
                colormap = src.colormap(1)
            except Exception:
                colormap = None
            if colormap:
                color = np.zeros((out_h, out_w, 3), dtype=np.uint8)
                for value, rgb in colormap.items():
                    color[band == value] = rgb[:3]
                return color
            return band

        if src.count >= 3:
            red = src.read(1, **read_kwargs)
            green = src.read(2, **read_kwargs)
            blue = src.read(3, **read_kwargs)
            return cv2.merge([blue, green, red])

        print(f"⚠️ 非标准波段组合，退化为单波段显示: count={src.count}")
        return src.read(1, **read_kwargs)

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
    def _read_viewport(
        src, level: int, viewport_rect: QRectF, is_label: bool = False
    ) -> Tuple[Optional[np.ndarray], float, Tuple[int, int]]:
        """读取视口区域（切片渲染）"""
        try:
            # 计算视口在原始图像中的位置
            x = max(0, int(viewport_rect.x()))
            y = max(0, int(viewport_rect.y()))
            w = min(src.width - x, int(viewport_rect.width()))
            h = min(src.height - y, int(viewport_rect.height()))

            if w <= 0 or h <= 0:
                return None, 1.0, (0, 0)

            # 根据 level 计算输出尺寸
            out_w = max(1, w // level)
            out_h = max(1, h // level)

            # 选择重采样方法
            resample = Resampling.nearest if is_label else Resampling.bilinear

            # 使用 rasterio 的 window 读取
            from rasterio.windows import Window
            window = Window(x, y, w, h)

            data = DynamicImageReader._read_raster_display_data(src, out_h, out_w, resample, window=window)
            return data, 1.0 / level, (x, y)

        except Exception as e:
            print(f"视口读取失败: {e}")
            return None, 1.0, (0, 0)

    @staticmethod
    def _read_full(src, out_h: int, out_w: int, is_label: bool = False) -> np.ndarray:
        # 对于标签图像，必须使用 nearest 重采样以保留类别索引
        if is_label:
            resample = Resampling.nearest
        else:
            # 对于普通图像，大尺寸用 nearest（性能），小尺寸用 bilinear（质量）
            resample = Resampling.nearest if out_h * out_w > 2000 * 2000 else Resampling.bilinear

        return DynamicImageReader._read_raster_display_data(src, out_h, out_w, resample)

    @staticmethod
    def _read_with_opencv(path: str, level: int, is_label: bool = False) -> Tuple[Optional[np.ndarray], float, Tuple[int, int]]:
        try:
            with open(path, 'rb') as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if img is None:
                return None, 1.0, (0, 0)
            if level > 1:
                h, w = img.shape[:2]
                new_h, new_w = max(1, h // level), max(1, w // level)
                # 标签图像必须用 INTER_NEAREST 保留类别索引
                interp = cv2.INTER_NEAREST if is_label else cv2.INTER_AREA
                img = cv2.resize(img, (new_w, new_h), interpolation=interp)
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


def normalize_palette(palette: Optional[Any]) -> Optional[List[Tuple[int, int, int]]]:
    if palette is None:
        return None

    if isinstance(palette, dict):
        try:
            keys = sorted(palette.keys(), key=int)
        except Exception:
            keys = list(palette.keys())
        values = [palette[key] for key in keys]
    else:
        values = list(palette)

    normalized: List[Tuple[int, int, int]] = []
    for color in values:
        if not isinstance(color, (list, tuple)) or len(color) < 3:
            normalized.append((128, 128, 128))
            continue
        r = int(max(0, min(255, color[0])))
        g = int(max(0, min(255, color[1])))
        b = int(max(0, min(255, color[2])))
        normalized.append((b, g, r))
    return normalized


def apply_label_colormap(label_np: np.ndarray, palette: Optional[Any] = None) -> np.ndarray:
    custom_palette = normalize_palette(palette) or []
    max_label = int(label_np.max()) if label_np.size else 0
    palette_bgr: List[Tuple[int, int, int]] = []
    for class_id in range(max(max_label + 1, len(custom_palette), len(VOC_PALETTE_BGR))):
        if class_id < len(custom_palette):
            palette_bgr.append(custom_palette[class_id])
        elif class_id < len(VOC_PALETTE_BGR):
            palette_bgr.append(VOC_PALETTE_BGR[class_id])
        else:
            palette_bgr.append((128, 128, 128))
    h, w = label_np.shape
    bgra = np.zeros((h, w, 4), dtype=np.uint8)
    for class_id, color in enumerate(palette_bgr):
        mask = label_np == class_id
        if np.any(mask):
            bgra[mask, :3] = color
            bgra[mask, 3] = 0 if class_id == 0 else 255
    return bgra


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

        # 保存上一次的视图变换 (用于 Zoom to Last)
        self._last_transform: Optional[QTransform] = None
        self._last_center: Optional[QPointF] = None

        # 是否处于"视口原始分辨率"模式 (只加载了视口区域)
        self._is_native_viewport_mode = False

        # Swipe compare state. The base image stays unchanged; label/prediction
        # layers are clipped to the left side of this divider.
        self._swipe_enabled = False
        self._swipe_position = 50
        self._swipe_line_item: Optional[QGraphicsLineItem] = None
        self._swipe_line_shadow_item: Optional[QGraphicsLineItem] = None

        # 右键菜单
        self._setup_context_menu()

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

        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _setup_context_menu(self):
        """创建右键菜单"""
        self._context_menu = QMenu(self)

        # Zoom Full - 适应窗口
        self._action_zoom_full = QAction("🔲 适应窗口 (Zoom Full)", self)
        self._action_zoom_full.triggered.connect(self._on_zoom_full)
        self._context_menu.addAction(self._action_zoom_full)

        # Zoom to Native Resolution - 原始分辨率 (1:1)
        self._action_zoom_native = QAction("🔍 原始分辨率 (1:1)", self)
        self._action_zoom_native.triggered.connect(self._on_zoom_native)
        self._context_menu.addAction(self._action_zoom_native)

        self._context_menu.addSeparator()

        # Zoom to Last - 恢复上次缩放
        self._action_zoom_last = QAction("↩️ 恢复上次视图 (Zoom to Last)", self)
        self._action_zoom_last.triggered.connect(self._on_zoom_last)
        self._action_zoom_last.setEnabled(False)  # 初始禁用
        self._context_menu.addAction(self._action_zoom_last)

        # 连接菜单显示信号
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        # 更新菜单项状态
        self._action_zoom_last.setEnabled(self._last_transform is not None)

        # 在鼠标位置显示菜单
        self._context_menu.exec(self.mapToGlobal(pos))

    def _save_current_view(self):
        """保存当前视图状态"""
        self._last_transform = QTransform(self.transform())
        self._last_center = self.mapToScene(self.viewport().rect().center())

    def _on_zoom_full(self):
        """Zoom Full - 适应窗口显示完整图像"""
        self._save_current_view()
        self.fit_to_view()

    def _on_zoom_native(self):
        """Zoom to Native Resolution - 缩放到原始分辨率 (1:1)"""
        self._save_current_view()

        # 获取当前视图中心 (在场景坐标中)
        current_center = self.mapToScene(self.viewport().rect().center())

        # 重置变换到 1:1
        self.resetTransform()

        # 保持当前视图中心不变
        self.centerOn(current_center)

        # 停止防抖定时器
        self._lod_update_timer.stop()

        # 获取当前视口在场景中的矩形 (1:1 缩放后)
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()

        # 同步加载视口区域的原始分辨率
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._current_lod_level = 1
            self._is_native_viewport_mode = True  # 标记进入视口原始分辨率模式
            for z_value, layer_info in self._layers.items():
                print(f"🔍 加载视口区域原始分辨率: z={z_value}")
                self._load_viewport_at_native(layer_info, viewport_rect)
            self.lod_changed.emit(1)
        finally:
            QApplication.restoreOverrideCursor()

    def _load_viewport_at_native(self, layer_info: ImageLayerInfo, viewport_rect: QRectF):
        """仅加载视口区域的原始分辨率"""
        if not HAS_RASTERIO:
            return

        path = layer_info.path

        # 计算视口对应的像素区域 (加边距)
        margin = 512  # 边距像素
        x1 = max(0, int(viewport_rect.left()) - margin)
        y1 = max(0, int(viewport_rect.top()) - margin)
        x2 = min(layer_info.width, int(viewport_rect.right()) + margin)
        y2 = min(layer_info.height, int(viewport_rect.bottom()) + margin)

        win_w = x2 - x1
        win_h = y2 - y1

        if win_w <= 0 or win_h <= 0:
            return

        print(f"   视口区域: ({x1}, {y1}) - ({x2}, {y2}), 尺寸: {win_w} x {win_h}")

        try:
            with rasterio.open(path) as src:
                window = Window(x1, y1, win_w, win_h)

                if src.count == 1:
                    data = src.read(1, window=window)
                elif src.count >= 3:
                    r = src.read(1, window=window)
                    g = src.read(2, window=window)
                    b = src.read(3, window=window)
                    data = cv2.merge([b, g, r])
                else:
                    data = src.read(1, window=window)

                print(f"   已读取: shape={data.shape}, colormap={layer_info.apply_colormap}")

                # 应用伪彩色 (用于 prediction/GT)
                if layer_info.apply_colormap:
                    if data.ndim == 3:
                        data = data[:, :, 0]
                    data = self._apply_voc_colormap(data, layer_info.palette)

                pixmap = self._numpy_to_pixmap(data)
                layer_info.source_pixmap = pixmap

                # 创建或更新 item，设置正确的位置偏移
                if layer_info.item is None:
                    layer_info.item = QGraphicsPixmapItem(pixmap)
                    layer_info.item.setZValue(layer_info.z_value)
                    layer_info.item.setOpacity(layer_info.opacity)
                    self._scene.addItem(layer_info.item)
                else:
                    layer_info.item.setPixmap(pixmap)

                layer_info.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                layer_info.item.setScale(1.0)  # 1:1 显示
                layer_info.item.setPos(x1, y1)  # 设置位置偏移
                layer_info.current_level = 1
                if self._is_swipe_layer(layer_info.z_value):
                    self._apply_swipe_clip_to_layer(layer_info)

                print(f"   ✅ 视口区域已加载")

        except Exception as e:
            print(f"   ⚠️ 加载失败: {e}")

    def _on_zoom_last(self):
        """Zoom to Last - 恢复上一次的缩放状态"""
        if self._last_transform is None:
            return

        # 交换当前和上次的变换
        current_transform = QTransform(self.transform())
        current_center = self.mapToScene(self.viewport().rect().center())

        # 恢复上次变换
        self.setTransform(self._last_transform)
        if self._last_center:
            self.centerOn(self._last_center)

        # 保存当前作为新的"上次"
        self._last_transform = current_transform
        self._last_center = current_center

        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def load_image_layer(
        self,
        path: str,
        pos: Tuple[int, int] = (0, 0),
        z_value: int = 0,
        opacity: float = 1.0,
        apply_colormap: bool = False,
        palette: Optional[Any] = None,
    ) -> Optional[QGraphicsPixmapItem]:
        if not os.path.exists(path):
            return None

        print(f"      🔄 SmartCanvas.load_image_layer: 创建 ImageLayerInfo...")
        QApplication.processEvents()

        layer_info = ImageLayerInfo(path, z_value, opacity, apply_colormap, palette=palette)

        QApplication.processEvents()

        if layer_info.width == 0:
            print(f"      ⚠️ 元数据加载失败，width=0")
            return None

        print(f"      ✅ 元数据加载完成: {layer_info.width}x{layer_info.height}")

        if z_value in self._layers:
            old = self._layers[z_value]
            if old.item:
                self._scene.removeItem(old.item)
            old.cache.clear()

        self._layers[z_value] = layer_info

        # 快速初始加载 (低分辨率)
        initial_level = self._calculate_initial_level(layer_info)
        print(f"      🔄 开始初始加载 level={initial_level}...")

        QApplication.processEvents()

        self._load_layer_sync(layer_info, initial_level)

        QApplication.processEvents()

        # 如果当前已有其他图层，同步到相同的LOD级别
        if self._current_lod_level > 0 and self._current_lod_level != initial_level:
            print(f"      🔄 同步到当前LOD级别: {self._current_lod_level}...")
            self._load_layer_sync(layer_info, self._current_lod_level)
            QApplication.processEvents()

        self._update_scene_rect()
        if self._swipe_enabled:
            self._apply_swipe_to_layers()

        print(f"      ✅ SmartCanvas.load_image_layer: 完成")

        # 调试：打印所有图层状态
        self.debug_layers()

        return layer_info.item

    def debug_layers(self):
        """调试方法：打印所有图层状态"""
        print(f"\n      ═══════════════════════════════════════════")
        print(f"      📋 所有图层状态汇总 (共 {len(self._layers)} 个图层)")
        print(f"      ═══════════════════════════════════════════")

        for z_value, layer_info in sorted(self._layers.items()):
            item = layer_info.item
            if item:
                print(f"      📦 z={z_value}: {os.path.basename(layer_info.path)}")
                print(f"         - 原始尺寸: {layer_info.width}x{layer_info.height}")
                print(f"         - current_level: {layer_info.current_level}")
                print(f"         - apply_colormap: {layer_info.apply_colormap}")
                print(f"         - item.zValue(): {item.zValue()}")
                print(f"         - item.opacity(): {item.opacity()}")
                print(f"         - item.isVisible(): {item.isVisible()}")
                print(f"         - item.scale(): {item.scale()}")
                print(f"         - item.pos(): ({item.pos().x()}, {item.pos().y()})")
                print(f"         - item.boundingRect(): {item.boundingRect().width():.0f}x{item.boundingRect().height():.0f}")
                print(f"         - in_scene: {item.scene() is not None}")
            else:
                print(f"      📦 z={z_value}: {os.path.basename(layer_info.path)} - ⚠️ item=None")

        print(f"      ═══════════════════════════════════════════\n")

    def load_layer_from_numpy(
        self,
        img_np: np.ndarray,
        pos: Tuple[int, int] = (0, 0),
        z_value: int = 0,
        opacity: float = 1.0,
        apply_colormap: bool = False,
        palette: Optional[Any] = None,
    ) -> Optional[QGraphicsPixmapItem]:
        if apply_colormap and img_np.ndim == 2:
            img_np = self._apply_voc_colormap(img_np, palette)
        return self._create_and_add_item(img_np, 1.0, pos, z_value, opacity)

    def clear_all(self):
        # 清理缓存
        for layer in self._layers.values():
            layer.cache.clear()
        self._scene.clear()
        self._layers.clear()
        self._current_lod_level = 0
        self._swipe_line_item = None
        self._swipe_line_shadow_item = None

    def clear(self):
        """Compatibility wrapper used by the dataset panel."""
        self.clear_all()

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
        self._save_current_view()
        self.scale(1.2, 1.2)
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def zoom_out(self, *args):
        self._save_current_view()
        self.scale(1 / 1.2, 1 / 1.2)
        self._schedule_lod_update(self.LOD_UPDATE_DELAY_ZOOM)

    def fit_to_window(self, *args):
        self.fit_to_view()

    def get_current_lod_level(self) -> int:
        return self._current_lod_level

    def set_image_visible(self, visible: bool):
        """设置底图（z_value=0）的可见性"""
        if 0 in self._layers and self._layers[0].item:
            self._layers[0].item.setVisible(visible)

    def set_label_visible(self, visible: bool):
        """设置标签层（z_value=1）的可见性"""
        if 1 in self._layers and self._layers[1].item:
            self._layers[1].item.setVisible(visible)

    def set_label_opacity(self, opacity: int):
        """设置标签层的透明度 (0-100)"""
        if 1 in self._layers and self._layers[1].item:
            self._layers[1].item.setOpacity(opacity / 100.0)
            self._layers[1].opacity = opacity / 100.0

    def set_layer_palette(self, z_value: int, palette: Optional[Any]) -> bool:
        layer_info = self._layers.get(z_value)
        if layer_info is None or not layer_info.apply_colormap:
            return False

        layer_info.palette = palette
        layer_info.cache.clear()
        layer_info.loading_level = 0
        layer_info.source_pixmap = None

        if self._is_native_viewport_mode and HAS_RASTERIO:
            viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            self._load_viewport_at_native(layer_info, viewport_rect)
        else:
            target_level = layer_info.current_level or self._current_lod_level or self._calculate_initial_level(layer_info)
            self._load_layer_sync(layer_info, target_level)

        self.viewport().update()
        return True

    def set_swipe_enabled(self, enabled: bool):
        """Enable/disable swipe comparison for label/prediction layers."""
        self._swipe_enabled = bool(enabled)
        self._apply_swipe_to_layers()

    def set_swipe_position(self, position: int):
        """Set swipe divider position as a percentage of the scene width."""
        self._swipe_position = max(0, min(100, int(position)))
        if self._swipe_enabled:
            self._apply_swipe_to_layers()

    def _is_swipe_layer(self, z_value: int) -> bool:
        """Only overlay layers are clipped; z=0 is the base image."""
        return z_value > 0

    def _get_swipe_scene_x(self) -> float:
        rect = self._scene.sceneRect()
        if not rect.isValid() or rect.width() <= 0:
            return 0.0
        return rect.left() + rect.width() * (self._swipe_position / 100.0)

    def _apply_swipe_to_layers(self):
        for z_value, layer_info in self._layers.items():
            if self._is_swipe_layer(z_value):
                self._apply_swipe_clip_to_layer(layer_info)
        self._update_swipe_line()
        self.viewport().update()

    def _apply_swipe_clip_to_layer(self, layer_info: ImageLayerInfo):
        if layer_info.item is None:
            return

        source_pixmap = getattr(layer_info, "source_pixmap", None)
        if source_pixmap is None or source_pixmap.isNull():
            source_pixmap = layer_info.item.pixmap()
            layer_info.source_pixmap = source_pixmap

        if not self._swipe_enabled:
            layer_info.item.setPixmap(source_pixmap)
            return

        item_scale = layer_info.item.scale()
        if item_scale == 0:
            item_scale = 1.0

        scene_x = self._get_swipe_scene_x()
        local_x = int(round((scene_x - layer_info.item.pos().x()) / item_scale))
        clip_width = max(0, min(source_pixmap.width(), local_x))

        clipped = QPixmap(source_pixmap.size())
        clipped.fill(Qt.GlobalColor.transparent)

        if clip_width > 0:
            painter = QPainter(clipped)
            painter.setClipRect(0, 0, clip_width, source_pixmap.height())
            painter.drawPixmap(0, 0, source_pixmap)
            painter.end()

        layer_info.item.setPixmap(clipped)

    def _ensure_swipe_line_items(self):
        if self._swipe_line_shadow_item is None:
            self._swipe_line_shadow_item = QGraphicsLineItem()
            shadow_pen = QPen(QColor(0, 0, 0, 190), 3)
            shadow_pen.setCosmetic(True)
            self._swipe_line_shadow_item.setPen(shadow_pen)
            self._swipe_line_shadow_item.setZValue(999998)
            self._scene.addItem(self._swipe_line_shadow_item)

        if self._swipe_line_item is None:
            self._swipe_line_item = QGraphicsLineItem()
            line_pen = QPen(QColor(255, 255, 255, 235), 1)
            line_pen.setCosmetic(True)
            self._swipe_line_item.setPen(line_pen)
            self._swipe_line_item.setZValue(999999)
            self._scene.addItem(self._swipe_line_item)

    def _update_swipe_line(self):
        if not self._swipe_enabled or not self._layers:
            if self._swipe_line_item:
                self._swipe_line_item.setVisible(False)
            if self._swipe_line_shadow_item:
                self._swipe_line_shadow_item.setVisible(False)
            return

        rect = self._scene.sceneRect()
        if not rect.isValid() or rect.height() <= 0:
            return

        self._ensure_swipe_line_items()
        x = self._get_swipe_scene_x()
        for item in (self._swipe_line_shadow_item, self._swipe_line_item):
            item.setLine(x, rect.top(), x, rect.bottom())
            item.setVisible(True)

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
                        z_value, layer_info.path, required_level, layer_info.apply_colormap, layer_info.palette
                    )

        self.lod_changed.emit(required_level)

    def _force_lod_level(self, level: int):
        """强制加载指定的LOD级别 (用于1:1缩放等场景)"""
        if not self._layers:
            return

        # 停止防抖定时器，避免被自动更新覆盖
        self._lod_update_timer.stop()

        print(f"🔄 强制 LOD 级别: {level}")
        self._current_lod_level = level

        for z_value, layer_info in self._layers.items():
            # 检查缓存
            cached = layer_info.cache.get(level)
            if cached:
                pixmap, scale, offset = cached
                self._apply_pixmap(layer_info, pixmap, scale, offset, level)
            else:
                # 后台加载
                if layer_info.loading_level != level:
                    layer_info.loading_level = level
                    self._loader_thread.add_task(
                        z_value, layer_info.path, level, layer_info.apply_colormap, layer_info.palette
                    )

        self.lod_changed.emit(level)

    def _on_layer_loaded(self, z_value: int, level: int, pixmap: QPixmap, scale: float, offset: tuple):
        """后台加载完成回调"""
        if z_value not in self._layers:
            return

        layer_info = self._layers[z_value]

        # 存入缓存
        layer_info.cache.put(level, pixmap, scale, offset)
        layer_info.loading_level = 0

        # 应用条件：
        # 1. 加载的级别等于当前需要的级别
        # 2. 或者加载的是更高分辨率（更小的level值）
        # 3. 或者当前还没有加载过
        should_apply = (
            level == self._current_lod_level or
            level < layer_info.current_level or
            layer_info.current_level == 0
        )

        if should_apply:
            self._apply_pixmap(layer_info, pixmap, scale, offset, level)

    def _apply_pixmap(self, layer_info: ImageLayerInfo, pixmap: QPixmap, scale: float, offset: tuple, level: int):
        """应用 Pixmap 到图层"""
        is_new_item = layer_info.item is None
        layer_info.source_pixmap = pixmap

        if layer_info.item is None:
            layer_info.item = QGraphicsPixmapItem(pixmap)
            layer_info.item.setZValue(layer_info.z_value)
            layer_info.item.setOpacity(layer_info.opacity)
            self._scene.addItem(layer_info.item)
            print(f"      📍 新建 GraphicsItem: z={layer_info.z_value}, opacity={layer_info.opacity}")
        else:
            layer_info.item.setPixmap(pixmap)

        layer_info.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        layer_info.item.setScale(1.0 / scale if scale > 0 and scale < 1.0 else 1.0)
        layer_info.item.setPos(offset[0], offset[1])
        layer_info.current_level = level
        if self._is_swipe_layer(layer_info.z_value):
            self._apply_swipe_clip_to_layer(layer_info)

        # 调试: 验证图层状态
        actual_z = layer_info.item.zValue()
        actual_opacity = layer_info.item.opacity()
        actual_visible = layer_info.item.isVisible()
        actual_scale = layer_info.item.scale()
        actual_pos = layer_info.item.pos()
        in_scene = layer_info.item.scene() is not None

        print(f"      📊 图层状态检查:")
        print(f"         - z-value: {actual_z} (expected: {layer_info.z_value})")
        print(f"         - opacity: {actual_opacity} (expected: {layer_info.opacity})")
        print(f"         - visible: {actual_visible}")
        print(f"         - scale: {actual_scale}")
        print(f"         - pos: ({actual_pos.x()}, {actual_pos.y()})")
        print(f"         - in_scene: {in_scene}")
        print(f"         - pixmap size: {pixmap.width()}x{pixmap.height()}")

    def _load_layer_sync(self, layer_info: ImageLayerInfo, level: int):
        """同步加载"""
        print(f"      🔄 _load_layer_sync: 开始读取 level={level}...")
        QApplication.processEvents()  # 让 UI 有机会更新

        # 对于标签图像 (apply_colormap=True)，使用 nearest 重采样以保留类别索引
        data, scale, offset = DynamicImageReader.read_at_level(
            layer_info.path, level, is_label=layer_info.apply_colormap
        )

        QApplication.processEvents()  # 读取完成后更新 UI

        if data is None:
            print(f"⚠️ 同步加载失败: level={level}")
            return

        print(f"✅ 已加载: level={level}, shape={data.shape}, scale={scale}, "
              f"原始尺寸=({layer_info.width}, {layer_info.height}), colormap={layer_info.apply_colormap}")

        QApplication.processEvents()

        # 应用伪彩色 (用于 prediction/GT 等灰度标签图)
        if layer_info.apply_colormap:
            # 如果是 3D 数组，取第一个通道
            if data.ndim == 3:
                data = data[:, :, 0] if data.shape[2] <= 3 else data[:, :, 0]

            # 调试：打印预测数据的值分布
            unique_values = np.unique(data)
            print(f"      📊 预测数据值分布:")
            print(f"         - dtype: {data.dtype}")
            print(f"         - 唯一值: {unique_values}")
            print(f"         - min: {data.min()}, max: {data.max()}")
            for v in unique_values[:5]:  # 只显示前5个值
                count = np.sum(data == v)
                pct = count / data.size * 100
                print(f"         - 值={v}: {count}个像素 ({pct:.2f}%)")

            # 应用 VOC 调色板
            data = self._apply_voc_colormap(data, layer_info.palette)

        QApplication.processEvents()

        pixmap = self._numpy_to_pixmap(data)
        print(f"   Pixmap: {pixmap.width()}x{pixmap.height()}")

        QApplication.processEvents()

        layer_info.cache.put(level, pixmap, scale, offset)
        self._apply_pixmap(layer_info, pixmap, scale, offset, level)
        print(f"      ✅ _load_layer_sync: 完成")

    def _restore_cached_overview(self):
        """从缓存恢复低分辨率整图 (退出视口原始分辨率模式时)"""
        view_scale = self._get_view_scale()
        target_level = DynamicImageReader.get_required_level(view_scale)

        print(f"🔄 恢复缓存概览图: target_level={target_level}")

        for z_value, layer_info in self._layers.items():
            # 尝试从缓存获取合适级别的图像
            # 按优先级尝试: target_level, 然后更低分辨率的级别
            levels_to_try = [target_level, target_level * 2, target_level * 4, 8, 16, 32]

            restored = False
            for level in levels_to_try:
                cached = layer_info.cache.get(level)
                if cached:
                    pixmap, scale, offset = cached
                    print(f"   ✅ 从缓存恢复 level={level}")
                    self._apply_pixmap(layer_info, pixmap, scale, offset, level)
                    restored = True
                    break

            if not restored:
                # 缓存中没有，同步加载一个低分辨率版本
                print(f"   ⚠️ 缓存未命中，同步加载 level={target_level}")
                self._load_layer_sync(layer_info, max(target_level, 8))

        self._current_lod_level = target_level

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

    def _apply_voc_colormap(self, label_np: np.ndarray, palette: Optional[Any] = None) -> np.ndarray:
        return apply_label_colormap(label_np, palette)

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
        # 保存当前状态 (仅在显著缩放时)
        if not hasattr(self, '_wheel_save_pending'):
            self._wheel_save_pending = False

        if not self._wheel_save_pending:
            self._save_current_view()
            self._wheel_save_pending = True
            # 500ms后重置标志
            QTimer.singleShot(500, lambda: setattr(self, '_wheel_save_pending', False))

        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

        # 如果从"视口原始分辨率"模式退出，立即恢复缓存的低分辨率图像
        if self._is_native_viewport_mode:
            self._is_native_viewport_mode = False
            self._restore_cached_overview()

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
        self._cleanup_thread()
        super().closeEvent(event)

    def __del__(self):
        """析构函数 - 确保线程被正确停止"""
        self._cleanup_thread()

    def _cleanup_thread(self):
        """清理后台线程"""
        try:
            if hasattr(self, '_loader_thread') and self._loader_thread is not None:
                if self._loader_thread.isRunning():
                    self._loader_thread.stop()
                self._loader_thread = None
        except RuntimeError:
            # Qt 对象可能已被删除
            pass
