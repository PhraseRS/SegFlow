# -*- coding: utf-8 -*-
"""
数据集重新划分对话框 (Dataset Resplit Dialog)
支持自动化划分和自定义划分两种模式
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QSpinBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QMessageBox, QWidget, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QAbstractItemView, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor


class DatasetResplitDialog(QDialog):
    """数据集重新划分对话框"""
    
    # 信号：划分完成 (mode, params)
    resplit_confirmed = Signal(str, dict)
    
    def __init__(self, current_train=0, current_val=0, current_test=0,
                 train_samples=None, val_samples=None, test_samples=None, parent=None):
        super().__init__(parent)
        self.current_train = current_train
        self.current_val = current_val
        self.current_test = current_test
        self.total_samples = current_train + current_val + current_test

        # P2-6: 在 _setup_ui 之前设置样本数据，确保 _init_available_samples 可用
        self.real_sample_data = {
            'train': train_samples or [],
            'val': val_samples or [],
            'test': test_samples or []
        }

        self._setup_ui()
        self.setWindowTitle("Dataset Resplit")
        self.resize(800, 600)
    
    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # 标题
        title_label = QLabel("Select Split Mode")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        title_label.setFont(font)
        layout.addWidget(title_label)
        
        # 当前数据集Info
        info_label = QLabel(
            f"Current Dataset: Train={self.current_train}, "
            f"Val={self.current_val}, Test={self.current_test} "
            f"(Total: {self.total_samples})"
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)
        
        # 模式选择
        mode_group = QGroupBox("Split Mode")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_button_group = QButtonGroup(self)
        
        self.radio_auto = QRadioButton("Automatic Split")
        self.radio_auto.setChecked(True)
        self.mode_button_group.addButton(self.radio_auto, 0)
        mode_layout.addWidget(self.radio_auto)
        
        self.radio_custom = QRadioButton("Custom Split")
        self.mode_button_group.addButton(self.radio_custom, 1)
        mode_layout.addWidget(self.radio_custom)
        
        layout.addWidget(mode_group)
        
        # 堆叠窗口：切换不同模式的参数设置
        self.stacked_widget = QStackedWidget()
        
        # 页面0: 自动化划分
        self.auto_page = self._create_auto_split_page()
        self.stacked_widget.addWidget(self.auto_page)
        
        # 页面1: 自定义划分
        self.custom_page = self._create_custom_split_page()
        self.stacked_widget.addWidget(self.custom_page)
        
        layout.addWidget(self.stacked_widget)
        
        # 连接模式切换信号
        self.radio_auto.toggled.connect(self._on_mode_changed)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)
        
        self.btn_confirm = QPushButton("Confirm Split")
        self.btn_confirm.setDefault(True)
        self.btn_confirm.clicked.connect(self._on_confirm)
        button_layout.addWidget(self.btn_confirm)
        
        layout.addLayout(button_layout)
    
    def _create_auto_split_page(self):
        """创建自动化划分页面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 说明
        desc_label = QLabel(
            "Automatic split will randomly partition the dataset according to the specified ratio.\n"
            "Suitable for quickly splitting large-scale datasets."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # 比例设置
        ratio_group = QGroupBox("Split Ratio")
        ratio_layout = QVBoxLayout(ratio_group)
        
        # Train 比例
        train_layout = QHBoxLayout()
        train_layout.addWidget(QLabel("Train:"))
        self.spin_train_ratio = QDoubleSpinBox()
        self.spin_train_ratio.setRange(0, 100)
        self.spin_train_ratio.setValue(70)
        self.spin_train_ratio.setSuffix(" %")
        self.spin_train_ratio.setDecimals(1)
        self.spin_train_ratio.valueChanged.connect(self._update_auto_preview)
        train_layout.addWidget(self.spin_train_ratio)
        train_layout.addStretch()
        ratio_layout.addLayout(train_layout)
        
        # Val 比例
        val_layout = QHBoxLayout()
        val_layout.addWidget(QLabel("Val:"))
        self.spin_val_ratio = QDoubleSpinBox()
        self.spin_val_ratio.setRange(0, 100)
        self.spin_val_ratio.setValue(20)
        self.spin_val_ratio.setSuffix(" %")
        self.spin_val_ratio.setDecimals(1)
        self.spin_val_ratio.valueChanged.connect(self._update_auto_preview)
        val_layout.addWidget(self.spin_val_ratio)
        val_layout.addStretch()
        ratio_layout.addLayout(val_layout)
        
        # Test 比例
        test_layout = QHBoxLayout()
        test_layout.addWidget(QLabel("Test:"))
        self.spin_test_ratio = QDoubleSpinBox()
        self.spin_test_ratio.setRange(0, 100)
        self.spin_test_ratio.setValue(10)
        self.spin_test_ratio.setSuffix(" %")
        self.spin_test_ratio.setDecimals(1)
        self.spin_test_ratio.valueChanged.connect(self._update_auto_preview)
        test_layout.addWidget(self.spin_test_ratio)
        test_layout.addStretch()
        ratio_layout.addLayout(test_layout)
        
        # 总和Tip
        self.label_ratio_sum = QLabel()
        self.label_ratio_sum.setStyleSheet("font-size: 11px;")
        ratio_layout.addWidget(self.label_ratio_sum)
        
        layout.addWidget(ratio_group)
        
        # 高级选项
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)
        
        self.check_shuffle = QCheckBox("Shuffle")
        self.check_shuffle.setChecked(True)
        advanced_layout.addWidget(self.check_shuffle)
        
        seed_layout = QHBoxLayout()
        seed_layout.addWidget(QLabel("Random Seed:"))
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 999999)
        self.spin_seed.setValue(42)
        seed_layout.addWidget(self.spin_seed)
        seed_layout.addStretch()
        advanced_layout.addLayout(seed_layout)
        
        layout.addWidget(advanced_group)
        
        # 预览
        self.label_auto_preview = QLabel()
        self.label_auto_preview.setWordWrap(True)
        self.label_auto_preview.setStyleSheet(
            "background-color: #f0f0f0; padding: 8px; border-radius: 4px; font-size: 11px;"
        )
        layout.addWidget(self.label_auto_preview)
        
        layout.addStretch()
        
        # 初始化预览
        self._update_auto_preview()
        
        return page
    
    def _create_custom_split_page(self):
        """创建自定义划分页面 - 增强版本支持可视化选择"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 说明
        desc_label = QLabel(
            "Custom split supports two modes:\n"
            "• Count Mode: Manually specify the number of samples for each dataset\n"
            "• Selection Mode: Visually select which dataset each sample is assigned to"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # 自定义模式选择
        custom_mode_group = QGroupBox("Custom Mode")
        custom_mode_layout = QVBoxLayout(custom_mode_group)
        
        self.custom_mode_button_group = QButtonGroup(self)
        
        self.radio_count_mode = QRadioButton("Count Mode")
        self.radio_count_mode.setChecked(True)
        self.custom_mode_button_group.addButton(self.radio_count_mode, 0)
        custom_mode_layout.addWidget(self.radio_count_mode)
        
        self.radio_select_mode = QRadioButton("Selection Mode")
        self.custom_mode_button_group.addButton(self.radio_select_mode, 1)
        custom_mode_layout.addWidget(self.radio_select_mode)
        
        layout.addWidget(custom_mode_group)
        
        # 堆叠窗口：切换不同自定义模式
        self.custom_stacked_widget = QStackedWidget()
        
        # 页面0: 数量模式（原有功能）
        self.count_mode_page = self._create_count_mode_page()
        self.custom_stacked_widget.addWidget(self.count_mode_page)
        
        # 页面1: 选择模式（新增功能）
        self.select_mode_page = self._create_select_mode_page()
        self.custom_stacked_widget.addWidget(self.select_mode_page)
        
        layout.addWidget(self.custom_stacked_widget)
        
        # 连接自定义模式切换信号
        self.radio_count_mode.toggled.connect(self._on_custom_mode_changed)
        
        return page
    
    def _create_count_mode_page(self):
        """创建数量模式页面（原有功能）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 数量设置
        count_group = QGroupBox("Sample Count")
        count_layout = QVBoxLayout(count_group)
        
        # Train 数量
        train_layout = QHBoxLayout()
        train_layout.addWidget(QLabel("Train:"))
        self.spin_train_count = QSpinBox()
        self.spin_train_count.setRange(0, self.total_samples)
        self.spin_train_count.setValue(self.current_train)
        self.spin_train_count.valueChanged.connect(self._update_custom_preview)
        train_layout.addWidget(self.spin_train_count)
        train_layout.addStretch()
        count_layout.addLayout(train_layout)
        
        # Val 数量
        val_layout = QHBoxLayout()
        val_layout.addWidget(QLabel("Val:"))
        self.spin_val_count = QSpinBox()
        self.spin_val_count.setRange(0, self.total_samples)
        self.spin_val_count.setValue(self.current_val)
        self.spin_val_count.valueChanged.connect(self._update_custom_preview)
        val_layout.addWidget(self.spin_val_count)
        val_layout.addStretch()
        count_layout.addLayout(val_layout)
        
        # Test 数量
        test_layout = QHBoxLayout()
        test_layout.addWidget(QLabel("Test:"))
        self.spin_test_count = QSpinBox()
        self.spin_test_count.setRange(0, self.total_samples)
        self.spin_test_count.setValue(self.current_test)
        self.spin_test_count.valueChanged.connect(self._update_custom_preview)
        test_layout.addWidget(self.spin_test_count)
        test_layout.addStretch()
        count_layout.addLayout(test_layout)
        
        # 总和Tip
        self.label_count_sum = QLabel()
        self.label_count_sum.setStyleSheet("font-size: 11px;")
        count_layout.addWidget(self.label_count_sum)
        
        layout.addWidget(count_group)
        
        # 快速设置按钮
        quick_layout = QHBoxLayout()
        quick_layout.addWidget(QLabel("Quick Set:"))
        
        btn_7_2_1 = QPushButton("7:2:1")
        btn_7_2_1.clicked.connect(lambda: self._quick_set_custom(0.7, 0.2, 0.1))
        quick_layout.addWidget(btn_7_2_1)
        
        btn_8_1_1 = QPushButton("8:1:1")
        btn_8_1_1.clicked.connect(lambda: self._quick_set_custom(0.8, 0.1, 0.1))
        quick_layout.addWidget(btn_8_1_1)
        
        btn_6_2_2 = QPushButton("6:2:2")
        btn_6_2_2.clicked.connect(lambda: self._quick_set_custom(0.6, 0.2, 0.2))
        quick_layout.addWidget(btn_6_2_2)
        
        quick_layout.addStretch()
        layout.addLayout(quick_layout)
        
        # 预览
        self.label_custom_preview = QLabel()
        self.label_custom_preview.setWordWrap(True)
        self.label_custom_preview.setStyleSheet(
            "background-color: #f0f0f0; padding: 8px; border-radius: 4px; font-size: 11px;"
        )
        layout.addWidget(self.label_custom_preview)
        
        layout.addStretch()
        
        # 初始化预览
        self._update_custom_preview()
        
        return page
    
    def _create_select_mode_page(self):
        """创建选择模式页面 - 真正的样本选择功能"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 说明
        desc_label = QLabel(
            "Select samples from the left and assign them to a dataset in the table on the right."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # 主分割器：样本树 | 分配表格 | 统计面板
        main_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：样本选择树
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        left_layout.addWidget(QLabel("Available Samples:"))
        
        self.tree_available_samples = QTreeWidget()
        self.tree_available_samples.setHeaderLabels(["Sample Name", "Current Split"])
        self.tree_available_samples.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.tree_available_samples)
        
        # 添加样本按钮
        add_buttons_layout = QHBoxLayout()
        self.btn_add_selected = QPushButton("Add Selected →")
        self.btn_add_selected.clicked.connect(self._add_selected_samples)
        add_buttons_layout.addWidget(self.btn_add_selected)
        
        self.btn_add_all = QPushButton("Add All →")
        self.btn_add_all.clicked.connect(self._add_all_samples)
        add_buttons_layout.addWidget(self.btn_add_all)
        
        left_layout.addLayout(add_buttons_layout)
        left_widget.setMaximumWidth(300)
        main_splitter.addWidget(left_widget)
        
        # 中间：分配表格
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(5, 5, 5, 5)
        
        # 批量操作工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("Batch Assign:"))
        
        self.combo_batch_target = QComboBox()
        self.combo_batch_target.addItems(["Train", "Val", "Test"])
        toolbar_layout.addWidget(self.combo_batch_target)
        
        self.btn_assign_selected = QPushButton("Assign Selected")
        self.btn_assign_selected.clicked.connect(self._assign_selected_samples)
        toolbar_layout.addWidget(self.btn_assign_selected)
        
        self.btn_remove_selected = QPushButton("← Remove Selected")
        self.btn_remove_selected.clicked.connect(self._remove_selected_samples)
        toolbar_layout.addWidget(self.btn_remove_selected)
        
        toolbar_layout.addStretch()
        middle_layout.addLayout(toolbar_layout)
        
        middle_layout.addWidget(QLabel("Sample Assignment:"))
        
        # Samples分配表格
        self.table_sample_assignment = QTableWidget()
        self.table_sample_assignment.setColumnCount(3)
        self.table_sample_assignment.setHorizontalHeaderLabels([
            "Sample Name", "Assigned To", "Action"
        ])
        
        # 设置表格属性
        self.table_sample_assignment.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_sample_assignment.setAlternatingRowColors(True)
        
        # 调整列宽
        header = self.table_sample_assignment.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Samples名称
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 分配到
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 操作
        
        middle_layout.addWidget(self.table_sample_assignment)
        main_splitter.addWidget(middle_widget)
        
        # 右侧：统计Info面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 实时统计
        stats_group = QGroupBox("Assignment Stats")
        stats_group_layout = QVBoxLayout(stats_group)
        
        self.label_assignment_stats = QLabel()
        self.label_assignment_stats.setWordWrap(True)
        self.label_assignment_stats.setStyleSheet(
            "background-color: #f8f9fa; padding: 8px; border-radius: 4px; font-size: 11px;"
        )
        stats_group_layout.addWidget(self.label_assignment_stats)
        
        right_layout.addWidget(stats_group)
        
        # 快速操作
        quick_group = QGroupBox("Quick Actions")
        quick_layout = QVBoxLayout(quick_group)
        
        self.btn_auto_assign_721 = QPushButton("Auto Assign 7:2:1")
        self.btn_auto_assign_721.clicked.connect(lambda: self._auto_assign_ratio(0.7, 0.2, 0.1))
        quick_layout.addWidget(self.btn_auto_assign_721)
        
        self.btn_auto_assign_811 = QPushButton("Auto Assign 8:1:1")
        self.btn_auto_assign_811.clicked.connect(lambda: self._auto_assign_ratio(0.8, 0.1, 0.1))
        quick_layout.addWidget(self.btn_auto_assign_811)
        
        self.btn_clear_all = QPushButton("Clear Assignments")
        self.btn_clear_all.clicked.connect(self._clear_all_assignments)
        quick_layout.addWidget(self.btn_clear_all)
        
        right_layout.addWidget(quick_group)
        
        # 变更日志
        log_group = QGroupBox("Action Log")
        log_layout = QVBoxLayout(log_group)
        
        self.text_assignment_log = QTextEdit()
        self.text_assignment_log.setMaximumHeight(120)
        self.text_assignment_log.setStyleSheet("font-size: 10px;")
        log_layout.addWidget(self.text_assignment_log)
        
        right_layout.addWidget(log_group)
        right_layout.addStretch()
        
        right_widget.setMaximumWidth(280)
        main_splitter.addWidget(right_widget)
        
        # 设置分割器比例
        main_splitter.setSizes([300, 500, 280])
        
        layout.addWidget(main_splitter)
        
        # 初始化数据
        self._init_available_samples()
        self.sample_assignments = {}  # {sample_name: split_type}
        self._update_assignment_stats()
        
        return page
    
    def _init_available_samples(self):
        """初始化可用样本树"""
        # 清空树
        self.tree_available_samples.clear()
        
        # 创建当前分配的分组
        train_item = QTreeWidgetItem(self.tree_available_samples, [f"Train [{self.current_train} samples]", ""])
        train_item.setExpanded(True)
        train_item.setBackground(0, QColor("#e3f2fd"))
        
        val_item = QTreeWidgetItem(self.tree_available_samples, [f"Val [{self.current_val} samples]", ""])
        val_item.setExpanded(True)
        val_item.setBackground(0, QColor("#f3e5f5"))
        
        test_item = QTreeWidgetItem(self.tree_available_samples, [f"Test [{self.current_test} samples]", ""])
        test_item.setExpanded(True)
        test_item.setBackground(0, QColor("#e8f5e8"))
        
        # 使用真实样本数据（如果可用）
        if hasattr(self, 'real_sample_data'):
            # 添加训练集样本
            for sample_id in self.real_sample_data['train']:
                child_item = QTreeWidgetItem(train_item, [sample_id, "Train"])
                child_item.setData(0, Qt.UserRole, {"name": sample_id, "current_split": "Train", "sample_id": sample_id})
            
            # 添加验证集样本
            for sample_id in self.real_sample_data['val']:
                child_item = QTreeWidgetItem(val_item, [sample_id, "Val"])
                child_item.setData(0, Qt.UserRole, {"name": sample_id, "current_split": "Val", "sample_id": sample_id})
            
            # 添加测试集样本
            for sample_id in self.real_sample_data['test']:
                child_item = QTreeWidgetItem(test_item, [sample_id, "Test"])
                child_item.setData(0, Qt.UserRole, {"name": sample_id, "current_split": "Test", "sample_id": sample_id})
        else:
            # 回退到模拟数据（用于测试）
            sample_index = 1
            
            # 添加训练集样本
            for i in range(self.current_train):
                sample_name = f"image_{sample_index:04d}"
                child_item = QTreeWidgetItem(train_item, [sample_name, "Train"])
                child_item.setData(0, Qt.UserRole, {"name": sample_name, "current_split": "Train", "sample_id": sample_name})
                sample_index += 1
            
            # 添加验证集样本
            for i in range(self.current_val):
                sample_name = f"image_{sample_index:04d}"
                child_item = QTreeWidgetItem(val_item, [sample_name, "Val"])
                child_item.setData(0, Qt.UserRole, {"name": sample_name, "current_split": "Val", "sample_id": sample_name})
                sample_index += 1
            
            # 添加测试集样本
            for i in range(self.current_test):
                sample_name = f"image_{sample_index:04d}"
                child_item = QTreeWidgetItem(test_item, [sample_name, "Test"])
                child_item.setData(0, Qt.UserRole, {"name": sample_name, "current_split": "Test", "sample_id": sample_name})
                sample_index += 1
    
    def _add_selected_samples(self):
        """添加选中的样本到分配表格"""
        selected_items = self.tree_available_samples.selectedItems()
        added_count = 0
        
        for item in selected_items:
            # 只处理叶子节点（实际样本）
            if item.childCount() == 0:
                sample_data = item.data(0, Qt.UserRole)
                if sample_data and sample_data["name"] not in self.sample_assignments:
                    self._add_sample_to_assignment(sample_data)
                    added_count += 1
        
        if added_count > 0:
            self.text_assignment_log.append(f"Added {added_count} samples to assignment list")
            self._update_assignment_stats()
    
    def _add_all_samples(self):
        """添加所有样本到分配表格"""
        added_count = 0
        
        # 遍历所有分组
        for group_idx in range(self.tree_available_samples.topLevelItemCount()):
            group_item = self.tree_available_samples.topLevelItem(group_idx)
            
            # 遍历分组下的所有样本
            for child_idx in range(group_item.childCount()):
                child_item = group_item.child(child_idx)
                sample_data = child_item.data(0, Qt.UserRole)
                
                if sample_data and sample_data["name"] not in self.sample_assignments:
                    self._add_sample_to_assignment(sample_data)
                    added_count += 1
        
        if added_count > 0:
            self.text_assignment_log.append(f"Added all {added_count} samples to assignment list")
            self._update_assignment_stats()
    
    def _add_sample_to_assignment(self, sample_data):
        """添加样本到分配表格"""
        sample_name = sample_data["name"]
        current_split = sample_data["current_split"]
        
        # 添加到分配字典
        self.sample_assignments[sample_name] = current_split
        
        # 添加到表格
        row = self.table_sample_assignment.rowCount()
        self.table_sample_assignment.insertRow(row)
        
        # Samples名称
        name_item = QTableWidgetItem(sample_name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table_sample_assignment.setItem(row, 0, name_item)
        
        # 分配下拉框
        split_combo = QComboBox()
        split_combo.addItems(["Train", "Val", "Test"])
        split_combo.setCurrentText(current_split)
        split_combo.currentTextChanged.connect(
            lambda text, name=sample_name: self._on_assignment_changed(name, text)
        )
        self.table_sample_assignment.setCellWidget(row, 1, split_combo)
        
        # 移除按钮
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda checked, name=sample_name: self._remove_sample_assignment(name))
        self.table_sample_assignment.setCellWidget(row, 2, remove_btn)
    
    def _on_assignment_changed(self, sample_name, new_split):
        """处理分配变更"""
        old_split = self.sample_assignments.get(sample_name, "")
        self.sample_assignments[sample_name] = new_split
        
        self.text_assignment_log.append(f"[{sample_name}] {old_split} → {new_split}")
        self._update_assignment_stats()
    
    def _assign_selected_samples(self):
        """批量分配选中的样本"""
        selected_rows = set()
        for item in self.table_sample_assignment.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "Tip", "Please select samples to assign first.")
            return
        
        target_split = self.combo_batch_target.currentText()
        
        for row in selected_rows:
            combo = self.table_sample_assignment.cellWidget(row, 1)
            if combo:
                combo.setCurrentText(target_split)
        
        self.text_assignment_log.append(f"Batch assigned {len(selected_rows)} samples to {target_split}")
    
    def _remove_selected_samples(self):
        """移除选中的样本"""
        selected_rows = []
        for item in self.table_sample_assignment.selectedItems():
            selected_rows.append(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "Tip", "Please select samples to remove first.")
            return
        
        # 按行号倒序排列，避免删除时索引变化
        selected_rows.sort(reverse=True)
        
        removed_samples = []
        for row in selected_rows:
            name_item = self.table_sample_assignment.item(row, 0)
            if name_item:
                sample_name = name_item.text()
                removed_samples.append(sample_name)
                if sample_name in self.sample_assignments:
                    del self.sample_assignments[sample_name]
                self.table_sample_assignment.removeRow(row)
        
        if removed_samples:
            self.text_assignment_log.append(f"Removed {len(removed_samples)} samples")
            self._update_assignment_stats()
    
    def _remove_sample_assignment(self, sample_name):
        """移除单个样本分配"""
        # 从字典中移除
        if sample_name in self.sample_assignments:
            del self.sample_assignments[sample_name]
        
        # 从表格中移除
        for row in range(self.table_sample_assignment.rowCount()):
            name_item = self.table_sample_assignment.item(row, 0)
            if name_item and name_item.text() == sample_name:
                self.table_sample_assignment.removeRow(row)
                break
        
        self.text_assignment_log.append(f"Removed sample: {sample_name}")
        self._update_assignment_stats()
    
    def _auto_assign_ratio(self, train_ratio, val_ratio, test_ratio):
        """按比例自动分配样本"""
        if not self.sample_assignments:
            QMessageBox.information(self, "Tip", "Please add samples to the assignment list first.")
            return
        
        import random
        
        # 获取所有样本名称并打乱
        sample_names = list(self.sample_assignments.keys())
        random.shuffle(sample_names)
        
        total_count = len(sample_names)
        train_count = int(total_count * train_ratio)
        val_count = int(total_count * val_ratio)
        test_count = total_count - train_count - val_count
        
        # 分配样本
        for i, sample_name in enumerate(sample_names):
            if i < train_count:
                target = "Train"
            elif i < train_count + val_count:
                target = "Val"
            else:
                target = "Test"
            
            # 更新字典
            self.sample_assignments[sample_name] = target
            
            # 更新表格中的下拉框
            for row in range(self.table_sample_assignment.rowCount()):
                name_item = self.table_sample_assignment.item(row, 0)
                if name_item and name_item.text() == sample_name:
                    combo = self.table_sample_assignment.cellWidget(row, 1)
                    if combo:
                        combo.setCurrentText(target)
                    break
        
        self.text_assignment_log.append(
            f"Auto assignment complete ({train_ratio*100:.0f}:{val_ratio*100:.0f}:{test_ratio*100:.0f}): "
            f"Train={train_count}, Val={val_count}, Test={test_count}"
        )
        self._update_assignment_stats()
    
    def _clear_all_assignments(self):
        """清空所有分配"""
        self.sample_assignments.clear()
        self.table_sample_assignment.setRowCount(0)
        self.text_assignment_log.append("Cleared all sample assignments")
        self._update_assignment_stats()
    
    def _update_assignment_stats(self):
        """更新分配统计Info"""
        if not self.sample_assignments:
            stats_text = "No samples added yet\n\nPlease select samples from the left to add to the assignment list"
            self.label_assignment_stats.setText(stats_text)
            return
        
        # 统计各类别数量
        counts = {"Train": 0, "Val": 0, "Test": 0}
        for split in self.sample_assignments.values():
            counts[split] += 1
        
        total = len(self.sample_assignments)
        
        # 计算百分比
        train_pct = counts["Train"] / total * 100 if total > 0 else 0
        val_pct = counts["Val"] / total * 100 if total > 0 else 0
        test_pct = counts["Test"] / total * 100 if total > 0 else 0
        
        stats_text = (
            f"Assigned Samples: {total}\n\n"
            f"Train: {counts['Train']} ({train_pct:.1f}%)\n"
            f"Val: {counts['Val']} ({val_pct:.1f}%)\n"
            f"Test: {counts['Test']} ({test_pct:.1f}%)\n\n"
            f"Total Samples: {self.total_samples}\n"
            f"Unassigned: {self.total_samples - total}"
        )
        
        self.label_assignment_stats.setText(stats_text)
        
        # 保存统计Info供Confirm时使用
        self.assignment_counts = counts
    
    def _on_custom_mode_changed(self, checked):
        """自定义模式切换"""
        if checked:  # count mode
            self.custom_stacked_widget.setCurrentIndex(0)
        else:  # select mode
            self.custom_stacked_widget.setCurrentIndex(1)
    
    def _on_mode_changed(self, checked):
        """模式切换"""
        if checked:  # auto mode
            self.stacked_widget.setCurrentIndex(0)
        else:  # custom mode
            self.stacked_widget.setCurrentIndex(1)
    
    def _update_auto_preview(self):
        """更新自动化划分预览"""
        train_ratio = self.spin_train_ratio.value()
        val_ratio = self.spin_val_ratio.value()
        test_ratio = self.spin_test_ratio.value()
        
        total_ratio = train_ratio + val_ratio + test_ratio
        
        # 更新总和Tip
        if abs(total_ratio - 100.0) < 0.01:
            self.label_ratio_sum.setText(f"✓ Sum: {total_ratio:.1f}%")
            self.label_ratio_sum.setStyleSheet("color: green; font-size: 11px;")
        else:
            self.label_ratio_sum.setText(f"⚠ Sum: {total_ratio:.1f}% (should be 100%)")
            self.label_ratio_sum.setStyleSheet("color: red; font-size: 11px;")
        
        # 计算预览
        if total_ratio > 0:
            train_count = int(self.total_samples * train_ratio / 100)
            val_count = int(self.total_samples * val_ratio / 100)
            test_count = self.total_samples - train_count - val_count
            
            preview_text = (
                f"Preview Result:\n"
                f"Train: {train_count} samples ({train_count/self.total_samples*100:.1f}%)\n"
                f"Val: {val_count} samples ({val_count/self.total_samples*100:.1f}%)\n"
                f"Test: {test_count} samples ({test_count/self.total_samples*100:.1f}%)"
            )
        else:
            preview_text = "Preview Result: Invalid ratio setting"
        
        self.label_auto_preview.setText(preview_text)
    
    def _update_custom_preview(self):
        """更新自定义划分预览"""
        train_count = self.spin_train_count.value()
        val_count = self.spin_val_count.value()
        test_count = self.spin_test_count.value()
        
        total_count = train_count + val_count + test_count
        
        # 更新总和Tip
        if total_count == self.total_samples:
            self.label_count_sum.setText(f"✓ Sum: {total_count} / {self.total_samples}")
            self.label_count_sum.setStyleSheet("color: green; font-size: 11px;")
        else:
            self.label_count_sum.setText(
                f"⚠ Sum: {total_count} / {self.total_samples} "
                f"(Diff: {total_count - self.total_samples:+d})"
            )
            self.label_count_sum.setStyleSheet("color: red; font-size: 11px;")
        
        # 计算预览
        if self.total_samples > 0:
            preview_text = (
                f"Preview Result:\n"
                f"Train: {train_count} samples ({train_count/self.total_samples*100:.1f}%)\n"
                f"Val: {val_count} samples ({val_count/self.total_samples*100:.1f}%)\n"
                f"Test: {test_count} samples ({test_count/self.total_samples*100:.1f}%)"
            )
        else:
            preview_text = "Preview Result: No samples"
        
        self.label_custom_preview.setText(preview_text)
    
    def _quick_set_custom(self, train_ratio, val_ratio, test_ratio):
        """快速设置自定义数量"""
        train_count = int(self.total_samples * train_ratio)
        val_count = int(self.total_samples * val_ratio)
        test_count = self.total_samples - train_count - val_count
        
        self.spin_train_count.setValue(train_count)
        self.spin_val_count.setValue(val_count)
        self.spin_test_count.setValue(test_count)
    
    def _on_confirm(self):
        """Confirm Split"""
        if self.radio_auto.isChecked():
            # 自动化划分
            train_ratio = self.spin_train_ratio.value()
            val_ratio = self.spin_val_ratio.value()
            test_ratio = self.spin_test_ratio.value()
            
            total_ratio = train_ratio + val_ratio + test_ratio
            
            if abs(total_ratio - 100.0) > 0.01:
                QMessageBox.warning(
                    self,
                    "Ratio Error",
                    f"Split ratio sum must be 100%, currently {total_ratio:.1f}%"
                )
                return
            
            params = {
                'train_ratio': train_ratio / 100,
                'val_ratio': val_ratio / 100,
                'test_ratio': test_ratio / 100,
                'shuffle': self.check_shuffle.isChecked(),
                'seed': self.spin_seed.value()
            }
            
            self.resplit_confirmed.emit('auto', params)
            
        else:
            # 自定义划分
            if self.radio_count_mode.isChecked():
                # 数量模式
                train_count = self.spin_train_count.value()
                val_count = self.spin_val_count.value()
                test_count = self.spin_test_count.value()
                
                total_count = train_count + val_count + test_count
                
                if total_count != self.total_samples:
                    QMessageBox.warning(
                        self,
                        "Count Error",
                        f"Total samples must be {self.total_samples}, currently {total_count}"
                    )
                    return
                
                params = {
                    'train_count': train_count,
                    'val_count': val_count,
                    'test_count': test_count
                }
                
                self.resplit_confirmed.emit('custom_count', params)
                
            else:
                # 选择模式
                if not hasattr(self, 'assignment_counts') or not self.sample_assignments:
                    QMessageBox.warning(self, "Error", "Please add samples and complete assignments first.")
                    return
                
                # 检查是否所有样本都已分配
                total_assigned = len(self.sample_assignments)
                if total_assigned == 0:
                    QMessageBox.warning(self, "Error", "Please assign at least one sample.")
                    return
                
                # Confirm分配
                reply = QMessageBox.question(
                    self,
                    "Confirm Sample Assignment",
                    f"Dataset will be created with the following assignments:\n\n"
                    f"Train: {self.assignment_counts['Train']} samples\n"
                    f"Val: {self.assignment_counts['Val']} samples\n"
                    f"Test: {self.assignment_counts['Test']} samples\n\n"
                    f"Total: {total_assigned} samples\n\n"
                    f"Confirm?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                
                # 构建样本分配列表
                sample_list = []
                for sample_name, split_type in self.sample_assignments.items():
                    sample_list.append({
                        'name': sample_name,
                        'split': split_type
                    })
                
                params = {
                    'sample_assignments': sample_list,
                    'train_count': self.assignment_counts['Train'],
                    'val_count': self.assignment_counts['Val'],
                    'test_count': self.assignment_counts['Test'],
                    'total_assigned': total_assigned
                }
                
                self.resplit_confirmed.emit('custom_select', params)
        
        self.accept()
    
    def set_sample_data(self, train_samples, val_samples, test_samples):
        """设置真实的样本数据（从主窗口调用）"""
        self.real_sample_data = {
            'train': train_samples,
            'val': val_samples,
            'test': test_samples
        }
        
        # 重新初始化可用样本树
        if hasattr(self, 'tree_available_samples'):
            self._init_available_samples()