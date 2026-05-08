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
    QToolButton, QMenu, QGraphicsPixmapItem, QTreeWidget, QProgressDialog, QApplication
)

from ui.widgets.smart_canvas import SmartCanvas
from ui.widgets.layer_manager import LayerManager, SlotType, create_layer_manager
from utils.pyramid_builder import PyramidBuilder

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
            print("⚠️ load_base_image: file_path 为空")
            return False
            
        path = str(Path(file_path))
        print(f"🔄 load_base_image: 开始加载 {path}")
        
        # 检查文件是否存在
        if not Path(path).exists():
            print(f"⚠️ 文件不存在: {path}")
            return False

        # 创建进度对话框 (可选)
        # 注意：对于快速加载，对话框可能不会显示
        progress = QProgressDialog("正在加载图像...", None, 0, 100, self)  # 移除取消按钮
        progress.setWindowTitle("加载中")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(1000)  # 1秒后才显示，避免闪烁
        progress.setValue(5)
        QApplication.processEvents()

        # 【关键】检查并构建金字塔（确保大图快速显示）
        print(f"   → 检查金字塔...")

        def pyramid_progress(percent, message):
            progress.setValue(5 + int(percent * 0.2))  # 5-25%
            progress.setLabelText(f"正在构建金字塔: {message}")
            QApplication.processEvents()

        pyramid_ok = PyramidBuilder.ensure_pyramids(path, progress_callback=pyramid_progress)
        if not pyramid_ok:
            print(f"⚠️ 金字塔构建失败，但继续加载")

        progress.setValue(30)
        progress.setLabelText("正在加载图像...")
        QApplication.processEvents()

        # 1. 提取元数据
        print(f"   → 读取元数据...")
        profile = self._read_profile(path)
        QApplication.processEvents()
            
        if not profile:
            progress.close()
            print(f"❌ 无法读取元数据: {path}")
            is_tiff = Path(path).suffix.lower() in {'.tif', '.tiff'}
            detail = (
                "\n\n当前文件为 TIFF/GeoTIFF，通常需要本机正确安装并配置 rasterio/GDAL，"
                "且底层驱动支持该影像格式。"
                if is_tiff else ""
            )
            QMessageBox.critical(self, "错误", f"无法读取元数据:\n{path}{detail}")
            return False

        progress.setValue(30)
        QApplication.processEvents()
            
        # 2. 清空
        print(f"   → 清理现有图层...")
        self.clear_all_layers()
        self._base_profile = profile
        QApplication.processEvents()
        
        progress.setValue(50)
        
        # 3. 加载到 SmartCanvas
        print(f"   → 加载图像到画布...")
        QApplication.processEvents()
        
        item = self.canvas.load_image_layer(path, pos=(0, 0), z_value=0)
            
        if item is None:
            progress.close()
            print(f"❌ 加载图像失败: {path}")
            is_tiff = Path(path).suffix.lower() in {'.tif', '.tiff'}
            detail = (
                "\n\n可能原因：当前机器的 rasterio/GDAL 环境不完整，或该 TIFF/GeoTIFF 的压缩/波段格式暂不受支持。"
                if is_tiff else ""
            )
            QMessageBox.critical(self, "错误", f"加载图像失败:\n{path}{detail}")
            return False

        progress.setValue(80)
        QApplication.processEvents()

        # 4. 如果有 LayerManager，使用模板初始化
        print(f"   → 初始化图层管理...")
        if self._layer_manager:
            success = self._layer_manager.init_task_group(path, item)
            if success:
                print(f"✅ Task Group 已通过 LayerManager 初始化")
        else:
            # 兼容旧模式
            self._add_layer_record("Base Image", path, item, 0, 1.0, profile)
        
        progress.setValue(90)
        QApplication.processEvents()
        
        # 5. 适应视图
        print(f"   → 调整视图...")
        self.canvas.fit_to_view()
        
        progress.setValue(100)
        progress.close()
        
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
    
    def inject_prediction(self, result_path: str, palette=None) -> bool:
        """
        注入预测结果 (显示为灰度图)
        
        Args:
            result_path: 预测结果文件路径
        
        Returns:
            bool: 是否成功
        """
        print(f"🔄 inject_prediction 被调用: {result_path}")
        
        if not self._layer_manager:
            print("⚠️ inject_prediction: _layer_manager 未设置")
            return False
            
        success = self._layer_manager.inject_layer_data(
            SlotType.TYPE_PRED, 
            result_path, 
            apply_colormap=True,  # 使用调色板显示
            palette=palette
        )
        
        if success:
            print(f"✅ inject_prediction: 成功注入预测结果")
        else:
            print(f"❌ inject_prediction: 注入失败")
            
        return success
        
    def set_prediction_loading(self, expected_filename: str) -> bool:
        """
        设置预测图层为加载状态
        
        Args:
            expected_filename: 预期输出文件名
            
        Returns:
            bool: 是否成功
        """
        if self._layer_manager:
            return self._layer_manager.set_slot_loading(
                SlotType.TYPE_PRED,
                text=expected_filename
            )
        return False

    def set_prediction_opacity(self, opacity: float) -> bool:
        """Update prediction layer opacity in the GIS canvas."""
        if not self._layer_manager:
            return False

        slot = self._layer_manager.get_slot(SlotType.TYPE_PRED)
        if not slot or not slot.graphics_item:
            return False

        slot.default_opacity = opacity
        slot.graphics_item.setOpacity(opacity)
        self.canvas.viewport().update()
        return True

    def set_prediction_palette(self, palette) -> bool:
        """Apply a custom palette to the prediction layer in the central canvas."""
        if not self._layer_manager:
            return False

        slot = self._layer_manager.get_slot(SlotType.TYPE_PRED)
        if not slot or not slot.graphics_item:
            return False

        updated = self.canvas.set_layer_palette(slot.default_z_value, palette)
        if updated:
            self.canvas.viewport().update()
        return updated
        
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
    
    def _cleanup_thread(self):
        """清理后台线程 - 转发到内部的 SmartCanvas"""
        if hasattr(self, 'canvas') and self.canvas is not None:
            try:
                self.canvas._cleanup_thread()
            except Exception as e:
                print(f"⚠️ GISCanvasWidget._cleanup_thread 出错: {e}")
