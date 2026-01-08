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

import os
import sys
import csv
import subprocess
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QSizePolicy, QFrame, QMenu, QApplication, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QCursor, QAction


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


# ==================== 系统集成工具函数 ====================

def reveal_in_explorer(file_path: str) -> bool:
    """
    在系统文件管理器中显示文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        bool: 是否成功
    """
    if not file_path:
        return False
    
    # 规范化路径
    file_path = os.path.normpath(file_path)
    
    # 检查文件/目录是否存在
    if not os.path.exists(file_path):
        # 尝试打开父目录
        parent_dir = os.path.dirname(file_path)
        if os.path.exists(parent_dir):
            file_path = parent_dir
        else:
            return False
    
    try:
        if sys.platform == 'win32':
            # Windows: explorer /select, <path>
            if os.path.isfile(file_path):
                subprocess.run(['explorer', '/select,', file_path], check=False)
            else:
                subprocess.run(['explorer', file_path], check=False)
        elif sys.platform == 'darwin':
            # macOS: open -R <path>
            subprocess.run(['open', '-R', file_path], check=False)
        else:
            # Linux: xdg-open (打开所在目录)
            if os.path.isfile(file_path):
                subprocess.run(['xdg-open', os.path.dirname(file_path)], check=False)
            else:
                subprocess.run(['xdg-open', file_path], check=False)
        return True
    except Exception as e:
        print(f"⚠️ 打开文件管理器失败: {e}")
        return False


def copy_path_to_clipboard(file_path: str) -> bool:
    """
    复制文件路径到剪贴板
    
    Args:
        file_path: 文件路径
    
    Returns:
        bool: 是否成功
    """
    if not file_path:
        return False
    
    try:
        clipboard = QApplication.clipboard()
        clipboard.setText(os.path.normpath(file_path))
        return True
    except Exception as e:
        print(f"⚠️ 复制到剪贴板失败: {e}")
        return False


def export_issues_to_csv(
    issues_data: List[Dict[str, Any]], 
    save_path: str,
    data_root: str = ""
) -> bool:
    """
    导出问题列表到 CSV 文件
    
    Args:
        issues_data: 问题数据列表，每项包含：
            - sample_id: 样本ID
            - issue_type: 问题类型
            - image_path: 图像路径
            - label_path: 标签路径
            - details: 详细信息（可选）
        save_path: 保存路径
        data_root: 数据根目录（用于计算相对路径）
    
    Returns:
        bool: 是否成功
    """
    if not issues_data or not save_path:
        return False
    
    try:
        with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                '样本ID (Sample ID)',
                '问题类型 (Issue Type)',
                '问题描述 (Description)',
                '图像路径 (Image Path)',
                '标签路径 (Label Path)',
                '详细信息 (Details)'
            ])
            
            # 写入数据
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
    # 信号：右键菜单操作
    revealRequested = Signal(str)      # 请求在文件管理器中显示
    copyPathRequested = Signal(str)    # 请求复制路径
    exportLogRequested = Signal(str)   # 请求导出问题日志
    
    def __init__(self, issue_type: str, count: int, level: IssueLevel, 
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._issue_type = issue_type
        self._count = count
        self._level = level
        self._is_hovered = False
        self._is_selected = False
        self._setup_ui()
        
        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
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
    
    def _show_context_menu(self, pos) -> None:
        """显示右键菜单"""
        menu = QMenu(self)
        
        # 在文件管理器中显示
        action_reveal = QAction("📂 在文件管理器中显示 (Reveal in Explorer)", self)
        action_reveal.triggered.connect(lambda: self.revealRequested.emit(self._issue_type))
        menu.addAction(action_reveal)
        
        # 复制路径
        action_copy = QAction("📋 复制路径 (Copy Path)", self)
        action_copy.triggered.connect(lambda: self.copyPathRequested.emit(self._issue_type))
        menu.addAction(action_copy)
        
        menu.addSeparator()
        
        # 导出问题日志
        action_export = QAction("📄 导出问题日志 (Export Issue Log)", self)
        action_export.triggered.connect(lambda: self.exportLogRequested.emit(self._issue_type))
        menu.addAction(action_export)
        
        menu.exec(self.mapToGlobal(pos))


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
    # 新增信号
    requestFocusOnRect = Signal(QRect)  # 请求聚焦到指定区域（用于噪点高亮）
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._issues: Dict[str, Dict[str, List[str]]] = {}
        self._issue_details: Dict[str, Dict[str, Any]] = {}  # 存储详细信息（如噪点位置）
        self._rows: Dict[str, IssueRow] = {}
        self._total_samples = 0
        self._passed_samples = 0
        self._current_filter: Optional[str] = None  # 当前过滤的问题类型
        self._data_root: str = ""  # 数据根目录
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
        
        # 导出报告按钮
        self.btn_export = QToolButton()
        self.btn_export.setText("📄 导出")
        self.btn_export.setToolTip("导出所有问题到 CSV 文件")
        self.btn_export.setStyleSheet("""
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
        self.btn_export.clicked.connect(self.export_all_issues)
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
        # 连接右键菜单信号
        row.revealRequested.connect(self._on_reveal_requested)
        row.copyPathRequested.connect(self._on_copy_path_requested)
        row.exportLogRequested.connect(self._on_export_log_requested)
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
    
    def set_data_root(self, data_root: str) -> None:
        """设置数据根目录"""
        self._data_root = data_root
    
    def set_issue_details(self, details: Dict[str, Dict[str, Any]]) -> None:
        """
        设置问题详细信息（如噪点位置等）
        
        Args:
            details: {sample_id: {issue_type: detail_info, ...}, ...}
        """
        self._issue_details = details
    
    def _on_reveal_requested(self, issue_type: str) -> None:
        """处理"在文件管理器中显示"请求"""
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        # 显示第一个文件
        first_file = files[0]
        
        # 尝试构建完整路径
        file_path = first_file
        if self._data_root and not os.path.isabs(first_file):
            # 尝试在常见目录中查找
            for subdir in ['JPEGImages', 'SegmentationClass', 'images', 'labels']:
                test_path = os.path.join(self._data_root, subdir, first_file)
                if os.path.exists(test_path):
                    file_path = test_path
                    break
                # 尝试添加扩展名
                for ext in ['.jpg', '.png', '.jpeg', '.tif']:
                    test_path_ext = test_path + ext
                    if os.path.exists(test_path_ext):
                        file_path = test_path_ext
                        break
        
        if not reveal_in_explorer(file_path):
            QMessageBox.warning(
                self, 
                "无法打开", 
                f"无法在文件管理器中显示文件:\n{file_path}\n\n文件可能已被删除或移动。"
            )
    
    def _on_copy_path_requested(self, issue_type: str) -> None:
        """处理"复制路径"请求"""
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        # 复制所有文件路径（每行一个）
        paths = []
        for f in files:
            if self._data_root and not os.path.isabs(f):
                paths.append(os.path.join(self._data_root, f))
            else:
                paths.append(f)
        
        path_text = '\n'.join(paths)
        if copy_path_to_clipboard(path_text):
            # 显示简短提示
            count = len(files)
            QMessageBox.information(
                self, 
                "已复制", 
                f"已复制 {count} 个文件路径到剪贴板"
            )
    
    def _find_sample_paths(self, sample_id: str) -> tuple:
        """
        查找样本的图像和标签路径
        
        Args:
            sample_id: 样本ID
        
        Returns:
            tuple: (image_path, label_path)
        """
        image_path = ''
        label_path = ''
        
        if not self._data_root:
            return image_path, label_path
        
        # 图像目录候选
        image_dirs = ['JPEGImages', 'images', 'img']
        # 标签目录候选
        label_dirs = ['SegmentationClass', 'labels', 'masks']
        # 图像扩展名
        image_exts = ['.jpg', '.png', '.jpeg', '.tif', '.tiff', '.bmp']
        # 标签扩展名
        label_exts = ['.png', '.tif', '.tiff']
        
        # 查找图像路径
        for img_dir in image_dirs:
            dir_path = os.path.join(self._data_root, img_dir)
            if not os.path.isdir(dir_path):
                continue
            for ext in image_exts:
                img_path = os.path.join(dir_path, f"{sample_id}{ext}")
                if os.path.exists(img_path):
                    image_path = img_path
                    break
            if image_path:
                break
        
        # 查找标签路径
        for lbl_dir in label_dirs:
            dir_path = os.path.join(self._data_root, lbl_dir)
            if not os.path.isdir(dir_path):
                continue
            for ext in label_exts:
                lbl_path = os.path.join(dir_path, f"{sample_id}{ext}")
                if os.path.exists(lbl_path):
                    label_path = lbl_path
                    break
            if label_path:
                break
        
        return image_path, label_path
    
    def _on_export_log_requested(self, issue_type: str) -> None:
        """处理"导出问题日志"请求"""
        files = self.get_files_by_issue(issue_type)
        if not files:
            QMessageBox.information(self, "提示", f"没有 {issue_type} 类型的问题文件")
            return
        
        # 选择保存路径
        config = ISSUE_TYPES.get(issue_type)
        default_name = f"health_check_{issue_type}.csv"
        
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出问题日志",
            default_name,
            "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        
        if not save_path:
            return
        
        # 构建导出数据
        export_data = []
        for sample_id in files:
            # 使用统一的路径查找方法
            image_path, label_path = self._find_sample_paths(sample_id)
            
            item = {
                'sample_id': sample_id,
                'issue_type': issue_type,
                'image_path': image_path,
                'label_path': label_path,
                'details': ''
            }
            
            # 尝试获取详细信息
            if sample_id in self._issue_details:
                details = self._issue_details[sample_id]
                item['details'] = str(details.get(issue_type, ''))
            
            export_data.append(item)
        
        # 导出
        if export_issues_to_csv(export_data, save_path, self._data_root):
            QMessageBox.information(
                self, 
                "导出成功", 
                f"已导出 {len(export_data)} 条记录到:\n{save_path}"
            )
        else:
            QMessageBox.warning(self, "导出失败", "导出 CSV 文件时发生错误")
    
    def export_all_issues(self) -> None:
        """导出所有问题到 CSV"""
        # 收集所有问题
        all_issues = []
        for level, issues in self._issues.items():
            for issue_type, files in issues.items():
                for sample_id in files:
                    # 使用统一的路径查找方法
                    image_path, label_path = self._find_sample_paths(sample_id)
                    
                    item = {
                        'sample_id': sample_id,
                        'issue_type': issue_type,
                        'image_path': image_path,
                        'label_path': label_path,
                        'details': ''
                    }
                    
                    # 尝试获取详细信息
                    if sample_id in self._issue_details:
                        details = self._issue_details[sample_id]
                        item['details'] = str(details.get(issue_type, ''))
                    
                    all_issues.append(item)
        
        if not all_issues:
            QMessageBox.information(self, "提示", "没有问题需要导出")
            return
        
        # 选择保存路径
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出所有问题",
            "health_check_report.csv",
            "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        
        if not save_path:
            return
        
        if export_issues_to_csv(all_issues, save_path, self._data_root):
            QMessageBox.information(
                self, 
                "导出成功", 
                f"已导出 {len(all_issues)} 条记录到:\n{save_path}"
            )
        else:
            QMessageBox.warning(self, "导出失败", "导出 CSV 文件时发生错误")
