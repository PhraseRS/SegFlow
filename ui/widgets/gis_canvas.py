"""
GISCanvasWidget - 支持 GeoTIFF 空间对齐的 GIS 画布组件
用于遥感影像的多图层叠加显示，支持基于地理坐标的空间对齐。
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
import numpy as np
import cv2

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QAction
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QToolButton, QMenu, QFileDialog, QMessageBox
)

try:
    import rasterio
    from rasterio.transform import Affine
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    Affine = None


@dataclass
class LayerInfo:
    """图层信息"""
    name: str
    path: str
    item: QGraphicsPixmapItem
    z_value: int
    opacity: float
    visible: bool
    profile: Dict[str, Any]


class GeoUtils:
    """GeoTIFF 工具类（静态方法）"""
    
    @staticmethod
    def read_image(path: str) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]]]:
        """
        读取 GeoTIFF 图像
        
        Args:
            path: 图像文件路径
        
        Returns:
            (image_data, profile) 或 (None, None) 如果失败
        """
        if not HAS_RASTERIO:
            # 回退到 OpenCV（无地理信息）
            return GeoUtils._read_with_opencv(path)
        
        try:
            with rasterio.open(path) as src:
                profile = {
                    'crs': src.crs,
                    'transform': src.transform,
                    'width': src.width,
                    'height': src.height,
                    'count': src.count,
                    'dtype': src.dtypes[0],
                    'nodata': src.nodata,
                }
                
                # 读取数据
                if src.count == 1:
                    # 单波段（灰度/Mask）
                    data = src.read(1)
                elif src.count >= 3:
                    # 多波段，取前3个作为 RGB
                    r = src.read(1)
                    g = src.read(2)
                    b = src.read(3)
                    data = cv2.merge([b, g, r])  # BGR for OpenCV compatibility
                else:
                    # 2波段，取第一个
                    data = src.read(1)
                
                return data, profile
                
        except rasterio.errors.RasterioIOError as e:
            print(f"⚠️ Rasterio 无法读取: {path}, 错误: {e}")
            return GeoUtils._read_with_opencv(path)
        except Exception as e:
            print(f"⚠️ 读取 GeoTIFF 失败: {path}, 错误: {e}")
            return None, None
    
    @staticmethod
    def _read_with_opencv(path: str) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]]]:
        """使用 OpenCV 读取（无地理信息）"""
        try:
            # 支持中文路径
            with open(path, 'rb') as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            
            if image is None:
                return None, None
            
            h, w = image.shape[:2]
            profile = {
                'crs': None,
                'transform': None,
                'width': w,
                'height': h,
                'count': 1 if image.ndim == 2 else image.shape[2],
                'dtype': str(image.dtype),
                'nodata': None,
            }
            return image, profile
        except Exception as e:
            print(f"⚠️ OpenCV 读取失败: {path}, 错误: {e}")
            return None, None

    @staticmethod
    def calculate_pixel_offset(
        base_transform: "Affine",
        overlay_transform: "Affine"
    ) -> Tuple[int, int]:
        """
        计算叠加图层相对于基础图层的像素偏移
        
        使用仿射变换逆运算:
        pixel_coords = ~base_transform * geo_coords
        
        Args:
            base_transform: 基础图层的仿射变换
            overlay_transform: 叠加图层的仿射变换
        
        Returns:
            (offset_x, offset_y) 像素偏移量
        """
        if base_transform is None or overlay_transform is None:
            return (0, 0)
        
        try:
            # 获取叠加图层左上角的地理坐标
            overlay_origin_x = overlay_transform.c
            overlay_origin_y = overlay_transform.f
            
            # 使用基础图层仿射变换的逆运算，将地理坐标转换为像素坐标
            inv_base = ~base_transform
            pixel_x, pixel_y = inv_base * (overlay_origin_x, overlay_origin_y)
            
            return (int(round(pixel_x)), int(round(pixel_y)))
        except Exception as e:
            print(f"⚠️ 计算像素偏移失败: {e}")
            # 回退到简单计算
            offset_x = (overlay_transform.c - base_transform.c) / base_transform.a
            offset_y = (overlay_transform.f - base_transform.f) / base_transform.e
            return (int(round(offset_x)), int(round(offset_y)))
    
    @staticmethod
    def check_crs_match(crs1, crs2) -> bool:
        """检查两个 CRS 是否匹配"""
        if crs1 is None or crs2 is None:
            return True  # 无 CRS 信息时假定匹配
        try:
            return crs1 == crs2
        except Exception:
            return str(crs1) == str(crs2)


class GISCanvasWidget(QGraphicsView):
    """
    GIS 画布组件
    
    支持:
    - GeoTIFF 加载与空间对齐
    - 多图层管理
    - 缩放/平移
    """
    
    # 信号
    layer_added = Signal(str)       # 图层名称
    layer_removed = Signal(str)     # 图层名称
    base_image_set = Signal(str)    # 基础图像路径
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        
        # 图层管理
        self._layers: List[LayerInfo] = []
        self._base_profile: Optional[Dict[str, Any]] = None
        self._next_z_value: int = 1
        
        # 配置视图
        self._setup_view()
    
    def _setup_view(self) -> None:
        """配置视图属性"""
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(self.renderHints().SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMouseTracking(True)
    
    def setup_add_menu(self, button: QToolButton) -> None:
        """
        设置添加图层按钮的菜单
        
        Args:
            button: 要附加菜单的 QToolButton
        """
        menu = QMenu(button)
        
        # 设置基础图像
        action_base = QAction("📂 加载底图 (Set Base Image)...", menu)
        action_base.triggered.connect(self.on_set_base_image)
        menu.addAction(action_base)
        
        menu.addSeparator()
        
        # 添加叠加栅格图层
        action_overlay = QAction("➕ 添加叠加层 (Add Overlay Raster)...", menu)
        action_overlay.triggered.connect(self.on_add_overlay)
        menu.addAction(action_overlay)
        
        # 添加矢量图层（占位）
        action_vector = QAction("🖍️ 添加矢量 (Add Vector Layer)...", menu)
        action_vector.setEnabled(False)  # 暂时禁用
        action_vector.setToolTip("矢量图层功能开发中...")
        menu.addAction(action_vector)
        
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    # ==================== 图层操作槽函数 ====================
    
    def on_set_base_image(self) -> None:
        """设置基础图像（清空现有图层，作为空间锚点）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择基础图像 (Select Base Image)",
            "",
            "GeoTIFF Files (*.tif *.tiff);;All Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All Files (*)"
        )
        
        if not file_path:
            return
        
        path = Path(file_path)
        
        # 读取图像
        image_data, profile = GeoUtils.read_image(str(path))
        if image_data is None:
            QMessageBox.critical(
                self, "错误", f"无法读取图像文件:\n{path}"
            )
            return
        
        # 清空现有图层
        self.clear_all_layers()
        
        # 存储基础图像的 profile 作为空间参考
        self._base_profile = profile
        
        # 创建 Pixmap
        pixmap = self._numpy_to_pixmap(image_data)
        if pixmap.isNull():
            QMessageBox.critical(self, "错误", "图像转换失败")
            return
        
        # 添加到场景 (0, 0) 位置
        item = QGraphicsPixmapItem(pixmap)
        item.setPos(0, 0)
        item.setZValue(0)
        item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._scene.addItem(item)
        
        # 记录图层信息
        layer_info = LayerInfo(
            name="Base Image",
            path=str(path),
            item=item,
            z_value=0,
            opacity=1.0,
            visible=True,
            profile=profile
        )
        self._layers.append(layer_info)
        
        # 设置场景范围
        h, w = image_data.shape[:2]
        self._scene.setSceneRect(0, 0, w, h)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        
        # 发出信号
        self.base_image_set.emit(str(path))
        self.layer_added.emit("Base Image")
        
        print(f"✅ 已设置基础图像: {path.name}")
        if profile.get('crs'):
            print(f"   CRS: {profile['crs']}")
        if profile.get('transform'):
            print(f"   Transform: {profile['transform']}")
    
    def on_add_overlay(self) -> None:
        """添加叠加图层（基于空间对齐）"""
        # 检查是否已设置基础图像
        if self._base_profile is None:
            QMessageBox.warning(
                self,
                "提示",
                "请先设置基础图像 (Please set Base Image first)"
            )
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择叠加图层 (Select Overlay Layer)",
            "",
            "GeoTIFF Files (*.tif *.tiff);;All Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All Files (*)"
        )
        
        if not file_path:
            return
        
        path = Path(file_path)
        
        # 读取图像
        image_data, profile = GeoUtils.read_image(str(path))
        if image_data is None:
            QMessageBox.critical(
                self, "错误", f"无法读取图像文件:\n{path}"
            )
            return
        
        # CRS 检查
        if not GeoUtils.check_crs_match(self._base_profile.get('crs'), profile.get('crs')):
            result = QMessageBox.warning(
                self,
                "CRS 不匹配",
                f"叠加图层的坐标系与基础图像不同:\n\n"
                f"基础图像: {self._base_profile.get('crs')}\n"
                f"叠加图层: {profile.get('crs')}\n\n"
                f"是否继续加载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        
        # 计算空间偏移
        offset_x, offset_y = GeoUtils.calculate_pixel_offset(
            self._base_profile.get('transform'),
            profile.get('transform')
        )
        
        # 创建 Pixmap（作为 Mask 处理，添加透明度）
        pixmap = self._numpy_to_pixmap(image_data, is_mask=True)
        if pixmap.isNull():
            QMessageBox.critical(self, "错误", "图像转换失败")
            return
        
        # 添加到场景
        item = QGraphicsPixmapItem(pixmap)
        item.setPos(offset_x, offset_y)
        item.setZValue(self._next_z_value)
        item.setOpacity(0.5)
        item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._scene.addItem(item)
        
        # 记录图层信息
        layer_name = path.name
        layer_info = LayerInfo(
            name=layer_name,
            path=str(path),
            item=item,
            z_value=self._next_z_value,
            opacity=0.5,
            visible=True,
            profile=profile
        )
        self._layers.append(layer_info)
        self._next_z_value += 1
        
        # 发出信号
        self.layer_added.emit(layer_name)
        
        print(f"✅ 已添加叠加图层: {layer_name}")
        print(f"   偏移: ({offset_x}, {offset_y}) pixels")

    # ==================== 图层管理 ====================
    
    def clear_all_layers(self) -> None:
        """清空所有图层"""
        for layer in self._layers:
            self._scene.removeItem(layer.item)
            self.layer_removed.emit(layer.name)
        self._layers.clear()
        self._base_profile = None
        self._next_z_value = 1
        self._scene.clear()
    
    def set_layer_visible(self, layer_name: str, visible: bool) -> None:
        """设置图层可见性"""
        for layer in self._layers:
            if layer.name == layer_name:
                layer.visible = visible
                layer.item.setVisible(visible)
                break
    
    def set_layer_opacity(self, layer_name: str, opacity: float) -> None:
        """设置图层透明度"""
        opacity = max(0.0, min(1.0, opacity))
        for layer in self._layers:
            if layer.name == layer_name:
                layer.opacity = opacity
                layer.item.setOpacity(opacity)
                break
    
    def remove_layer(self, layer_name: str) -> None:
        """移除指定图层"""
        for i, layer in enumerate(self._layers):
            if layer.name == layer_name:
                self._scene.removeItem(layer.item)
                self._layers.pop(i)
                self.layer_removed.emit(layer_name)
                break
    
    def get_layer_names(self) -> List[str]:
        """获取所有图层名称"""
        return [layer.name for layer in self._layers]
    
    def get_layer_info(self, layer_name: str) -> Optional[LayerInfo]:
        """获取图层信息"""
        for layer in self._layers:
            if layer.name == layer_name:
                return layer
        return None
    
    # ==================== 图像转换 ====================
    
    def _numpy_to_pixmap(self, data_np: np.ndarray, is_mask: bool = False) -> QPixmap:
        """将 Numpy 数组转换为 QPixmap"""
        h, w = data_np.shape[:2]
        
        if data_np.ndim == 2:
            if is_mask:
                # Mask: 转为 RGBA，背景透明
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                # 应用简单的伪彩色
                rgba[..., 0] = np.clip(data_np * 2, 0, 255).astype(np.uint8)
                rgba[..., 1] = data_np
                rgba[..., 2] = np.clip(255 - data_np, 0, 255).astype(np.uint8)
                rgba[..., 3] = (data_np > 0).astype(np.uint8) * 255
                data_np = rgba
            else:
                # 灰度图转 RGB
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
    
    # ==================== 视图控制 ====================
    
    def wheelEvent(self, event) -> None:
        """鼠标滚轮缩放"""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1 / zoom_factor, 1 / zoom_factor)
    
    def fit_to_view(self) -> None:
        """适应视图"""
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def zoom_in(self) -> None:
        """放大"""
        self.scale(1.2, 1.2)
    
    def zoom_out(self) -> None:
        """缩小"""
        self.scale(1 / 1.2, 1 / 1.2)
