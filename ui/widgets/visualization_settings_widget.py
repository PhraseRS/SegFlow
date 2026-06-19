# -*- coding: utf-8 -*-
"""
Visualization settings widget for inference preview rendering.
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.mask_renderer import MaskRenderer


class VisualizationSettingsWidget(QWidget):
    palette_changed = Signal(dict)
    alpha_changed = Signal(float)
    apply_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.class_names: List[str] = []
        self.current_palette: Dict[int, List[int]] = {}
        self.default_palette: Dict[int, List[int]] = {}
        self.color_buttons: Dict[int, QPushButton] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        alpha_group = QGroupBox(self.tr("Alpha"))
        alpha_layout = QHBoxLayout(alpha_group)

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)

        self.alpha_label = QLabel(self.tr("50%"))
        self.alpha_label.setMinimumWidth(40)
        self.alpha_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        alpha_layout.addWidget(QLabel(self.tr("Overlay Alpha:")))
        alpha_layout.addWidget(self.alpha_slider)
        alpha_layout.addWidget(self.alpha_label)
        layout.addWidget(alpha_group)

        color_group = QGroupBox(self.tr("类别Color配置"))
        color_layout = QVBoxLayout(color_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMaximumHeight(300)

        self.color_list_widget = QWidget()
        self.color_list_layout = QVBoxLayout(self.color_list_widget)
        self.color_list_layout.setContentsMargins(5, 5, 5, 5)
        self.color_list_layout.setSpacing(5)
        scroll.setWidget(self.color_list_widget)
        color_layout.addWidget(scroll)
        layout.addWidget(color_group)

        btn_layout = QHBoxLayout()
        self.reset_btn = QPushButton(self.tr("Reset to Default"))
        self.reset_btn.clicked.connect(self._reset_palette)
        btn_layout.addWidget(self.reset_btn)

        self.apply_btn = QPushButton(self.tr("Apply to Preview"))
        self.apply_btn.setStyleSheet("font-weight: bold;")
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def set_classes_and_palette(
        self,
        class_names: Optional[List[str]],
        palette: Optional[List[List[int]]],
    ):
        names = []
        for idx, name in enumerate(class_names or []):
            names.append(str(name) if name is not None else f"Class {idx}")

        palette = list(palette or [])
        target_count = max(len(names), len(palette))

        if target_count <= 0:
            self.class_names = []
            self.current_palette = {}
            self.default_palette = {}
            self._rebuild_color_list()
            return

        if not names:
            names = [f"Class {idx}" for idx in range(target_count)]
        elif len(names) < target_count:
            names.extend(f"Class {idx}" for idx in range(len(names), target_count))

        fallback_palette = MaskRenderer(num_classes=target_count).get_palette()
        normalized_palette = {}
        for idx in range(target_count):
            if idx < len(palette) and isinstance(palette[idx], (list, tuple)) and len(palette[idx]) >= 3:
                normalized_palette[idx] = [int(palette[idx][0]), int(palette[idx][1]), int(palette[idx][2])]
            else:
                normalized_palette[idx] = list(fallback_palette[idx])

        self.class_names = names
        self.current_palette = {idx: color[:] for idx, color in normalized_palette.items()}
        self.default_palette = {idx: color[:] for idx, color in normalized_palette.items()}
        self._rebuild_color_list()

    def _rebuild_color_list(self):
        while self.color_list_layout.count():
            child = self.color_list_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        self.color_buttons.clear()

        if not self.class_names:
            placeholder = QLabel(self.tr("推理完成后会在这里列出可调整的类别Color。"))
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet("color: #6C757D; padding: 4px;")
            self.color_list_layout.addWidget(placeholder)
            self.color_list_layout.addStretch()
            return

        for class_id, class_name in enumerate(self.class_names):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)

            color_preview = QPushButton()
            color_preview.setFixedSize(40, 30)
            color = self.current_palette.get(class_id, [128, 128, 128])
            color_preview.setStyleSheet(
                f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); "
                "border: 1px solid #ccc; border-radius: 3px;"
            )
            color_preview.setToolTip(f"点击Select {class_name} 的Color")
            color_preview.clicked.connect(lambda _checked=False, cid=class_id: self._choose_color(cid))

            label = QLabel(class_name)
            label.setMinimumWidth(100)

            row.addWidget(color_preview)
            row.addWidget(label)
            row.addStretch()

            self.color_list_layout.addWidget(row_widget)
            self.color_buttons[class_id] = color_preview

        self.color_list_layout.addStretch()

    def _on_alpha_changed(self, value: int):
        alpha = value / 100.0
        self.alpha_label.setText(f"{value}%")
        self.alpha_changed.emit(alpha)

    def _choose_color(self, class_id: int):
        if class_id >= len(self.class_names):
            return

        current_color = self.current_palette.get(class_id, [128, 128, 128])
        qcolor = QColor(current_color[0], current_color[1], current_color[2])
        color = QColorDialog.getColor(qcolor, self, f"Select {self.class_names[class_id]} 的Color")

        if not color.isValid():
            return

        self.current_palette[class_id] = [color.red(), color.green(), color.blue()]
        self.color_buttons[class_id].setStyleSheet(
            f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
            "border: 1px solid #ccc; border-radius: 3px;"
        )
        self.palette_changed.emit(self.current_palette.copy())

    def _reset_palette(self):
        if not self.default_palette:
            return

        self.current_palette = {idx: color[:] for idx, color in self.default_palette.items()}
        for class_id, color in self.current_palette.items():
            if class_id in self.color_buttons:
                self.color_buttons[class_id].setStyleSheet(
                    f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); "
                    "border: 1px solid #ccc; border-radius: 3px;"
                )

        self.palette_changed.emit(self.current_palette.copy())

    def get_current_palette(self) -> Dict[int, List[int]]:
        return {idx: color[:] for idx, color in self.current_palette.items()}

    def get_current_alpha(self) -> float:
        return self.alpha_slider.value() / 100.0

    def set_alpha(self, alpha: float):
        value = max(0, min(100, int(alpha * 100)))
        self.alpha_slider.setValue(value)
