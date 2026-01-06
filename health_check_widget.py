# -*- coding: utf-8 -*-
"""
健康检查卡片 (Health Check Card)
汇总数据集中的错误和警告，支持问题过滤和自动修复

布局：
+----------------------------------------------------------+
| ▼ 健康检查 (Health Check)   [ 🔴 5 | 🟠 125 ]            | <--- 标题带统计
+----------------------------------------------------------+
| [ 🔄 重新扫描 ]  [ 🔧 一键清理 ]                          | <--- 顶部工具栏
+----------------------------------------------------------+
| 🔴 尺寸不匹配 (Size Mismatch)              [ 2 项 ] >    | <--- 问题列表
| 🔴 文件损坏 (Corrupt Files)                [ 3 项 ] >    |
| 🟠 空标签样本 (Empty Masks)                [ 120 项 ] >  |
| 🟠 极微小噪点 (<5px Area)                  [ 5 项 ] >    |
+----------------------------------------------------------+
| ( 🟢 1,200 个样本通过检查 )                               | <--- 底部统计
+----------------------------------------------------------+
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor


# ==================== 样式配置 ====================
# 颜色
COLOR_FATAL = "#E57373"      # 柔和红色（严重错误）
COLOR_WARNING = "#FFB74D"    # 琥珀色（警告）
COLOR_SUCCESS = "#81C784"    # 柔和绿色（通过）
COLOR_LABEL = "#666"         # 标签颜色

# 尺寸
ROW_HEIGHT_PX = 26           # 列表项高度（紧凑）
ICON_SIZE_PX = 12            # 图标尺寸
FONT_SIZE_PX = 10            # 字体大小
COUNT_WIDTH_PX = 60          # 数量标签宽度
# ================================================


class IssueLevel(Enum):
    """问题级别枚举"""
    FATAL = "fatal"
    WARNING = "warning"


@dataclass
class IssueTypeConfig:
    """问题类型配置"""
    key: str
    name: str
    description: str
    level: IssueLevel
    auto_fixable: bool = False


# 问题类型配置（key 与 dataset_metadata.py 中的常量一致）
ISSUE_TYPES: Dict[str, IssueTypeConfig] = {
    # === Fatal 级别 ===
    "file_missing": IssueTypeConfig(
        key="file_missing",
        name="文件缺失 (File Missing)",
        description="图像或标签文件不存在",
        level=IssueLevel.FATAL
    ),
    "corrupt_file": IssueTypeConfig(
        key="corrupt_file",
        name="文件损坏 (Corrupt Files)",
        description="无法读取的图像或标签文件",
        level=IssueLevel.FATAL
    ),
    "dimension_mismatch": IssueTypeConfig(
        key="dimension_mismatch",
        name="尺寸不匹配 (Dimension Mismatch)",
        description="图像与标签尺寸不一致",
        level=IssueLevel.FATAL
    ),
    "channel_mismatch": IssueTypeConfig(
        key="channel_mismatch",
        name="通道数异常 (Channel Mismatch)",
        description="图像或标签通道数异常（如 3 vs 4）",
        level=IssueLevel.FATAL
    ),
    "invalid_class_id": IssueTypeConfig(
        key="invalid_class_id",
        name="无效类别ID (Invalid Class ID)",
        description="标签中存在定义外的类别ID",
        level=IssueLevel.FATAL
    ),
    "dtype_mismatch": IssueTypeConfig(
        key="dtype_mismatch",
        name="位深错误 (Dtype Mismatch)",
        description="标签位深错误（如 16bit vs 8bit）",
        level=IssueLevel.FATAL
    ),
    # === Warning 级别 ===
    "empty_mask": IssueTypeConfig(
        key="empty_mask",
        name="空标签样本 (Empty Masks)",
        description="标签全为背景类（无前景目标）",
        level=IssueLevel.WARNING,
        auto_fixable=True
    ),
    "noise_artifact": IssueTypeConfig(
        key="noise_artifact",
        name="极微小噪点 (<5px Area)",
        description="标签包含极小的噪声区域",
        level=IssueLevel.WARNING,
        auto_fixable=True
    ),
    "high_nodata_coverage": IssueTypeConfig(
        key="high_nodata_coverage",
        name="高无数据覆盖 (>80% Nodata)",
        description="黑边/无数据区域超过 80%",
        level=IssueLevel.WARNING,
        auto_fixable=True
    ),
}


class IssueRow(QWidget):
    """问题类型行组件"""
    
    # 信号：点击行
    clicked = Signal(str)  # issue_type
    
    def __init__(self, issue_type: str, count: int, level: IssueLevel, 
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._issue_type = issue_type
        self._count = count
        self._level = level
        self._is_hovered = False
        self._is_selected = False
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        
        # 图标（圆点）
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE_PX, ICON_SIZE_PX)
        color = COLOR_FATAL if self._level == IssueLevel.FATAL else COLOR_WARNING
        self.icon_label.setStyleSheet(f"""
            background-color: {color};
            border-radius: {ICON_SIZE_PX // 2}px;
        """)
        layout.addWidget(self.icon_label)
        
        # 问题描述
        config = ISSUE_TYPES.get(self._issue_type)
        name = config.name if config else self._issue_type
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if config:
            self.name_label.setToolTip(config.description)
        layout.addWidget(self.name_label, 1)
        
        # 数量（格式：[ X 项 ]）
        self.count_label = QLabel(f"[ {self._count} 项 ]")
        self.count_label.setFixedWidth(COUNT_WIDTH_PX)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.count_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
        layout.addWidget(self.count_label)
        
        # 箭头
        self.arrow_label = QLabel(">")
        self.arrow_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: #999;")
        layout.addWidget(self.arrow_label)
        
        self.setFixedHeight(ROW_HEIGHT_PX)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_style()
    
    def _update_style(self) -> None:
        """更新背景样式（与 QTreeWidget 选中效果一致）"""
        if self._is_selected:
            # 选中状态：使用系统高亮色，文字使用高亮文字色
            self.setStyleSheet("background-color: palette(highlight);")
            self.name_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: palette(highlighted-text);")
            self.count_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: palette(highlighted-text);")
            self.arrow_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: palette(highlighted-text);")
        elif self._is_hovered:
            self.setStyleSheet("background-color: palette(light);")
            self.name_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
            self.count_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
            self.arrow_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: #999;")
        else:
            self.setStyleSheet("background-color: transparent;")
            self.name_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
            self.count_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_LABEL};")
            self.arrow_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: #999;")
    
    def set_selected(self, selected: bool) -> None:
        """设置选中状态"""
        self._is_selected = selected
        self._update_style()
    
    def enterEvent(self, event) -> None:
        """鼠标进入"""
        self._is_hovered = True
        self._update_style()
    
    def leaveEvent(self, event) -> None:
        """鼠标离开"""
        self._is_hovered = False
        self._update_style()
    
    def mousePressEvent(self, event) -> None:
        """鼠标点击"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._issue_type)
    
    def update_count(self, count: int) -> None:
        """更新数量"""
        self._count = count
        self.count_label.setText(f"[ {count} 项 ]")


class HealthCheckCard(QWidget):
    """
    健康检查卡片
    
    汇总数据集中的错误和警告，支持问题过滤和自动修复。
    """
    
    # 信号
    filterRequested = Signal(str)   # 请求过滤指定问题类型
    clearFilterRequested = Signal() # 请求清除过滤
    rescanRequested = Signal()      # 请求重新扫描
    autoFixRequested = Signal()     # 请求自动修复
    summaryChanged = Signal(str)    # 摘要变化（供标题栏更新）
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._issues: Dict[str, Dict[str, List[str]]] = {}
        self._rows: Dict[str, IssueRow] = {}
        self._total_samples = 0
        self._passed_samples = 0
        self._current_filter: Optional[str] = None  # 当前过滤的问题类型
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # === 工具栏 ===
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(4)
        toolbar_layout.setContentsMargins(0, 0, 0, 4)
        
        # 重新扫描按钮
        self.btn_rescan = QToolButton()
        self.btn_rescan.setText("🔄 重新扫描 (Re-scan)")
        self.btn_rescan.setToolTip("重新运行健康检查")
        self.btn_rescan.setStyleSheet("""
            QToolButton {
                font-size: 10px;
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 3px;
                background: transparent;
            }
            QToolButton:hover { background-color: palette(light); }
            QToolButton:disabled { color: gray; }
        """)
        self.btn_rescan.clicked.connect(self.rescanRequested.emit)
        toolbar_layout.addWidget(self.btn_rescan)
        
        # 自动修复按钮
        self.btn_autofix = QToolButton()
        self.btn_autofix.setText("🔧 一键清理 (Auto-Fix)")
        self.btn_autofix.setToolTip("自动修复可修复的警告（如删除空样本）")
        self.btn_autofix.setStyleSheet("""
            QToolButton {
                font-size: 10px;
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 3px;
                background: transparent;
            }
            QToolButton:hover { background-color: palette(light); }
            QToolButton:disabled { color: gray; }
        """)
        self.btn_autofix.setEnabled(False)
        self.btn_autofix.clicked.connect(self.autoFixRequested.emit)
        toolbar_layout.addWidget(self.btn_autofix)
        
        # 清除过滤按钮
        self.btn_clear_filter = QToolButton()
        self.btn_clear_filter.setText("✕ 清除过滤")
        self.btn_clear_filter.setToolTip("清除过滤，显示所有样本")
        self.btn_clear_filter.setStyleSheet("""
            QToolButton {
                font-size: 10px;
                padding: 4px 8px;
                border: 1px solid palette(mid);
                border-radius: 3px;
                background: transparent;
            }
            QToolButton:hover { background-color: palette(light); }
            QToolButton:disabled { color: gray; }
        """)
        self.btn_clear_filter.setEnabled(False)
        self.btn_clear_filter.clicked.connect(self._on_clear_filter_clicked)
        toolbar_layout.addWidget(self.btn_clear_filter)
        
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)
        
        # === 问题列表容器 ===
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.list_widget)
        
        # === 底部通过统计 ===
        self.passed_label = QLabel()
        self.passed_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.passed_label.setStyleSheet(f"font-size: {FONT_SIZE_PX}px; color: {COLOR_SUCCESS}; padding: 4px;")
        layout.addWidget(self.passed_label)
        
        # 底部弹性空间
        layout.addStretch()
        
        # 设置尺寸策略
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # 初始状态
        self._update_ui()
    
    def _count_issues(self) -> tuple:
        """统计问题数量，返回 (fatal_count, warning_count, has_fixable)"""
        fatal_count = 0
        warning_count = 0
        has_fixable = False
        
        for level, issues in self._issues.items():
            for issue_type, files in issues.items():
                count = len(files)
                if level == "fatal":
                    fatal_count += count
                else:
                    warning_count += count
                    config = ISSUE_TYPES.get(issue_type)
                    if config and config.auto_fixable and count > 0:
                        has_fixable = True
        
        return fatal_count, warning_count, has_fixable
    
    def _update_ui(self) -> None:
        """更新UI状态"""
        fatal_count, warning_count, has_fixable = self._count_issues()
        
        # 更新自动修复按钮状态
        self.btn_autofix.setEnabled(has_fixable)
        
        # 更新底部通过统计
        if self._total_samples > 0:
            self._passed_samples = self._total_samples - fatal_count - warning_count
            self.passed_label.setText(f"( 🟢 {self._passed_samples:,} 个样本通过检查 )")
            self.passed_label.setVisible(True)
        else:
            self.passed_label.setVisible(False)
        
        # 发射摘要变化信号
        summary = self.get_header_summary()
        self.summaryChanged.emit(summary)
    
    def _rebuild_list(self) -> None:
        """重建问题列表"""
        # 清除旧行
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        
        # 先添加严重错误
        if "fatal" in self._issues:
            for issue_type, files in self._issues["fatal"].items():
                if len(files) > 0:
                    self._add_row(issue_type, len(files), IssueLevel.FATAL)
        
        # 再添加警告
        if "warning" in self._issues:
            for issue_type, files in self._issues["warning"].items():
                if len(files) > 0:
                    self._add_row(issue_type, len(files), IssueLevel.WARNING)
    
    def _add_row(self, issue_type: str, count: int, level: IssueLevel) -> None:
        """添加问题行"""
        row = IssueRow(issue_type, count, level)
        row.clicked.connect(self._on_row_clicked)
        self.list_layout.addWidget(row)
        self._rows[issue_type] = row
    
    def _on_row_clicked(self, issue_type: str) -> None:
        """问题行点击处理（支持切换过滤）"""
        if self._current_filter == issue_type:
            # 再次点击同一行，清除过滤
            self._clear_filter()
        else:
            # 点击新行，应用过滤
            self._current_filter = issue_type
            self.btn_clear_filter.setEnabled(True)
            self._update_row_selection()
            self.filterRequested.emit(issue_type)
    
    def _on_clear_filter_clicked(self) -> None:
        """清除过滤按钮点击"""
        self._clear_filter()
    
    def _clear_filter(self) -> None:
        """清除过滤状态"""
        self._current_filter = None
        self.btn_clear_filter.setEnabled(False)
        self._update_row_selection()
        self.clearFilterRequested.emit()
    
    def _update_row_selection(self) -> None:
        """更新行选中状态的视觉反馈"""
        for issue_type, row in self._rows.items():
            row.set_selected(self._current_filter and issue_type == self._current_filter)
    
    def get_header_summary(self) -> str:
        """
        获取标题栏摘要文本（供折叠面板标题栏显示）
        
        Returns:
            str: 如 "[ 🔴 5 | 🟠 125 ]" 或 "[ 🟢 All Passed ]"
        """
        fatal_count, warning_count, _ = self._count_issues()
        
        if fatal_count > 0 and warning_count > 0:
            return f"[ 🔴 {fatal_count} | 🟠 {warning_count} ]"
        elif fatal_count > 0:
            return f"[ 🔴 {fatal_count} ]"
        elif warning_count > 0:
            return f"[ 🟠 {warning_count} ]"
        else:
            return "[ 🟢 All Passed ]"
    
    def get_header_widget(self) -> QLabel:
        """
        获取标题栏摘要控件（供添加到折叠面板标题栏）
        
        Returns:
            QLabel: 摘要标签控件
        """
        label = QLabel(self.get_header_summary())
        label.setStyleSheet(f"font-size: 10px; color: {COLOR_LABEL};")
        
        # 连接信号以自动更新
        self.summaryChanged.connect(label.setText)
        
        return label
    
    def set_issues(self, issues: Dict[str, Dict[str, List[str]]], total_samples: int = 0) -> None:
        """
        设置问题数据
        
        Args:
            issues: 问题数据，格式：
                {
                    'fatal': {'size_mismatch': ['file1', 'file2'], 'corrupt': []},
                    'warning': {'empty_mask': ['file3', ...], 'noise': ['file10']}
                }
            total_samples: 总样本数（用于计算通过数）
        """
        self._issues = issues
        self._total_samples = total_samples
        self._rebuild_list()
        self._update_ui()
    
    def clear(self) -> None:
        """清空数据"""
        self._issues = {}
        self._total_samples = 0
        self._passed_samples = 0
        self._rebuild_list()
        self._update_ui()
    
    def get_files_by_issue(self, issue_type: str) -> List[str]:
        """获取指定问题类型的文件列表"""
        for level, issues in self._issues.items():
            if issue_type in issues:
                return issues[issue_type]
        return []
