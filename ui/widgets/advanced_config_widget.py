# -*- coding: utf-8 -*-
"""
高级配置组件 (Advanced Config Widget)

基于 mmseg_params.py 动态生成的高级配置表单，
包含可折叠面板、锁定机制（用于响应推荐配置）和底层 JSON 字典覆写功能。

Training Roadmap Phase 4, Task X
"""

import json
from typing import Any, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QPlainTextEdit,
    QPushButton, QDialog, QDialogButtonBox, QScrollArea
)
from PySide6.QtCore import Signal, Slot

from ui.widgets.custom_widgets import CollapsibleBox, ParamRow
from ui.widgets.wheel_guard import install_wheel_guard

from config.mmseg_params import mmseg_params as DEFAULT_CONFIG


class AdvancedConfigWidget(QWidget):
    """
    高级(专家)配置面板

    1. 默认仅显示一个"开启高级配置选项"的开关。
    2. 开启后，展开基于 mmseg_params 定义的具体配置树。
    3. 支持通过 lock_param 方法锁定由 ConfigAdvisor 推荐的参数。
    4. 底部包含纯文本 JSON 字典覆写区。

    Signals:
        config_changed(): 配置发生变化时触发
    """

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._param_rows: Dict[str, ParamRow] = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        self._expert_dialog = None
        self.button_open_expert_card = QPushButton(self.tr("🛠️ Enable Expert Settings"))
        self.button_open_expert_card.setStyleSheet(
            "font-weight: bold; color: #424242; text-align: left; padding: 6px;"
        )
        self.button_open_expert_card.setToolTip(self.tr("打开独立卡片，调整 MMSegmentation 的底层或较不常用的超参数"))
        self.button_open_expert_card.clicked.connect(self._show_expert_card)
        main_layout.addWidget(self.button_open_expert_card)

        self.card_advanced = self._create_advanced_card()
        self.card_advanced.setVisible(False)  # 仅在弹出对话框时显示

    def _create_advanced_card(self) -> QFrame:
        """创建高级专家配置卡片内容。"""
        card = QFrame(self)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 8px; }")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(6)

        title_label = QLabel(self.tr("🛠️ Expert Settings"))
        title_label.setStyleSheet("font-weight: bold; color: #424242; padding: 4px 4px 0 4px;")
        card_layout.addWidget(title_label)

        self.container_advanced = QWidget()
        container_layout = QVBoxLayout(self.container_advanced)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        self._build_config_tree(container_layout)
        self._build_override_area(container_layout)
        card_layout.addWidget(self.container_advanced)

        # UI-09：阻止鼠标悬停时滚轮误改高级配置中的 SpinBox / ComboBox
        install_wheel_guard(card)
        return card

    @Slot()
    def _show_expert_card(self):
        """以独立弹出卡片展示高级专家配置内容。"""
        if self._expert_dialog is None:
            self._expert_dialog = QDialog(self)
            self._expert_dialog.setWindowTitle("Expert Settings")
            self._expert_dialog.resize(720, 620)
            self._expert_dialog.setModal(False)

            dialog_layout = QVBoxLayout(self._expert_dialog)
            dialog_layout.setContentsMargins(12, 12, 12, 12)
            dialog_layout.setSpacing(8)

            scroll_area = QScrollArea(self._expert_dialog)
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            scroll_area.setWidget(self.card_advanced)
            self.card_advanced.setVisible(True)
            dialog_layout.addWidget(scroll_area)

            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self._expert_dialog)
            button_box.rejected.connect(self._expert_dialog.close)
            dialog_layout.addWidget(button_box)

        self._expert_dialog.show()
        self._expert_dialog.raise_()
        self._expert_dialog.activateWindow()


    def _build_config_tree(self, parent_layout):
        """根据 mmseg_params.py 构建折叠面板"""
        for section, params in DEFAULT_CONFIG.items():
            # 为每个大类创建一个 CollapsibleBox
            box = CollapsibleBox(section, self)
            content_layout = QVBoxLayout()
            content_layout.setContentsMargins(12, 4, 4, 8)
            content_layout.setSpacing(6)

            for key, info in params.items():
                input_type = info.get("type", "lineedit")
                default_value = info.get("value")
                options = info.get("options", [])
                help_text = info.get("help_text", "")

                # 转换类型适应 ParamRow
                param_type = self._map_input_type(input_type)
                initial_value = options if param_type == "combo" else default_value

                # 创建单行参数控件
                row = ParamRow(key, param_type, initial_value, help_text)
                if param_type == "combo" and default_value is not None:
                    # 对于下拉框，设置默认选中项
                    idx = row.input.findText(str(default_value))
                    if idx >= 0:
                        row.input.setCurrentIndex(idx)

                # 绑定信号
                if hasattr(row.input, "textChanged"):
                    row.input.textChanged.connect(lambda _, r=row: self._on_param_changed(r))
                elif hasattr(row.input, "valueChanged"):
                    row.input.valueChanged.connect(lambda _, r=row: self._on_param_changed(r))
                elif hasattr(row.input, "currentTextChanged"):
                    row.input.currentTextChanged.connect(lambda _, r=row: self._on_param_changed(r))

                content_layout.addWidget(row)
                self._param_rows[key] = row

            box.setContentLayout(content_layout)
            parent_layout.addWidget(box)

    def _build_override_area(self, parent_layout):
        """构建底部的 JSON 字典覆写区"""
        box_override = CollapsibleBox("Dictionary Overrides", self)
        # 默认覆写区收起
        box_override.toggle_btn.setChecked(False)

        override_layout = QVBoxLayout()
        override_layout.setContentsMargins(12, 4, 4, 8)

        lbl_info = QLabel(self.tr("Enter parameters to forcefully override here (JSON format):\nExample: {\"model.decode_head.dropout_ratio\": 0.2}"))
        lbl_info.setStyleSheet("color: #757575; font-size: 11px;")
        override_layout.addWidget(lbl_info)

        self.text_override = QPlainTextEdit()
        self.text_override.setPlaceholderText(self.tr("{\n    \n}"))
        self.text_override.setMaximumHeight(100)
        self.text_override.setStyleSheet("font-family: Consolas, monospace; background-color: #FAFAFA;")

        # 简单校验 JSON 格式
        self.text_override.textChanged.connect(self._validate_override_json)

        override_layout.addWidget(self.text_override)

        self.lbl_json_error = QLabel(self.tr(""))
        self.lbl_json_error.setStyleSheet("color: #D32F2F; font-size: 11px;")
        self.lbl_json_error.setVisible(False)
        override_layout.addWidget(self.lbl_json_error)

        box_override.setContentLayout(override_layout)

        # 手动触发展开/折叠动画来初始化状态
        box_override._on_toggled(False)

        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        parent_layout.addWidget(line)

        parent_layout.addWidget(box_override)

    def _map_input_type(self, source_type: str) -> str:
        """映射配置字典中的类型到 ParamRow 支持的类型"""
        t = source_type.lower()
        if t in {"select", "combo"}:
            return "combo"
        if t in {"float", "double"}:
            return "double"
        if t in {"int", "integer"}:
            return "int"
        return "lineedit"

    @Slot(object)
    def _on_param_changed(self, row_widget):
        self.config_changed.emit()

    @Slot()
    def _validate_override_json(self):
        """验证覆写区的内容是否为合法的 JSON 字典"""
        text = self.text_override.toPlainText().strip()
        if not text:
            self.lbl_json_error.setVisible(False)
            self.text_override.setStyleSheet("font-family: Consolas, monospace; background-color: #FAFAFA;")
            self.config_changed.emit()
            return

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("根节点必须是 JSON 对象 (字典)")
            self.lbl_json_error.setVisible(False)
            self.text_override.setStyleSheet("font-family: Consolas, monospace; background-color: #FAFAFA;")
            self.config_changed.emit()
        except Exception as e:
            self.lbl_json_error.setText(f"JSON format error: {str(e)}")
            self.lbl_json_error.setVisible(True)
            self.text_override.setStyleSheet("font-family: Consolas, monospace; background-color: #FFEBEE;")

    # ====== Public API ======

    # ====== Recommendation API ======

    def set_recommendations(self, rec_dict: Dict[str, Dict[str, Any]]):
        """
        为底层高级参数分发推荐。
        Args:
            rec_dict: 类似 { 'crop_size': {'value': 512, 'reason': '...'} }
        """
        for key, rec_data in rec_dict.items():
            if key in self._param_rows:
                val = rec_data.get('value')
                reason = rec_data.get('reason', '')
                self._param_rows[key].set_recommendation(val, reason)

    def apply_all_recommendations(self):
        """Apply all recommendations in this component"""
        for row in self._param_rows.values():
            if row.has_recommendation:
                row.apply_recommendation()

    def clear_all_recommendations(self):
        """Clear all recommendations"""
        for row in self._param_rows.values():
            row.clear_recommendation()

    def get_params(self) -> Dict[str, Any]:
        """
        获取当前面板中设置或锁定的表单参数
        注意：这扁平化了层级结构，返回 {key: value}
        """
        result = {}
        for key, row in self._param_rows.items():
            result[key] = row.get_value()
        return result

    def set_params(self, params: Dict[str, Any]):
        if not isinstance(params, dict):
            return
        for key, value in params.items():
            row = self._param_rows.get(key)
            if row is not None:
                row.set_value(value)
        self.config_changed.emit()

    def get_overrides(self) -> Dict[str, Any]:
        """
        获取底部文本框中填写的强制覆写字典
        """
        text = self.text_override.toPlainText().strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except:
            pass
        return {}

    def set_overrides(self, overrides: Dict[str, Any]):
        if not overrides:
            self.text_override.clear()
            return
        self.text_override.setPlainText(json.dumps(overrides, ensure_ascii=False, indent=2))
