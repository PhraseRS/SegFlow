# -*- coding: utf-8 -*-
"""
数据集概览组件 (Dataset Overview Widget)
显示数据集统计信息和划分比例
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen


class StackedBarWidget(QWidget):
    """分段进度条组件 - 显示 Train/Val/Test 比例"""
    
    # 默认颜色
    COLORS = {
        'train': QColor(76, 175, 80),    # 绿色
        'val': QColor(33, 150, 243),     # 蓝色
        'test': QColor(255, 152, 0),     # 橙色
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        
        # 数据
        self._train_count = 0
        self._val_count = 0
        self._test_count = 0
        self._total = 0
    
    def set_data(self, train_count, val_count, test_count):
        """设置数据"""
        self._train_count = train_count
        self._val_count = val_count
        self._test_count = test_count
        self._total = train_count + val_count + test_count
        self.update()
    
    def paintEvent(self, event):
        """绘制分段进度条"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        # 绘制背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(200, 200, 200, 50))
        painter.drawRoundedRect(rect, 4, 4)
        
        if self._total == 0:
            return
        
        # 计算各段宽度
        train_width = int(width * self._train_count / self._total)
        val_width = int(width * self._val_count / self._total)
        test_width = width - train_width - val_width
        
        x = 0
        
        # 绘制 Train 段
        if train_width > 0:
            painter.setBrush(self.COLORS['train'])
            if val_width == 0 and test_width == 0:
                painter.drawRoundedRect(x, 0, train_width, height, 4, 4)
            else:
                painter.drawRoundedRect(x, 0, train_width + 4, height, 4, 4)
                painter.drawRect(x + train_width, 0, 4, height)
            x += train_width
        
        # 绘制 Val 段
        if val_width > 0:
            painter.setBrush(self.COLORS['val'])
            if test_width == 0:
                if train_width == 0:
                    painter.drawRoundedRect(x, 0, val_width, height, 4, 4)
                else:
                    painter.drawRoundedRect(x - 4, 0, val_width + 4, height, 4, 4)
                    painter.drawRect(x - 4, 0, 4, height)
            else:
                painter.drawRect(x, 0, val_width, height)
            x += val_width
        
        # 绘制 Test 段
        if test_width > 0:
            painter.setBrush(self.COLORS['test'])
            if train_width == 0 and val_width == 0:
                painter.drawRoundedRect(x, 0, test_width, height, 4, 4)
            else:
                painter.drawRoundedRect(x - 4, 0, test_width + 4, height, 4, 4)
                painter.drawRect(x - 4, 0, 4, height)


class DatasetOverviewWidget(QWidget):
    """数据集概览组件"""
    
    resplit_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.update_data(0, 0, 0)
    
    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        self.label_total = QLabel("0")
        self.label_total.setObjectName("label_total_samples")
        font = self.label_total.font()
        font.setPointSize(24)
        font.setBold(True)
        self.label_total.setFont(font)
        self.label_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_total)
        
        self.label_total_desc = QLabel("总样本数 (Total Samples)")
        self.label_total_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_total_desc.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.label_total_desc)
        
        self.stacked_bar = StackedBarWidget()
        layout.addWidget(self.stacked_bar)
        
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        
        self.legend_train = self._create_legend_item("Train", StackedBarWidget.COLORS['train'])
        legend_layout.addWidget(self.legend_train)
        
        self.legend_val = self._create_legend_item("Val", StackedBarWidget.COLORS['val'])
        legend_layout.addWidget(self.legend_val)
        
        self.legend_test = self._create_legend_item("Test", StackedBarWidget.COLORS['test'])
        legend_layout.addWidget(self.legend_test)
        
        legend_layout.addStretch()
        layout.addLayout(legend_layout)
        
        self.label_detail = QLabel()
        self.label_detail.setWordWrap(True)
        self.label_detail.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.label_detail)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_resplit = QPushButton("重新划分 (Resplit)")
        self.btn_resplit.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.btn_resplit.clicked.connect(self.resplit_clicked.emit)
        self.btn_resplit.setEnabled(False)
        button_layout.addWidget(self.btn_resplit)
        
        layout.addLayout(button_layout)
    
    def _create_legend_item(self, text, color):
        """创建图例项"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        color_box = QFrame()
        color_box.setFixedSize(12, 12)
        color_box.setStyleSheet(f"background-color: {color.name()}; border-radius: 2px;")
        layout.addWidget(color_box)
        
        label = QLabel(text)
        label.setStyleSheet("font-size: 11px;")
        layout.addWidget(label)
        
        return widget
    
    def update_data(self, train_count, val_count, test_count):
        """更新数据显示"""
        total = train_count + val_count + test_count
        
        self.label_total.setText(f"{total:,}")
        self.stacked_bar.set_data(train_count, val_count, test_count)
        
        if total > 0:
            train_pct = train_count / total * 100
            val_pct = val_count / total * 100
            test_pct = test_count / total * 100
            
            detail_text = (
                f"Train: {train_count:,} ({train_pct:.1f}%) | "
                f"Val: {val_count:,} ({val_pct:.1f}%) | "
                f"Test: {test_count:,} ({test_pct:.1f}%)"
            )
            self.btn_resplit.setEnabled(True)
        else:
            detail_text = "暂无数据，请先加载数据集"
            self.btn_resplit.setEnabled(False)
        
        self.label_detail.setText(detail_text)
    
    def clear(self):
        """清空数据"""
        self.update_data(0, 0, 0)
