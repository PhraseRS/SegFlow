import copy
from typing import Any, Dict

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
)

from ui.widgets.custom_widgets import CollapsibleBox, ParamRow


class ConfigEditor(QWidget):
    def __init__(self, default_config: Dict[str, Dict[str, Dict[str, Any]]], parent=None):
        super().__init__(parent)
        self._defaults = copy.deepcopy(default_config)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        for section, params in default_config.items():
            box = CollapsibleBox(section, self)
            content_layout = QVBoxLayout()
            content_layout.setContentsMargins(0, 0, 0, 0)

            for key, info in params.items():
                input_type = info.get("type", "lineedit")
                default_value = info.get("value")
                options = info.get("options", [])
                help_text = info.get("help_text", "")

                param_type = self._map_input_type(input_type)
                initial_value = options if param_type == "combo" else default_value
                row = ParamRow(key, param_type, initial_value, help_text)
                row.input.setObjectName(key)
                if param_type == "combo" and default_value is not None:
                    row.input.setCurrentText(str(default_value))
                content_layout.addWidget(row)

            content_layout.addStretch()
            box.setContentLayout(content_layout)
            main_layout.addWidget(box)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.reset_btn = QPushButton("Reset")
        self.export_btn = QPushButton("Export Config")
        button_row.addWidget(self.reset_btn)
        button_row.addWidget(self.export_btn)

        main_layout.addLayout(button_row)
        main_layout.addStretch()

        self.reset_btn.clicked.connect(self.reset_to_defaults)

    def _map_input_type(self, source_type: str) -> str:
        t = source_type.lower()
        if t in {"select", "combo"}:
            return "combo"
        if t in {"float", "double"}:
            return "double"
        if t in {"int", "integer"}:
            return "int"
        return "lineedit"

    def _find_input(self, name: str):
        classes = (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)
        matches = self.findChildren(classes, name=name)
        return matches[0] if matches else None

    def reset_to_defaults(self):
        for section, params in self._defaults.items():
            for key, info in params.items():
                widget = self._find_input(key)
                if widget is None:
                    continue
                value = info.get("value")
                if isinstance(widget, QLineEdit):
                    widget.setText("" if value is None else str(value))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(value) if value is not None else 0)
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value) if value is not None else 0.0)
                elif isinstance(widget, QComboBox):
                    if info.get("options"):
                        widget.clear()
                        widget.addItems([str(v) for v in info.get("options", [])])
                    if value is not None:
                        widget.setCurrentText(str(value))

    def export_to_dict(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for section, params in self._defaults.items():
            result[section] = {}
            for key, info in params.items():
                widget = self._find_input(key)
                if widget is None:
                    continue
                if isinstance(widget, QLineEdit):
                    current_value = widget.text()
                elif isinstance(widget, QSpinBox):
                    current_value = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    current_value = widget.value()
                elif isinstance(widget, QComboBox):
                    current_value = widget.currentText()
                else:
                    current_value = info.get("value")

                result[section][key] = {
                    "value": current_value,
                    "type": info.get("type"),
                    "options": info.get("options", []),
                    "help_text": info.get("help_text", ""),
                }
        return result