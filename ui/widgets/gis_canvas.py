"""
GISCanvasWidget - GIS 容器组件
负责处理从地理坐标(Geo)到像素坐标(Pixel)的映射，并协调 SmartCanvas 进行渲染。
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
import numpy as np

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QToolButton, QMenu, QGraphicsPixmapItem
)

from ui.widgets.smart_canvas import SmartCanvas

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

class GISCanvasWidget(QWidget):
    """
    GIS Canvas Wrapper
    Inherits QWidget (Container) instead of QGraphicsView
    """
    
    # 信号 (用于 Sidebar)
    layer_added = Signal(str)
    layer_removed = Signal(str)
    base_image_set = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 核心画布
        self.canvas = SmartCanvas(self)
        self.layout.addWidget(self.canvas)
        
        # 状态
        self._layers: List[LayerInfo] = []
        self._base_profile: Optional[Dict[str, Any]] = None
        self._next_z_value: int = 1
        
    # ==================== Public API (Compatible with Sidebar) ====================
    
    def setup_add_menu(self, button: QToolButton) -> None:
        """为 Sidebar 的添加按钮设置菜单"""
        menu = QMenu(button)
        
        action_base = QAction("📂 加载底图 (Set Base Image)...", menu)
        action_base.triggered.connect(self.on_set_base_image)
        menu.addAction(action_base)
        
        menu.addSeparator()
        
        action_overlay = QAction("➕ 添加叠加层 (Add Overlay Raster)...", menu)
        action_overlay.triggered.connect(self.on_add_overlay)
        menu.addAction(action_overlay)
        
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def on_set_base_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择基础图像", "", "GeoTIFF (*.tif *.tiff);;All Files (*)"
        )
        if not file_path:
            return
            
        path = str(Path(file_path))
        
        # 1. 提取元数据 (Transform)
        profile = self._read_profile(path)
        if not profile:
            QMessageBox.critical(self, "错误", f"无法读取元数据: {path}")
            return
            
        # 2. 清空
        self.clear_all_layers()
        self._base_profile = profile
        
        # 3. 加载到 SmartCanvas
        item = self.canvas.load_image_layer(path, pos=(0, 0), z_value=0)
        if hasattr(item, 'isNull') and item.isNull(): # Check if failed (item might be None or dummy)
             pass
        if item is None:
             QMessageBox.critical(self, "错误", "加载图像失败")
             return

        # 4. 记录
        self._add_layer_record("Base Image", path, item, 0, 1.0, profile)
        
        # 5. 适应视图
        self.canvas.fit_to_view()
        
        self.base_image_set.emit(path)
        self.layer_added.emit("Base Image")
        print(f"✅ Base Image Set: {path}")

    def on_add_overlay(self) -> None:
        if self._base_profile is None:
            QMessageBox.warning(self, "提示", "请先设置基础图像")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择叠加图层", "", "GeoTIFF (*.tif *.tiff);;All Files (*)"
        )
        if not file_path:
            return
            
        path = str(Path(file_path))
        profile = self._read_profile(path)
        if not profile:
            return
            
        # 检查 CRS
        if not self._check_crs_match(self._base_profile.get('crs'), profile.get('crs')):
            ret = QMessageBox.warning(
                self, "CRS 不匹配", 
                f"当前: {self._base_profile.get('crs')}\n新图层: {profile.get('crs')}\n继续?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        # 计算偏移
        offset_x, offset_y = self._calculate_offset(
            self._base_profile.get('transform'),
            profile.get('transform')
        )
        print(f"Overlay Offset: {offset_x}, {offset_y}")
        
        # 加载
        z = self._next_z_value
        item = self.canvas.load_image_layer(path, pos=(offset_x, offset_y), z_value=z, opacity=0.5)
        if item is None:
            return
            
        self._add_layer_record(Path(path).name, path, item, z, 0.5, profile)
        self._next_z_value += 1
        
        self.layer_added.emit(Path(path).name)

    def set_layer_visible(self, layer_name: str, visible: bool):
        layer = self._get_layer(layer_name)
        if layer and layer.item:
            layer.visible = visible
            layer.item.setVisible(visible)

    def set_layer_opacity(self, layer_name: str, opacity: float):
        layer = self._get_layer(layer_name)
        if layer and layer.item:
            layer.opacity = opacity
            layer.item.setOpacity(opacity)

    def remove_layer(self, layer_name: str):
        layer = self._get_layer(layer_name)
        if layer:
            if hasattr(self.canvas, '_scene'):
                self.canvas._scene.removeItem(layer.item)
            self._layers.remove(layer)
            self.layer_removed.emit(layer_name)

    def clear_all_layers(self):
        self.canvas.clear_all()
        self._layers.clear()
        self._base_profile = None
        self._next_z_value = 1

    # ==================== Internal Utils ====================

    def _read_profile(self, path: str) -> Optional[Dict[str, Any]]:
        if not HAS_RASTERIO:
            # Fallback for non-geo
            return {'crs': None, 'transform': None}
        try:
            with rasterio.open(path) as src:
                return {
                    'crs': src.crs,
                    'transform': src.transform,
                    'width': src.width,
                    'height': src.height
                }
        except Exception as e:
            print(f"Metadata read failed: {e}")
            return None

    def _calculate_offset(self, base_tf: "Affine", overlay_tf: "Affine") -> Tuple[int, int]:
        if not base_tf or not overlay_tf:
            return (0, 0)
        try:
            # pixel = ~base * geo
            # geo_origin = overlay_tf * (0, 0) -> (c, f)
            geo_x, geo_y = overlay_tf.c, overlay_tf.f
            
            inv_base = ~base_tf
            px, py = inv_base * (geo_x, geo_y)
            return int(round(px)), int(round(py))
        except:
            return (0, 0)

    def _check_crs_match(self, crs1, crs2) -> bool:
        if not crs1 or not crs2: return True
        return str(crs1) == str(crs2)

    def _add_layer_record(self, name, path, item, z, opacity, profile):
        info = LayerInfo(name, path, item, z, opacity, True, profile)
        self._layers.append(info)

    def _get_layer(self, name) -> Optional[LayerInfo]:
        for x in self._layers:
            if x.name == name: return x
        return None
