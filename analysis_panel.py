# -*- coding: utf-8 -*-
"""
数据分析面板 (Analysis Panel)
智能混合启动策略：缓存优先 + 阈值判断 + 分支处理

布局结构：
- 顶部 (Top)：数据集概览 - 永远可见（毫秒级加载）
- 中部 (Middle)：分析控制器 - 按钮/进度条（单独放置）
- 底部 (Bottom)：深度图表 - 类别分布、尺度分析、健康检查（独立显示）
"""

from typing import Optional, Dict, Any
from enum import Enum, auto
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QStackedWidget, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

from dataset_metadata import DatasetMetadataManager


class AnalysisState(Enum):
    """分析状态枚举"""
    IDLE = auto()       # 空闲状态（未开始/等待手动触发）
    RUNNING = auto()    # 正在分析
    COMPLETED = auto()  # 分析完成


class AnalysisControlWidget(QWidget):
    """
    分析控制器组件（单独放置）
    
    包含三种状态：
    1. 按钮状态：显示"开始深度分析"按钮
    2. 进度状态：显示进度条和状态文字
    3. 完成状态：显示完成提示信息
    """
    
    # 信号
    start_clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._sample_count = 0
        self._is_large_dataset = False
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # 边距由外层统一控制
        layout.setSpacing(0)
        
        # 使用 QStackedWidget 切换不同状态视图
        self.stacked = QStackedWidget()
        self.stacked.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        # === 页面0: 按钮视图 ===
        self.button_page = QWidget()
        button_layout = QVBoxLayout(self.button_page)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(2)
        
        # 提示文案（可选显示）
        self.hint_label = QLabel()
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: gray; font-size: 11px;")
        button_layout.addWidget(self.hint_label)
        
        # 开始分析按钮
        self.start_button = QPushButton("📊 启动深度像素统计 (Start Deep Analysis)")
        self.start_button.setMinimumHeight(36)
        self.start_button.setMaximumHeight(36)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_button.clicked.connect(self.start_clicked.emit)
        button_layout.addWidget(self.start_button)
        
        self.stacked.addWidget(self.button_page)
        
        # === 页面1: 进度视图 ===
        self.progress_page = QWidget()
        progress_layout = QVBoxLayout(self.progress_page)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(2)
        
        # 状态文字
        self.status_label = QLabel("准备中...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        progress_layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(36)
        self.progress_bar.setMaximumHeight(36)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid palette(mid);
                border-radius: 4px;
                text-align: center;
                background-color: palette(base);
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        self.stacked.addWidget(self.progress_page)
        
        # === 页面2: 完成状态视图 ===
        self.completed_page = QWidget()
        completed_layout = QVBoxLayout(self.completed_page)
        completed_layout.setContentsMargins(0, 0, 0, 0)
        completed_layout.setSpacing(2)
        
        # 完成提示（可选显示）
        self.completed_hint = QLabel()
        self.completed_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.completed_hint.setStyleSheet("color: gray; font-size: 11px;")
        completed_layout.addWidget(self.completed_hint)
        
        # 完成状态标签（与按钮同高）
        self.completed_label = QLabel("✅ 像素统计已完成 (Analysis Completed)")
        self.completed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.completed_label.setMinimumHeight(36)
        self.completed_label.setMaximumHeight(36)
        self.completed_label.setStyleSheet("""
            QLabel {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                color: #4CAF50;
                font-size: 12px;
                font-weight: bold;
                padding: 8px 16px;
            }
        """)
        completed_layout.addWidget(self.completed_label)
        
        self.stacked.addWidget(self.completed_page)
        
        layout.addWidget(self.stacked)
        
        # 默认显示按钮（禁用状态，等待加载样本）
        self.stacked.setCurrentIndex(0)
        self.start_button.setEnabled(False)
        self.hint_label.setText("请先加载数据集")
    
    def set_sample_count(self, count: int, is_large: bool) -> None:
        """设置样本数量"""
        self._sample_count = count
        self._is_large_dataset = is_large
        
        if count == 0:
            # 无样本，禁用按钮
            self.hint_label.setText("请先加载数据集")
            self.start_button.setEnabled(False)
        elif is_large:
            self.hint_label.setText(
                f"数据集较大（{count:,} 个样本），为节省资源请手动开启分析"
            )
            self.start_button.setEnabled(True)
        else:
            self.hint_label.setText("")
            self.start_button.setEnabled(True)
        self.hint_label.setVisible(True)  # 保持占位
    
    def show_button(self) -> None:
        """显示按钮状态"""
        self.stacked.setCurrentIndex(0)
        self.start_button.setEnabled(True)
    
    def show_progress(self) -> None:
        """显示进度状态"""
        self.progress_bar.setValue(0)
        self.status_label.setText("准备中...")
        self.stacked.setCurrentIndex(1)
    
    def set_progress(self, current: int, total: int, message: str = "") -> None:
        """更新进度"""
        if total > 0:
            percentage = int(current / total * 100)
            self.progress_bar.setValue(percentage)
            self.status_label.setText(f"{message} ({current:,}/{total:,})")
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText(message or "准备中...")
    
    def set_completed(self, from_cache: bool = False) -> None:
        """设置为完成状态"""
        if from_cache:
            self.completed_hint.setText("已从缓存加载统计数据")
        else:
            self.completed_hint.setText("")
        self.stacked.setCurrentIndex(2)
    
    def hide_control(self) -> None:
        """隐藏控制器（不再使用，保留接口兼容）"""
        pass  # 不隐藏，保持占位
    
    def show_control(self) -> None:
        """显示控制器"""
        self.setVisible(True)


class AnalysisPanel(QWidget):
    """
    数据分析面板
    
    布局结构（垂直排列，填满整个Tab）：
    - 顶部：数据集概览（外部提供，永远可见）
    - 中部：分析控制器（按钮/进度条，单独放置）
    - 底部：深度图表（可折叠面板，外部提供，独立显示）
    """
    
    # 配置常量
    AUTO_ANALYZE_THRESHOLD: int = 5000  # 自动分析阈值
    
    # 信号
    analysis_started = Signal()
    analysis_finished = Signal()
    analysis_error = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # 状态
        self._current_state: AnalysisState = AnalysisState.IDLE
        self._data_root: Optional[str] = None
        self._sample_count: int = 0
        self._samples_info: list = []
        self._images_dir: str = ""
        self._labels_dir: str = ""
        
        # 元数据管理器
        self.metadata_manager = DatasetMetadataManager()
        
        # 外部组件引用
        self._overview_widget: Optional[QWidget] = None
        self._charts_widget: Optional[QWidget] = None
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """初始化UI - 使用 QScrollArea 填满整个 Tab"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 使用 QScrollArea 包裹，支持内容超出时滚动
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 滚动区域内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(8)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # === 1. 顶部：数据集概览占位（永远可见）===
        self.overview_container = QWidget()
        self.overview_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.overview_layout = QVBoxLayout(self.overview_container)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_layout.setSpacing(0)
        self.content_layout.addWidget(self.overview_container)
        
        # === 2. 中部：分析控制器（单独放置，不与卡片合并）===
        self.control_widget = AnalysisControlWidget()
        self.control_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.content_layout.addWidget(self.control_widget)
        
        # === 3. 底部：深度图表占位（独立显示）===
        self.charts_container = QWidget()
        self.charts_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.charts_layout = QVBoxLayout(self.charts_container)
        self.charts_layout.setContentsMargins(0, 0, 0, 0)
        self.charts_layout.setSpacing(0)
        self.content_layout.addWidget(self.charts_container)
        
        # 底部弹性空间
        self.content_layout.addStretch()
        
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)
    
    def _connect_signals(self) -> None:
        """连接信号"""
        # 控制器的开始按钮
        self.control_widget.start_clicked.connect(self._on_manual_start)
        
        # 元数据管理器信号
        self.metadata_manager.signals.progress.connect(self._on_progress)
        self.metadata_manager.signals.finished.connect(self._on_finished)
        self.metadata_manager.signals.error.connect(self._on_error)
    
    # ==================== 外部组件设置 ====================
    
    def set_overview_widget(self, widget: QWidget) -> None:
        """设置数据集概览组件（顶部，永远可见）"""
        # 清空现有内容
        while self.overview_layout.count():
            item = self.overview_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        self._overview_widget = widget
        self.overview_layout.addWidget(widget)
    
    def set_charts_widget(self, widget: QWidget) -> None:
        """设置深度图表组件（底部，独立显示）"""
        # 清空现有内容
        while self.charts_layout.count():
            item = self.charts_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        self._charts_widget = widget
        self.charts_layout.addWidget(widget)
    
    # ==================== 核心逻辑 ====================
    
    def initialize_statistics_flow(
        self, 
        data_root: str, 
        samples_info: list,
        images_dir: str,
        labels_dir: str
    ) -> None:
        """
        初始化统计流程（智能混合启动策略）
        
        Args:
            data_root: 数据根目录
            samples_info: [(sample_id, dataset_type), ...]
            images_dir: 图像目录
            labels_dir: 标签目录
        """
        self._data_root = data_root
        self._sample_count = len(samples_info)
        self._samples_info = samples_info
        self._images_dir = images_dir
        self._labels_dir = labels_dir
        
        # 设置 metadata_manager 的目录
        self.metadata_manager.set_directories(images_dir, labels_dir)
        
        # 更新控制器显示
        is_large = not self._is_below_threshold()
        self.control_widget.set_sample_count(self._sample_count, is_large)
        self.control_widget.show_control()
        self.control_widget.show_button()
        
        # 设置深度图表为禁用状态（灰显）
        self._set_charts_pending()
        
        # Step 1: 检查缓存
        if self._check_cache_valid(samples_info):
            print("✅ [AnalysisPanel] 缓存有效，直接加载结果")
            self._load_from_cache()
            return
        
        # Step 2: 判断数据量
        if self._is_below_threshold():
            print(f"🔄 [AnalysisPanel] 小数据集 ({self._sample_count} 样本)，自动开始分析")
            self._start_analysis()
        else:
            print(f"⏸️ [AnalysisPanel] 大数据集 ({self._sample_count} 样本)，等待用户手动触发")
            self._current_state = AnalysisState.IDLE
    
    def _check_cache_valid(self, samples_info: list) -> bool:
        """检查缓存是否有效"""
        if not self._data_root:
            return False
        self.metadata_manager.init_database(self._data_root)
        return self.metadata_manager.is_cache_valid(samples_info)
    
    def _is_below_threshold(self) -> bool:
        """判断样本数量是否低于自动分析阈值"""
        return self._sample_count < self.AUTO_ANALYZE_THRESHOLD
    
    def _load_from_cache(self) -> None:
        """从缓存加载结果并显示"""
        self._current_state = AnalysisState.COMPLETED
        self.control_widget.set_completed(from_cache=True)
        self._set_charts_ready()
        self.analysis_finished.emit()
    
    def _set_charts_pending(self) -> None:
        """设置深度图表为待分析状态（灰显/禁用）"""
        if self._charts_widget:
            self._charts_widget.setEnabled(False)
    
    def _set_charts_ready(self) -> None:
        """设置深度图表为就绪状态（启用）"""
        if self._charts_widget:
            self._charts_widget.setEnabled(True)
    
    def _start_analysis(self) -> None:
        """启动后台分析"""
        self._current_state = AnalysisState.RUNNING
        self.control_widget.show_progress()
        self.analysis_started.emit()
        self.metadata_manager.start_calculation(
            self._samples_info,
            self._images_dir,
            self._labels_dir
        )
    
    # ==================== 槽函数 ====================
    
    @Slot()
    def _on_manual_start(self) -> None:
        """用户手动点击开始分析"""
        print("👆 [AnalysisPanel] 用户手动触发分析")
        self._start_analysis()
    
    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, sample_id: str) -> None:
        """进度更新回调"""
        self.control_widget.set_progress(current, total, f"正在分析: {sample_id}")
    
    @Slot()
    def _on_finished(self) -> None:
        """分析完成回调"""
        print("✅ [AnalysisPanel] 分析完成")
        self._current_state = AnalysisState.COMPLETED
        self.control_widget.set_completed(from_cache=False)
        self._set_charts_ready()
        self.analysis_finished.emit()
    
    @Slot(str)
    def _on_error(self, error_msg: str) -> None:
        """分析错误回调"""
        print(f"❌ [AnalysisPanel] 分析错误: {error_msg}")
        self._current_state = AnalysisState.IDLE
        self.control_widget.show_button()
        self.analysis_error.emit(error_msg)
    
    # ==================== 公共方法 ====================
    
    def get_aggregated_stats(self) -> Optional[Dict[str, Any]]:
        """获取聚合统计数据"""
        return self.metadata_manager.get_aggregated_stats()
    
    def stop_analysis(self) -> None:
        """停止分析"""
        self.metadata_manager.stop_calculation()
        self._current_state = AnalysisState.IDLE
        self.control_widget.show_button()
    
    def get_current_state(self) -> AnalysisState:
        """获取当前分析状态"""
        return self._current_state
