# -*- coding: utf-8 -*-
"""
类别配置组件 (Class Config Widget)

提供类别名称可编辑列表 + 颜色选择器，供 Tab2 任务配置使用。
Public API:
    set_num_classes(n)          由 spin_num_classes 联动调用
    get_class_config() -> dict  返回 {'class_names': [...], 'palette': [[r,g,b], ...]}
    load_from_advisor(names, palette)  由推荐系统批量填入
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QColorDialog, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor

from ui.widgets.wheel_guard import install_wheel_guard

# 默认调色板（VOC 风格，循环使用）
_DEFAULT_PALETTE = [
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (128, 128, 128),
    (64, 0, 0), (192, 0, 0),
]


def _default_color(idx: int) -> tuple:
    return _DEFAULT_PALETTE[idx % len(_DEFAULT_PALETTE)]


class ClassConfigWidget(QWidget):
    """类别名称 + 颜色配置控件。"""

    config_changed = Signal()

    # 列索引常量
    _COL_ID = 0
    _COL_NAME = 1
    _COL_COLOR = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        hint = QLabel("定义数据集的类别名称和可视化颜色（第 0 行通常为背景类）")
        hint.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "类别名称", "颜色"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(2, 56)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(180)
        self.table.itemChanged.connect(lambda: self.config_changed.emit())
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("+ 添加类别")
        self.btn_del = QPushButton("- 删除选中")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.btn_add.clicked.connect(self._add_row)
        self.btn_del.clicked.connect(self._del_row)

        # 初始化 2 行（背景 + 目标）
        self._add_row()
        self._add_row()

        # UI-09：阻止鼠标悬停时滚轮误改可能存在的输入控件
        install_wheel_guard(self)

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    def _add_row(self, name: str = '', color: tuple = None):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # ID 列（只读）
        id_item = QTableWidgetItem(str(row))
        id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, self._COL_ID, id_item)

        # 名称列
        default_name = name if name else f"class_{row}"
        self.table.setItem(row, self._COL_NAME, QTableWidgetItem(default_name))

        # 颜色列
        rgb = color if color else _default_color(row)
        self._set_color_btn(row, rgb)
        self.config_changed.emit()

    def _set_color_btn(self, row: int, rgb: tuple):
        r, g, b = rgb
        btn = QPushButton()
        btn.setFixedSize(40, 20)
        btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #aaa;")
        btn.setProperty('rgb', list(rgb))
        btn.clicked.connect(lambda _, r=row: self._pick_color(r))
        self.table.setCellWidget(row, self._COL_COLOR, btn)

    def _pick_color(self, row: int):
        btn = self.table.cellWidget(row, self._COL_COLOR)
        if not btn:
            return
        rgb = btn.property('rgb') or [0, 0, 0]
        init_color = QColor(*rgb)
        color = QColorDialog.getColor(init_color, self, f"选择 class_{row} 的颜色")
        if color.isValid():
            new_rgb = (color.red(), color.green(), color.blue())
            self._set_color_btn(row, new_rgb)
            self.config_changed.emit()

    def _del_row(self):
        if self.table.rowCount() <= 2:
            QMessageBox.information(self, "删除类别", "至少保留 2 个类别。")
            return
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._refresh_ids()
        self.config_changed.emit()

    def _refresh_ids(self):
        """删除行后重新编号 ID 列。"""
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self._COL_ID)
            if item:
                item.setText(str(r))
        self.table.blockSignals(False)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_num_classes(self, n: int):
        """由 spin_num_classes 联动调用，自动增减行数至 n 行。"""
        if n < 2:
            return
        current = self.table.rowCount()
        if n > current:
            for i in range(current, n):
                self._add_row()
        elif n < current:
            for _ in range(current - n):
                self.table.removeRow(self.table.rowCount() - 1)
            self.config_changed.emit()

    def get_class_config(self) -> dict:
        """返回 {'class_names': [...], 'palette': [[r,g,b], ...]}"""
        names, palette = [], []
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, self._COL_NAME)
            names.append(name_item.text().strip() if name_item else f"class_{r}")
            btn = self.table.cellWidget(r, self._COL_COLOR)
            palette.append(list(btn.property('rgb')) if btn else list(_default_color(r)))
        return {'class_names': names, 'palette': palette}

    def set_class_config(self, config: dict):
        if not isinstance(config, dict):
            return
        class_names = config.get('class_names') or []
        palette = config.get('palette') or []
        if not class_names:
            return

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for i, name in enumerate(class_names):
            color = tuple(palette[i]) if i < len(palette) else _default_color(i)
            self._add_row(name=name, color=color)
        self.table.blockSignals(False)
        self.config_changed.emit()

    def load_from_advisor(self, class_names: list, palette: list = None):
        """由推荐系统或 Tab1 联动批量填入类别名和颜色。"""
        if not class_names:
            return
        # 若已有用户编辑内容，询问是否覆盖
        existing = self.get_class_config()
        has_custom = any(
            n != f"class_{i}" for i, n in enumerate(existing['class_names'])
        )
        if has_custom:
            reply = QMessageBox.question(
                self, "覆盖类别配置",
                "检测到已有手动编辑的类别配置，是否用推荐结果覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.table.blockSignals(True)
        # 清空并重建
        self.table.setRowCount(0)
        for i, name in enumerate(class_names):
            color = tuple(palette[i]) if palette and i < len(palette) else _default_color(i)
            self._add_row(name=name, color=color)
        self.table.blockSignals(False)
        self.config_changed.emit()
