"""
侧边栏组件模块
包含不同模式下的侧边栏组件
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QTreeWidget, QTreeWidgetItem,
    QPushButton, QCheckBox, QHBoxLayout, QLabel, QSlider, QFrame,
    QSizePolicy, QToolButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class SampleManagementSidebar(QWidget):
    """
    样本管理侧边栏 (Data Profile Mode)
    包含：数据源树 + 简单图层控制
    """
    
    # 信号
    add_sample_clicked = Signal()
    base_image_toggled = Signal(bool)
    overlay_toggled = Signal(bool)
    label_only_toggled = Signal(bool)
    opacity_changed = Signal(int)
    swipe_toggled = Signal(bool)
    swipe_position_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._connect_signals()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ========== 数据源管理 ==========
        self.groupBox_dataSource = QGroupBox("数据源管理 (Data Source Manager)")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.groupBox_dataSource.setSizePolicy(sizePolicy)
        
        dataSource_layout = QVBoxLayout(self.groupBox_dataSource)
        
        # 数据源树
        self.treeWidget_dataSources = QTreeWidget()
        self.treeWidget_dataSources.setHeaderHidden(True)
        self.treeWidget_dataSources.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        dataSource_layout.addWidget(self.treeWidget_dataSources)
        
        # 添加样本按钮
        self.pushButton_addSample = QPushButton("添加样本")
        dataSource_layout.addWidget(self.pushButton_addSample)
        
        layout.addWidget(self.groupBox_dataSource, stretch=3)
        
        # ========== 图层控制 ==========
        self.groupBox_layerControl = QGroupBox("图层控制 (Layer Control)")
        layerControl_layout = QVBoxLayout(self.groupBox_layerControl)
        
        # Overlay Prediction
        self.checkBox_overlayPrediction = QCheckBox("Overlay Prediction")
        self.checkBox_overlayPrediction.setChecked(True)
        layerControl_layout.addWidget(self.checkBox_overlayPrediction)
        
        # Base Image
        self.checkBox_baseImage = QCheckBox("Base Image (RGB/False Color)")
        self.checkBox_baseImage.setChecked(True)
        layerControl_layout.addWidget(self.checkBox_baseImage)
        
        # Label Only
        self.checkBox_labelOnly = QCheckBox("Label Only")
        layerControl_layout.addWidget(self.checkBox_labelOnly)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(70)
        opacity_layout.addWidget(self.slider_opacity)
        self.label_opacityValue = QLabel("70%")
        opacity_layout.addWidget(self.label_opacityValue)
        layerControl_layout.addLayout(opacity_layout)
        
        # Swipe Compare
        self.checkBox_swipeCompare = QCheckBox("卷帘对比 (Swipe Compare)")
        layerControl_layout.addWidget(self.checkBox_swipeCompare)
        
        # Swipe Position
        swipe_layout = QHBoxLayout()
        swipe_layout.addWidget(QLabel("Position:"))
        self.slider_swipe = QSlider(Qt.Orientation.Horizontal)
        self.slider_swipe.setRange(0, 100)
        self.slider_swipe.setValue(50)
        self.slider_swipe.setEnabled(False)
        swipe_layout.addWidget(self.slider_swipe)
        self.label_swipeValue = QLabel("50%")
        swipe_layout.addWidget(self.label_swipeValue)
        layerControl_layout.addLayout(swipe_layout)
        
        layout.addWidget(self.groupBox_layerControl, stretch=1)
    
    def _connect_signals(self):
        """连接内部信号"""
        self.pushButton_addSample.clicked.connect(self.add_sample_clicked)
        self.checkBox_baseImage.toggled.connect(self.base_image_toggled)
        self.checkBox_overlayPrediction.toggled.connect(self.overlay_toggled)
        self.checkBox_labelOnly.toggled.connect(self.label_only_toggled)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        self.checkBox_swipeCompare.toggled.connect(self._on_swipe_toggled)
        self.slider_swipe.valueChanged.connect(self._on_swipe_position_changed)
    
    def _on_opacity_changed(self, value: int):
        self.label_opacityValue.setText(f"{value}%")
        self.opacity_changed.emit(value)
    
    def _on_swipe_toggled(self, checked: bool):
        self.slider_swipe.setEnabled(checked)
        self.swipe_toggled.emit(checked)
    
    def _on_swipe_position_changed(self, value: int):
        self.label_swipeValue.setText(f"{value}%")
        self.swipe_position_changed.emit(value)


class GISLayerControlSidebar(QWidget):
    """
    GIS 图层控制侧边栏 (Inference Mode)
    类似 GIS 软件的 TOC (Table of Contents) 风格
    全高度图层树，支持拖拽排序、可见性切换、透明度调节
    """
    
    # 信号
    layer_visibility_changed = Signal(str, bool)  # layer_name, visible
    layer_opacity_changed = Signal(str, float)    # layer_name, opacity
    layer_order_changed = Signal(list)            # new_order
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas = None  # GISCanvasWidget 引用
        self._init_ui()
        self._connect_signals()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题栏 - 使用系统主题色
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        
        title_label = QLabel("图层 (Layers)")
        title_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # 添加图层按钮 (使用 QToolButton 支持菜单)
        self.btn_add_layer = QToolButton()
        self.btn_add_layer.setText("+")
        self.btn_add_layer.setFixedSize(24, 24)
        self.btn_add_layer.setToolTip("添加图层")
        header_layout.addWidget(self.btn_add_layer)
        
        # 初始化默认菜单
        self._setup_default_menu()
        
        layout.addWidget(header)
        
        # 图层树 - 不设置样式，使用系统主题
        self.layer_tree = QTreeWidget()
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.layer_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.layer_tree)
        
        # 初始化默认图层
        self._init_default_layers()
    
    def _setup_default_menu(self):
        """设置默认的添加图层菜单"""
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QMessageBox
        
        menu = QMenu(self.btn_add_layer)
        
        # 设置基础图像
        action_base = QAction("📂 加载底图 (Set Base Image)...", menu)
        action_base.triggered.connect(self._on_set_base_image)
        menu.addAction(action_base)
        
        menu.addSeparator()
        
        # 添加叠加栅格图层
        action_overlay = QAction("➕ 添加叠加层 (Add Overlay Raster)...", menu)
        action_overlay.triggered.connect(self._on_add_overlay)
        menu.addAction(action_overlay)
        
        # 添加矢量图层（占位）
        action_vector = QAction("🖍️ 添加矢量 (Add Vector Layer)...", menu)
        action_vector.setEnabled(False)
        action_vector.setToolTip("矢量图层功能开发中...")
        menu.addAction(action_vector)
        
        self.btn_add_layer.setMenu(menu)
        self.btn_add_layer.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # 隐藏下拉箭头
        self.btn_add_layer.setStyleSheet("QToolButton::menu-indicator { image: none; }")
    
    def _on_set_base_image(self):
        """设置基础图像"""
        if self._canvas:
            self._canvas.on_set_base_image()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "提示", 
                "请先切换到推理可视化模式，画布组件将自动加载。"
            )
    
    def _on_add_overlay(self):
        """添加叠加图层"""
        if self._canvas:
            self._canvas.on_add_overlay()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "提示",
                "请先切换到推理可视化模式，画布组件将自动加载。"
            )
    
    def _connect_signals(self):
        """连接内部信号"""
        self.layer_tree.itemChanged.connect(self._on_item_changed)
    
    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """图层项变化时的处理"""
        if column == 0:
            layer_name = item.text(0)
            visible = item.checkState(0) == Qt.CheckState.Checked
            self.layer_visibility_changed.emit(layer_name, visible)
    
    def set_canvas(self, canvas: 'GISCanvasWidget') -> None:
        """
        设置关联的 GISCanvasWidget
        
        Args:
            canvas: GISCanvasWidget 实例
        """
        self._canvas = canvas
        # 设置添加按钮的菜单
        canvas.setup_add_menu(self.btn_add_layer)
        # 连接信号
        canvas.layer_added.connect(self._on_canvas_layer_added)
        canvas.layer_removed.connect(self._on_canvas_layer_removed)
        canvas.base_image_set.connect(self._on_base_image_set)
    
    def _on_canvas_layer_added(self, layer_name: str):
        """画布添加图层时更新 TOC"""
        # 检查是否已存在
        for i in range(self.layer_tree.topLevelItemCount()):
            if self.layer_tree.topLevelItem(i).text(0) == layer_name:
                return
        
        # 添加新图层项
        item = QTreeWidgetItem([layer_name])
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "overlay", "opacity": 0.5})
        self.layer_tree.insertTopLevelItem(0, item)
    
    def _on_canvas_layer_removed(self, layer_name: str):
        """画布移除图层时更新 TOC"""
        for i in range(self.layer_tree.topLevelItemCount()):
            item = self.layer_tree.topLevelItem(i)
            if item.text(0) == layer_name:
                self.layer_tree.takeTopLevelItem(i)
                break
    
    def _on_base_image_set(self, path: str):
        """设置基础图像时清空并重建 TOC"""
        self.layer_tree.clear()
        # 添加基础图像项
        base_item = QTreeWidgetItem(["🗺️ Base Image"])
        base_item.setCheckState(0, Qt.CheckState.Checked)
        base_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "base", "opacity": 1.0})
        self.layer_tree.addTopLevelItem(base_item)
    
    def _init_default_layers(self):
        """初始化默认图层结构"""
        # 预测结果图层
        pred_item = QTreeWidgetItem(["🎯 预测结果 (Prediction)"])
        pred_item.setCheckState(0, Qt.CheckState.Checked)
        pred_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "prediction", "opacity": 0.7})
        self.layer_tree.addTopLevelItem(pred_item)
        
        # GT 标签图层
        gt_item = QTreeWidgetItem(["🏷️ 真值标签 (Ground Truth)"])
        gt_item.setCheckState(0, Qt.CheckState.Unchecked)
        gt_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "gt", "opacity": 0.7})
        self.layer_tree.addTopLevelItem(gt_item)
        
        # 底图图层
        base_item = QTreeWidgetItem(["🗺️ 底图 (Base Image)"])
        base_item.setCheckState(0, Qt.CheckState.Checked)
        base_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "base", "opacity": 1.0})
        self.layer_tree.addTopLevelItem(base_item)
    
    def add_layer(self, name: str, layer_type: str, visible: bool = True, opacity: float = 1.0):
        """添加图层"""
        item = QTreeWidgetItem([name])
        item.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": layer_type, "opacity": opacity})
        self.layer_tree.insertTopLevelItem(0, item)
    
    def clear_layers(self):
        """清空所有图层"""
        self.layer_tree.clear()
        self._init_default_layers()


class TaskConfigSidebar(QWidget):
    """
    任务配置侧边栏 (Task Config Mode)
    显示当前任务的快速配置选项
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 标题
        title = QLabel("快速配置")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # 分隔线 - 使用系统主题
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 占位信息
        info = QLabel("选择右侧任务类型后\n此处显示快速配置选项")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        
        layout.addStretch()
