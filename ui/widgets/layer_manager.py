"""
LayerManager - 基于模板的图层树管理器
用于推理任务的结构化图层组管理。
"""

import os
from datetime import datetime
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QColor, QBrush, QPixmap, QPainter
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMenu, QMessageBox,
    QGraphicsPixmapItem, QWidget
)


# ==================== 常量定义 ====================

class SlotType(Enum):
    """图层槽类型"""
    TYPE_BASE = auto()      # 底图
    TYPE_PRED = auto()      # 预测结果
    TYPE_GT = auto()        # Ground Truth
    TYPE_ROI = auto()       # 感兴趣区域


# Z-Order 常量 (确保 Prediction 始终在 Base 之上)
class ZOrder:
    """Z轴顺序常量"""
    BASE = 0        # 底图 (最底层)
    GT = 5          # Ground Truth
    PRED = 10       # 预测结果
    ROI = 20        # ROI (最顶层)


# ==================== 数据结构 ====================

@dataclass
class LayerSlot:
    """
    图层槽 - 表示一个标准化的图层类型
    """
    slot_type: SlotType
    name: str
    display_name: str
    default_opacity: float
    default_z_value: int
    is_filled: bool = False
    data_path: Optional[str] = None
    graphics_item: Optional[QGraphicsPixmapItem] = None
    tree_item: Optional[QTreeWidgetItem] = None
    
    # 文件过滤器
    file_filter: str = "GeoTIFF (*.tif *.tiff);;PNG (*.png);;All Files (*)"
    
    @property
    def status_text(self) -> str:
        """状态文本"""
        if self.is_filled:
            return Path(self.data_path).name if self.data_path else "已填充"
        return "空"
    
    @property
    def status_icon(self) -> str:
        """状态图标"""
        icons = {
            SlotType.TYPE_BASE: "🗺️",
            SlotType.TYPE_PRED: "🎯",
            SlotType.TYPE_GT: "✅",
            SlotType.TYPE_ROI: "📐",
        }
        return icons.get(self.slot_type, "📄")
    
    @property
    def display_text(self) -> str:
        """显示文本 (包含状态)"""
        if self.is_filled and self.data_path:
            filename = Path(self.data_path).name
            # 截断过长的文件名
            if len(filename) > 25:
                filename = filename[:22] + "..."
            return f"{self.status_icon} {self.display_name}: {filename}"
        elif self.is_filled:
            return f"{self.status_icon} {self.display_name} ✓"
        else:
            return f"{self.status_icon} {self.display_name} (空)"


@dataclass
class TaskGroup:
    """
    任务组 - 包含一组相关的图层槽
    """
    name: str
    timestamp: datetime
    base_image_path: str
    slots: Dict[SlotType, LayerSlot] = field(default_factory=dict)
    tree_item: Optional[QTreeWidgetItem] = None
    
    @property
    def display_name(self) -> str:
        return f"Task {self.timestamp.strftime('%H:%M:%S')}"


# ==================== 图层槽模板 ====================

def create_default_slots() -> Dict[SlotType, LayerSlot]:
    """创建默认的图层槽模板"""
    return {
        SlotType.TYPE_PRED: LayerSlot(
            slot_type=SlotType.TYPE_PRED,
            name="prediction",
            display_name="Prediction",
            default_opacity=0.5,
            default_z_value=ZOrder.PRED,
        ),
        SlotType.TYPE_GT: LayerSlot(
            slot_type=SlotType.TYPE_GT,
            name="ground_truth",
            display_name="Ground Truth",
            default_opacity=0.5,
            default_z_value=ZOrder.GT,
        ),
        SlotType.TYPE_ROI: LayerSlot(
            slot_type=SlotType.TYPE_ROI,
            name="roi",
            display_name="ROI",
            default_opacity=1.0,
            default_z_value=ZOrder.ROI,
            is_filled=True,  # ROI 默认为整个图像范围
        ),
        SlotType.TYPE_BASE: LayerSlot(
            slot_type=SlotType.TYPE_BASE,
            name="base_image",
            display_name="Base Image",
            default_opacity=1.0,
            default_z_value=ZOrder.BASE,
        ),
    }


# ==================== LayerManager 类 ====================

class LayerManager(QObject):
    """
    图层管理器
    管理基于模板的图层树，支持推理任务的结构化图层组。
    """
    
    # 信号
    task_initialized = Signal(str)          # 任务初始化完成 (base_path)
    slot_filled = Signal(str, str)          # 槽位被填充 (slot_name, data_path)
    slot_cleared = Signal(str)              # 槽位被清空 (slot_name)
    layer_visibility_changed = Signal(str, bool)  # 图层可见性改变
    layer_opacity_changed = Signal(str, float)    # 图层透明度改变
    base_image_cleared = Signal()           # 底图被清空信号
    base_image_replaced = Signal(str)       # 底图被替换信号 (new_path)
    
    def __init__(self, tree_widget: QTreeWidget, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._tree = tree_widget
        self._parent_widget = parent
        
        # 当前任务组
        self._current_task: Optional[TaskGroup] = None
        
        # 图层加载回调 (由外部设置，用于实际加载图像到画布)
        self._load_layer_callback: Optional[Callable] = None
        self._remove_layer_callback: Optional[Callable] = None
        
        # 设置树形控件
        self._setup_tree()
    
    def _setup_tree(self):
        """设置树形控件 - 单列分组样式"""
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setIndentation(20)
        self._tree.setAnimated(True)
        
        # 连接信号
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
    
    def set_load_callback(self, callback: Callable):
        """
        设置图层加载回调
        callback(path, z_value, opacity, apply_colormap) -> QGraphicsPixmapItem
        """
        self._load_layer_callback = callback
    
    def set_remove_callback(self, callback: Callable):
        """
        设置图层移除回调
        callback(graphics_item) -> None
        """
        self._remove_layer_callback = callback
    
    # ==================== 核心方法 ====================
    
    def init_task_group(self, base_image_path: str, base_item: QGraphicsPixmapItem, band_count: int = 3) -> bool:
        """
        初始化任务组
        
        触发条件：当 Set Base Image 成功时调用
        
        Args:
            base_image_path: 底图路径
            base_item: 底图的 QGraphicsPixmapItem
            band_count: 波段数量（用于显示波段信息子节点）
        
        Returns:
            bool: 是否成功
        """
        if not base_image_path or not os.path.exists(base_image_path):
            return False
        
        # 1. 清空现有图层树
        self._tree.clear()
        self._current_task = None
        
        # 2. 创建任务组
        task = TaskGroup(
            name="inference_task",
            timestamp=datetime.now(),
            base_image_path=base_image_path,
            slots=create_default_slots()
        )
        
        # 3. 创建顶级树项
        task_item = QTreeWidgetItem(self._tree)
        task_item.setText(0, task.display_name)
        task_item.setText(1, "")
        task_item.setExpanded(True)
        task_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "task_group"})
        task.tree_item = task_item
        
        # 4. 按 Z 值顺序创建子项 (从高到低显示，但底图在最后)
        slot_order = [SlotType.TYPE_PRED, SlotType.TYPE_GT, SlotType.TYPE_ROI, SlotType.TYPE_BASE]
        
        for slot_type in slot_order:
            slot = task.slots[slot_type]
            self._create_slot_tree_item(task_item, slot)
        
        # 5. 绑定底图
        base_slot = task.slots[SlotType.TYPE_BASE]
        base_slot.is_filled = True
        base_slot.data_path = base_image_path
        base_slot.graphics_item = base_item
        self._update_slot_tree_item(base_slot)
        
        # 6. 添加波段信息子节点
        self._add_band_info_nodes(base_slot.tree_item, band_count)
        
        # 7. 保存当前任务
        self._current_task = task
        
        self.task_initialized.emit(base_image_path)
        print(f"✅ Task Group 初始化完成: {task.display_name}")
        
        return True
    
    def _create_color_icon(self, color: QColor, size: int = 12) -> QIcon:
        """
        创建纯色方块图标
        
        Args:
            color: 颜色
            size: 图标大小
        
        Returns:
            QIcon: 生成的图标
        """
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, size, size)
        painter.end()
        return QIcon(pixmap)
    
    def _add_band_info_nodes(self, parent_item: QTreeWidgetItem, band_count: int):
        """
        为底图添加波段信息子节点
        
        Args:
            parent_item: 底图的树项
            band_count: 波段数量
        """
        if not parent_item:
            return
        
        # 清除现有子节点
        while parent_item.childCount() > 0:
            parent_item.removeChild(parent_item.child(0))
        
        if band_count >= 3:
            # RGB 三通道
            band_info = [
                (QColor(220, 53, 69), "Band 1 (Red channel)"),    # 红色
                (QColor(40, 167, 69), "Band 2 (Green channel)"),   # 绿色
                (QColor(0, 123, 255), "Band 3 (Blue channel)"),    # 蓝色
            ]
        elif band_count == 1:
            # 单通道灰度
            band_info = [
                (QColor(128, 128, 128), "Gray: Band 1"),
            ]
        else:
            # 其他情况（如2通道）
            band_info = [
                (QColor(128, 128, 128), f"Band {i+1}") for i in range(band_count)
            ]
        
        for color, text in band_info:
            child_item = QTreeWidgetItem(parent_item)
            child_item.setText(0, text)
            child_item.setIcon(0, self._create_color_icon(color))
            child_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "band_info"})
            # 子项不可选中、不可勾选
            child_item.setFlags(child_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            child_item.setFlags(child_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            # 设置为灰色斜体
            child_item.setForeground(0, QBrush(QColor(100, 100, 100)))
        
        # 展开底图节点显示波段信息
        parent_item.setExpanded(True)
    
    def inject_layer_data(
        self, 
        slot_type: SlotType, 
        data_path: str,
        apply_colormap: bool = False
    ) -> bool:
        """
        注入图层数据到指定槽位
        
        用于程序化填充槽位，例如推理完成后调用：
        inject_layer_data(SlotType.TYPE_PRED, result_path)
        
        Args:
            slot_type: 槽位类型
            data_path: 数据文件路径
            apply_colormap: 是否应用伪彩色 (用于 mask)
        
        Returns:
            bool: 是否成功
        """
        print(f"🔄 inject_layer_data: slot_type={slot_type}, path={data_path}, colormap={apply_colormap}")
        
        if not self._current_task:
            print("⚠️ inject_layer_data: 没有活动的任务组")
            return False
        
        if slot_type not in self._current_task.slots:
            print(f"⚠️ inject_layer_data: 无效的槽位类型: {slot_type}")
            return False
        
        if not os.path.exists(data_path):
            print(f"⚠️ inject_layer_data: 文件不存在: {data_path}")
            return False
        
        slot = self._current_task.slots[slot_type]
        
        # 如果已有图层，先移除
        if slot.graphics_item and self._remove_layer_callback:
            print(f"   → 移除旧图层")
            self._remove_layer_callback(slot.graphics_item)
        
        # 加载新图层
        if self._load_layer_callback:
            print(f"   → 调用 _load_layer_callback...")
            item = self._load_layer_callback(
                data_path, 
                slot.default_z_value, 
                slot.default_opacity,
                apply_colormap
            )
            if item:
                slot.graphics_item = item
                slot.is_filled = True
                slot.data_path = data_path
                self._update_slot_tree_item(slot)
                
                self.slot_filled.emit(slot.name, data_path)
                print(f"✅ 已填充 {slot.display_name}: {Path(data_path).name}")
                return True
            else:
                print(f"❌ _load_layer_callback 返回 None")
        else:
            print(f"❌ _load_layer_callback 未设置")
        
        return False
    
    def set_slot_loading(self, slot_type: SlotType, text: str = "") -> bool:
        """
        设置槽位为加载状态
        
        Args:
            slot_type: 槽位类型
            text: 显示的文件名文本
        """
        if not self._current_task:
            return False
        
        if slot_type not in self._current_task.slots:
            return False
            
        slot = self._current_task.slots[slot_type]
        
        # 1. 更新树项显示
        if slot.tree_item:
            item = slot.tree_item
            if text:
                display_text = f"🔄 [处理中...] {text}"
            else:
                display_text = f"🔄 [处理中...] {slot.display_name}"
            
            item.setText(0, display_text)
            item.setForeground(0, QBrush(QColor(128, 128, 128)))  # 灰色
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)  # 禁用复选框
            item.setCheckState(0, Qt.CheckState.Unchecked)
        
        return True
    
    def clear_slot(self, slot_type: SlotType) -> bool:
        """清空指定槽位"""
        if not self._current_task:
            return False
        
        if slot_type not in self._current_task.slots:
            return False
        
        slot = self._current_task.slots[slot_type]
        
        # 不能清空底图
        if slot_type == SlotType.TYPE_BASE:
            QMessageBox.warning(
                self._parent_widget, 
                "提示", 
                "无法清空底图。请使用\"设置新底图\"来替换。"
            )
            return False
        
        # 移除图层
        if slot.graphics_item and self._remove_layer_callback:
            self._remove_layer_callback(slot.graphics_item)
        
        slot.graphics_item = None
        slot.is_filled = False
        slot.data_path = None
        self._update_slot_tree_item(slot)
        
        self.slot_cleared.emit(slot.name)
        return True
    
    def get_slot(self, slot_type: SlotType) -> Optional[LayerSlot]:
        """获取指定类型的槽位"""
        if self._current_task and slot_type in self._current_task.slots:
            return self._current_task.slots[slot_type]
        return None
    
    def get_current_task(self) -> Optional[TaskGroup]:
        """获取当前任务组"""
        return self._current_task
    
    # ==================== 树项管理 ====================
    
    def _create_slot_tree_item(self, parent_item: QTreeWidgetItem, slot: LayerSlot):
        """为槽位创建树项 - 单列分组样式"""
        item = QTreeWidgetItem(parent_item)
        item.setText(0, slot.display_text)
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "slot",
            "slot_type": slot.slot_type
        })
        
        # 添加复选框控制可见性 (底图默认选中，空槽位不选中)
        if slot.is_filled:
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)  # 空槽位禁用复选框
        
        # 空槽位显示为灰色
        if not slot.is_filled:
            item.setForeground(0, QBrush(QColor(128, 128, 128)))
        
        # 设置提示
        if slot.data_path:
            item.setToolTip(0, slot.data_path)
        else:
            item.setToolTip(0, "双击加载文件")
        
        slot.tree_item = item
    
    def _update_slot_tree_item(self, slot: LayerSlot):
        """更新槽位的树项显示"""
        if not slot.tree_item:
            return
        
        item = slot.tree_item
        item.setText(0, slot.display_text)
        
        # 更新复选框状态
        if slot.is_filled:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setForeground(0, QBrush(QColor(0, 0, 0)))  # 黑色
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setForeground(0, QBrush(QColor(128, 128, 128)))  # 灰色
        
        # 更新提示
        if slot.data_path:
            item.setToolTip(0, slot.data_path)
        else:
            item.setToolTip(0, "双击加载文件")
    
    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """处理复选框状态变化 - 切换可见性"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "slot":
            return
        
        slot_type = data.get("slot_type")
        if not slot_type or not self._current_task:
            return
        
        slot = self._current_task.slots.get(slot_type)
        if slot and slot.graphics_item:
            visible = item.checkState(0) == Qt.CheckState.Checked
            slot.graphics_item.setVisible(visible)
            self.layer_visibility_changed.emit(slot.name, visible)
    
    # ==================== 事件处理 ====================
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项处理 - 空槽位打开文件对话框"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "slot":
            return
        
        slot_type = data.get("slot_type")
        if not slot_type or not self._current_task:
            return
        
        slot = self._current_task.slots.get(slot_type)
        if not slot:
            return
        
        # 如果是空槽位，打开文件对话框
        if not slot.is_filled:
            self._open_file_for_slot(slot)
    
    def _on_context_menu(self, pos):
        """右键菜单"""
        item = self._tree.itemAt(pos)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_type = data.get("type")
        
        # 波段信息节点不显示菜单
        if item_type == "band_info":
            return
        
        # 只处理槽位节点
        if item_type != "slot":
            return
        
        slot_type = data.get("slot_type")
        if not slot_type or not self._current_task:
            return
        
        slot = self._current_task.slots.get(slot_type)
        if not slot:
            return
        
        # 使用统一的菜单构建方法
        self._show_slot_context_menu(slot, pos)
    
    def _show_slot_context_menu(self, slot: LayerSlot, pos):
        """
        显示槽位的右键菜单 - 统一 UI 组件
        
        Args:
            slot: 图层槽位
            pos: 菜单位置
        """
        menu = QMenu(self._tree)
        
        if slot.is_filled:
            # 已填充的槽位 - 统一的菜单项
            
            # 替换选项
            action_replace = menu.addAction("🔄 替换...")
            if slot.slot_type == SlotType.TYPE_BASE:
                action_replace.triggered.connect(self._replace_base_image)
            else:
                action_replace.triggered.connect(lambda: self._open_file_for_slot(slot))
            
            # 清空选项
            action_clear = menu.addAction("🗑️ 清空")
            if slot.slot_type == SlotType.TYPE_BASE:
                action_clear.triggered.connect(self._clear_base_image)
            else:
                action_clear.triggered.connect(lambda: self.clear_slot(slot.slot_type))
            
            menu.addSeparator()
            
            # 显示/隐藏选项（所有已填充槽位都有）
            action_show = menu.addAction("👁️ 显示/隐藏")
            action_show.triggered.connect(lambda: self._toggle_visibility(slot))
        else:
            # 空槽位
            action_load = menu.addAction("📂 加载文件...")
            action_load.triggered.connect(lambda: self._open_file_for_slot(slot))
        
        menu.exec(self._tree.mapToGlobal(pos))
    
    def _replace_base_image(self):
        """替换底图 - 打开文件对话框选择新底图"""
        if not self._current_task:
            return
        
        base_slot = self._current_task.slots.get(SlotType.TYPE_BASE)
        if not base_slot:
            return
        
        # 获取当前底图目录作为起始目录
        start_dir = ""
        if base_slot.data_path:
            start_dir = os.path.dirname(base_slot.data_path)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "选择新底图",
            start_dir,
            "GeoTIFF (*.tif *.tiff);;PNG (*.png);;JPEG (*.jpg *.jpeg);;All Files (*)"
        )
        
        if file_path:
            # 发出替换信号，让外部处理实际的图像加载
            self.base_image_replaced.emit(file_path)
    
    def _clear_base_image(self):
        """清空底图"""
        if not self._current_task:
            return
        
        # 确认对话框
        reply = QMessageBox.question(
            self._parent_widget,
            "确认清空",
            "清空底图将同时移除所有叠加图层。\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 清空所有槽位
            for slot_type in list(self._current_task.slots.keys()):
                slot = self._current_task.slots[slot_type]
                if slot.graphics_item and self._remove_layer_callback:
                    self._remove_layer_callback(slot.graphics_item)
            
            # 清空任务组
            self._tree.clear()
            self._current_task = None
            
            # 发出信号
            self.base_image_cleared.emit()
            print("✅ 底图已清空")
    
    def _open_file_for_slot(self, slot: LayerSlot):
        """为槽位打开文件选择对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            f"选择 {slot.display_name}",
            "",
            slot.file_filter
        )
        
        if file_path:
            # Prediction 和 GT 显示为灰度图 (不应用伪彩色)
            apply_colormap = False
            self.inject_layer_data(slot.slot_type, file_path, apply_colormap)
    
    def _toggle_visibility(self, slot: LayerSlot):
        """切换图层可见性"""
        if slot.graphics_item:
            current = slot.graphics_item.isVisible()
            slot.graphics_item.setVisible(not current)
            self.layer_visibility_changed.emit(slot.name, not current)


# ==================== 便捷函数 ====================

def create_layer_manager(tree_widget: QTreeWidget, canvas) -> LayerManager:
    """
    创建并配置 LayerManager
    
    Args:
        tree_widget: QTreeWidget 实例
        canvas: SmartCanvas 或 GISCanvasWidget 实例
    
    Returns:
        LayerManager: 配置好的管理器实例
    """
    manager = LayerManager(tree_widget)
    
    # 设置加载回调
    def load_callback(path, z_value, opacity, apply_colormap):
        if hasattr(canvas, 'load_image_layer'):
            return canvas.load_image_layer(
                path, 
                pos=(0, 0), 
                z_value=z_value, 
                opacity=opacity,
                apply_colormap=apply_colormap
            )
        return None
    
    # 设置移除回调
    def remove_callback(item):
        if hasattr(canvas, '_scene') and item:
            canvas._scene.removeItem(item)
    
    manager.set_load_callback(load_callback)
    manager.set_remove_callback(remove_callback)
    
    return manager
