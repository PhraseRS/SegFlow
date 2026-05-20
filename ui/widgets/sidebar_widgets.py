"""
侧边栏组件模块
包含不同模式下的侧边栏组件
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QTreeWidget, QTreeWidgetItem,
    QPushButton, QCheckBox, QHBoxLayout, QLabel, QSlider, QFrame,
    QSizePolicy, QToolButton, QComboBox, QSpinBox
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
    band_mapping_changed = Signal(list)  # D-01: [R_band, G_band, B_band]
    
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
        self.pushButton_addSample = QPushButton("📂 加载数据集")
        self.pushButton_addSample.setToolTip("选择 VOC 格式数据集根目录（需包含 JPEGImages、SegmentationClass、ImageSets 目录）")
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

        # ========== D-01: 波段映射控件 ==========
        self.frame_bandMapping = QFrame()
        self.frame_bandMapping.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_bandMapping.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 3px; padding: 2px; }")
        band_layout = QVBoxLayout(self.frame_bandMapping)
        band_layout.setContentsMargins(4, 4, 4, 4)
        band_layout.setSpacing(2)

        self.label_bandInfo = QLabel("波段: -")
        self.label_bandInfo.setStyleSheet("font-size: 10px; color: gray;")
        band_layout.addWidget(self.label_bandInfo)

        # 预设下拉（去掉"预设:"标签，节省空间）
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(4)
        self.combo_bandPreset = QComboBox()
        self.combo_bandPreset.addItems(["RGB (1,2,3)", "NIR假彩色 (4,3,2)", "SWIR (5,4,3)", "自定义"])
        self.combo_bandPreset.setToolTip("波段映射预设")
        self.combo_bandPreset.setStyleSheet("font-size: 10px;")
        preset_layout.addWidget(self.combo_bandPreset)
        band_layout.addLayout(preset_layout)

        # R/G/B 通道选择
        rgb_layout = QHBoxLayout()
        rgb_layout.setSpacing(4)
        for label_text, attr_name in [("R:", "spin_bandR"), ("G:", "spin_bandG"), ("B:", "spin_bandB")]:
            rgb_layout.addWidget(QLabel(label_text))
            spin = QSpinBox()
            spin.setRange(1, 99)
            spin.setStyleSheet("font-size: 10px;")
            spin.setFixedWidth(50)
            spin.setToolTip(f"{label_text[0]} 通道对应的波段序号")
            setattr(self, attr_name, spin)
            rgb_layout.addWidget(spin)
        self.spin_bandR.setValue(1)
        self.spin_bandG.setValue(2)
        self.spin_bandB.setValue(3)
        band_layout.addLayout(rgb_layout)

        layerControl_layout.addWidget(self.frame_bandMapping)
        # 默认隐藏（当图像波段 ≤ 3 时不显示）
        self.frame_bandMapping.setVisible(False)

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
        # D-01: 波段映射
        self.combo_bandPreset.currentIndexChanged.connect(self._on_band_preset_changed)
        self.spin_bandR.valueChanged.connect(self._on_band_spin_changed)
        self.spin_bandG.valueChanged.connect(self._on_band_spin_changed)
        self.spin_bandB.valueChanged.connect(self._on_band_spin_changed)

    def _on_opacity_changed(self, value: int):
        self.label_opacityValue.setText(f"{value}%")
        self.opacity_changed.emit(value)

    def _on_swipe_toggled(self, checked: bool):
        self.slider_swipe.setEnabled(checked)
        self.swipe_toggled.emit(checked)

    def _on_swipe_position_changed(self, value: int):
        self.label_swipeValue.setText(f"{value}%")
        self.swipe_position_changed.emit(value)

    def _on_band_preset_changed(self, index: int):
        """波段预设切换"""
        presets = [(1, 2, 3), (4, 3, 2), (5, 4, 3)]
        if index < len(presets):
            r, g, b = presets[index]
            self.spin_bandR.blockSignals(True)
            self.spin_bandG.blockSignals(True)
            self.spin_bandB.blockSignals(True)
            self.spin_bandR.setValue(r)
            self.spin_bandG.setValue(g)
            self.spin_bandB.setValue(b)
            self.spin_bandR.blockSignals(False)
            self.spin_bandG.blockSignals(False)
            self.spin_bandB.blockSignals(False)
            self.band_mapping_changed.emit([r, g, b])

    def _on_band_spin_changed(self):
        """自定义波段值改变"""
        self.combo_bandPreset.blockSignals(True)
        self.combo_bandPreset.setCurrentIndex(3)  # "自定义"
        self.combo_bandPreset.blockSignals(False)
        self.band_mapping_changed.emit([self.spin_bandR.value(), self.spin_bandG.value(), self.spin_bandB.value()])

    def update_band_info(self, band_count: int):
        """D-01: 更新波段信息显示，当波段 > 3 时显示波段映射控件"""
        if band_count <= 3:
            self.frame_bandMapping.setVisible(False)
            self.label_bandInfo.setText(f"波段: {band_count} (RGB)")
        else:
            self.frame_bandMapping.setVisible(True)
            r, g, b = self.spin_bandR.value(), self.spin_bandG.value(), self.spin_bandB.value()
            self.label_bandInfo.setText(f"波段: {band_count} (当前显示: R={r}, G={g}, B={b})")


class GISLayerControlSidebar(QWidget):
    """
    GIS 图层控制侧边栏 (Inference Mode)
    类似 GIS 软件的 TOC (Table of Contents) 风格
    集成 LayerManager 实现基于模板的图层组初始化
    """
    
    # 信号
    layer_visibility_changed = Signal(str, bool)  # layer_name, visible
    layer_opacity_changed = Signal(str, float)    # layer_name, opacity
    layer_order_changed = Signal(list)            # new_order
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas = None  # GISCanvasWidget 引用
        self._layer_manager = None  # LayerManager 引用
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

        # 图层树 - 单列分组样式 (类似 QGIS)
        self.layer_tree = QTreeWidget()
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setColumnCount(1)
        self.layer_tree.setIndentation(20)
        self.layer_tree.setAnimated(True)
        self.layer_tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.layer_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.layer_tree)

        # Phase 4: 可视化设置控件（从推理面板迁移到此处）
        from ui.widgets.visualization_settings_widget import VisualizationSettingsWidget
        self.visualization_settings = VisualizationSettingsWidget()
        self.visualization_settings.setVisible(False)
        layout.addWidget(self.visualization_settings)

        # 初始提示
        self._show_empty_hint()
    
    def _show_empty_hint(self):
        """显示空状态提示"""
        hint_item = QTreeWidgetItem(self.layer_tree)
        hint_item.setText(0, "💡 点击 + 加载底图开始")
        hint_item.setForeground(0, QColor(128, 128, 128))
        hint_item.setFlags(Qt.ItemFlag.NoItemFlags)  # 禁用交互
    
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
        设置关联的 GISCanvasWidget 并初始化 LayerManager
        
        Args:
            canvas: GISCanvasWidget 实例
        """
        self._canvas = canvas
        
        # 使用新的 LayerManager 系统
        self._layer_manager = canvas.setup_layer_manager(self.layer_tree)
        
        # 连接 LayerManager 信号
        self._layer_manager.task_initialized.connect(self._on_task_initialized)
        self._layer_manager.slot_filled.connect(self._on_slot_filled)
        self._layer_manager.slot_cleared.connect(self._on_slot_cleared)
        
        # 设置添加按钮的菜单 (使用 canvas 的菜单)
        canvas.setup_add_menu(self.btn_add_layer)
        
        # 连接 canvas 信号
        canvas.layer_added.connect(self._on_canvas_layer_added)
        canvas.layer_removed.connect(self._on_canvas_layer_removed)
        
        print("✅ GISLayerControlSidebar: LayerManager 已初始化")
    
    def get_layer_manager(self):
        """获取 LayerManager 实例"""
        return self._layer_manager
    
    def _on_task_initialized(self, base_path: str):
        """任务组初始化完成"""
        print(f"📋 任务组已创建: {base_path}")
        # 展开所有项
        self.layer_tree.expandAll()
    
    def _on_slot_filled(self, slot_name: str, data_path: str):
        """槽位被填充"""
        from pathlib import Path
        print(f"📌 槽位已填充: {slot_name} <- {Path(data_path).name}")
    
    def _on_slot_cleared(self, slot_name: str):
        """槽位被清空"""
        print(f"🗑️ 槽位已清空: {slot_name}")
    
    def _on_canvas_layer_added(self, layer_name: str):
        """画布添加图层时 (兼容旧模式)"""
        # LayerManager 模式下由 LayerManager 管理
        pass
    
    def _on_canvas_layer_removed(self, layer_name: str):
        """画布移除图层时 (兼容旧模式)"""
        pass
    
    def add_layer(self, name: str, layer_type: str, visible: bool = True, opacity: float = 1.0):
        """添加图层 (兼容旧接口)"""
        item = QTreeWidgetItem([name])
        item.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": layer_type, "opacity": opacity})
        self.layer_tree.insertTopLevelItem(0, item)
    
    def clear_layers(self):
        """清空所有图层"""
        self.layer_tree.clear()
        self._show_empty_hint()



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
