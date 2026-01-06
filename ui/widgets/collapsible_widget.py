# -*- coding: utf-8 -*-
"""
可折叠面板组件 (Collapsible Panel Widget)
支持独立展开/折叠的卡片式布局
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                QFrame, QSizePolicy, QScrollArea, QToolButton)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QIcon, QFont


class CollapsiblePanel(QWidget):
    """可折叠面板组件"""
    
    # 信号：展开/折叠状态改变
    toggled = Signal(bool)
    
    def __init__(self, title="Panel", parent=None, expanded=True):
        super().__init__(parent)
        self._is_expanded = expanded
        self._title = title
        self._content_height = 0
        self._header_widgets = []  # 标题栏额外控件
        
        self._setup_ui()
    
    def _setup_ui(self):
        """初始化UI"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 设置尺寸策略：宽度扩展，高度由内容决定（不拉伸）
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # 标题栏容器
        self.header_frame = QFrame(self)
        self.header_frame.setObjectName("collapsibleHeaderFrame")
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(0, 0, 4, 0)
        self.header_layout.setSpacing(4)
        
        # 标题按钮（可点击展开/折叠）
        self.header_button = QPushButton(self)
        self.header_button.setObjectName("collapsibleHeader")
        self.header_button.setCheckable(True)
        self.header_button.setChecked(self._is_expanded)
        self.header_button.clicked.connect(self._on_header_clicked)
        self.header_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_header_text()
        
        # 标题栏样式
        self.header_frame.setStyleSheet("""
            QFrame#collapsibleHeaderFrame {
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 4px;
            }
        """)
        self.header_button.setStyleSheet("""
            QPushButton#collapsibleHeader {
                background-color: transparent;
                color: palette(button-text);
                border: none;
                padding: 6px 8px;
                text-align: left;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#collapsibleHeader:hover {
                background-color: palette(light);
                border-radius: 4px;
            }
        """)
        
        self.header_layout.addWidget(self.header_button)
        self.main_layout.addWidget(self.header_frame)
        
        # 内容区域容器
        self.content_frame = QFrame(self)
        self.content_frame.setObjectName("collapsibleContent")
        self.content_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content_frame.setStyleSheet("""
            QFrame#collapsibleContent {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-top: none;
                border-radius: 0 0 4px 4px;
            }
        """)
        
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        self.main_layout.addWidget(self.content_frame)
        
        # 应用初始展开状态
        self.content_frame.setVisible(self._is_expanded)
    
    def _update_header_text(self):
        """更新标题栏文字"""
        if self._is_expanded:
            self.header_button.setText(f"▼ {self._title}")
        else:
            self.header_button.setText(f"▶ {self._title}")
    
    def _on_header_clicked(self, checked):
        """标题栏点击事件"""
        self._is_expanded = checked
        self._update_ui()
        self.toggled.emit(checked)
    
    def _update_ui(self):
        """更新UI状态"""
        self._update_header_text()
        self.content_frame.setVisible(self._is_expanded)
    
    def set_expanded(self, expanded):
        """设置展开/折叠状态"""
        self._is_expanded = expanded
        self.header_button.setChecked(expanded)
        self._update_ui()
    
    def is_expanded(self):
        """获取展开状态"""
        return self._is_expanded
    
    def set_title(self, title):
        """设置标题"""
        self._title = title
        self._update_ui()
    
    def add_header_widget(self, widget):
        """
        向标题栏添加控件（如按钮）
        
        Args:
            widget: 要添加的控件
        """
        self._header_widgets.append(widget)
        self.header_layout.addWidget(widget)
    
    def get_content_layout(self):
        """获取内容区域布局，用于添加子控件"""
        return self.content_layout
    
    def add_widget(self, widget):
        """向内容区域添加控件"""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """向内容区域添加布局"""
        self.content_layout.addLayout(layout)


class CollapsibleContainer(QWidget):
    """可折叠面板容器（不带滚动条，由外层控制滚动）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """初始化UI"""
        # 设置尺寸策略：宽度扩展，高度由内容决定
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # 内容布局
        self.container_layout = QVBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    
    def add_panel(self, title, expanded=True):
        """
        添加一个可折叠面板
        
        Args:
            title: 面板标题
            expanded: 初始是否展开
        
        Returns:
            CollapsiblePanel: 创建的面板对象
        """
        panel = CollapsiblePanel(title, self)
        panel.set_expanded(expanded)
        
        self.container_layout.addWidget(panel)
        self._panels.append(panel)
        
        return panel
    
    def get_panel(self, index):
        """获取指定索引的面板"""
        if 0 <= index < len(self._panels):
            return self._panels[index]
        return None
    
    def get_panels(self):
        """获取所有面板"""
        return self._panels
    
    def expand_all(self):
        """展开所有面板"""
        for panel in self._panels:
            panel.set_expanded(True)
    
    def collapse_all(self):
        """折叠所有面板"""
        for panel in self._panels:
            panel.set_expanded(False)
