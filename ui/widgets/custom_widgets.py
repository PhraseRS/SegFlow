from PySide6.QtCore import Qt, QPropertyAnimation, Signal
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
    """
    带推荐标注能力的参数行组件。

    推荐交互设计:
    - 💡 图标: 有推荐值可用但尚未应用，点击可快速应用
    - ✅ 图标: 推荐值已应用
    - 蓝色值 (#1565C0): 当前值来自推荐
    - 橙色值 (#E65100): 用户在推荐应用后手动覆写
    """

    # 当推荐被单项应用时发出 (param_key, recommended_value)
    recommendation_applied = Signal(str, object)

    # Color常量
    COLOR_RECOMMENDED = "#1565C0"  # 蓝色 — 值来自推荐
    COLOR_OVERRIDDEN = "#E65100"   # 橙色 — 用户覆写了推荐值
    COLOR_DEFAULT = ""             # 默认

    def __init__(self, label_text: str, input_type: str, default_value=None,
                 tooltip: str = "", param_key: str = "", parent=None):
        super().__init__(parent)
        self._param_key = param_key or label_text
        self._original_tooltip = tooltip

        self.label = QLabel(label_text)
        self.label.setToolTip(tooltip)

        self.input = self._build_input(input_type, default_value)
        if tooltip:
            self.input.setToolTip(tooltip)

        # ---- 推荐状态 ----
        self._has_recommendation = False
        self._recommendation_applied = False
        self._recommended_value = None
        self._recommend_reason = ""

        # 推荐图标按钮 (初始隐藏)
        self._recommend_btn = QToolButton()
        self._recommend_btn.setFixedSize(22, 22)
        self._recommend_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; font-size: 14px; }"
        )
        self._recommend_btn.setVisible(False)
        self._recommend_btn.setCursor(Qt.PointingHandCursor)
        self._recommend_btn.clicked.connect(self._on_recommend_btn_clicked)

        # 布局
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label)
        row.addWidget(self.input, 1)
        row.addWidget(self._recommend_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)

        # 监听用户修改值
        self._connect_value_changed()

    # ==================== 构建 & 取值 ====================

    def _build_input(self, input_type: str, default_value):
        t = input_type.lower()
        if t == "lineedit":
            widget = QLineEdit()
            if default_value is not None:
                widget.setText(str(default_value))
        elif t == "int":
            widget = QSpinBox()
            widget.setRange(-1, 1000000)
            if default_value is not None:
                widget.setValue(int(default_value))
        elif t == "double":
            widget = QDoubleSpinBox()
            widget.setRange(-1.0, 1000000.0)
            widget.setDecimals(6)
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

    def set_value(self, value):
        if isinstance(self.input, QLineEdit):
            self.input.setText(str(value) if value is not None else "")
        elif isinstance(self.input, QSpinBox):
            self.input.setValue(int(value) if value is not None else 0)
        elif isinstance(self.input, QDoubleSpinBox):
            self.input.setValue(float(value) if value is not None else 0.0)
        elif isinstance(self.input, QComboBox):
            val_str = str(value)
            idx = self.input.findText(val_str)
            if idx >= 0:
                self.input.setCurrentIndex(idx)
            else:
                self.input.addItem(val_str)
                self.input.setCurrentText(val_str)

    # ==================== 推荐 API ====================

    def set_recommendation(self, value, reason: str = ""):
        """
        设置推荐值，显示 💡 图标（未应用状态）。

        Args:
            value: 推荐值
            reason: 推荐理由
        """
        self._has_recommendation = True
        self._recommendation_applied = False
        self._recommended_value = value
        self._recommend_reason = reason

        # 显示 💡 图标
        self._recommend_btn.setText("💡")
        self._recommend_btn.setVisible(True)
        self._recommend_btn.setToolTip(
            f"Recommended value: {value}\n{reason}\n\n🔹 Click to apply this recommendation"
        )
        # 值保持默认Color（用户未操作前不改变任何东西）
        self._set_value_color(self.COLOR_DEFAULT)

    def apply_recommendation(self):
        """应用当前推荐值：写入控件、图标切 ✅、值变蓝。"""
        if not self._has_recommendation:
            return

        self._recommendation_applied = True
        # 填入推荐值
        self.set_value(self._recommended_value)
        # 图标切为 ✅
        self._recommend_btn.setText("✅")
        self._recommend_btn.setToolTip(
            f"已应用Recommended value: {self._recommended_value}\n{self._recommend_reason}"
        )
        # 值变蓝
        self._set_value_color(self.COLOR_RECOMMENDED)

    def clear_recommendation(self):
        """清除推荐状态，恢复默认外观。"""
        self._has_recommendation = False
        self._recommendation_applied = False
        self._recommended_value = None
        self._recommend_reason = ""
        self._recommend_btn.setVisible(False)
        self._set_value_color(self.COLOR_DEFAULT)
        self.input.setToolTip(self._original_tooltip)

    @property
    def has_recommendation(self) -> bool:
        return self._has_recommendation

    @property
    def is_recommendation_applied(self) -> bool:
        return self._recommendation_applied

    # ==================== 内部交互 ====================

    def _on_recommend_btn_clicked(self):
        """用户点击 💡 图标 → 应用推荐值"""
        if self._has_recommendation and not self._recommendation_applied:
            self.apply_recommendation()
            self.recommendation_applied.emit(self._param_key, self._recommended_value)

    def _on_value_changed(self):
        """用户手动修改值后的Color反馈。"""
        if not self._recommendation_applied:
            return  # 尚未应用推荐，无需Color反馈

        current = self.get_value()
        rec = self._recommended_value

        # 比较当前值与推荐值
        try:
            if isinstance(current, (int, float)) and isinstance(rec, (int, float)):
                is_same = abs(current - rec) < 1e-9
            else:
                is_same = str(current) == str(rec)
        except (TypeError, ValueError):
            is_same = False

        if is_same:
            self._set_value_color(self.COLOR_RECOMMENDED)  # 蓝色
        else:
            self._set_value_color(self.COLOR_OVERRIDDEN)    # 橙色

    def _set_value_color(self, color: str):
        """设置输入控件文字Color。"""
        if color:
            style = f"color: {color}; font-weight: bold;"
        else:
            style = ""

        if isinstance(self.input, QComboBox):
            # QComboBox 需要特殊的 QSS
            if color:
                self.input.setStyleSheet(
                    f"QComboBox {{ color: {color}; font-weight: bold; }}"
                )
            else:
                self.input.setStyleSheet("")
        else:
            self.input.setStyleSheet(style)

    def _connect_value_changed(self):
        """连接控件的值变更信号以驱动Color反馈。"""
        if isinstance(self.input, QLineEdit):
            self.input.textChanged.connect(self._on_value_changed)
        elif isinstance(self.input, QSpinBox):
            self.input.valueChanged.connect(self._on_value_changed)
        elif isinstance(self.input, QDoubleSpinBox):
            self.input.valueChanged.connect(self._on_value_changed)
        elif isinstance(self.input, QComboBox):
            self.input.currentTextChanged.connect(self._on_value_changed)