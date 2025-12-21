from PySide6.QtCore import Qt, QPropertyAnimation
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolButton,
    QSizePolicy,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
)


class CollapsibleBox(QWidget):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.toggle_btn = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_btn.setStyleSheet("QToolButton { border: none; }")
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.DownArrow)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.toggle_btn)
        header = QWidget()
        header.setLayout(header_layout)

        self.content_area = QWidget()
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(self.content_area)

        self._animation = QPropertyAnimation(self.content_area, b"maximumHeight")
        self._animation.setDuration(120)

        self.toggle_btn.clicked.connect(self._on_toggled)

    def setContentLayout(self, layout: QVBoxLayout):
        """Assign layout for the collapsible content."""
        self.content_area.setLayout(layout)
        self.content_area.setMaximumHeight(layout.sizeHint().height())

    def _on_toggled(self, checked: bool):
        self.toggle_btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        full_height = self.content_area.layout().sizeHint().height() if self.content_area.layout() else 0
        start = self.content_area.maximumHeight()
        end = full_height if checked else 0
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        self.content_area.setVisible(checked)


class ParamRow(QWidget):
    def __init__(self, label_text: str, input_type: str, default_value=None, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.label = QLabel(label_text)
        self.label.setToolTip(tooltip)

        self.input = self._build_input(input_type, default_value)
        if tooltip:
            self.input.setToolTip(tooltip)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label)
        row.addWidget(self.input, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)

    def _build_input(self, input_type: str, default_value):
        t = input_type.lower()
        if t == "lineedit":
            widget = QLineEdit()
            if default_value is not None:
                widget.setText(str(default_value))
        elif t == "int":
            widget = QSpinBox()
            if default_value is not None:
                widget.setValue(int(default_value))
        elif t == "double":
            widget = QDoubleSpinBox()
            if default_value is not None:
                widget.setValue(float(default_value))
        elif t == "combo":
            widget = QComboBox()
            if isinstance(default_value, (list, tuple)):
                widget.addItems([str(v) for v in default_value])
                if default_value:
                    widget.setCurrentIndex(0)
            elif default_value is not None:
                widget.addItem(str(default_value))
        else:
            raise ValueError(f"Unknown input_type: {input_type}")
        return widget

    def get_value(self):
        if isinstance(self.input, QLineEdit):
            return self.input.text()
        if isinstance(self.input, QSpinBox):
            return self.input.value()
        if isinstance(self.input, QDoubleSpinBox):
            return self.input.value()
        if isinstance(self.input, QComboBox):
            return self.input.currentText()
        return None