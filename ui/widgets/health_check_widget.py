# -*- coding: utf-8 -*-
"""
健康检查卡片 (Health Check Card)
汇总数据集中的错误和警告，支持问题过滤和自动修复

关键约束：禁止使用 CSS/QSS (setStyleSheet)
必须通过 Qt 原生组件属性或 qtawesome 来实现样式控制
"""

import os
import csv
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QSizePolicy, QFrame, QMenu, QApplication, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QCursor, QAction, QPalette, QColor, QPainter

from ui.widgets.ui_utils import create_flat_button, create_toolbar_separator


# ==================== 颜色配置 ====================
COLOR_FATAL = QColor(229, 115, 115)      # 柔和红色（严重错误）
COLOR_WARNING = QColor(255, 183, 77)     # 琥珀色（警告）
COLOR_SUCCESS = QColor(129, 199, 132)    # 柔和绿色（通过）
COLOR_LABEL = QColor(102, 102, 102)      # 标签颜色

# 尺寸
ROW_HEIGHT_PX = 26
ICON_SIZE_PX = 12
FONT_SIZE_PX = 10
COUNT_WIDTH_PX = 60


# ==================== 系统集成工具函数 (引用 Skill) ====================
from skills.skill_file_utils import reveal_in_explorer, copy_path_to_clipboard


def export_issues_to_csv(
    issues_data: List[Dict[str, Any]], 
    save_path: str,
    data_root: str = ""
) -> bool:
    """导出问题列表到 CSV 文件"""
    if not issues_data or not save_path:
        return False
    
    try:
        with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                '样本ID (Sample ID)',
                '问题类型 (Issue Type)',
                '问题描述 (Description)',
                '图像路径 (Image Path)',
                '标签路径 (Label Path)',
                '详细信息 (Details)'
            ])
            
            for item in issues_data:
                issue_type = item.get('issue_type', '')
                config = ISSUE_TYPES.get(issue_type)
                description = config.description if config else issue_type
                
                writer.writerow([
                    item.get('sample_id', ''),
                    issue_type,
                    description,
                    item.get('image_path', ''),
                    item.get('label_path', ''),
                    item.get('details', '')
                ])
        
        return True
    except Exception as e:
        print(f"⚠️ 导出 CSV 失败: {e}")
        return False


# ==================== 数据类型定义 ====================

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


ISSUE_TYPES: Dict[str, IssueTypeConfig] = {
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
        description="图像或标签通道数异常",
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
        description="标签位深错误",
        level=IssueLevel.FATAL
    ),
    "empty_mask": IssueTypeConfig(
        key="empty_mask",
        name="空标签样本 (Empty Masks)",
        description="标签全为背景类",
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


# ==================== 状态指示器组件 ====================

class StatusDot(QWidget):
    """状态圆点指示器（替代 stylesheet 实现）"""
    
    def __init__(self, color: QColor, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(ICON_SIZE_PX, ICON_SIZE_PX)
    
    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()
    
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


class IssueRow(QWidget):
    """问题类型行组件"""
    
    clicked = Signal(str)
    revealRequested = Signal(str)
    copyPathRequested = Signal(str)
    exportLogRequested = Signal(str)
    
    def __init__(
        self, 
        issue_type: str, 
        count: int, 
        level: IssueLevel, 
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._issue_type = issue_type
        self._count = count
        self._level = level
        self._is_hovered = False
        self._is_selected = False
        self._setup_ui()
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        
        # 状态圆点
        color = COLOR_FATAL if self._level == IssueLevel.FATAL else COLOR_WARNING
        self.status_dot = StatusDot(color)
        layout.addWidget(self.status_dot)
        
        # 问题描述
        config = ISSUE_TYPES.get(self._issue_type)
        name = config.name if config else self._issue_type
        self.name_label = QLabel(name)
        name_font = self.name_label.font()
        name_font.setPointSize(FONT_SIZE_PX)
        self.name_label.setFont(name_font)
        self._set_label_color(self.name_label, COLOR_LABEL)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if config:
            self.name_label.setToolTip(config.description)
        layout.addWidget(self.name_label, 1)
        
        # 数量
        self.count_label = QLabel(f"[ {self._count} 项 ]")
        self.count_label.setFixedWidth(COUNT_WIDTH_PX)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        count_font = self.count_label.font()
        count_font.setPointSize(FONT_SIZE_PX)
        self.count_label.setFont(count_font)
        self._set_label_color(self.count_label, COLOR_LABEL)
        layout.addWidget(self.count_label)
        
        # 箭头
        self.arrow_label = QLabel(">")
        arrow_font = self.arrow_label.font()
        arrow_font.setPointSize(FONT_SIZE_PX)
        self.arrow_label.setFont(arrow_font)
        self._set_label_color(self.arrow_label, QColor(153, 153, 153))
        layout.addWidget(self.arrow_label)
        
        self.setFixedHeight(ROW_HEIGHT_PX)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    
    def _set_label_color(self, label: QLabel, color: QColor) -> None:
        """使用 palette 设置标签颜色"""
        palette = label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        label.setPalette(palette)
    
    def _update_style(self) -> None:
        """更新背景样式"""
        if self._is_selected:
            self.setAutoFillBackground(True)
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, palette.color(QPalette.ColorRole.Highlight))
            self.setPalette(palette)
            # 选中时文字使用高亮文字色
            highlight_text = self.palette().color(QPalette.ColorRole.HighlightedText)
            self._set_label_color(self.name_label, highlight_text)
            self._set_label_color(self.count_label, highlight_text)
            self._set_label_color(self.arrow_label, highlight_text)
        elif self._is_hovered:
            self.setAutoFillBackground(True)
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, palette.color(QPalette.ColorRole.Light))
            self.setPalette(palette)
            self._set_label_color(self.name_label, COLOR_LABEL)
            self._set_label_color(self.count_label, COLOR_LABEL)
            self._set_label_color(self.arrow_label, QColor(153, 153, 153))
        else:
            self.setAutoFillBackground(False)
            self._set_label_color(self.name_label, COLOR_LABEL)
            self._set_label_color(self.count_label, COLOR_LABEL)
            self._set_label_color(self.arrow_label, QColor(153, 153, 153))
    
    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_style()
    
    def enterEvent(self, event) -> None:
        self._is_hovered = True
        self._update_style()
    
    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self._update_style()
    
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._issue_type)
    
    def update_count(self, count: int) -> None:
        self._count = count
        self.count_label.setText(f"[ {count} 项 ]")
    
    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        
        action_reveal = QAction("📂 在文件管理器中显示", self)
        action_reveal.triggered.connect(lambda: self.revealRequested.emit(self._issue_type))
        menu.addAction(action_reveal)
        
        action_copy = QAction("📋 复制路径", self)
        action_copy.triggered.connect(lambda: self.copyPathRequested.emit(self._issue_type))
        menu.addAction(action_copy)
        
        menu.addSeparator()
        
        action_export = QAction("📄 导出问题日志", self)
        action_export.triggered.connect(lambda: self.exportLogRequested.emit(self._issue_type))
        menu.addAction(action_export)
        
        menu.exec(self.mapToGlobal(pos))


class HealthCheckCard(QWidget):
    """
    健康检查卡片
    
    工具栏使用 QToolButton + autoRaise 实现扁平按钮风格
    """
    
    filterRequested = Signal(str)
    clearFilterRequested = Signal()
    rescanRequested = Signal()
    autoFixRequested = Signal()
    summaryChanged = Signal(str)
    requestFocusOnRect = Signal(QRect)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._issues: Dict[str, Dict[str, List[str]]] = {}
        self._issue_details: Dict[str, Dict[str, Any]] = {}
        self._rows: Dict[str, IssueRow] = {}
        self._total_samples = 0
        self._passed_samples = 0
        self._current_filter: Optional[str] = None
        self._data_root: str = ""
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # === 工具栏（使用 flat buttons）===
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(4)
        toolbar_layout.setContentsMargins(0, 0, 0, 4)
        
        # Re-scan 按钮
        self.btn_rescan = create_flat_button(
            text="Re-scan",
            icon_name='fa5s.search',
            icon_color='default',
            tooltip="重新运行健康检查",
            on_clicked=self.rescanRequested.emit
        )
        toolbar_layout.addWidget(self.btn_rescan)
        
        # Auto-Fix 按钮
        self.btn_autofix = create_flat_button(
            text="Auto-Fix",
            icon_name='fa5s.magic',
            icon_color='default',
            tooltip="自动修复可修复的警告",
            enabled=False,
            on_clicked=self.autoFixRequested.emit
        )
        toolbar_layout.addWidget(self.btn_autofix)
        
        # 分隔线
        toolbar_layout.addWidget(create_toolbar_separator())
        
        # Clear Filter 按钮
        self.btn_clear_filter = create_flat_button(
            text="Clear Filter",
            icon_name='fa5s.filter',
            icon_color='default',
            tooltip="清除过滤，显示所有样本",
            enabled=False,
            on_clicked=self._on_clear_filter_clicked
        )
        toolbar_layout.addWidget(self.btn_clear_filter)
        
        # Export 按钮
        self.btn_export = create_flat_button(
            text="Export",
            icon_name='fa5s.file-export',
            icon_color='default',
            tooltip="导出所有问题到 CSV 文件",
            on_clicked=self.export_all_issues
        )
        toolbar_layout.addWidget(self.btn_export)
        
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
        passed_font = self.passed_label.font()
        passed_font.setPointSize(FONT_SIZE_PX)
        self.passed_label.setFont(passed_font)
        self._set_label_color(self.passed_label, COLOR_SUCCESS)
        layout.addWidget(self.passed_label)
        
        layout.addStretch()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_ui()
    
    def _set_label_color(self, label: QLabel, color: QColor) -> None:
        palette = label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        label.setPalette(palette)
    
    def _count_issues(self) -> tuple:
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
        fatal_count, warning_count, has_fixable = self._count_issues()
        self.btn_autofix.setEnabled(has_fixable)
        
        if self._total_samples > 0:
            self._passed_samples = self._total_samples - fatal_count - warning_count
            self.passed_label.setText(f"( 🟢 {self._passed_samples:,} 个样本通过检查 )")
            self.passed_label.setVisible(True)
        else:
            self.passed_label.setVisible(False)
        
        summary = self.get_header_summary()
        self.summaryChanged.emit(summary)
    
    def _rebuild_list(self) -> None:
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        
        if "fatal" in self._issues:
            for issue_type, files in self._issues["fatal"].items():
                if len(files) > 0:
                    self._add_row(issue_type, len(files), IssueLevel.FATAL)
        
        if "warning" in self._issues:
            for issue_type, files in self._issues["warning"].items():
                if len(files) > 0:
                    self._add_row(issue_type, len(files), IssueLevel.WARNING)
    
    def _add_row(self, issue_type: str, count: int, level: IssueLevel) -> None:
        row = IssueRow(issue_type, count, level)
        row.clicked.connect(self._on_row_clicked)
        row.revealRequested.connect(self._on_reveal_requested)
        row.copyPathRequested.connect(self._on_copy_path_requested)
        row.exportLogRequested.connect(self._on_export_log_requested)
        self.list_layout.addWidget(row)
        self._rows[issue_type] = row
    
    def _on_row_clicked(self, issue_type: str) -> None:
        if self._current_filter == issue_type:
            self._clear_filter()
        else:
            self._current_filter = issue_type
            self.btn_clear_filter.setEnabled(True)
            self._update_row_selection()
            self.filterRequested.emit(issue_type)
    
    def _on_clear_filter_clicked(self) -> None:
        self._clear_filter()
    
    def _clear_filter(self) -> None:
        self._current_filter = None
        self.btn_clear_filter.setEnabled(False)
        self._update_row_selection()
        self.clearFilterRequested.emit()
    
    def _update_row_selection(self) -> None:
        for issue_type, row in self._rows.items():
            row.set_selected(self._current_filter and issue_type == self._current_filter)
    
    def get_header_summary(self) -> str:
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
        label = QLabel(self.get_header_summary())
        label_font = label.font()
        label_font.setPointSize(10)
        label.setFont(label_font)
        self._set_label_color(label, COLOR_LABEL)
        self.summaryChanged.connect(label.setText)
        return label
    
    def set_issues(self, issues: Dict[str, Dict[str, List[str]]], total_samples: int = 0) -> None:
        self._issues = issues
        self._total_samples = total_samples
        self._rebuild_list()
        self._update_ui()
    
    def clear(self) -> None:
        self._issues = {}
        self._total_samples = 0
        self._passed_samples = 0
        self._rebuild_list()
        self._update_ui()
    
    def get_files_by_issue(self, issue_type: str) -> List[str]:
        for level, issues in self._issues.items():
            if issue_type in issues:
                return issues[issue_type]
        return []
    
    def set_data_root(self, data_root: str) -> None:
        self._data_root = data_root
    
    def set_issue_details(self, details: Dict[str, Dict[str, Any]]) -> None:
        self._issue_details = details

    
    def _on_reveal_requested(self, issue_type: str) -> None:
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        first_file = files[0]
        file_path = first_file
        
        if self._data_root and not os.path.isabs(first_file):
            for subdir in ['JPEGImages', 'SegmentationClass', 'images', 'labels']:
                test_path = os.path.join(self._data_root, subdir, first_file)
                if os.path.exists(test_path):
                    file_path = test_path
                    break
                for ext in ['.jpg', '.png', '.jpeg', '.tif']:
                    test_path_ext = test_path + ext
                    if os.path.exists(test_path_ext):
                        file_path = test_path_ext
                        break
        
        if not reveal_in_explorer(file_path):
            QMessageBox.warning(
                self, 
                "无法打开", 
                f"无法在文件管理器中显示文件:\n{file_path}"
            )
    
    def _on_copy_path_requested(self, issue_type: str) -> None:
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        paths = []
        for f in files:
            if self._data_root and not os.path.isabs(f):
                paths.append(os.path.join(self._data_root, f))
            else:
                paths.append(f)
        
        path_text = '\n'.join(paths)
        if copy_path_to_clipboard(path_text):
            QMessageBox.information(self, "已复制", f"已复制 {len(files)} 个文件路径到剪贴板")
    
    def _on_export_log_requested(self, issue_type: str) -> None:
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        config = ISSUE_TYPES.get(issue_type)
        default_name = f"health_check_{issue_type}.csv"
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出问题日志", default_name, "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        
        if not save_path:
            return
        
        export_data = []
        for sample_id in files:
            item = {
                'sample_id': sample_id,
                'issue_type': issue_type,
                'image_path': '',
                'label_path': '',
                'details': ''
            }
            
            if sample_id in self._issue_details:
                details = self._issue_details[sample_id]
                item['details'] = str(details.get(issue_type, ''))
            
            if self._data_root:
                for ext in ['.jpg', '.png', '.jpeg']:
                    img_path = os.path.join(self._data_root, 'JPEGImages', f"{sample_id}{ext}")
                    if os.path.exists(img_path):
                        item['image_path'] = img_path
                        break
                for ext in ['.png', '.tif']:
                    lbl_path = os.path.join(self._data_root, 'SegmentationClass', f"{sample_id}{ext}")
                    if os.path.exists(lbl_path):
                        item['label_path'] = lbl_path
                        break
            
            export_data.append(item)
        
        if export_issues_to_csv(export_data, save_path, self._data_root):
            QMessageBox.information(self, "导出成功", f"已导出 {len(export_data)} 条记录到:\n{save_path}")
        else:
            QMessageBox.warning(self, "导出失败", "导出 CSV 文件时发生错误")
    
    def export_all_issues(self) -> None:
        all_issues = []
        for level, issues in self._issues.items():
            for issue_type, files in issues.items():
                for sample_id in files:
                    all_issues.append({
                        'sample_id': sample_id,
                        'issue_type': issue_type,
                        'image_path': '',
                        'label_path': '',
                        'details': ''
                    })
        
        if not all_issues:
            QMessageBox.information(self, "提示", "没有问题需要导出")
            return
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出所有问题", "health_check_report.csv", "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        
        if not save_path:
            return
        
        if export_issues_to_csv(all_issues, save_path, self._data_root):
            QMessageBox.information(self, "导出成功", f"已导出 {len(all_issues)} 条记录到:\n{save_path}")
        else:
            QMessageBox.warning(self, "导出失败", "导出 CSV 文件时发生错误")
