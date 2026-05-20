# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen


class StackedBarWidget(QWidget):
    COLORS = {
        'train': QColor(76, 175, 80),
        'val': QColor(33, 150, 243),
        'test': QColor(255, 152, 0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        self._train_count = 0
        self._val_count = 0
        self._test_count = 0
        self._total = 0

    def set_data(self, train_count, val_count, test_count):
        self._train_count = train_count
        self._val_count = val_count
        self._test_count = test_count
        self._total = train_count + val_count + test_count
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(200, 200, 200, 50))
        painter.drawRoundedRect(rect, 4, 4)
        if self._total == 0:
            return
        train_width = int(width * self._train_count / self._total)
        val_width = int(width * self._val_count / self._total)
        test_width = width - train_width - val_width
        x = 0
        if train_width > 0:
            painter.setBrush(self.COLORS['train'])
            if val_width == 0 and test_width == 0:
                painter.drawRoundedRect(x, 0, train_width, height, 4, 4)
            else:
                painter.drawRoundedRect(x, 0, train_width + 4, height, 4, 4)
                painter.drawRect(x + train_width, 0, 4, height)
            x += train_width
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
        if test_width > 0:
            painter.setBrush(self.COLORS['test'])
            if train_width == 0 and val_width == 0:
                painter.drawRoundedRect(x, 0, test_width, height, 4, 4)
            else:
                painter.drawRoundedRect(x - 4, 0, test_width + 4, height, 4, 4)
                painter.drawRect(x - 4, 0, 4, height)


class DatasetOverviewWidget(QWidget):
    resplit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.update_data(0, 0, 0)

    def _setup_ui(self):
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
        self.label_total_desc = QLabel("Total Samples")
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

    def _create_legend_item(self, text, color):
        widget = QWidget()
        lo = QHBoxLayout(widget)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(4)
        color_box = QFrame()
        color_box.setFixedSize(12, 12)
        color_box.setStyleSheet(f"background-color: {color.name()}; border-radius: 2px;")
        lo.addWidget(color_box)
        label = QLabel(text)
        label.setStyleSheet("font-size: 11px;")
        lo.addWidget(label)
        return widget

    def update_data(self, train_count, val_count, test_count, unique_total=None):
        total = unique_total if unique_total is not None else (train_count + val_count + test_count)
        self.label_total.setText(f"{total:,}")
        self.stacked_bar.set_data(train_count, val_count, test_count)
        if total > 0:
            train_pct = train_count / total * 100
            val_pct = val_count / total * 100
            test_pct = test_count / total * 100
            detail_text = f"Train: {train_count:,} ({train_pct:.1f}%) | Val: {val_count:,} ({val_pct:.1f}%) | Test: {test_count:,} ({test_pct:.1f}%)"
        else:
            detail_text = "No data"
        self.label_detail.setText(detail_text)

    def clear(self):
        self.update_data(0, 0, 0)
