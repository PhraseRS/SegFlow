"""
数据源管理树形控件示例
展示如何初始化和操作 QTreeWidget 来管理 Train/Val/Test 数据集
支持点击样本显示影像和对应的label影像
"""

from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidgetItem, QFileDialog,
                                QMessageBox, QGraphicsScene, QGraphicsPixmapItem, QSplitter,
                                QGraphicsRectItem, QGraphicsLineItem, QListWidgetItem,
                                QMenu)
from PySide6.QtCore import Qt, QRectF, QSize, QThread, Signal, QObject, QTimer, Slot
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen, QBrush, QAction
from ui.main_frame_ui import Ui_MainWindow
from core.dataset_metadata import DatasetMetadataManager
from core.project_manager import ProjectManager
from core.project_state import InputState, ModelState, ProjectInfo, ProjectState
from core.thumbnail_manager import ThumbnailLazyLoader
import sys
import os


# 视图模式常量
VIEW_MODE_DETAIL = 0
VIEW_MODE_GRID = 1


class DataSourceManager:
    """数据源管理器 - 负责管理树形控件中的数据"""
    
    def __init__(self, tree_widget):
        self.tree = tree_widget
        self.train_node = None
        self.val_node = None
        self.test_node = None
        self.data_root = None  # 数据根目录
        self.images_dir = None  # 影像目录
        self.labels_dir = None  # 标签目录
        self._init_tree_structure()
    
    def _init_tree_structure(self):
        """初始化树形结构：创建三个固定的顶级节点"""
        self.tree.clear()
        
        # 创建三个顶级节点
        self.train_node = QTreeWidgetItem(self.tree)
        self.train_node.setText(0, "📂 Train Set [0 samples]")
        self.train_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "train"})
        
        self.val_node = QTreeWidgetItem(self.tree)
        self.val_node.setText(0, "📂 Val Set [0 samples]")
        self.val_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "val"})
        
        self.test_node = QTreeWidgetItem(self.tree)
        self.test_node.setText(0, "📂 Test Set [0 samples]")
        self.test_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "test"})
        
        # 默认展开所有节点
        self.tree.expandAll()
    
    def load_from_txt_files(self, data_root):
        """
        从 train.txt, val.txt, test.txt 加载样本列表（支持VOC格式）
        
        VOC格式：txt文件在 ImageSets/Segmentation/ 目录下
        其他格式：txt文件在根目录下
        
        Args:
            data_root: 数据根目录
        """
        self.data_root = data_root
        
        # Auto检测影像和标签目录
        self._detect_directories()
        
        # 清空现有数据
        self.train_node.takeChildren()
        self.val_node.takeChildren()
        self.test_node.takeChildren()
        
        # VOC格式：ImageSets/Segmentation/train.txt
        voc_txt_dir = os.path.join(data_root, 'ImageSets', 'Segmentation')
        
        # 加载各个数据集（优先VOC格式路径）
        datasets = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }
        
        # 构建txt文件路径列表
        txt_paths = {}
        for dataset_type in datasets.keys():
            # 优先检查VOC格式路径
            voc_path = os.path.join(voc_txt_dir, f'{dataset_type}.txt')
            root_path = os.path.join(data_root, f'{dataset_type}.txt')
            
            if os.path.exists(voc_path):
                txt_paths[dataset_type] = voc_path
            elif os.path.exists(root_path):
                txt_paths[dataset_type] = root_path
            else:
                txt_paths[dataset_type] = None
        
        # 转换为原有格式
        datasets = {
            'train': (txt_paths['train'], self.train_node),
            'val': (txt_paths['val'], self.val_node),
            'test': (txt_paths['test'], self.test_node)
        }
        
        for dataset_type, (txt_path, parent_node) in datasets.items():
            if txt_path and os.path.exists(txt_path):
                try:
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            sample_id = line.strip()
                            if sample_id:  # 跳过空行
                                self._add_sample_node(parent_node, sample_id, dataset_type)
                    print(f"✅ Loaded {dataset_type}: {parent_node.childCount()} samples")
                except Exception as e:
                    print(f"❌ Load {txt_path} Failed: {e}")
            else:
                print(f"⚠️  {dataset_type}.txt 不存在，跳过")
            
            # 更新计数
            self._update_count(parent_node)
        
        # 展开所有节点
        self.tree.expandAll()
    
    def _detect_directories(self):
        """Auto检测影像和标签目录（支持VOC格式）"""
        if not self.data_root:
            return
        
        # VOC格式目录命名
        image_dirs = ['JPEGImages', 'images', 'img', 'image', 'imgs', 'data']
        label_dirs = ['SegmentationClass', 'labels', 'label', 'masks', 'mask', 'annotations', 'ann']
        
        # 检测影像目录
        for dir_name in image_dirs:
            path = os.path.join(self.data_root, dir_name)
            if os.path.isdir(path):
                self.images_dir = path
                print(f"📁 检测到影像目录: {path}")
                break
        
        # 检测标签目录
        for dir_name in label_dirs:
            path = os.path.join(self.data_root, dir_name)
            if os.path.isdir(path):
                self.labels_dir = path
                print(f"📁 Detected label dir: {path}")
                break
        
        # 如果没有检测到，使用VOC默认路径
        if not self.images_dir:
            self.images_dir = os.path.join(self.data_root, 'JPEGImages')
        if not self.labels_dir:
            self.labels_dir = os.path.join(self.data_root, 'SegmentationClass')
    
    def get_sample_paths(self, sample_id, dataset_type):
        """
        获取样本的影像和标签路径（支持VOC格式）
        
        VOC格式目录结构：
        data_root/
        ├── JPEGImages/          # 所有影像（不分train/val/test子目录）
        │   ├── sample_id.jpg
        │   └── ...
        ├── SegmentationClass/   # 所有标签（不分train/val/test子目录）
        │   ├── sample_id.png
        │   └── ...
        └── ImageSets/Segmentation/
            ├── train.txt
            ├── val.txt
            └── test.txt
        
        Args:
            sample_id: 样本ID
            dataset_type: 数据集类型 ('train', 'val', 'test')
        
        Returns:
            tuple: (image_path, label_path) 或 (None, None)
        """
        if not self.data_root:
            return None, None
        
        # 支持的影像扩展名
        image_exts = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
        label_exts = ['.png', '.tif', '.tiff', '.jpg', '.jpeg', '.bmp']
        
        image_path = None
        label_path = None
        
        # VOC格式：影像和标签都在同一目录下，不分train/val/test子目录
        # 查找影像文件
        search_paths = [
            self.images_dir,  # VOC: JPEGImages/
            os.path.join(self.images_dir, dataset_type),  # 兼容其他格式
        ]
        
        for base_path in search_paths:
            if not os.path.isdir(base_path):
                continue
            for ext in image_exts:
                path = os.path.join(base_path, f"{sample_id}{ext}")
                if os.path.exists(path):
                    image_path = path
                    break
            if image_path:
                break
        
        # 查找标签文件
        search_paths = [
            self.labels_dir,  # VOC: SegmentationClass/
            os.path.join(self.labels_dir, dataset_type),  # 兼容其他格式
        ]
        
        for base_path in search_paths:
            if not os.path.isdir(base_path):
                continue
            for ext in label_exts:
                path = os.path.join(base_path, f"{sample_id}{ext}")
                if os.path.exists(path):
                    label_path = path
                    break
            if label_path:
                break
        
        return image_path, label_path
    
    def _add_sample_node(self, parent_node, sample_id, dataset_type):
        """添加样本子节点"""
        child = QTreeWidgetItem(parent_node)
        child.setText(0, sample_id)
        # 存储节点信息：类型为叶子节点，包含样本ID和所属数据集
        child.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "leaf",
            "sample_id": sample_id,
            "dataset": dataset_type
        })
    
    def add_sample(self, dataset_type, sample_id):
        """
        添加样本到指定数据集
        
        Args:
            dataset_type: 'train', 'val', 或 'test'
            sample_id: 样本ID，如 'image_0001'
        """
        # 选择对应的父节点
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node is None:
            print(f"Error: Unknown dataset type '{dataset_type}'")
            return
        
        # 创建子节点
        self._add_sample_node(parent_node, sample_id, dataset_type)
        
        # 更新父节点的样本计数
        self._update_count(parent_node)
    
    def add_samples_batch(self, dataset_type, sample_ids):
        """Batch Add Samples"""
        for sample_id in sample_ids:
            self.add_sample(dataset_type, sample_id)
    
    def remove_selected_sample(self):
        """删除当前选中的样本（不能删除顶级节点）"""
        current_item = self.tree.currentItem()
        if current_item is None:
            return
        
        # 检查是No是顶级节点
        parent = current_item.parent()
        if parent is None:
            print("Cannot delete top-level nodes (Train/Val/Test)")
            return
        
        # 删除子节点
        parent.removeChild(current_item)
        self._update_count(parent)
    
    def clear_dataset(self, dataset_type):
        """清空指定数据集的所有样本"""
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node:
            parent_node.takeChildren()  # 移除所有子节点
            self._update_count(parent_node)
    
    def get_samples(self, dataset_type):
        """获取指定数据集的所有样本ID"""
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node is None:
            return []
        
        samples = []
        for i in range(parent_node.childCount()):
            child = parent_node.child(i)
            node_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node_data, dict):
                sample_id = node_data.get('sample_id', '')
            else:
                sample_id = node_data
            samples.append(sample_id)
        
        return samples
    
    def get_all_samples(self):
        """获取所有数据集的样本"""
        return {
            'train': self.get_samples('train'),
            'val': self.get_samples('val'),
            'test': self.get_samples('test')
        }
    
    def _update_count(self, parent_node):
        """更新父节点显示的样本数量"""
        count = parent_node.childCount()
        node_data = parent_node.data(0, Qt.ItemDataRole.UserRole)
        
        if isinstance(node_data, dict):
            dataset_type = node_data.get('dataset', '')
        else:
            dataset_type = node_data
        
        # 更新显示文本
        labels = {
            'train': f"📂 Train Set [{count} samples]",
            'val': f"📂 Val Set [{count} samples]",
            'test': f"📂 Test Set [{count} samples]"
        }
        
        parent_node.setText(0, labels.get(dataset_type, f"Unknown [{count} samples]"))
    
    def is_parent_node(self, item):
        """判断是No为父节点"""
        if item is None:
            return False
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return node_data.get('type') == 'parent'
        return item.parent() is None
    
    def is_leaf_node(self, item):
        """判断是No为叶子节点（样本节点）"""
        if item is None:
            return False
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return node_data.get('type') == 'leaf'
        return item.parent() is not None
    
    def get_sample_info(self, item):
        """
        获取样本节点的信息
        
        Returns:
            dict: {'sample_id': str, 'dataset': str} 或 None
        """
        if not self.is_leaf_node(item):
            return None
        
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return {
                'sample_id': node_data.get('sample_id', ''),
                'dataset': node_data.get('dataset', '')
            }
        return None


class MainWindow(QMainWindow):
    """MainWindow"""
    
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # --- 注入实时训练曲线组件 (训练指标 Tab 内部) ---
        try:
            from ui.widgets.metrics_plot_widget import MetricsPlotWidget
            self.metrics_plot = MetricsPlotWidget(self.ui.tab_metrics)
            # 移除原有的占位 Label
            self.ui.verticalLayout_metrics.removeWidget(self.ui.label_metricsPlaceholder)
            self.ui.label_metricsPlaceholder.deleteLater()
            # 加入精美的动态图表
            self.ui.verticalLayout_metrics.addWidget(self.metrics_plot)
        except Exception as e:
            print(f"MetricsPlotWidget loading failed: {e}")
            self.metrics_plot = None
            
        self._last_train_iter = 0
        
        # 当前视图模式
        self.current_view_mode = VIEW_MODE_DETAIL
        
        # 初始化数据源管理器
        self.data_manager = DataSourceManager(self.ui.treeWidget_dataSources)
        
        # 初始化元数据管理器
        self.metadata_manager = DatasetMetadataManager()

        self.project_manager = ProjectManager()
        self._current_project_path = ""
        self._current_data_root = ""
        self._setup_project_actions()
        
        # 影像查看器 (SmartCanvas 已在 UI 中创建)
        self.image_viewer = self.ui.graphicsView_canvas
        
        # 初始化缩略图懒加载管理器
        self.thumbnail_manager = ThumbnailLazyLoader(self.ui.listWidget_thumbnails, thumbnail_size=120)
        
        # 防抖定时器（用于图层设置变化时刷新）
        self._layer_refresh_timer = QTimer()
        self._layer_refresh_timer.setSingleShot(True)
        self._layer_refresh_timer.setInterval(50)  # 50ms 防抖
        self._layer_refresh_timer.timeout.connect(self._do_refresh_layer_settings)
        
        # Phase 4: 训练线程状态
        self._training_thread = None
        self._current_advisor = None  # ConfigAdvisor 实例缓存
        
        # 连接信号
        self._connect_signals()
        
        # 初始化图层控制
        self._init_layer_controls()
        
        # 初始化视图切换
        self._init_view_switcher()
        
        # Phase 5: 训练结果联动推理面板
        from PySide6.QtWidgets import QPushButton
        self.btn_send_to_inference = QPushButton("🚀 Model just trained -> Sent to Inference")
        self.btn_send_to_inference.setStyleSheet("background-color: #E8F5E9; color: #2E7D32; font-weight: bold; padding: 8px;")
        self.btn_send_to_inference.setMinimumHeight(40)
        self.btn_send_to_inference.setVisible(False)
        self.ui.verticalLayout_actions.addWidget(self.btn_send_to_inference)
        self.btn_send_to_inference.clicked.connect(self._on_send_to_inference_clicked)
        self._last_work_dir = None

    def _setup_project_actions(self):
        self.action_new_project = QAction("新建工程", self)
        self.action_save_project_as = QAction("工程另存为", self)

        self.ui.action_open.setText("Open Project")
        self.ui.action_save.setText("Save Project")
        self.ui.menu_file.insertAction(self.ui.action_open, self.action_new_project)
        self.ui.menu_file.insertAction(self.ui.action_exit, self.action_save_project_as)

        self.action_new_project.triggered.connect(self._on_new_project)
        self.ui.action_open.triggered.connect(self._on_open_project)
        self.ui.action_save.triggered.connect(self._on_save_project)
        self.action_save_project_as.triggered.connect(self._on_save_project_as)

    @Slot()
    def _on_new_project(self):
        self._current_project_path = ""
        self.statusBar().showMessage("已新建工程，当前状态可通过“Save Project”写入工程文件")

    @Slot()
    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project文件",
            "",
            "RS Seg Project (*.rsgproj);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            state = self.project_manager.load_project(path)
            warnings = self.project_manager.validate_state(state)
            self._apply_project_state(state)
            self._current_project_path = state.project_path
            self._log_project_warnings(warnings)
            self.statusBar().showMessage(f"Current Project: {os.path.basename(state.project_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Open Project失败", f"无法Open Project文件:\n{e}")

    @Slot()
    def _on_save_project(self):
        if not self._current_project_path:
            self._on_save_project_as()
            return
        self._save_project_to_path(self._current_project_path)

    @Slot()
    def _on_save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project文件",
            self._default_project_path(),
            "RS Seg Project (*.rsgproj);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        self._save_project_to_path(path)

    def _save_project_to_path(self, path: str):
        try:
            state = self._collect_project_state()
            self.project_manager.save_project(path, state)
            self._current_project_path = state.project_path
            warnings = self.project_manager.validate_state(state)
            self._log_project_warnings(warnings)
            self.statusBar().showMessage(f"Current Project: {os.path.basename(state.project_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Project失败", f"无法Save Project文件:\n{e}")

    def _collect_project_state(self) -> ProjectState:
        data_root = getattr(self.data_manager, "data_root", "") or self._current_data_root
        inference_panel = getattr(self.ui, "inference_panel", None)

        config_path = ""
        checkpoint_path = ""
        device = "Auto"
        strategy = "large_image_block"
        crop_size = 1024
        overlap_rate = 0.2

        if inference_panel is not None:
            config_path = inference_panel.lineEdit_configFile.text().strip()
            checkpoint_path = inference_panel.lineEdit_checkpointFile.text().strip()
            device = inference_panel.comboBox_device.currentText()
            crop_size = inference_panel.spinBox_cropSize.value()
            overlap_rate = inference_panel.doubleSpinBox_overlapRate.value()
            if getattr(inference_panel, "radioButton_resize", None) and inference_panel.radioButton_resize.isChecked():
                strategy = "resize"
            elif getattr(inference_panel, "radioButton_slidingWindow", None) and inference_panel.radioButton_slidingWindow.isChecked():
                strategy = "sliding_window"

        work_dir = os.path.dirname(config_path) if config_path else ""
        custom_modules = self.project_manager.infer_custom_modules(config_path, work_dir)
        if inference_panel is not None and hasattr(inference_panel, "get_custom_module_files"):
            panel_module_files = inference_panel.get_custom_module_files()
            for module_file in panel_module_files:
                name = os.path.basename(module_file)
                if name == "custom_rs_dataset.py":
                    custom_modules.custom_rs_dataset = module_file
                elif name == "custom_live_pred_hook.py":
                    custom_modules.custom_live_pred_hook = module_file
        if inference_panel is not None and hasattr(inference_panel, "get_custom_module_dirs"):
            panel_module_dirs = inference_panel.get_custom_module_dirs()
            if panel_module_dirs:
                custom_modules.module_dirs = panel_module_dirs
        return ProjectState(
            project_path=self._current_project_path,
            project=ProjectInfo(name=self._default_project_name(data_root)),
            inputs=InputState(dataset_root=data_root, sample_library=data_root),
            model=ModelState(config=config_path, checkpoint=checkpoint_path, work_dir=work_dir),
            custom_modules=custom_modules,
            inference={
                "strategy": strategy,
                "crop_size": crop_size,
                "overlap_rate": overlap_rate,
                "device": device,
            },
            task_config=self._collect_task_config_state(),
            ui={"last_tab": self.ui.tabWidget_contextControl.currentIndex()},
        )

    def _apply_project_state(self, state: ProjectState):
        data_root = state.inputs.dataset_root
        if data_root and os.path.isdir(data_root):
            self._current_data_root = data_root
            if hasattr(self.ui.inference_panel, "set_data_root"):
                self.ui.inference_panel.set_data_root(data_root)
            self.data_manager.load_from_txt_files(data_root)
            self._sync_inference_dataset_context()
            self.ui.action_detailView.setEnabled(True)
            self.ui.action_gridView.setEnabled(True)
            self.on_switch_to_detail_view()
            self.thumbnail_manager.set_cache_dir(data_root)
            self._update_dataset_overview()
            self._initialize_analysis_panel(data_root)

        inference_panel = getattr(self.ui, "inference_panel", None)
        if inference_panel is not None:
            module_files = [
                state.custom_modules.custom_rs_dataset,
                state.custom_modules.custom_live_pred_hook,
            ]
            if hasattr(inference_panel, "set_custom_module_files"):
                inference_panel.set_custom_module_files([path for path in module_files if path])
            if hasattr(inference_panel, "set_custom_module_dirs"):
                inference_panel.set_custom_module_dirs(state.custom_modules.module_dirs)
            if state.model.config:
                inference_panel.lineEdit_configFile.setText(state.model.config)
            if state.model.checkpoint:
                inference_panel.lineEdit_checkpointFile.setText(state.model.checkpoint)
            self._set_combo_text(inference_panel.comboBox_device, state.inference.get("device", ""))
            self._apply_inference_strategy(state.inference)

        self._apply_task_config_state(state.task_config)

        last_tab = state.ui.get("last_tab")
        if isinstance(last_tab, int) and 0 <= last_tab < self.ui.tabWidget_contextControl.count():
            self.ui.tabWidget_contextControl.setCurrentIndex(last_tab)

    def _collect_task_config_state(self) -> dict:
        task_config = {}
        if hasattr(self.ui, 'widget_modelSelection'):
            task_config['model_selection'] = self.ui.widget_modelSelection.get_params()
        if hasattr(self.ui, 'widget_weightSelection'):
            task_config['weight_selection'] = self.ui.widget_weightSelection.get_params()
        if hasattr(self.ui, 'widget_hyperparamTabs'):
            task_config['hyperparams'] = self.ui.widget_hyperparamTabs.get_params()
        if hasattr(self.ui, 'widget_classConfig'):
            task_config['class_config'] = self.ui.widget_classConfig.get_class_config()
        if hasattr(self.ui, 'widget_advancedConfig'):
            task_config['advanced_params'] = self.ui.widget_advancedConfig.get_params()
            task_config['advanced_overrides'] = self.ui.widget_advancedConfig.get_overrides()
        return task_config

    def _apply_task_config_state(self, task_config: dict):
        if not isinstance(task_config, dict) or not task_config:
            return

        model_selection = task_config.get('model_selection')
        if model_selection and hasattr(self.ui, 'widget_modelSelection'):
            self.ui.widget_modelSelection.set_params(model_selection)

        weight_selection = task_config.get('weight_selection')
        if weight_selection and hasattr(self.ui, 'widget_weightSelection'):
            self.ui.widget_weightSelection.set_params(weight_selection)

        hyperparams = task_config.get('hyperparams')
        if hyperparams and hasattr(self.ui, 'widget_hyperparamTabs'):
            self.ui.widget_hyperparamTabs.set_params(hyperparams)

        class_config = task_config.get('class_config')
        if class_config and hasattr(self.ui, 'widget_classConfig'):
            self.ui.widget_classConfig.set_class_config(class_config)

        advanced_params = task_config.get('advanced_params')
        if advanced_params and hasattr(self.ui, 'widget_advancedConfig'):
            self.ui.widget_advancedConfig.set_params(advanced_params)

        advanced_overrides = task_config.get('advanced_overrides')
        if hasattr(self.ui, 'widget_advancedConfig'):
            self.ui.widget_advancedConfig.set_overrides(advanced_overrides or {})

        self._update_task_config_dashboard()

    def _apply_inference_strategy(self, inference_state: dict):
        inference_panel = getattr(self.ui, "inference_panel", None)
        if inference_panel is None:
            return

        strategy = inference_state.get("strategy")
        if strategy == "resize" and getattr(inference_panel, "radioButton_resize", None):
            inference_panel.radioButton_resize.setChecked(True)
        elif strategy == "sliding_window" and getattr(inference_panel, "radioButton_slidingWindow", None):
            inference_panel.radioButton_slidingWindow.setChecked(True)
        elif getattr(inference_panel, "radioButton_largeImageBlock", None):
            inference_panel.radioButton_largeImageBlock.setChecked(True)

        crop_size = inference_state.get("crop_size")
        if isinstance(crop_size, int):
            inference_panel.spinBox_cropSize.setValue(crop_size)
        overlap_rate = inference_state.get("overlap_rate")
        if isinstance(overlap_rate, (int, float)):
            inference_panel.doubleSpinBox_overlapRate.setValue(float(overlap_rate))

    @staticmethod
    def _set_combo_text(combo, text: str):
        if not text:
            return
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _default_project_path(self) -> str:
        data_root = getattr(self.data_manager, "data_root", "") or self._current_data_root
        if data_root:
            return os.path.join(data_root, f"{self._default_project_name(data_root)}.rsgproj")
        return "untitled.rsgproj"

    @staticmethod
    def _default_project_name(data_root: str) -> str:
        if data_root:
            return os.path.basename(os.path.normpath(data_root)) or "untitled"
        return "untitled"

    def _log_project_warnings(self, warnings: list[str]):
        if not warnings:
            return
        message = "工程文件已加载/保存，但存在路径Info:\n" + "\n".join(warnings)
        self._log_to_bottom(message)
        QMessageBox.warning(self, "工程路径Info", message)
    
    def _init_view_switcher(self):
        """初始化视图切换器"""
        # 默认显示详情视图，数据集加载前禁用视图切换按钮
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_DETAIL)
        self.ui.action_detailView.setChecked(True)
        self.ui.action_gridView.setChecked(False)
        self.ui.action_detailView.setEnabled(False)
        self.ui.action_gridView.setEnabled(False)
    
    def _connect_signals(self):
        """连接所有信号"""
        # 添加样本按钮
        self.ui.pushButton_addSample.clicked.connect(self.on_add_sample)
        
        # 数据集概览 - 重新划分按钮（通过 Header action）
        self.ui.btn_resplit.clicked.connect(self.on_resplit_dataset)
        
        # 树控件的点击信号
        self.ui.treeWidget_dataSources.currentItemChanged.connect(self.on_tree_item_changed)
        self.ui.treeWidget_dataSources.itemClicked.connect(self.on_tree_item_clicked)
        
        # 树控件右键菜单 (Phase 2: 样本列表快捷交互)
        self.ui.treeWidget_dataSources.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget_dataSources.customContextMenuRequested.connect(self._show_tree_context_menu)
        
        # 图层控制
        self.ui.checkBox_baseImage.stateChanged.connect(self.on_base_image_toggled)
        self.ui.checkBox_overlayPrediction.stateChanged.connect(self.on_overlay_toggled)
        self.ui.checkBox_labelOnly.stateChanged.connect(self.on_label_only_toggled)
        self.ui.slider_opacity.valueChanged.connect(self.on_opacity_changed)
        
        # 卷帘对比
        self.ui.checkBox_swipeCompare.stateChanged.connect(self.on_swipe_toggled)
        self.ui.slider_swipe.valueChanged.connect(self.on_swipe_position_changed)
        
        # 视图控制
        self.ui.action_zoomIn.triggered.connect(self.image_viewer.zoom_in)
        self.ui.action_zoomOut.triggered.connect(self.image_viewer.zoom_out)
        self.ui.action_fitToWindow.triggered.connect(self.image_viewer.fit_to_window)
        
        # 视图切换
        self.ui.action_detailView.triggered.connect(self.on_switch_to_detail_view)
        self.ui.action_gridView.triggered.connect(self.on_switch_to_grid_view)
        
        # 网格视图双击
        self.ui.listWidget_thumbnails.itemDoubleClicked.connect(self.on_thumbnail_double_clicked)
        
        # 网格视图单击同步 (Phase 1.1: Right -> Left)
        self.ui.listWidget_thumbnails.currentItemChanged.connect(self._on_thumbnail_single_clicked)
        
        # 健康检查卡片过滤信号
        self.ui.widget_healthCheck.filterRequested.connect(self._on_health_filter_requested)
        self.ui.widget_healthCheck.clearFilterRequested.connect(self.clear_tree_filter)
        self.ui.widget_healthCheck.rescanRequested.connect(self._on_health_rescan)
        
        # 推理面板信号连接
        self.ui.inference_panel.log_message.connect(self._log_to_bottom)
        self.ui.inference_panel.model_loaded.connect(self._on_inference_model_loaded)
        self.ui.inference_panel.inference_started.connect(self._on_inference_started)
        self.ui.inference_panel.inference_finished.connect(self._on_inference_finished)
        self.ui.inference_panel.inference_error.connect(self._on_inference_error)
        # 连接预测初始化信号
        self.ui.inference_panel.prediction_initializing.connect(self._on_prediction_initializing)
        # 可视化设置信号：右侧推理面板的类别颜色配置 → GIS 画布
        self.ui.inference_panel.visualization_settings.alpha_changed.connect(
            self._on_prediction_alpha_changed
        )
        self.ui.inference_panel.visualization_settings.palette_changed.connect(
            self._on_prediction_palette_changed
        )
        self.ui.inference_panel.visualization_settings.apply_requested.connect(
            self._on_prediction_visualization_apply
        )
        
        # 双向同步：GIS 图层控制 <-> 推理面板
        # 方向 1: 左侧 GIS 底图变化 -> 右侧推理面板输入路径
        self.ui.gisCanvas.base_image_set.connect(self._sync_base_image_to_inference)
        
        # 方向 2: 右侧推理面板选择图像 -> 左侧 GIS 底图
        self.ui.inference_panel.input_path_selected.connect(self._sync_inference_to_base_image)
        
        # Phase 3.3: 推荐训练配置分发逻辑
        self.ui.widget_advisorConfig.generate_requested.connect(self._on_generate_recommend_config)
        
        # Phase 4: 训练控制按钮
        self.ui.pushButton_run.clicked.connect(self._on_start_training)
        self.ui.pushButton_stop.clicked.connect(self._on_stop_training)
        self.ui.pushButton_stop.setEnabled(False)
        self.ui.pushButton_export.clicked.connect(self._on_export_config)

        # 联动：spin_num_classes ↔ ClassConfigWidget 行数同步
        self.ui.widget_hyperparamTabs.spin_num_classes.valueChanged.connect(
            self.ui.widget_classConfig.set_num_classes
        )
        self.ui.widget_classConfig.config_changed.connect(self._on_config_params_changed)
        
        # 联动：当 ModelSelection 的 Backbone 改变时，通知 WeightSelection 更新预训练模型下拉列表
        self.ui.widget_modelSelection.combo_backbone.currentTextChanged.connect(
            self.ui.widget_weightSelection.update_backbone
        )
        # 初始化调用一次以填充默认的预训练列表
        self.ui.widget_weightSelection.update_backbone(self.ui.widget_modelSelection.combo_backbone.currentText())
        # 联动：框架切换时通知 EnvConfigWidget 更新探针包列表
        self.ui.widget_modelSelection.framework_changed.connect(
            self.ui.widget_envConfig.set_framework
        )
        # 初始化：用当前框架的显示名称和包列表初始化 EnvConfigWidget
        from core.framework_registry import get_required_packages
        initial_framework = self.ui.widget_modelSelection.combo_framework.currentText()
        initial_packages = get_required_packages(initial_framework)
        self.ui.widget_envConfig.set_framework(initial_framework, initial_packages)
        
        # ========== 核心：主 Tab 与侧边栏联动 ==========
        # 右侧 Tab 切换时，Auto切换左侧侧边栏
        self.ui.tabWidget_contextControl.currentChanged.connect(self._on_main_tab_changed)

        # ========== 任务配置 Dashboard: 参数实时刷新 ==========
        # 当超参数面板或模型选择面板中任何参数改变时，实时更新蓝图
        self.ui.widget_hyperparamTabs.config_changed.connect(self._on_config_params_changed)
        self.ui.widget_modelSelection.config_changed.connect(self._on_config_params_changed)

        # ========== P1-6: Class Weight联动 Tab2 ==========
        self.ui.widget_classDistribution.weightsCalculated.connect(self._on_weights_calculated)

        # ========== D-01: 波段映射联动画布 ==========
        self.ui.sidebar_sampleManagement.band_mapping_changed.connect(self.image_viewer.set_band_mapping)

    def _on_config_params_changed(self):
        """当任何训练参数改变时，如果任务配置面板当前可见，则刷新蓝图"""
        if self.ui.tabWidget_contextControl.currentIndex() == 1:
            self._update_task_config_dashboard()


    def _init_layer_controls(self):
        """初始化图层控制"""
        # 设置初始透明度显示
        self.ui.label_opacityValue.setText(f"{self.ui.slider_opacity.value()}%")
        # 设置初始卷帘位置显示
        self.ui.label_swipeValue.setText(f"{self.ui.slider_swipe.value()}%")
    
    def on_add_sample(self):
        """添加样本按钮点击事件 - 从VOC格式数据集加载"""
        # 打开文件夹选择对话框
        data_root = QFileDialog.getExistingDirectory(
            self,
            "Select VOC Dataset Root Dir",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not data_root:
            return
        
        # 验证VOC格式结构
        is_valid, error_msg = self._validate_voc_structure(data_root)
        
        if not is_valid:
            QMessageBox.critical(
                self,
                "目录结构Error",
                f"Selected directory is not a valid VOC dataset.\n\n{error_msg}\n\n"
                f"VOC格式要求的目录结构：\n"
                f"├── JPEGImages/          (影像目录)\n"
                f"├── SegmentationClass/   (标签目录)\n"
                f"└── ImageSets/\n"
                f"    └── Segmentation/\n"
                f"        ├── train.txt\n"
                f"        ├── val.txt\n"
                f"        └── test.txt (可选)\n\n"
                f"💡 Info：如果您的数据不是 VOC 格式，请先将其转换为以上结构再加载。\n"
                f"详细说明请参考项目文档。"
            )
            return
        
        # 保存数据根目录
        self._current_data_root = data_root

        # BUG-INFER-02: keep the inference panel in sync with the dataset
        # loaded in Data Insight, so Tab3 can scan trained models immediately.
        if (
            hasattr(self, 'ui')
            and hasattr(self.ui, 'inference_panel')
            and hasattr(self.ui.inference_panel, 'set_data_root')
        ):
            self.ui.inference_panel.set_data_root(data_root)
        
        # 加载数据
        self.data_manager.load_from_txt_files(data_root)
        self._sync_inference_dataset_context()
        self.statusBar().showMessage(f"From {data_root} Load VOC Dataset")

        # 数据集加载后激活视图切换按钮，默认切换到详细视图
        self.ui.action_detailView.setEnabled(True)
        self.ui.action_gridView.setEnabled(True)
        self.on_switch_to_detail_view()
        
        # Phase 1.4: 设置缩略图磁盘缓存目录
        self.thumbnail_manager.set_cache_dir(data_root)
        
        # 更新数据集概览（基本统计）
        self._update_dataset_overview()
        
        # 使用 AnalysisPanel 智能启动统计流程
        self._initialize_analysis_panel(data_root)
    
    def _initialize_analysis_panel(self, data_root):
        """使用 AnalysisPanel 智能启动统计流程"""
        # 收集样本信息
        samples_info = []
        for dataset_type in ['train', 'val', 'test']:
            for sample_id in self.data_manager.get_samples(dataset_type):
                samples_info.append((sample_id, dataset_type))

        # P1-8: 防止信号重复连接，先断开再连接
        try:
            self.ui.analysis_panel.analysis_started.disconnect(self._on_analysis_started)
            self.ui.analysis_panel.analysis_finished.disconnect(self._on_analysis_finished)
            self.ui.analysis_panel.analysis_error.disconnect(self._on_analysis_error)
        except RuntimeError:
            pass
        self.ui.analysis_panel.analysis_started.connect(self._on_analysis_started)
        self.ui.analysis_panel.analysis_finished.connect(self._on_analysis_finished)
        self.ui.analysis_panel.analysis_error.connect(self._on_analysis_error)

        # 启动智能分析流程
        images_dir = self.data_manager.images_dir
        labels_dir = self.data_manager.labels_dir
        self.ui.analysis_panel.initialize_statistics_flow(
            data_root,
            samples_info,
            images_dir,
            labels_dir
        )
    
    def _on_analysis_started(self):
        """分析开始回调"""
        self.statusBar().showMessage("Analyzing dataset...")
    
    def _on_analysis_finished(self):
        """分析完成回调"""
        self.statusBar().showMessage("数据集分析完成")
        self._on_metadata_ready()
    
    def _on_analysis_error(self, error_msg):
        """分析Error回调"""
        self.statusBar().showMessage(f"分析Error: {error_msg}")
        print(f"⚠️ 分析Error: {error_msg}")

    def _on_weights_calculated(self, weights):
        """P1-6: Class Weight计算完成回调，联动到 Tab2 任务配置"""
        weights_str = ", ".join(f"{w:.2f}" for w in weights)
        msg = f"Calculated class weights (Median Frequency Balancing):\n[{weights_str}]\n\nApply to task config?"
        reply = QMessageBox.question(self, "Class Weight", msg,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.ui.widget_hyperparamTabs.set_class_weights(weights)
            self._log_to_bottom("✅ Class weights applied to task config")

    def _load_or_calculate_metadata(self, data_root):
        """加载缓存的元数据，或启动后台进程计算（保留用于兼容）"""
        # 初始化数据库
        self.metadata_manager.init_database(data_root)
        
        # 收集样本信息
        samples_info = []
        for dataset_type in ['train', 'val', 'test']:
            for sample_id in self.data_manager.get_samples(dataset_type):
                samples_info.append((sample_id, dataset_type))
        
        # 连接信号
        self.metadata_manager.signals.progress.connect(self._on_metadata_progress)
        self.metadata_manager.signals.finished.connect(self._on_metadata_finished)
        self.metadata_manager.signals.error.connect(self._on_metadata_error)
        
        # 检查缓存是No有效
        if self.metadata_manager.is_cache_valid(samples_info):
            print("✅ Using cached metadata")
            self.statusBar().showMessage("Metadata cache loaded")
            self._on_metadata_ready()
            return
        
        # 缓存无效，启动后台进程计算
        print("🔄 启动后台进程计算元数据...")
        self.statusBar().showMessage("Calculating dataset metadata (background)...")
        
        labels_dir = self.data_manager.labels_dir
        self.metadata_manager.start_calculation(samples_info, labels_dir)
    
    def _on_metadata_progress(self, current, total, sample_id):
        """元数据计算进度回调（已在后端降频，约每50-100个样本触发一次）"""
        self.statusBar().showMessage(f"Analyzing samples... {current}/{total} ({sample_id})")
        # 更新统计面板（从数据库读取，毫秒级）
        self._on_metadata_ready()
    
    def _on_metadata_finished(self):
        """元数据计算完成回调"""
        self.statusBar().showMessage("数据集分析完成")
        self._on_metadata_ready()
    
    def _on_metadata_error(self, error_msg):
        """元数据计算Error回调"""
        print(f"⚠️ 元数据计算Error: {error_msg}")
    
    def _on_metadata_ready(self):
        """元数据准备就绪，更新UI（从数据库读取）- UI 层分流逻辑"""
        # 优先从 AnalysisPanel 获取统计数据
        stats = self.ui.analysis_panel.get_aggregated_stats()
        if not stats:
            # 回退到直接从 metadata_manager 获取
            stats = self.metadata_manager.get_aggregated_stats()
        
        if stats:
            # 1. 更新类别分布卡片（传递 image_counts）
            self._update_class_distribution(
                stats.get('class_distribution', {}),
                stats.get('image_counts', {})
            )
            
            # 2. 更新覆盖率分析卡片
            self._update_coverage_analysis()
            
            # 3. 更新健康检查卡片
            self._update_health_check()
            
            # Phase 3.3: 启用推荐配置按钮 (该按钮已重构至 AdvisorConfigWidget)
            if hasattr(self.ui, 'pushButton_applyRecommend'):
                self.ui.pushButton_applyRecommend.setEnabled(True)
    
    def _update_class_distribution(self, class_distribution, image_counts=None):
        """更新类别分布面板
        
        Args:
            class_distribution: 各类别像素总数 {class_id: pixel_count}
            image_counts: 各类别出现在多少张图像中 {class_id: image_count}
        """
        if not class_distribution:
            self.ui.widget_classDistribution.clear()
            return
        
        # 按类别ID排序
        sorted_classes = sorted(class_distribution.items(), 
                                key=lambda x: int(x[0]))
        
        # 准备数据格式
        class_vals = [str(k) for k, v in sorted_classes]
        pixel_counts = [int(v) for k, v in sorted_classes]
        
        # 使用真实的 image_counts（如果提供），No则默认为0
        if image_counts:
            img_counts = [int(image_counts.get(k, 0)) for k, v in sorted_classes]
        else:
            img_counts = [0] * len(class_vals)
        
        stats = {
            'class_vals': class_vals,
            'pixel_counts': pixel_counts,
            'image_counts': img_counts
        }
        
        self.ui.widget_classDistribution.set_data(stats)
    
    def _update_coverage_analysis(self):
        """更新覆盖率分析面板"""
        # 从 AnalysisPanel 的 metadata_manager 获取数据库
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            self.ui.widget_coverageAnalysis.clear()
            return
        
        image_records = database.get_image_records()
        if not image_records:
            self.ui.widget_coverageAnalysis.clear()
            return
        
        self.ui.widget_coverageAnalysis.set_data(image_records)
    
    def _update_health_check(self):
        """更新健康检查面板"""
        # 从 AnalysisPanel 的 metadata_manager 获取数据库
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            self.ui.widget_healthCheck.clear()
            return
        
        # 获取健康检查问题汇总
        health_data = database.get_health_check_issues()
        if not health_data:
            self.ui.widget_healthCheck.clear()
            return
        
        # 设置数据根目录（用于右键菜单功能）
        if hasattr(self, '_current_data_root') and self._current_data_root:
            self.ui.widget_healthCheck.set_data_root(self._current_data_root)
        
        # 设置问题数据
        issues = {
            'fatal': health_data.get('fatal', {}),
            'warning': health_data.get('warning', {})
        }
        total_samples = health_data.get('total_samples', 0)
        
        self.ui.widget_healthCheck.set_issues(issues, total_samples)
    
    def _on_generate_recommend_config(self):
        """
        Phase 3.3: 生成并分发推荐训练配置
        
        从 MetadataDatabase 构建 ConfigAdvisor，
        生成推荐摘要并显示在 Task Config 面板中，
        并将推荐的配置分发给通用详细配置与高级配置页签。
        """
        self.ui.widget_advisorConfig.show_loading()
        
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            self._log_to_bottom("⚠️ No metadata DB, please load dataset")
            self.ui.widget_advisorConfig.clear()
            return
        
        try:
            from core.config_advisor import ConfigAdvisor
            
            advisor = ConfigAdvisor.from_database(database)
            self._current_advisor = advisor
            summary = advisor.get_summary()
            
            # Phase 4: 填充 AdvisorConfigWidget
            rs_params = advisor.recommend_rs_params()
            self.ui.widget_advisorConfig.set_advisor_params(rs_params)
            
            # 高级参数推荐清查（如有）
            self.ui.widget_advancedConfig.clear_all_recommendations()
            advanced_recs = {}
            self.ui.widget_advancedConfig.set_recommendations(advanced_recs)
            
            # 分发数据增强与常规设置给 HyperparamTabsWidget
            self.ui.widget_hyperparamTabs.clear_all_recommendations()
            hyper_recs = {}
            
            if 'in_channels' in rs_params:
                hyper_recs['in_channels'] = {
                    'value': rs_params['in_channels'],
                    'reason': "根据数据集波段Auto分配"
                }

            # 推送 num_classes 到控件（直接设值，不走推荐系统）
            if 'num_classes' in rs_params and rs_params['num_classes']:
                self.ui.widget_hyperparamTabs.set_num_classes(rs_params['num_classes'])
                self._log_to_bottom(f"💡 类别数量已Auto设置为: {rs_params['num_classes']}")

            # 推送 class_names 到类别配置控件
            class_names = rs_params.get('class_names') or []
            if class_names:
                self.ui.widget_classConfig.load_from_advisor(class_names)
            
            if 'crop_size' in rs_params:
                crop = rs_params['crop_size']
                crop_val = crop[0] if isinstance(crop, (list, tuple)) else crop
                hyper_recs['crop_size'] = {
                    'value': crop_val,
                    'reason': "基于数据集最小宽度乘 0.8"
                }

            if 'class_weight' in rs_params and rs_params['class_weight']:
                hyper_recs['class_weight'] = {
                    'value': True,
                    'reason': "Class imbalance detected, recommend loss weight compensation"
                }
                
            if 'loss_config' in rs_params and rs_params['loss_config'] and 'type' in rs_params['loss_config']:
                hyper_recs['loss_type'] = {
                    'value': rs_params['loss_config']['type'],
                    'reason': rs_params['loss_config'].get('_reason', "Dynamic loss adaptation based on dataset features")
                }
            
            aug_config = advisor.recommend_augmentation()
            # 根据 aug_config 设置布尔类型的 aug_xxx
            aug_types = [aug.get('type') for aug in aug_config.get('augmentations', [])]
            if 'RandomFlip' in aug_types:
                hyper_recs['aug_random_flip'] = {'value': True, 'reason': "Add HorizontalFlip for data augmentation"}
            if 'PhotoMetricDistortion' in aug_types:
                hyper_recs['aug_photo_distortion'] = {'value': True, 'reason': "Add PhotometricDistortion for robustness"}
            if 'RandomRotate' in aug_types:
                hyper_recs['aug_random_rotate'] = {'value': True, 'reason': "Add RandomRotate for orientation variance"}
            
            self.ui.widget_hyperparamTabs.set_recommendations(hyper_recs)
            
            # 监听全局的一键应用信号
            try:
                self.ui.widget_advisorConfig.apply_all_requested.disconnect()
            except RuntimeError:
                pass  # 未连接时不抛错
            self.ui.widget_advisorConfig.apply_all_requested.connect(self._on_apply_all_recommendations)
            
            # 切换到 Task Config tab
            task_config_idx = self.ui.tabWidget_contextControl.indexOf(self.ui.tab_taskConfig)
            if task_config_idx >= 0:
                self.ui.tabWidget_contextControl.setCurrentIndex(task_config_idx)
            
            # 获取推荐的 crop_size 并应用到推理策略
            aug_config = advisor.recommend_augmentation()
            for aug in aug_config.get('augmentations', []):
                if aug.get('type') == 'RandomCrop':
                    crop_size = aug.get('crop_size', (512, 512))
                    self.ui.inference_panel.spinBox_cropSize.setValue(crop_size[0])
                    break
            
            self._log_to_bottom(f"💡 Recommended config applied")
            
        except Exception as e:
            self.ui.widget_advisorConfig.clear()
            self._log_to_bottom(f"❌ Recommended config gen failed: {e}")
            import traceback
            traceback.print_exc()

    def _on_apply_all_recommendations(self, rs_params: dict):
        """响应 AdvisorConfigWidget 中的 '一键全部应用' 按钮"""
        self.ui.widget_advancedConfig.apply_all_recommendations()
        self.ui.widget_hyperparamTabs.apply_all_recommendations()
        self._log_to_bottom("✅ Applied all recommended params")

    # ========== Phase 4: 训练控制 ==========

    def _on_start_training(self):
        """
        Phase 4: 点击「运行」按钮 → 收集参数 → 生成配置 → 启动训练线程
        """
        from PySide6.QtWidgets import QMessageBox
        
        # 检查是No已有训练在运行
        if self._training_thread is not None and self._training_thread.isRunning():
            QMessageBox.warning(self, "Training in Progress", "已有训练任务在运行，请先停止当前训练。")
            return
        
        # 检查数据集是No已加载
        if not hasattr(self, '_current_data_root') or not self._current_data_root:
            QMessageBox.warning(self, "Dataset Not Loaded", "Please load VOC dataset via 'Add Sample'.")
            return

        if hasattr(self.ui, 'widget_envConfig'):
            is_env_ready, env_message = self.ui.widget_envConfig.ensure_ready_for_training()
            if not is_env_ready:
                self.ui.tabWidget_contextControl.setCurrentWidget(self.ui.tab_taskConfig)
                QMessageBox.warning(
                    self,
                    "Env Not Ready",
                    f"Current training env validation failed:\n\n{env_message}\n\n"
                    "请先在“环境准备状态”面板中选择或校验 Python 解释器。",
                )
                return
        
        try:
            # ====== Step 1: 收集 UI 参数 ======
            model_params = self.ui.widget_modelSelection.get_params()
            weight_params = self.ui.widget_weightSelection.get_params()
            advisor_params = self.ui.widget_advisorConfig.get_params()
            hyper_params = self.ui.widget_hyperparamTabs.get_params()
            
            # 合并 model_params 和 weight_params 作为向下传递的完整模型参数
            full_model_params = {**model_params, **weight_params}
            
            # 新增：收集底层高级配置 (专家表单) 以及 JSON 覆写
            advanced_params = self.ui.widget_advancedConfig.get_params()
            json_overrides = self.ui.widget_advancedConfig.get_overrides()
            
            # 使用 ConfigAggregator 执行优先级合并
            from core.config_aggregator import ConfigAggregator
            aggregator = ConfigAggregator()
            final_ui_params = aggregator.aggregate(
                advanced_params=advanced_params,
                hyper_params=hyper_params,
                advisor_params=advisor_params,
                json_overrides=json_overrides
            )
            
            self._log_to_bottom(f"📋 Model: {model_params['backbone']} | "
                                f"优化器: {final_ui_params.get('optimizer', 'Unknown')} | "
                                f"LR: {final_ui_params.get('learning_rate', 'Unknown')} | "
                                f"MaxIters: {final_ui_params.get('max_iters', 'Unknown')}")
            
            # ====== Step 2: 组装 ui_params ======
            # 查找 base config（从 mmseg 包中查找，或使用用户指定路径）
            base_config = self._find_base_config(full_model_params)
            if not base_config:
                # Auto查找失败 → 弹出文件选择对话框让用户手动选取
                from PySide6.QtWidgets import QFileDialog
                self._log_to_bottom("⚠️ Auto-find failed, please manually select base config")
                
                # 使用上次选择的路径作为默认目录
                start_dir = getattr(self, '_last_config_dir', '')
                
                base_config, _ = QFileDialog.getOpenFileName(
                    self, 
                    f"选择 {full_model_params['backbone']} 的 MMSeg 基础配置文件",
                    start_dir,
                    "Python 配置文件 (*.py);;所有文件 (*)"
                )
                if not base_config:
                    self._log_to_bottom("❌ 用户Cancel了配置文件选择")
                    return
                
                # 缓存目录以便下次使用
                import os
                self._last_config_dir = os.path.dirname(base_config)
                self._log_to_bottom(f"📄 User selected config: {base_config}")
            
            # 将基础配置和前面合并的参数打包，准备传给 MMSegTrainer
            ui_params = {}
            ui_params.update(final_ui_params)  # 先放入所有高级配置
            ui_params['base_config'] = base_config
            ui_params['data_root'] = self._current_data_root  # 强制覆盖为真正的绝对路径

            # ====== 预训练权重路径映射（修复断链）======
            if weight_params.get('use_custom_weight') and weight_params.get('custom_weight_path'):
                ui_params['pretrained'] = weight_params['custom_weight_path']
            elif weight_params.get('use_pretrained') and weight_params.get('pretrained_model'):
                ui_params['pretrained'] = weight_params['pretrained_model']

            # ====== 类别配置（class_names + palette）======
            if hasattr(self.ui, 'widget_classConfig'):
                class_cfg = self.ui.widget_classConfig.get_class_config()
                ui_params['class_names'] = class_cfg.get('class_names', [])
                ui_params['palette'] = class_cfg.get('palette', [])
            # ====== Step 3: 生成训练配置文件 ======
            import os
            import tempfile
            
            work_dir = os.path.join(self._current_data_root, 'work_dirs',
                                     f"{model_params['backbone_key']}_{hyper_params['max_iters']}iters")
            os.makedirs(work_dir, exist_ok=True)
            
            config_save_path = os.path.join(work_dir, 'train_config.py')
            
            from core.framework_adapters.mmseg_trainer import MMSegTrainer
            
            trainer = MMSegTrainer()
            config_path = trainer.generate_config(ui_params, advisor_params, config_save_path)
            self._last_config_path = config_path  # 缓存供导出功能使用

            self._log_to_bottom(f"📄 Config file generated: {config_path}")
            self._log_to_bottom(f"📂 Work dir: {work_dir}")

            self._last_work_dir = work_dir
            self.btn_send_to_inference.setVisible(False)

            # ====== Step 4: 训练前确认弹窗 ======
            if not self._show_pretrain_confirm_dialog(ui_params, model_params, config_path):
                self._log_to_bottom("⏸ 用户Cancel了训练")
                return

            # ====== Step 5: 创建并启动训练线程 ======
            from core.training_dispatcher import TrainingThread

            # 从 EnvStateManager 获取已验证的 Python 解释器路径（解耦）
            # 回退：若 EnvStateManager 无缓存，则直接从 widget 读取
            from core.env_state_manager import EnvStateManager
            env_mgr = EnvStateManager.instance()
            if env_mgr.python_path:
                python_path = env_mgr.python_path
            elif hasattr(self.ui, 'widget_envConfig'):
                python_path = self.ui.widget_envConfig.get_selected_python_path() or None
            else:
                python_path = None

            self._training_thread = TrainingThread(
                trainer=trainer,
                config_path=config_path,
                work_dir=work_dir,
                python_path=python_path,
            )
            if python_path:
                self._log_to_bottom(f"🐍 使用解释器: {python_path}")
            
            # 连接信号
            self._training_thread.log_raw.connect(self._on_training_log_raw)
            self._training_thread.log_parsed.connect(self._on_training_log_parsed)
            self._training_thread.progress_updated.connect(self._on_training_progress)
            self._training_thread.training_finished.connect(self._on_training_finished)
            self._training_thread.training_error.connect(self._on_training_error)
            self._training_thread.live_prediction_updated.connect(self._on_live_prediction_updated)
            
            # 更新按钮状态
            self.ui.pushButton_run.setEnabled(False)
            self.ui.pushButton_stop.setEnabled(True)
            self.statusBar().showMessage("🚀 Training in progress...")
            
            # 启动前清理旧的曲线残留并Auto切换到指标 Tab
            if getattr(self, 'metrics_plot', None):
                self.metrics_plot.clear_plots()
                self.ui.tabWidget_bottom.setCurrentWidget(self.ui.tab_metrics)
            
            # 同步清理任务配置仓表板内嵌的图表
            if hasattr(self.ui, 'page_taskConfigDashboard'):
                dashboard_plot = getattr(
                    self.ui.page_taskConfigDashboard.training_view, 'metrics_plot', None
                )
                if dashboard_plot:
                    dashboard_plot.clear_plots()
                
            # 启动
            self._training_thread.start()
            self._log_to_bottom(f"🚀 Training started!")
            
            # 切换到训练视图
            if hasattr(self.ui, 'page_taskConfigDashboard'):
                self.ui.page_taskConfigDashboard.switch_to_training()
                
        except Exception as e:
            self._log_to_bottom(f"❌ 训练启动失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "训练启动失败", f"Error: {e}")
            self._reset_training_ui()
    
    def _on_stop_training(self):
        """Phase 4: 点击「停止」按钮 → 停止训练线程"""
        if self._training_thread is not None and self._training_thread.isRunning():
            self._log_to_bottom("⏹ 正在停止训练...")
            self._training_thread.stop()
            self.statusBar().showMessage("⏹ 正在停止训练...")
            self.ui.pushButton_stop.setEnabled(False)
        else:
            self._log_to_bottom("⚠️ 没有正在运行的训练任务")
    
    def _on_training_log_raw(self, line: str):
        """训练原始日志输出"""
        line = line.strip()
        if line:
            self.ui.textEdit_logs.append(line)
            scrollbar = self.ui.textEdit_logs.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _on_training_log_parsed(self, parsed: dict):
        """训练结构化日志处理"""
        log_type = parsed.get('type', '')
        
        if log_type == 'train_loss':
            iter_num = parsed.get('iter', 0)
            self._last_train_iter = iter_num  # 保存当前 iter 供 validation 使用
            max_iter = parsed.get('max_iter', 0)
            loss = parsed.get('loss', 0)
            lr = parsed.get('lr', 0)
            eta = parsed.get('eta', '')
            msg = f"📈 Iter [{iter_num}/{max_iter}]  loss: {loss:.4f}  lr: {lr:.6f}"
            if eta:
                msg += f"  ETA: {eta}"
            self.statusBar().showMessage(msg)
            
            # 更新实时曲线 (指标 Tab)
            if getattr(self, 'metrics_plot', None):
                self.metrics_plot.update_train_loss(iter_num, loss)
            # 同步更新仓表板内嵌曲线
            if hasattr(self.ui, 'page_taskConfigDashboard'):
                dashboard_plot = getattr(
                    self.ui.page_taskConfigDashboard.training_view, 'metrics_plot', None
                )
                if dashboard_plot:
                    dashboard_plot.update_train_loss(iter_num, loss)
            
        elif log_type == 'val_metric':
            miou = parsed.get('mIoU', 0)
            macc = parsed.get('mAcc', 0)
            self._log_to_bottom(f"✅ 验证结果 — mIoU: {miou:.4f}  mAcc: {macc:.4f}")
            
            # 更新实时散点/折线 (指标 Tab)
            if getattr(self, 'metrics_plot', None):
                self.metrics_plot.update_val_metric(self._last_train_iter, miou, macc)
            # 同步更新仓表板内嵌曲线
            if hasattr(self.ui, 'page_taskConfigDashboard'):
                dashboard_plot = getattr(
                    self.ui.page_taskConfigDashboard.training_view, 'metrics_plot', None
                )
                if dashboard_plot:
                    dashboard_plot.update_val_metric(self._last_train_iter, miou, macc)

    def _on_live_prediction_updated(self, parsed: dict):
        """处理实时验证集预测样本"""
        if hasattr(self.ui, 'page_taskConfigDashboard'):
            strip = getattr(self.ui.page_taskConfigDashboard.training_view, 'prediction_strip', None)
            if strip:
                strip.update_live_predictions(parsed)
    
    def _on_training_progress(self, current: int, total: int):
        """训练进度更新"""
        pct = (current / total * 100) if total > 0 else 0
        self.statusBar().showMessage(
            f"🚀 Training in Progress: {current}/{total}  ({pct:.1f}%)"
        )
    
    def _on_training_finished(self, exit_code: int):
        """训练完成回调"""
        if exit_code == 0:
            self._log_to_bottom("✅ Training successfully completed!")
            self.statusBar().showMessage("✅ 训练完成")

            if hasattr(self, '_last_work_dir') and self._last_work_dir:
                self.btn_send_to_inference.setVisible(True)
        else:
            self._log_to_bottom(f"⚠️ Training exit (exit code: {exit_code})")
            self.statusBar().showMessage(f"⚠️ Training exit (code: {exit_code})")
        self._reset_training_ui()
    
    def _on_training_error(self, error_msg: str):
        """训练Error回调"""
        self._log_to_bottom(f"❌ Training error: {error_msg}")
        self.statusBar().showMessage(f"训练Error: {error_msg[:60]}")
    
    def _reset_training_ui(self):
        """重置训练相关 UI 状态"""
        self.ui.pushButton_run.setEnabled(True)
        self.ui.pushButton_stop.setEnabled(False)

    def _show_pretrain_confirm_dialog(self, ui_params: dict, model_params: dict, config_path: str) -> bool:
        """
        训练前配置汇总确认弹窗。
        返回 True 表示用户确认开始训练，False 表示Cancel。
        """
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QPushButton, QLabel
        import subprocess as _sp

        dlg = QDialog(self)
        dlg.setWindowTitle("▶ 训练配置确认")
        dlg.setMinimumWidth(480)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        hint = QLabel("Please verify the following config before starting training:")
        hint.setStyleSheet("font-weight: bold; color: #1565C0;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(4)

        def _row(label, value):
            lbl = QLabel(str(value) if value else "—")
            lbl.setWordWrap(True)
            form.addRow(label, lbl)

        _row("Algorithm / Backbone:", f"{model_params.get('method', '—')} / {model_params.get('backbone', '—')}")
        _row("Classes:", ui_params.get('num_classes', '—'))
        _row("数据根目录:", ui_params.get('data_root', '—'))
        _row("Image / Mask Suffix:", f"{ui_params.get('img_suffix', 'Auto')} / {ui_params.get('seg_map_suffix', 'Auto')}")
        _row("Batch Size / Max Iters:", f"{ui_params.get('batch_size', '—')} / {ui_params.get('max_iters', '—')}")
        _row("Val Interval:", ui_params.get('val_interval', '—'))
        _row("LR / Optimizer:", f"{ui_params.get('lr', '—')} / {ui_params.get('optimizer', '—')}")
        _row("保存最佳模型:", "✅ Yes" if ui_params.get('save_best', True) else "No")
        _row("配置文件:", config_path)
        layout.addLayout(form)

        btn_view = QPushButton("📄 View Full Config")
        btn_view.setFlat(True)
        btn_view.setStyleSheet("color: #1565C0; text-decoration: underline;")

        def _open_config():
            try:
                if sys.platform == 'win32':
                    os.startfile(config_path)
                else:
                    _sp.Popen(['xdg-open', config_path])
            except Exception:
                pass

        btn_view.clicked.connect(_open_config)
        layout.addWidget(btn_view)

        buttons = QDialogButtonBox()
        btn_cancel = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        btn_start = buttons.addButton("▶ Start Training", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_start.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 4px 12px;")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        return dlg.exec() == QDialog.DialogCode.Accepted

    def _on_export_config(self):
        """导出当前训练配置文件到用户指定路径（UI-03）"""
        import shutil
        config_path = getattr(self, '_last_config_path', None)
        if not config_path or not os.path.isfile(config_path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "导出配置",
                "Training config not generated.\nPlease click 'Run' to generate.")
            return
        from PySide6.QtWidgets import QFileDialog
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出训练配置", config_path,
            "Python 配置文件 (*.py);;所有文件 (*)")
        if save_path:
            shutil.copy2(config_path, save_path)
            self.statusBar().showMessage(f"✅ Config exported to: {save_path}")
        
    def _on_send_to_inference_clicked(self):
        """一键打包流转至推理分析面板"""
        if not hasattr(self, '_last_work_dir') or not self._last_work_dir:
            return
            
        work_dir = self._last_work_dir
        
        if hasattr(self, '_current_data_root') and self._current_data_root:
            self.ui.inference_panel.scan_trained_models(self._current_data_root)
            
        success = self.ui.inference_panel.select_model_by_dir(work_dir)
        if success:
            index = self.ui.tabWidget_contextControl.indexOf(self.ui.tab_inferenceVis)
            if index >= 0:
                self.ui.tabWidget_contextControl.setCurrentIndex(index)
            self._log_to_bottom(f"🚀 Auto-routed to Inference panel and triggered load")
            self.btn_send_to_inference.setVisible(False)
            
            # --- 核心行动：真正触发模型在显存中的加载动作，而不仅是填上文件路径 ---
            self.ui.inference_panel.pushButton_loadModel.click()
        else:
            self._log_to_bottom("⚠️ Route failed: Could not find generated model record")
    
    def _find_base_config(self, model_params: dict) -> str:
        """
        Phase 4: 根据模型参数查找 base config 文件路径。

        多策略查找：mmseg.__file__ 上溯、glob 模糊匹配、项目本地 configs/ 等。
        支持算法+Backbone组合查找。
        """
        import os
        import glob
        from config.backbone_registry import CONFIG_MAP

        method = model_params.get('method', '')
        backbone_key = model_params.get('backbone_key', 'resnet50')


        # 优先使用算法+Backbone组合查找
        entry = CONFIG_MAP.get((method, backbone_key))

        if not entry:
            self._log_to_bottom(f"⚠️ 未定义 ({method}, {backbone_key}) 的配置映射")
            return ''

        sub_dir, file_pattern = entry
        
        # ====== 收集候选 configs 根目录 ======
        config_roots = []
        
        # 策略 1: 从 mmseg.__file__ 上溯查找
        try:
            import mmseg
            mmseg_dir = os.path.dirname(os.path.abspath(mmseg.__file__))
            config_roots.extend([
                os.path.join(mmseg_dir, '.mim', 'configs'),
                os.path.join(mmseg_dir, 'configs'),
                os.path.join(os.path.dirname(mmseg_dir), 'configs'),
            ])
            self._log_to_bottom(f"🔍 mmseg 路径: {mmseg_dir}")
        except (ImportError, Exception):
            pass
        
        # 策略 2: 从 sys.executable 推算 site-packages 并查找 egg-link
        if not config_roots:
            import sys
            
            # 收集所有可能的 site-packages 路径
            site_packages_dirs = set()
            
            # 2a: 从 sys.executable 推算（EXE模式下会失效）
            exe_dir = os.path.dirname(sys.executable)
            site_packages_dirs.add(os.path.join(exe_dir, 'Lib', 'site-packages')) 

            # =========================================================
            # [新增防坑补丁]：穿透 EXE，直接定位真实的 Conda 炼丹炉
            # =========================================================
            
            # 补丁 1：从启动脚本的系统环境变量中抓取 CONDA 路径
            conda_prefix = os.environ.get('CONDA_PREFIX')
            if conda_prefix:
                site_packages_dirs.add(os.path.join(conda_prefix, 'Lib', 'site-packages'))
                
            # 补丁 2：从软件右侧 "环境准备状态" 面板中用户选中的路径推算
            try:
                from core.env_state_manager import EnvStateManager
                env_mgr = EnvStateManager.instance()
                if env_mgr.python_path:
                    env_dir = os.path.dirname(env_mgr.python_path)
                    site_packages_dirs.add(os.path.join(env_dir, 'Lib', 'site-packages'))
            except Exception:
                pass
            # =========================================================
            # 2b: 从 site 模块获取
            try:
                import site
                for sp in site.getsitepackages():
                    site_packages_dirs.add(sp)
            except Exception:
                pass
            
            # 2c: 从 sys.path 获取
            for p in sys.path:
                if 'site-packages' in p and os.path.isdir(p):
                    site_packages_dirs.add(p)
            
            self._log_to_bottom(f"🔍 Searching site-packages: {[sp for sp in site_packages_dirs if os.path.isdir(sp)]}")
            
            for sp_dir in site_packages_dirs:
                if not os.path.isdir(sp_dir):
                    continue
                    
                # 查找 egg-link 文件
                egg_link = os.path.join(sp_dir, 'mmsegmentation.egg-link')
                if os.path.isfile(egg_link):
                    for enc in ['utf-8', 'gbk', 'latin-1']:
                        try:
                            with open(egg_link, 'r', encoding=enc) as f:
                                mmseg_root = f.readline().strip()
                            if os.path.isdir(mmseg_root):
                                configs_dir = os.path.join(mmseg_root, 'configs')
                                config_roots.append(configs_dir)
                                self._log_to_bottom(f"🔍 egg-link ({enc}): {mmseg_root}")
                                break
                        except (UnicodeDecodeError, OSError):
                            continue
                
                # 直接查找 mmseg 包目录
                mmseg_pkg = os.path.join(sp_dir, 'mmseg')
                if os.path.isdir(mmseg_pkg):
                    config_roots.extend([
                        os.path.join(mmseg_pkg, '.mim', 'configs'),
                        os.path.join(os.path.dirname(mmseg_pkg), 'configs'),
                    ])
                    self._log_to_bottom(f"🔍 site-packages mmseg: {mmseg_pkg}")
        
        # 策略 2: 项目本地 configs/
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_roots.append(os.path.join(project_root, 'configs'))
        
        # ====== 在候选目录中搜索 ======
        for config_root in config_roots:
            if not os.path.isdir(config_root):
                continue
            
            target_dir = os.path.join(config_root, sub_dir)
            if not os.path.isdir(target_dir):
                continue
            
            # glob 模糊匹配
            matches = glob.glob(os.path.join(target_dir, file_pattern))
            if matches:
                result = matches[0]
                self._log_to_bottom(f"✅ 找到配置: {result}")
                return result
        
        # ====== 策略 3: 递归 glob 搜索（更宽松） ======
        for config_root in config_roots:
            if not os.path.isdir(config_root):
                continue
            matches = glob.glob(os.path.join(config_root, '**', file_pattern), recursive=True)
            if matches:
                result = matches[0]
                self._log_to_bottom(f"✅ Found config (recursive): {result}")
                return result
        
        # 日志输出搜索过的路径，帮助调试
        self._log_to_bottom(f"❌ Not found {backbone_key} 的配置文件")
        self._log_to_bottom(f"   Search mode: {sub_dir}/{file_pattern}")
        for cr in config_roots:
            self._log_to_bottom(f"   搜索路径: {cr} (exists={os.path.isdir(cr)})")
        return ''

    def _on_health_filter_requested(self, issue_type: str):
        """
        健康检查卡片过滤请求回调
        
        交互流程：
        1. 用户点击问题行（如 "🔴 尺寸不匹配 [ 2 项 ]"）
        2. 左侧文件列表过滤显示问题文件
        3. Auto加载第一个问题文件到主视图
        
        Args:
            issue_type: 问题类型（如 'empty_mask', 'corrupt_file' 等）
        """
        print(f"🔍 健康检查过滤请求: {issue_type}")
        
        # 从数据库获取问题文件列表
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            return
        
        problem_samples = database.get_samples_by_issue(issue_type)
        if not problem_samples:
            self.statusBar().showMessage(f"未找到 {issue_type} 类型的问题文件")
            return
        
        print(f"📋 Found {len(problem_samples)} 个问题文件: {problem_samples[:5]}...")
        
        # 过滤树形控件：隐藏非问题文件，只显示问题文件
        self._filter_tree_by_samples(problem_samples, issue_type)
        
        # Auto选中并加载第一个问题文件
        if problem_samples:
            first_sample_id = problem_samples[0]
            # 查找该样本所属的数据集
            dataset_type = self._find_sample_dataset(first_sample_id)
            if dataset_type:
                # 在树形控件中选中该样本
                self._select_sample_in_tree(first_sample_id, dataset_type)
                # 加载样本可视化
                self.load_sample_visualization({
                    'sample_id': first_sample_id,
                    'dataset': dataset_type
                })
        
        self.statusBar().showMessage(f"Filtered display {len(problem_samples)} 个 {issue_type} 问题文件")

    def _on_health_rescan(self):
        """健康检查 Re-scan 回调：重新触发分析"""
        if self._current_data_root:
            self._initialize_analysis_panel(self._current_data_root)
            self.statusBar().showMessage("正在重新扫描健康检查...")
        else:
            self.statusBar().showMessage("⚠️ 请先加载数据集")

    def _filter_tree_by_samples(self, sample_ids: list, issue_type: str):
        """
        过滤树形控件，只显示指定的样本
        
        Args:
            sample_ids: 要显示的样本ID列表
            issue_type: 问题类型（用于更新父节点标题）
        """
        sample_set = set(sample_ids)
        
        # 遍历所有数据集节点
        for parent_node in [self.data_manager.train_node, 
                           self.data_manager.val_node, 
                           self.data_manager.test_node]:
            visible_count = 0
            
            # 遍历子节点
            for i in range(parent_node.childCount()):
                child = parent_node.child(i)
                node_data = child.data(0, Qt.ItemDataRole.UserRole)
                
                if isinstance(node_data, dict):
                    sample_id = node_data.get('sample_id', '')
                else:
                    sample_id = child.text(0)
                
                # 根据是No在问题列表中决定显示/隐藏
                if sample_id in sample_set:
                    child.setHidden(False)
                    visible_count += 1
                else:
                    child.setHidden(True)
            
            # 更新父节点标题显示过滤后的数量
            node_data = parent_node.data(0, Qt.ItemDataRole.UserRole)
            dataset_type = node_data.get('dataset', '') if isinstance(node_data, dict) else ''
            
            labels = {
                'train': f"📂 Train Set [Filtered: {visible_count}个]",
                'val': f"📂 Val Set [Filtered: {visible_count}个]",
                'test': f"📂 Test Set [Filtered: {visible_count}个]"
            }
            parent_node.setText(0, labels.get(dataset_type, f"Unknown [{visible_count}个]"))
            
            # 展开有问题文件的节点
            if visible_count > 0:
                parent_node.setExpanded(True)
    
    def _find_sample_dataset(self, sample_id: str) -> str:
        """
        查找样本所属的数据集类型
        
        Args:
            sample_id: 样本ID
        
        Returns:
            str: 数据集类型 ('train', 'val', 'test') 或空字符串
        """
        for dataset_type in ['train', 'val', 'test']:
            samples = self.data_manager.get_samples(dataset_type)
            if sample_id in samples:
                return dataset_type
        return ''
    
    def clear_tree_filter(self):
        """
        清除树形控件过滤，恢复显示所有样本
        """
        for parent_node in [self.data_manager.train_node, 
                           self.data_manager.val_node, 
                           self.data_manager.test_node]:
            # 显示所有子节点
            for i in range(parent_node.childCount()):
                child = parent_node.child(i)
                child.setHidden(False)
            
            # 恢复父节点标题
            self.data_manager._update_count(parent_node)
        
        self.statusBar().showMessage("已清除过滤，显示所有样本")
    
    def _update_dataset_overview(self):
        """更新数据集概览面板"""
        train_samples = self.data_manager.get_samples('train')
        val_samples = self.data_manager.get_samples('val')
        test_samples = self.data_manager.get_samples('test')
        train_count = len(train_samples)
        val_count = len(val_samples)
        test_count = len(test_samples)
        # 去重计算唯一样本总数
        unique_total = len(set(train_samples) | set(val_samples) | set(test_samples))

        self.ui.widget_datasetOverview.update_data(train_count, val_count, test_count, unique_total=unique_total)
        # 有数据时启用 Resplit 按钮
        total = train_count + val_count + test_count
        self.ui.btn_resplit.setEnabled(total > 0)
        
        # 当数据集发生变化时，如果当前处于任务配置选项卡，则主动刷新一次蓝图
        if self.ui.tabWidget_contextControl.currentIndex() == 1:
            self._update_task_config_dashboard()
    
    def _validate_voc_structure(self, data_root):
        """
        验证目录是No为有效的VOC格式结构（仅检查第一级目录）
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        errors = []
        
        # 检查第一级目录中必须存在的目录
        # 1. JPEGImages 目录
        jpeg_dir = os.path.join(data_root, 'JPEGImages')
        if not os.path.isdir(jpeg_dir):
            errors.append("Missing JPEGImages directory")
        
        # 2. SegmentationClass 目录
        seg_dir = os.path.join(data_root, 'SegmentationClass')
        if not os.path.isdir(seg_dir):
            errors.append("Missing SegmentationClass directory")
        
        # 3. ImageSets 目录
        imagesets_dir = os.path.join(data_root, 'ImageSets')
        if not os.path.isdir(imagesets_dir):
            errors.append("缺少 ImageSets 目录")
        else:
            # 检查 ImageSets/Segmentation 目录
            seg_sets_dir = os.path.join(imagesets_dir, 'Segmentation')
            if not os.path.isdir(seg_sets_dir):
                errors.append("缺少 ImageSets/Segmentation 目录")
            else:
                # 检查至少存在 train.txt 或 val.txt
                train_txt = os.path.join(seg_sets_dir, 'train.txt')
                val_txt = os.path.join(seg_sets_dir, 'val.txt')
                
                if not os.path.isfile(train_txt) and not os.path.isfile(val_txt):
                    errors.append("ImageSets/Segmentation/ 中缺少 train.txt 和 val.txt")
        
        if errors:
            return False, "\n".join(f"• {e}" for e in errors)
        
        return True, ""
    
    def on_tree_item_changed(self, current, previous):
        """树控件当前项改变事件"""
        if current is None:
            return
        
        # 判断节点类型
        if self.data_manager.is_parent_node(current):
            # 点击父节点：显示统计信息
            node_data = current.data(0, Qt.ItemDataRole.UserRole)
            dataset = node_data.get('dataset', '') if isinstance(node_data, dict) else ''
            count = current.childCount()
            self.statusBar().showMessage(f"数据集: {dataset.upper()} | Samples: {count}")
            
            # 如果在网格视图模式，过滤显示该数据集的样本
            if self.current_view_mode == VIEW_MODE_GRID:
                self._filter_grid_by_dataset(dataset)
            
        elif self.data_manager.is_leaf_node(current):
            # 点击叶子节点：加载样本可视化
            sample_info = self.data_manager.get_sample_info(current)
            if sample_info:
                if self.current_view_mode == VIEW_MODE_GRID:
                    # Phase 1.1: Grid 模式下，不切换视图，而是在网格中高亮对应缩略图
                    self._select_thumbnail_in_grid(sample_info['sample_id'], sample_info['dataset'])
                else:
                    self.load_sample_visualization(sample_info)
    
    def _filter_grid_by_dataset(self, dataset_type):
        """根据数据集类型过滤网格视图（懒加载模式）"""
        # 清空现有内容
        self.thumbnail_manager.clear()
        
        # 只获取指定数据集的样本
        if dataset_type:
            samples = self.data_manager.get_samples(dataset_type)
            
            if not samples:
                self.statusBar().showMessage(f"{dataset_type.upper()}: 无样本")
                return
            
            # 添加样本（只创建占位项）
            for sample_id in samples:
                image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset_type)
                key = f"{dataset_type}_{sample_id}"
                self.thumbnail_manager.add_sample(key, sample_id, dataset_type, image_path, label_path)
            
            self.statusBar().showMessage(f"{dataset_type.upper()}: Total {len(samples)} samples")
            
            # 触发初始加载（只加载可见区域）
            self.thumbnail_manager.trigger_initial_load()
    
    def on_tree_item_clicked(self, item, column):
        """树控件项点击事件"""
        # 这里可以添加额外的点击处理逻辑
        pass
    
    # ==================== Phase 1.1: 双向选择同步 ====================
    
    def _on_thumbnail_single_clicked(self, current, previous):
        """
        网格视图单击事件 (Phase 1.1: Right -> Left)
        当用户在右侧画廊单击某张缩略图时，Auto在左侧树形控件中展开并高亮该文件项。
        使用 blockSignals 防止无限循环触发。
        """
        if current is None:
            return
        
        sample_info = current.data(Qt.ItemDataRole.UserRole)
        if not sample_info or not isinstance(sample_info, dict):
            return
        
        sample_id = sample_info.get('sample_id', '')
        dataset_type = sample_info.get('dataset', '')
        
        if not sample_id:
            return
        
        # 使用 blockSignals 防止树形控件的 currentItemChanged 反向触发
        self.ui.treeWidget_dataSources.blockSignals(True)
        self._select_sample_in_tree(sample_id, dataset_type)
        self.ui.treeWidget_dataSources.blockSignals(False)
        
        self.statusBar().showMessage(f'已同步选中: {sample_id} ({dataset_type.upper()})')
    
    def _select_thumbnail_in_grid(self, sample_id, dataset_type):
        """
        在网格视图中高亮指定样本 (Phase 1.1: Left -> Right)
        当用户在左侧树形控件单击某个样本时，Auto滚动到对应缩略图并高亮选中。
        使用 blockSignals 防止无限循环触发。
        """
        target_key = f"{dataset_type}_{sample_id}"
        
        # 遍历 listWidget 查找匹配的项
        for i in range(self.ui.listWidget_thumbnails.count()):
            item = self.ui.listWidget_thumbnails.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(item_data, dict):
                if item_data.get('sample_id') == sample_id and item_data.get('dataset') == dataset_type:
                    # 使用 blockSignals 防止反向触发
                    self.ui.listWidget_thumbnails.blockSignals(True)
                    self.ui.listWidget_thumbnails.setCurrentItem(item)
                    self.ui.listWidget_thumbnails.scrollToItem(
                        item,
                        self.ui.listWidget_thumbnails.ScrollHint.PositionAtCenter
                    )
                    self.ui.listWidget_thumbnails.blockSignals(False)
                    break
    
    def _show_tree_context_menu(self, pos):
        """
        树控件右键菜单 (Phase 2: 样本列表快捷交互)
        
        提供：
        - 📋 Copy Filename
        - 🔗 Copy Full Path
        - 📂 在文件夹中显示 (Reveal in Explorer)
        
        引用 Skill: skills.skill_file_utils
        """
        from skills.skill_file_utils import (
            reveal_in_explorer, copy_path_to_clipboard, copy_filename_to_clipboard
        )
        
        item = self.ui.treeWidget_dataSources.itemAt(pos)
        if item is None or not self.data_manager.is_leaf_node(item):
            return
        
        sample_info = self.data_manager.get_sample_info(item)
        if not sample_info:
            return
        
        sample_id = sample_info['sample_id']
        dataset_type = sample_info['dataset']
        image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset_type)
        
        # 优先使用影像路径，没有则用标签路径
        target_path = image_path or label_path
        
        menu = QMenu(self)
        
        # 操作 1：复制文件名
        action_copy_name = QAction('📋 Copy Filename', self)
        action_copy_name.triggered.connect(
            lambda: self._do_copy_filename(sample_id, target_path)
        )
        menu.addAction(action_copy_name)
        
        # 操作 2：复制完整路径
        action_copy_path = QAction('🔗 Copy Full Path', self)
        action_copy_path.setEnabled(target_path is not None)
        action_copy_path.triggered.connect(
            lambda: self._do_copy_path(target_path)
        )
        menu.addAction(action_copy_path)
        
        menu.addSeparator()
        
        # 操作 3：在文件夹中显示
        action_reveal = QAction('📂 在文件夹中显示', self)
        action_reveal.setEnabled(target_path is not None)
        action_reveal.triggered.connect(
            lambda: self._do_reveal_in_explorer(target_path)
        )
        menu.addAction(action_reveal)
        
        menu.exec(self.ui.treeWidget_dataSources.viewport().mapToGlobal(pos))
    
    def _do_copy_filename(self, sample_id, file_path):
        """复制文件名到剪贴板"""
        from skills.skill_file_utils import copy_filename_to_clipboard
        if file_path:
            copy_filename_to_clipboard(file_path)
        else:
            # 如果没有实际文件路径，直接用 sample_id
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(sample_id)
        self.statusBar().showMessage(f'已复制文件名: {sample_id}')
    
    def _do_copy_path(self, file_path):
        """复制完整路径到剪贴板"""
        from skills.skill_file_utils import copy_path_to_clipboard
        if file_path and copy_path_to_clipboard(file_path):
            self.statusBar().showMessage(f'Copied path: {file_path}')
        else:
            self.statusBar().showMessage('⚠️ Cannot copy path')
    
    def _do_reveal_in_explorer(self, file_path):
        """在文件管理器中显示"""
        from skills.skill_file_utils import reveal_in_explorer
        if file_path and reveal_in_explorer(file_path):
            self.statusBar().showMessage(f'已在文件管理器中定位: {os.path.basename(file_path)}')
        else:
            self.statusBar().showMessage('⚠️ Cannot locate file')
    
    def load_sample_visualization(self, sample_info):
        """
        加载样本可视化
        
        Args:
            sample_info: {'sample_id': str, 'dataset': str}
        """
        sample_id = sample_info['sample_id']
        dataset = sample_info['dataset']
        
        print(f"🖼️ Load sample visualization: {sample_id} (来自 {dataset} Dataset)")
        
        # 获取影像和标签路径
        image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset)
        
        if image_path:
            # 加载影像和标签
            self.image_viewer.load_sample(image_path, label_path)

            # D-02 修复：加载后同步 UI 控件当前状态到渲染层
            self.image_viewer.set_image_visible(self.ui.checkBox_baseImage.isChecked())
            self.image_viewer.set_label_visible(self.ui.checkBox_overlayPrediction.isChecked())
            self.image_viewer.set_label_opacity(self.ui.slider_opacity.value())

            # D-01: 更新波段信息
            band_count = self.image_viewer.get_band_count()
            self.ui.sidebar_sampleManagement.update_band_info(band_count)

            # 更新状态栏
            status_msg = f"当前样本: {sample_id} | 数据集: {dataset.upper()}"
            if label_path:
                status_msg += " | Loaded Label"
            else:
                status_msg += " | No Label"
            self.statusBar().showMessage(status_msg)
        else:
            # 没有找到影像文件
            self.image_viewer.clear()
            self.statusBar().showMessage(f"⚠️ Sample not found {sample_id}'s image file")
            
            # 显示Info信息
            QMessageBox.information(
                self,
                "Info",
                f"未找到样本 '{sample_id}''s image file。\n\n"
                f"请确保数据目录结构正确：\n"
                f"- images/{dataset}/{sample_id}.tif\n"
                f"- labels/{dataset}/{sample_id}.png\n\n"
                f"或者：\n"
                f"- images/{sample_id}.tif\n"
                f"- labels/{sample_id}.png"
            )
    
    def on_base_image_toggled(self, state):
        """底图可见性切换"""
        self.image_viewer.set_image_visible(state == Qt.CheckState.Checked.value)
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def on_overlay_toggled(self, state):
        """叠加层可见性切换"""
        self.image_viewer.set_label_visible(state == Qt.CheckState.Checked.value)
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def on_label_only_toggled(self, state):
        """单独显示标签切换"""
        if state == Qt.CheckState.Checked.value:
            # 勾选Label Only：隐藏底图，显示标签，透明度设为100%
            self.ui.checkBox_baseImage.setChecked(False)
            self.ui.checkBox_overlayPrediction.setChecked(True)
            self.ui.slider_opacity.setValue(100)
        else:
            # Cancel勾选：恢复默认显示
            self.ui.checkBox_baseImage.setChecked(True)
            self.ui.slider_opacity.setValue(70)
        # 网格视图模式下刷新缩略图（由于上面的setChecked会触发各自的toggled事件，这里不需要额外刷新）
    
    def on_opacity_changed(self, value):
        """透明度滑块变化"""
        self.image_viewer.set_label_opacity(value)
        self.ui.label_opacityValue.setText(f"{value}%")
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def _schedule_layer_refresh(self):
        """调度图层刷新（防抖）"""
        self._layer_refresh_timer.start()
    
    def _do_refresh_layer_settings(self):
        """执行图层设置刷新"""
        show_image = self.ui.checkBox_baseImage.isChecked()
        show_label = self.ui.checkBox_overlayPrediction.isChecked()
        opacity = self.ui.slider_opacity.value()
        self.thumbnail_manager.set_layer_settings(show_image, show_label, opacity)
    
    def on_swipe_toggled(self, state):
        """卷帘对比模式切换"""
        enabled = state == Qt.CheckState.Checked.value
        self.ui.slider_swipe.setEnabled(enabled)
        self.image_viewer.set_swipe_enabled(enabled)
        
        if enabled:
            # 禁用其他图层控制选项
            self.ui.checkBox_baseImage.setEnabled(False)
            self.ui.checkBox_overlayPrediction.setEnabled(False)
            self.ui.checkBox_labelOnly.setEnabled(False)
            self.ui.slider_opacity.setEnabled(False)
        else:
            # 恢复其他图层控制选项
            self.ui.checkBox_baseImage.setEnabled(True)
            self.ui.checkBox_overlayPrediction.setEnabled(True)
            self.ui.checkBox_labelOnly.setEnabled(True)
            self.ui.slider_opacity.setEnabled(True)
    
    def on_swipe_position_changed(self, value):
        """卷帘位置滑块变化"""
        self.image_viewer.set_swipe_position(value)
        self.ui.label_swipeValue.setText(f"{value}%")
    
    # ==================== 主 Tab 与侧边栏联动 ====================
    
    # 视图模式常量
    VIEW_MODE_GIS = 2  # GIS 视图（推理模式）
    
    def _on_main_tab_changed(self, index: int):
        """
        主 Tab 切换时的处理槽函数
        
        Tab Index 与 Sidebar Stack Index 映射关系:
        - Tab 0 (Data Profile)    -> Sidebar 0 (SampleManagementSidebar), View 0/1 (Detail/Grid)
        - Tab 1 (Task Config)     -> Sidebar 0 (SampleManagementSidebar), View 0/1 (Detail/Grid)
        - Tab 2 (Inference)       -> Sidebar 1 (GISLayerControlSidebar), View 2 (GIS)
        
        Args:
            index: 当前激活的 Tab 索引
        """
        # 定义 Tab Index 到 Sidebar Index 的映射
        TAB_TO_SIDEBAR_MAP = {
            0: 0,  # Data Profile -> SampleManagement
            1: 0,  # Task Config  -> SampleManagement
            2: 1,  # Inference    -> GISLayerControl
        }
        
        sidebar_index = TAB_TO_SIDEBAR_MAP.get(index, 0)
        self.ui.sidebar_stack.setCurrentIndex(sidebar_index)
        
        # 切换到推理模式时，显示 GIS 视图
        if index == 2:
            self.ui.stackedWidget_views.setCurrentIndex(2)  # GIS View
        elif index == 1:
            # Task Config Mode
            self.ui.stackedWidget_views.setCurrentIndex(3)  # Task Config Dashboard
            self._update_task_config_dashboard()
        else:
            # 数据洞察模式，恢复到之前的视图模式（Detail 或 Grid）
            self.ui.stackedWidget_views.setCurrentIndex(self.current_view_mode)

        # 详细视图/网格视图按钮仅在数据洞察面板（Tab 0）且数据集已加载时启用
        dataset_loaded = hasattr(self, '_current_data_root') and bool(self._current_data_root)
        is_data_insight = (index == 0)
        self.ui.action_detailView.setEnabled(is_data_insight and dataset_loaded)
        self.ui.action_gridView.setEnabled(is_data_insight and dataset_loaded)
            
        # 根据模式更新状态栏Info
        mode_names = {
            0: "数据洞察模式",
            1: "Task Config Mode", 
            2: "推理可视化模式"
        }
        self.statusBar().showMessage(f"Switched to {mode_names.get(index, '未知模式')}")
            
    def _update_task_config_dashboard(self):
        """更新任务配置仪表盘状态"""
        if not hasattr(self.ui, 'page_taskConfigDashboard'):
            return
            
        # 如果正在训练中，切到监控视图并返回
        if self._training_thread and self._training_thread.isRunning():
            self.ui.page_taskConfigDashboard.switch_to_training()
            return
            
        # No则切换到蓝图并在上面显示参数
        self.ui.page_taskConfigDashboard.switch_to_blueprint()
        
        # 收集全部参数给 Dashboard 显示
        try:
            params = {}
            # 模型选择
            if hasattr(self.ui, 'widget_modelSelection'):
                framework = self.ui.widget_modelSelection.combo_framework.currentText()
                backbone = self.ui.widget_modelSelection.combo_backbone.currentText()
                if framework and backbone:
                    params['model'] = f"UNet/FPN | {backbone}"
                params['backbone'] = backbone

            # HyperparamTabs 全量参数
            if hasattr(self.ui, 'widget_hyperparamTabs'):
                hyper = self.ui.widget_hyperparamTabs.get_params()
                params.update(hyper)

            # 数据集信息
            if hasattr(self, '_current_data_root') and self._current_data_root:
                params['data_root'] = self._current_data_root
                train_samples = self.data_manager.get_samples('train')
                val_samples = self.data_manager.get_samples('val')
                params['dataset_samples'] = len(train_samples) + len(val_samples)
            
            self.ui.page_taskConfigDashboard.update_config_params(params)
            
            # 从数据集中随机提取最多3个样本显示预览
            import random
            train_samples = self.data_manager.get_samples('train')
            if train_samples:
                num_samples = min(3, len(train_samples))
                selected_sids = random.sample(train_samples, num_samples)
                preview_data = []
                for sid in selected_sids:
                    img_path, lbl_path = self.data_manager.get_sample_paths(sid, 'train')
                    preview_data.append({
                        'img_path': img_path,
                        'lbl_path': lbl_path,
                        'name': sid
                    })
                self.ui.page_taskConfigDashboard.blueprint_view.preview_strip.update_previews(preview_data)
                
        except Exception as e:
            print(f"Update dashboard error: {e}")
    
    def on_switch_to_detail_view(self):
        """切换到详情视图"""
        self.current_view_mode = VIEW_MODE_DETAIL
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_DETAIL)
        self.ui.action_detailView.setChecked(True)
        self.ui.action_gridView.setChecked(False)
        
        # 启用卷帘对比功能
        self.ui.checkBox_swipeCompare.setEnabled(True)
        
        # Phase 1.3: 启用 Canvas 专用工具按钮
        self.ui.action_zoomIn.setEnabled(True)
        self.ui.action_zoomOut.setEnabled(True)
        self.ui.action_fitToWindow.setEnabled(True)
        
        self.statusBar().showMessage('已切换到详情视图')
    
    def on_switch_to_grid_view(self):
        """Switch to Grid View"""
        self.current_view_mode = VIEW_MODE_GRID
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_GRID)
        self.ui.action_gridView.setChecked(True)
        self.ui.action_detailView.setChecked(False)
        
        # 禁用卷帘对比功能（网格视图下不可用）
        self.ui.checkBox_swipeCompare.setEnabled(False)
        self.ui.slider_swipe.setEnabled(False)
        
        # Phase 1.3: 禁用 Canvas 专用工具按钮（缩放等）
        self.ui.action_zoomIn.setEnabled(False)
        self.ui.action_zoomOut.setEnabled(False)
        self.ui.action_fitToWindow.setEnabled(False)
        
        # 初始化图层设置
        show_image = self.ui.checkBox_baseImage.isChecked()
        show_label = self.ui.checkBox_overlayPrediction.isChecked()
        opacity = self.ui.slider_opacity.value()
        self.thumbnail_manager.set_layer_settings(show_image, show_label, opacity)
        
        # 加载缩略图（懒加载模式）
        self._populate_grid_view()
    
    def _populate_grid_view(self):
        """填充网格视图（只创建占位项，懒加载缩略图）"""
        # 清空现有内容
        self.thumbnail_manager.clear()
        
        # 收集所有样本信息
        all_samples = self.data_manager.get_all_samples()
        total = sum(len(samples) for samples in all_samples.values())
        
        if total == 0:
            self.statusBar().showMessage("Grid View: No Samples")
            return
        
        # 添加所有样本（只创建占位项）
        for dataset_type, samples in all_samples.items():
            for sample_id in samples:
                image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset_type)
                key = f"{dataset_type}_{sample_id}"
                self.thumbnail_manager.add_sample(key, sample_id, dataset_type, image_path, label_path)
        
        self.statusBar().showMessage(f"网格视图: Total {total} samples")
        
        # 触发初始加载（只加载可见区域）
        self.thumbnail_manager.trigger_initial_load()
    
    def on_thumbnail_double_clicked(self, item):
        """缩略图双击事件 - 切换到详情视图并显示该样本"""
        sample_info = item.data(Qt.ItemDataRole.UserRole)
        if sample_info:
            # 切换到详情视图
            self.on_switch_to_detail_view()
            
            # 在树形控件中定位到该样本
            self._select_sample_in_tree(sample_info['sample_id'], sample_info['dataset'])
            
            # 加载样本
            self.load_sample_visualization(sample_info)
    
    def _select_sample_in_tree(self, sample_id, dataset_type):
        """在树形控件中选中指定样本"""
        # 获取对应的父节点
        parent_node = {
            'train': self.data_manager.train_node,
            'val': self.data_manager.val_node,
            'test': self.data_manager.test_node
        }.get(dataset_type)
        
        if not parent_node:
            return
        
        # 遍历子节点查找匹配的样本
        for i in range(parent_node.childCount()):
            child = parent_node.child(i)
            node_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node_data, dict) and node_data.get('sample_id') == sample_id:
                # 展开父节点
                parent_node.setExpanded(True)
                # 选中该节点
                self.ui.treeWidget_dataSources.setCurrentItem(child)
                # 滚动到中间位置
                self.ui.treeWidget_dataSources.scrollToItem(
                    child, 
                    self.ui.treeWidget_dataSources.ScrollHint.PositionAtCenter
                )
                break
    
    # ========================================
    # 推理面板回调方法
    # ========================================
    
    def _on_inference_model_loaded(self, model_info: dict):
        """推理模型加载完成回调"""
        self.statusBar().showMessage("推理模型已加载")
        self._log_to_bottom(f"✅ Model load complete: {model_info.get('config', 'unknown')}")
    
    def _on_inference_started(self):
        """推理开始回调"""
        self.statusBar().showMessage("正在执行推理...")

    def _on_inference_error(self, error_msg: str):
        """推理Error回调"""
        self.statusBar().showMessage(f"Inference error: {error_msg}")
        self._log_to_bottom(f"❌ Inference error: {error_msg}")
    
    def _log_to_bottom(self, message: str):
        """输出日志到底部日志面板"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        
        print(log_message)
        self.ui.textEdit_logs.append(log_message)
        
        scrollbar = self.ui.textEdit_logs.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    # ========================================
    # 双向同步槽方法
    # ========================================
    
    def _sync_base_image_to_inference(self, path: str):
        """
        同步方向 1: 左侧 GIS 底图变化 -> 右侧推理面板输入路径
        
        触发条件: 当用户在左侧 GISCanvasWidget 中成功加载底图时
        
        Args:
            path: 底图文件路径
        """
        if not path:
            return
        
        # 直接同步路径到推理面板的输入影像框
        self.ui.inference_panel.set_image_path(path)
        self._log_to_bottom(f"🔄 [Sync] GIS base map -> Inference input: {os.path.basename(path)}")
    
    def _sync_inference_to_base_image(self, path: str):
        """
        同步方向 2: 右侧推理面板选择图像 -> 左侧 GIS 底图
        
        触发条件: 当用户在右侧 InferencePanel 中选择/浏览输入图像时
        
        Args:
            path: 图像文件路径
        """
        if not path or not os.path.exists(path):
            return
        
        # 检查是No支持的图像格式
        supported_exts = {'.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp'}
        ext = os.path.splitext(path)[1].lower()
        if ext not in supported_exts:
            self._log_to_bottom(f"⚠️ 不支持同步的文件格式: {ext}")
            return
        
        # 加载到 GIS 画布，使用 suppress_signal=True 防止循环
        success = self.ui.gisCanvas.load_base_image(path, suppress_signal=True)
        
        if success:
            self._log_to_bottom(f"🔄 [Sync] Inference input -> GIS base map: {os.path.basename(path)}")
        else:
            self._log_to_bottom(f"⚠️ [Sync Failed] Cannot load image to GIS base map: {os.path.basename(path)}")
    
    def on_resplit_dataset(self):
        """重新划分数据集"""
        # 获取当前数据集统计
        train_samples = self.data_manager.get_samples('train')
        val_samples = self.data_manager.get_samples('val')
        test_samples = self.data_manager.get_samples('test')
        train_count = len(train_samples)
        val_count = len(val_samples)
        test_count = len(test_samples)

        if train_count + val_count + test_count == 0:
            QMessageBox.information(self, "Info", "No dataset loaded, please load data first.")
            return

        # 导入重新划分对话框
        from ui.widgets.dataset_resplit_dialog import DatasetResplitDialog

        # P2-6: 将样本数据直接传入构造函数，确保 _init_available_samples 可用
        dialog = DatasetResplitDialog(
            train_count, val_count, test_count,
            train_samples=train_samples, val_samples=val_samples, test_samples=test_samples,
            parent=self
        )
        dialog.resplit_confirmed.connect(self._perform_resplit)

        dialog.exec()
    
    def _perform_resplit(self, mode, params):
        """执行数据集重新划分
        
        Args:
            mode: 划分模式 ('auto', 'custom_count', 'custom_select')
            params: 划分参数
        """
        import random
        
        # 获取所有样本
        all_samples = []
        all_samples.extend(self.data_manager.get_samples('train'))
        all_samples.extend(self.data_manager.get_samples('val'))
        all_samples.extend(self.data_manager.get_samples('test'))
        
        if not all_samples:
            QMessageBox.warning(self, "Error", "No samples available for resplit.")
            return
        
        # 根据模式执行不同的划分逻辑
        if mode == 'auto':
            # Auto化划分
            if params.get('shuffle', True):
                random.seed(params.get('seed', 42))
                random.shuffle(all_samples)
            
            total_count = len(all_samples)
            train_count = int(total_count * params['train_ratio'])
            val_count = int(total_count * params['val_ratio'])
            test_count = total_count - train_count - val_count
            
            train_samples = all_samples[:train_count]
            val_samples = all_samples[train_count:train_count + val_count]
            test_samples = all_samples[train_count + val_count:]
            
        elif mode == 'custom_count':
            # 数量模式
            random.shuffle(all_samples)
            
            train_count = params['train_count']
            val_count = params['val_count']
            test_count = params['test_count']
            
            train_samples = all_samples[:train_count]
            val_samples = all_samples[train_count:train_count + val_count]
            test_samples = all_samples[train_count + val_count:train_count + val_count + test_count]
            
        elif mode == 'custom_select':
            # 选择模式
            train_samples = []
            val_samples = []
            test_samples = []
            
            # 根据用户的分配构建样本列表
            for assignment in params['sample_assignments']:
                sample_name = assignment['name']
                split_type = assignment['split']
                
                if split_type == 'Train':
                    train_samples.append(sample_name)
                elif split_type == 'Val':
                    val_samples.append(sample_name)
                elif split_type == 'Test':
                    test_samples.append(sample_name)
        
        else:
            QMessageBox.warning(self, "Error", f"Unknown split mode: {mode}")
            return
        
        # 清空现有数据集
        self.data_manager.clear_dataset('train')
        self.data_manager.clear_dataset('val')
        self.data_manager.clear_dataset('test')
        
        # 添加新的样本分配
        self.data_manager.add_samples_batch('train', train_samples)
        self.data_manager.add_samples_batch('val', val_samples)
        self.data_manager.add_samples_batch('test', test_samples)
        
        # 保存新的划分到txt文件
        if hasattr(self.data_manager, 'data_root') and self.data_manager.data_root:
            self._save_split_to_txt()
        
        # 更新数据集概览
        self.ui.widget_datasetOverview.update_data(len(train_samples), len(val_samples), len(test_samples))
        self._sync_inference_dataset_context()
        
        self.statusBar().showMessage("数据集重新划分完成")
        
        QMessageBox.information(
            self,
            "划分完成",
            f"数据集已重新划分:\n"
            f"Train: {len(train_samples)} 样本\n"
            f"Val: {len(val_samples)} 样本\n"
            f"Test: {len(test_samples)} 样本"
        )

        # P1-8: Resplit 后重置分析状态并重新触发
        if self._current_data_root:
            self.ui.analysis_panel.stop_analysis()
            self._initialize_analysis_panel(self._current_data_root)
    
    def _sync_inference_dataset_context(self):
        if (
            not hasattr(self, 'ui')
            or not hasattr(self.ui, 'inference_panel')
            or not hasattr(self.ui.inference_panel, 'set_dataset_context')
        ):
            return

        data_root = getattr(self.data_manager, 'data_root', None) or self._current_data_root
        if not data_root:
            return

        context = {
            'data_root': data_root,
            'splits': {
                'train': self._build_inference_split_context('train'),
                'val': self._build_inference_split_context('val'),
                'test': self._build_inference_split_context('test'),
            },
        }
        self.ui.inference_panel.set_dataset_context(context)

    def _build_inference_split_context(self, split: str):
        samples = []
        for sample_id in self.data_manager.get_samples(split):
            image_path, label_path = self.data_manager.get_sample_paths(sample_id, split)
            samples.append({
                'sample_id': sample_id,
                'image_path': image_path or '',
                'label_path': label_path or '',
            })
        return samples

    def _on_prediction_palette_changed(self, palette: dict):
        """右侧可视化设置：调色板变化 → 更新 GIS 主图预测图层"""
        ok = self.ui.gisCanvas.set_prediction_palette(palette)
        if ok:
            self._log_to_bottom("🎨 已应用预测类别颜色到主图")
        else:
            self._log_to_bottom("🎨 预测类别颜色已记录，图层就绪后Auto应用")

    def _on_prediction_alpha_changed(self, alpha: float):
        """右侧可视化设置：透明度变化 → 更新 GIS 主图预测图层"""
        self.ui.gisCanvas.set_prediction_opacity(alpha)

    def _on_prediction_visualization_apply(self):
        """右侧可视化设置：点击应用按钮 → 强制刷新 GIS 主图"""
        vs = self.ui.inference_panel.visualization_settings
        self.ui.gisCanvas.set_prediction_palette(vs.get_current_palette())
        self.ui.gisCanvas.set_prediction_opacity(vs.get_current_alpha())
        self._log_to_bottom("🎨 Applied viz settings to main map")

    def _on_prediction_initializing(self, input_path, expected_output_filename):
        """
        预测初始化回调：设置图层为加载状态
        
        Args:
            input_path: 输入文件路径
            expected_output_filename: 预期输出文件名
        """
        self._log_to_bottom(f"🔄 Prepare to receive prediction: {expected_output_filename}...")
        
        # 切换到 Inference 视图
        if self.ui.tabWidget_contextControl.currentIndex() != 2:
            self.ui.tabWidget_contextControl.setCurrentIndex(2)
            
        # 调用 GISCanvasWidget 的 set_prediction_loading 方法
        # 如果该方法不存在，需要先在 GISCanvasWidget 中实现
        if hasattr(self.ui.gisCanvas, 'set_prediction_loading'):
            self.ui.gisCanvas.set_prediction_loading(expected_output_filename)
    
    def _on_inference_finished(self, result):
        """推理完成回调"""
        print(f"🔵 _on_inference_finished 被调用")
        print(f"   result keys: {result.keys() if result else 'None'}")

        # 推理完成后显示右侧类别颜色配置控件
        if hasattr(self.ui.inference_panel, 'visualization_settings'):
            self.ui.inference_panel.visualization_settings.setVisible(True)

        # 显示结果
        mask = result.get('mask')
        output_path = result.get('output_path')
        
        print(f"   mask is None: {mask is None}")
        print(f"   output_path: {output_path}")
        palette = None
        if hasattr(self.ui.inference_panel, 'visualization_settings'):
            palette = self.ui.inference_panel.visualization_settings.get_current_palette()
        
        if mask is not None:
             self._log_to_bottom(f"✅ Inference complete, results ready")

             preferred_path = None
             if output_path and os.path.exists(output_path):
                 preferred_path = output_path
             elif hasattr(self.ui.inference_panel, 'last_inference_result'):
                 saved_path = self.ui.inference_panel.last_inference_result.get('saved_path')
                 print(f"   last_inference_result.saved_path: {saved_path}")
                 if saved_path and os.path.exists(saved_path):
                     preferred_path = saved_path

             if preferred_path:
                 print(f"   → 调用 inject_prediction({preferred_path})")
                 self.ui.gisCanvas.inject_prediction(preferred_path, palette=palette)
             else:
                 print(f"   ⚠️ output_path 和 saved_path 都不可用")
        else:
            print(f"   ⚠️ mask 为 None，不调用 inject_prediction")
            # 对于大图分块推理，mask 可能为 None，但 output_path 存在
            if output_path and os.path.exists(output_path):
                print(f"   → 尝试直接使用 output_path: {output_path}")
                self._log_to_bottom(f"🔄 加载大图推理结果: {output_path}")
                self.ui.gisCanvas.inject_prediction(output_path, palette=palette)
    
    def _save_split_to_txt(self):
        """Save dataset split to txt file"""
        if not hasattr(self.data_manager, 'data_root') or not self.data_manager.data_root:
            return
        
        data_root = self.data_manager.data_root
        
        # 检查是No为VOC格式（存在ImageSets/Segmentation目录）
        voc_txt_dir = os.path.join(data_root, 'ImageSets', 'Segmentation')
        
        # 确定保存路径
        if os.path.exists(voc_txt_dir):
            # VOC格式，保存到ImageSets/Segmentation/
            save_dir = voc_txt_dir
        else:
            # 其他格式，保存到数据根目录
            save_dir = data_root
        
        # 保存各个数据集
        datasets = {
            'train': self.data_manager.get_samples('train'),
            'val': self.data_manager.get_samples('val'),
            'test': self.data_manager.get_samples('test')
        }
        
        for dataset_type, samples in datasets.items():
            txt_path = os.path.join(save_dir, f'{dataset_type}.txt')
            try:
                with open(txt_path, 'w', encoding='utf-8') as f:
                    for sample_id in samples:
                        f.write(f"{sample_id}\n")
                print(f"✅ Saved {dataset_type}.txt: {len(samples)} samples")
            except Exception as e:
                print(f"❌ 保存 {txt_path} Failed: {e}")
                QMessageBox.warning(self, "保存失败", f"无法保存 {dataset_type}.txt: {e}")
    
    def closeEvent(self, event):
        """
        窗口关闭事件 - 清理后台线程
        
        解决问题: QThread: Destroyed while thread is still running
        """
        # 停止 SmartCanvas 的后台加载线程
        if hasattr(self, 'image_viewer') and self.image_viewer is not None:
            try:
                self.image_viewer._cleanup_thread()
            except Exception as e:
                print(f"⚠️ Clean image_viewer thread error: {e}")
        
        # 停止 GISCanvasWidget 的后台线程（如果有）
        if hasattr(self.ui, 'gisCanvas') and self.ui.gisCanvas is not None:
            try:
                if hasattr(self.ui.gisCanvas, '_cleanup_thread'):
                    self.ui.gisCanvas._cleanup_thread()
            except Exception as e:
                print(f"⚠️ Clean gisCanvas thread error: {e}")
        
        # 停止 AnalysisPanel 的后台线程（如果有）
        if hasattr(self.ui, 'analysis_panel') and self.ui.analysis_panel is not None:
            try:
                if hasattr(self.ui.analysis_panel, 'stop_analysis'):
                    self.ui.analysis_panel.stop_analysis()
            except Exception as e:
                print(f"⚠️ Clean analysis_panel thread error: {e}")
        
        # 停止 InferencePanel 的后台线程（如果有）
        if hasattr(self.ui, 'inference_panel') and self.ui.inference_panel is not None:
            try:
                if hasattr(self.ui.inference_panel, 'stop_inference'):
                    self.ui.inference_panel.stop_inference()
            except Exception as e:
                print(f"⚠️ 清理 inference_panel 线程时出错: {e}")
        
        # Phase 4: 停止训练线程
        if self._training_thread is not None and self._training_thread.isRunning():
            try:
                self._training_thread.stop()
                self._training_thread.wait(3000)
            except Exception as e:
                print(f"⚠️ Clean training thread error: {e}")
        
        # 调用父类的 closeEvent
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置默认字体，避免 QFont::setPointSize 警告
    from PySide6.QtGui import QFont
    default_font = app.font()
    if default_font.pointSize() <= 0:
        default_font.setPointSize(9)
        app.setFont(default_font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
