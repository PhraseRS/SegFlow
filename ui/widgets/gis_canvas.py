"""
GISCanvasWidget - GIS 容器组件
负责处理从地理坐标(Geo)到像素坐标(Pixel)的映射，并协调 SmartCanvas 进行渲染。
集成 LayerManager 支持基于模板的图层树初始化。
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
import numpy as np

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, 
    QToolButton, QMenu, QGraphicsPixmapItem, QTreeWidget
)

from ui.widgets.smart_canvas import SmartCanvas
from ui.widgets.layer_manager import LayerManager, SlotType, create_layer_manager

try:
    import rasterio
    from rasterio.transform import Affine
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    Affine = None


@dataclass
class LayerInfo:
    """图层信息 (兼容旧代码)"""
    name: str
    path: str
    item: QGraphicsPixmapItem
    z_value: int
    opacity: float
    visible: bool
    profile: Dict[str, Any]


class GISCanvasWidget(QWidget):
    """
    GIS Canvas Wrapper with LayerManager Integration
    """
    
    # 信号
    layer_added = Signal(str)
    layer_removed = Signal(str)
    base_image_set = Signal(str)
    task_initialized = Signal(str)  # 任务组初始化完成
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 核心画布
        self.canvas = SmartCanvas(self)
        self.layout.addWidget(self.canvas)
        
        # 状态 (兼容旧代码)
        self._layers: List[LayerInfo] = []
        self._base_profile: Optional[Dict[str, Any]] = None
        self._next_z_value: int = 100  # 保留 0-99 给模板槽位
        
        # LayerManager (需要外部设置 tree widget)
        self._layer_manager: Optional[LayerManager] = None
        
    # ==================== LayerManager 集成 ====================
    
    def setup_layer_manager(self, tree_widget: QTreeWidget) -> LayerManager:
        """
        设置 LayerManager
        
        Args:
            tree_widget: 用于显示图层树的 QTreeWidget
        
        Returns:
            LayerManager: 配置好的管理器实例
        """
        self._layer_manager = create_layer_manager(tree_widget, self.canvas)
        
        # 连接信号
        self._layer_manager.task_initialized.connect(self._on_task_initialized)
        self._layer_manager.slot_filled.connect(self._on_slot_filled)
        
        return self._layer_manager
    
    def get_layer_manager(self) -> Optional[LayerManager]:
        """获取 LayerManager 实例"""
        return self._layer_manager
    
    def _on_task_initialized(self, base_path: str):
        """任务组初始化完成"""
        self.task_initialized.emit(base_path)
    
    def _on_slot_filled(self, slot_name: str, data_path: str):
        """槽位被填充"""
        self.layer_added.emit(slot_name)
        
    # ==================== Public API (With LayerManager) ====================
    
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
        """设置底图 (通过文件对话框) - 集成 LayerManager"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择基础图像", "", "GeoTIFF (*.tif *.tiff);;All Files (*)"
        )
        if not file_path:
            return
        
        # 调用共享的加载逻辑
        self.load_base_image(file_path)
    
    def load_base_image(self, file_path: str, suppress_signal: bool = False) -> bool:
        """
        加载底图 (程序化调用)
        
        用于从外部同步调用，例如从右侧推理面板同步过来的路径。
        
        Args:
            file_path: 图像文件路径
            suppress_signal: 如果为 True，则不发出 base_image_set 信号
                            用于防止循环同步
        
        Returns:
            bool: 是否加载成功
        """
        if not file_path:
            return False
            
        path = str(Path(file_path))
        
        # 检查文件是否存在
        if not Path(path).exists():
            print(f"⚠️ 文件不存在: {path}")
            return False
        
        # 1. 提取元数据
        profile = self._read_profile(path)
        if not profile:
            QMessageBox.critical(self, "错误", f"无法读取元数据: {path}")
            return False
            
        # 2. 清空
        self.clear_all_layers()
        self._base_profile = profile
        
        # 3. 加载到 SmartCanvas
        item = self.canvas.load_image_layer(path, pos=(0, 0), z_value=0)
        if item is None:
            QMessageBox.critical(self, "错误", "加载图像失败")
            return False

        # 4. 如果有 LayerManager，使用模板初始化
        if self._layer_manager:
            success = self._layer_manager.init_task_group(path, item)
            if success:
                print(f"✅ Task Group 已通过 LayerManager 初始化")
        else:
            # 兼容旧模式
            self._add_layer_record("Base Image", path, item, 0, 1.0, profile)
        
        # 5. 适应视图
        self.canvas.fit_to_view()
        
        # 6. 发出信号 (除非被抑制)
        if not suppress_signal:
            self.base_image_set.emit(path)
        
        self.layer_added.emit("Base Image")
        print(f"✅ Base Image Set: {path}")
        return True

    def on_add_overlay(self) -> None:
        """添加叠加层"""
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
        
        # 加载
        z = self._next_z_value
        item = self.canvas.load_image_layer(path, pos=(offset_x, offset_y), z_value=z, opacity=0.5)
        if item is None:
            return
            
        self._add_layer_record(Path(path).name, path, item, z, 0.5, profile)
        self._next_z_value += 1
        
        self.layer_added.emit(Path(path).name)

    # ==================== LayerManager 便捷方法 ====================
    
    def inject_prediction(self, result_path: str) -> bool:
        """
        注入预测结果 (显示为灰度图)
        
        Args:
            result_path: 预测结果文件路径
        
        Returns:
            bool: 是否成功
        """
        if self._layer_manager:
            return self._layer_manager.inject_layer_data(
                SlotType.TYPE_PRED, 
                result_path, 
                apply_colormap=False  # 灰度显示
            )
        return False
    
    def inject_ground_truth(self, gt_path: str) -> bool:
        """
        注入 Ground Truth (显示为灰度图)
        
        Args:
            gt_path: GT 文件路径
        
        Returns:
            bool: 是否成功
        """
        if self._layer_manager:
            return self._layer_manager.inject_layer_data(
                SlotType.TYPE_GT, 
                gt_path, 
                apply_colormap=False  # 灰度显示
            )
        return False
    
    def get_base_image_path(self) -> Optional[str]:
        """获取当前底图路径"""
        if self._layer_manager:
            task = self._layer_manager.get_current_task()
            if task:
                return task.base_image_path
        return None

    # ==================== 兼容旧代码 ====================

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
        self._next_z_value = 100

    # ==================== Internal Utils ====================

    def _read_profile(self, path: str) -> Optional[Dict[str, Any]]:
        if not HAS_RASTERIO:
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
            geo_x, geo_y = overlay_tf.c, overlay_tf.f
            inv_base = ~base_tf
            px, py = inv_base * (geo_x, geo_y)
            return int(round(px)), int(round(py))
        except:
            return (0, 0)

    def _check_crs_match(self, crs1, crs2) -> bool:
        if not crs1 or not crs2:
            return True
        return str(crs1) == str(crs2)

    def _add_layer_record(self, name, path, item, z, opacity, profile):
        info = LayerInfo(name, path, item, z, opacity, True, profile)
        self._layers.append(info)

    def _get_layer(self, name) -> Optional[LayerInfo]:
        for x in self._layers:
            if x.name == name:
                return x
        return None
