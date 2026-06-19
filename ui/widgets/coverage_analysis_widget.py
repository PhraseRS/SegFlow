# -*- coding: utf-8 -*-
"""
覆盖率分析卡片 (Coverage Analysis Card)
展示每个类别在单张图像中的占比分布 (Occupancy Ratio)
帮助用户发现"稀疏样本"或"全图充满样本"
"""

from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QToolTip
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent


# ==================== 统一样式配置（与 ClassDistributionChart 保持一致）====================
# 条形尺寸
BAR_HEIGHT_PX = 10          # 条形高度
BAR_GAP_PX = 6              # 条形间距
ROW_HEIGHT_PX = 16          # 行高

# 标签尺寸
LABEL_WIDTH_PX = 24         # Y轴标签宽度

# 文字样式
# 注意：Matplotlib fontsize 单位是 pt，Qt CSS font-size 单位是 px
# 7pt ≈ 9.3px，为保持视觉一致，Qt 使用 9px
LABEL_FONT_SIZE_PX = 9      # Y轴标签字号（px，对应 Matplotlib 7pt）
LEGEND_FONT_SIZE = 10       # 图例字号（与控制栏 Px/Img/Log/NoBG 一致）
LEGEND_BLOCK_SIZE = 10      # 图例Color块尺寸

# Color
LABEL_COLOR = '#666'        # 标签Color
# ================================================


class CoverageBin(Enum):
    """覆盖率分箱枚举"""
    SPARSE = "sparse"      # < 10%
    MODERATE = "moderate"  # 10% - 50%
    DENSE = "dense"        # 50% - 90%
    FULL = "full"          # > 90%


@dataclass
class BinConfig:
    """分箱配置"""
    name: str
    min_ratio: float
    max_ratio: float
    color: str
    description: str


# 分箱配置
BIN_CONFIGS: Dict[CoverageBin, BinConfig] = {
    CoverageBin.SPARSE: BinConfig(
        name="Sparse",
        min_ratio=0.0,
        max_ratio=0.1,
        color="#B0BEC5",  # 浅灰色
        description="Sparse (<10%)"
    ),
    CoverageBin.MODERATE: BinConfig(
        name="Moderate", 
        min_ratio=0.1,
        max_ratio=0.5,
        color="#4CAF50",  # 绿色
        description="Moderate (10%-50%)"
    ),
    CoverageBin.DENSE: BinConfig(
        name="Dense",
        min_ratio=0.5,
        max_ratio=0.9,
        color="#2E7D32",  # 深绿色
        description="Dense (50%-90%)"
    ),
    CoverageBin.FULL: BinConfig(
        name="Full",
        min_ratio=0.9,
        max_ratio=1.0,
        color="#FF9800",  # 警示橙色
        description="Full (>90%)"
    ),
}


@dataclass
class ClassBinStats:
    """单个类别的分箱统计"""
    class_id: str
    class_name: str
    total_images: int  # 包含该类别的图像总数
    bin_counts: Dict[CoverageBin, int]  # 各分箱的图像数量


class SegmentedHeatmapBar(QWidget):
    """分段热力条组件"""
    
    # 信号：点击某个分段
    segment_clicked = Signal(str, str)  # (class_id, bin_name)
    
    # 使用模块级样式配置
    MIN_SEGMENT_WIDTH = 2   # 最小分段宽度（像素）
    
    def __init__(self, class_stats: ClassBinStats, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._stats = class_stats
        self._hover_bin: Optional[CoverageBin] = None
        self._segment_rects: Dict[CoverageBin, QRect] = {}
        
        self.setMinimumHeight(BAR_HEIGHT_PX)
        self.setMaximumHeight(BAR_HEIGHT_PX)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
    
    def set_stats(self, stats: ClassBinStats) -> None:
        """更新统计数据"""
        self._stats = stats
        self.update()
    
    def paintEvent(self, event) -> None:
        """绘制热力条"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        if self._stats.total_images == 0:
            # 无数据，绘制空条
            painter.fillRect(0, 0, width, height, QColor("#E0E0E0"))
            painter.setPen(QColor("#999"))
            painter.drawText(QRect(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, self.tr("N/A"))
            return
        
        # 计算各分段宽度（使用完整宽度，无边框）
        self._segment_rects.clear()
        x = 0
        
        for bin_type in [CoverageBin.SPARSE, CoverageBin.MODERATE, CoverageBin.DENSE, CoverageBin.FULL]:
            count = self._stats.bin_counts.get(bin_type, 0)
            if count == 0:
                continue
            
            # 计算宽度比例
            ratio = count / self._stats.total_images
            segment_width = max(int(width * ratio), self.MIN_SEGMENT_WIDTH)
            
            # 确保不超出边界
            if x + segment_width > width:
                segment_width = width - x
            
            if segment_width <= 0:
                continue
            
            # 获取Color
            config = BIN_CONFIGS[bin_type]
            color = QColor(config.color)
            
            # 悬停高亮
            if self._hover_bin == bin_type:
                color = color.lighter(120)
            
            # 绘制分段（无边框，使用完整高度）
            rect = QRect(x, 0, segment_width, height)
            painter.fillRect(rect, color)
            self._segment_rects[bin_type] = rect
            
            x += segment_width
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动，更新悬停状态和 Tooltip"""
        pos = event.pos()
        new_hover = None
        
        for bin_type, rect in self._segment_rects.items():
            if rect.contains(pos):
                new_hover = bin_type
                break
        
        if new_hover != self._hover_bin:
            self._hover_bin = new_hover
            self.update()
            
            if new_hover:
                config = BIN_CONFIGS[new_hover]
                count = self._stats.bin_counts.get(new_hover, 0)
                tooltip = f"{self.tr(config.description)}: {count} {self.tr('Images')}"
                QToolTip.showText(event.globalPos(), tooltip, self)
            else:
                QToolTip.hideText()
    
    def leaveEvent(self, event) -> None:
        """鼠标离开"""
        self._hover_bin = None
        self.update()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标点击"""
        if event.button() == Qt.MouseButton.LeftButton and self._hover_bin:
            self.segment_clicked.emit(
                self._stats.class_id, 
                BIN_CONFIGS[self._hover_bin].name
            )


class ClassCoverageRow(QWidget):
    """单个类别的覆盖率行"""
    
    # 使用模块级样式配置
    segment_clicked = Signal(str, str)
    
    def __init__(self, class_stats: ClassBinStats, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._stats = class_stats
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 类别名标签
        self.label = QLabel(f"C{self._stats.class_id}")
        self.label.setFixedWidth(LABEL_WIDTH_PX)
        self.label.setStyleSheet(f"font-size: {LABEL_FONT_SIZE_PX}px; color: {LABEL_COLOR};")
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)
        
        # 热力条（占据剩余空间，不显示数值）
        self.bar = SegmentedHeatmapBar(self._stats)
        self.bar.segment_clicked.connect(self.segment_clicked.emit)
        layout.addWidget(self.bar, 1)
        
        self.setFixedHeight(ROW_HEIGHT_PX)
    
    def update_stats(self, stats: ClassBinStats) -> None:
        """更新统计数据"""
        self._stats = stats
        self.label.setText(f"C{stats.class_id}")
        self.bar.set_stats(stats)


class CoverageAnalysisCard(QWidget):
    """
    覆盖率分析卡片
    
    展示每个类别在单张图像中的占比分布，使用分段热力条可视化。
    布局与 ClassDistributionWidget 保持一致，由外层 AnalysisPanel 统一控制滚动。
    """
    
    # 信号
    class_bin_clicked = Signal(str, str)  # (class_id, bin_name)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._class_stats: Dict[str, ClassBinStats] = {}
        self._rows: Dict[str, ClassCoverageRow] = {}
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI - 与 ClassDistributionWidget 布局一致"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # 说明文字
        self.desc_label = QLabel(self.tr("展示每个类别在单张图像中的像素占比分布，帮助发现稀疏样本或全图充满的异常样本"))
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(self.desc_label)

        # 图例（与控制栏字号一致）
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(6)
        legend_layout.setContentsMargins(0, 0, 0, 2)
        
        for bin_type in [CoverageBin.SPARSE, CoverageBin.MODERATE, CoverageBin.DENSE, CoverageBin.FULL]:
            config = BIN_CONFIGS[bin_type]
            
            # Color块
            color_block = QLabel()
            color_block.setFixedSize(LEGEND_BLOCK_SIZE, LEGEND_BLOCK_SIZE)
            color_block.setStyleSheet(f"background-color: {config.color}; border: 1px solid #ccc;")
            legend_layout.addWidget(color_block)
            
            # 标签
            label = QLabel(self.tr(config.name))
            label.setStyleSheet(f"font-size: {LEGEND_FONT_SIZE}px; color: {LABEL_COLOR};")
            legend_layout.addWidget(label)
        
        legend_layout.addStretch()
        layout.addLayout(legend_layout)
        
        # 内容容器（不使用 QScrollArea，由外层统一控制滚动）
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 空状态Tip
        self.empty_label = QLabel(self.tr("No Data"))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: gray; font-size: 11px; padding: 10px;")
        self.content_layout.addWidget(self.empty_label)
        
        layout.addWidget(self.content_widget, 0, Qt.AlignmentFlag.AlignTop)
        
        # 底部弹性空间
        layout.addStretch()
        
        # 设置尺寸策略 - Fixed 高度，不被拉伸
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def _calculate_bins(self, image_records: List[Dict[str, Any]]) -> Dict[str, ClassBinStats]:
        """
        计算分箱统计
        
        Args:
            image_records: 单图记录列表，每条记录包含 class_ratios: {class_id: ratio}
        
        Returns:
            Dict[str, ClassBinStats]: 各类别的分箱统计
        """
        # 收集所有类别
        all_classes: Dict[str, Dict[CoverageBin, int]] = {}
        class_image_counts: Dict[str, int] = {}
        
        for record in image_records:
            class_ratios = record.get('class_ratios', {})
            
            for class_id, ratio in class_ratios.items():
                if ratio <= 0:
                    continue  # 跳过占比为0的类别
                
                # 初始化
                if class_id not in all_classes:
                    all_classes[class_id] = {b: 0 for b in CoverageBin}
                    class_image_counts[class_id] = 0
                
                class_image_counts[class_id] += 1
                
                # 分箱
                if ratio < 0.1:
                    all_classes[class_id][CoverageBin.SPARSE] += 1
                elif ratio < 0.5:
                    all_classes[class_id][CoverageBin.MODERATE] += 1
                elif ratio < 0.9:
                    all_classes[class_id][CoverageBin.DENSE] += 1
                else:
                    all_classes[class_id][CoverageBin.FULL] += 1
        
        # 构建结果
        result: Dict[str, ClassBinStats] = {}
        for class_id in sorted(all_classes.keys(), key=lambda x: int(x) if x.isdigit() else x):
            result[class_id] = ClassBinStats(
                class_id=class_id,
                class_name=f"Class {class_id}",
                total_images=class_image_counts[class_id],
                bin_counts=all_classes[class_id]
            )
        
        return result
    
    def set_data(self, image_records: List[Dict[str, Any]]) -> None:
        """
        设置数据
        
        Args:
            image_records: 单图记录列表，格式：
                [{'class_ratios': {'0': 0.8, '1': 0.1, ...}}, ...]
        """
        # 计算分箱
        self._class_stats = self._calculate_bins(image_records)
        
        # 隐藏空状态Tip
        self.empty_label.setVisible(len(self._class_stats) == 0)
        
        # 清除旧行
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        
        # 创建新行
        for class_id, stats in self._class_stats.items():
            row = ClassCoverageRow(stats)
            row.segment_clicked.connect(self.class_bin_clicked.emit)
            self.content_layout.addWidget(row)
            self._rows[class_id] = row
    
    def clear(self) -> None:
        """清空数据"""
        self._class_stats.clear()
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self.empty_label.setVisible(True)
    
    def get_class_stats(self, class_id: str) -> Optional[ClassBinStats]:
        """获取指定类别的统计数据"""
        return self._class_stats.get(class_id)
