# -*- coding: utf-8 -*-
"""
示例：如何使用重构后的组件

展示如何：
1. 创建 CollapsiblePanel 并添加 Header Action 按钮
2. 使用 create_flat_button 创建统一风格的按钮
3. 组装 Dataset Overview、Class Distribution、Health Check 卡片
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame
from PySide6.QtCore import Qt

from ui.widgets import (
    CollapsiblePanel,
    CollapsibleContainer,
    DatasetOverviewWidget,
    ClassDistributionWidget,
    HealthCheckCard,
    create_flat_button
)


def create_analysis_panel_example(parent: Optional[QWidget] = None) -> QWidget:
    """
    创建数据分析面板示例
    
    展示如何组装三个卡片：
    - Card 1: Dataset Overview (Header 有 Resplit 按钮)
    - Card 2: Class Distribution (Header 有 Calc Weights 按钮)
    - Card 3: Health Check (内容区有工具栏)
    """
    # 主容器
    container = QWidget(parent)
    main_layout = QVBoxLayout(container)
    main_layout.setContentsMargins(8, 8, 8, 8)
    main_layout.setSpacing(8)
    
    # 使用 QScrollArea 包裹
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    
    content_widget = QWidget()
    content_layout = QVBoxLayout(content_widget)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(8)
    content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    
    # ==================== Card 1: Dataset Overview ====================
    panel_overview = CollapsiblePanel("数据集概览 (Dataset Overview)", expanded=True)
    
    # 添加 Header Action: Resplit 按钮
    btn_resplit = panel_overview.add_header_action(
        text="Resplit",
        icon_name='fa5s.sync-alt',
        icon_color='#2196F3',  # 蓝色强调
        tooltip="重新划分数据集 (Train/Val/Test)"
    )
    
    # 添加内容组件
    overview_widget = DatasetOverviewWidget()
    panel_overview.add_widget(overview_widget)
    
    # 连接信号
    btn_resplit.clicked.connect(lambda: print("Resplit clicked!"))
    # 或者连接到 overview_widget.resplit_clicked（如果需要兼容旧代码）
    
    content_layout.addWidget(panel_overview)
    
    # ==================== Card 2: Class Distribution ====================
    panel_class = CollapsiblePanel("类别分布 (Class Distribution)", expanded=True)
    
    # 添加 Header Action: Calc Weights 按钮
    btn_calc_weights = panel_class.add_header_action(
        text="Calc Weights",
        icon_name='fa5s.balance-scale',
        icon_color='default',
        tooltip="计算类别权重 (Median Frequency Balancing)"
    )
    
    # 添加内容组件
    class_widget = ClassDistributionWidget()
    panel_class.add_widget(class_widget)
    
    # 连接信号
    btn_calc_weights.clicked.connect(lambda: print("Calc Weights clicked!"))
    
    content_layout.addWidget(panel_class)
    
    # ==================== Card 3: Health Check ====================
    panel_health = CollapsiblePanel("健康检查 (Health Check)", expanded=True)
    
    # Health Check 的按钮在内容区工具栏，不在 Header
    # 但可以在 Header 添加摘要标签
    health_widget = HealthCheckCard()
    summary_label = health_widget.get_header_widget()
    panel_health.add_header_action(text="")  # 占位，实际使用 summary_label
    # 注意：这里简化处理，实际可以直接添加 summary_label 到 header
    
    panel_health.add_widget(health_widget)
    
    content_layout.addWidget(panel_health)
    
    # 底部弹性空间
    content_layout.addStretch()
    
    scroll_area.setWidget(content_widget)
    main_layout.addWidget(scroll_area)
    
    return container


# ==================== 独立测试 ====================
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow
    
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    window.setWindowTitle("Analysis Panel Example")
    window.resize(400, 600)
    
    panel = create_analysis_panel_example()
    window.setCentralWidget(panel)
    
    window.show()
    sys.exit(app.exec())
