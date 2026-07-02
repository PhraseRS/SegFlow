from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.toolbox_registry import Toolbox, ToolboxParameter, ToolboxRegistry, ToolboxTool
from core.toolbox_runner import ToolRunner


VOC_CATEGORY = "VOC Dataset Conversion"
CATEGORY_ORDER = {
    VOC_CATEGORY: 0,
    "Raster Tools": 1,
    "Analysis Tools": 2,
    "Utility Tools": 3,
}
TOOL_ORDER = {
    "raster.rasterize": 0,
    "raster.clip": 1,
    "label.remap": 2,
    "voc.build": 3,
    "voc.validate": 4,
}
ROOT_TOOL_IDS = {"voc.build", "voc.validate"}
VOC_TOOL_NUMBERS = {
    "raster.rasterize": 1,
    "raster.clip": 2,
    "label.remap": 3,
}


class ToolboxDialog(QDialog):
    """Managed toolbox browser.

    The browser only lists available toolboxes and tools. Double-clicking a
    runnable tool opens a dedicated parameter dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Toolbox"))
        self.resize(430, 620)
        self._registry = ToolboxRegistry()
        self._setup_ui()
        self._connect_signals()
        self.refresh_toolboxes()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton(self.tr("Refresh"))
        self.btn_refresh.setToolTip(self.tr("Rescan managed toolboxes"))
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        root_layout.addLayout(toolbar)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        root_layout.addWidget(self.tree, 1)

        self.hint_label = QLabel(self.tr("Double-click a tool to open its parameters."))
        self.hint_label.setWordWrap(True)
        root_layout.addWidget(self.hint_label)

        button_row = QHBoxLayout()
        self.btn_open = QPushButton(self.tr("Open"))
        self.btn_open.setEnabled(False)
        self.btn_close = QPushButton(self.tr("Close"))
        button_row.addStretch()
        button_row.addWidget(self.btn_open)
        button_row.addWidget(self.btn_close)
        root_layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        self.btn_refresh.clicked.connect(self.refresh_toolboxes)
        self.btn_open.clicked.connect(self._open_selected_tool)
        self.btn_close.clicked.connect(self.close)
        self.tree.currentItemChanged.connect(self._on_tree_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

    @Slot()
    def refresh_toolboxes(self) -> None:
        self.tree.clear()
        self._registry.scan()
        for toolbox in self._registry.toolboxes:
            toolbox_item = QTreeWidgetItem(self.tree, [toolbox.name])
            toolbox_item.setData(0, Qt.ItemDataRole.UserRole, {"toolbox": toolbox, "tool": None})
            categories: dict[str, QTreeWidgetItem] = {}
            for tool in sorted(toolbox.tools, key=self._tool_sort_key):
                parent_item = toolbox_item
                if not self._is_root_tool(tool):
                    category_item = categories.get(tool.category)
                    if category_item is None:
                        category_item = QTreeWidgetItem(toolbox_item, [tool.category])
                        category_item.setData(0, Qt.ItemDataRole.UserRole, {"toolbox": toolbox, "tool": None})
                        categories[tool.category] = category_item
                    parent_item = category_item
                tool_item = QTreeWidgetItem(parent_item, [self._tool_display_name(tool)])
                tool_item.setToolTip(0, tool.description)
                tool_item.setData(0, Qt.ItemDataRole.UserRole, {"toolbox": toolbox, "tool": tool})
        self.tree.expandAll()

        if self._registry.errors:
            QMessageBox.warning(self, self.tr("Toolbox scan warnings"), "\n".join(self._registry.errors))

    def _tool_sort_key(self, tool: ToolboxTool) -> tuple[int, int, str, str, str]:
        root_rank = 0 if self._is_root_tool(tool) else 1
        category_rank = CATEGORY_ORDER.get(tool.category, 99)
        tool_rank = TOOL_ORDER.get(tool.id, 99)
        return root_rank, category_rank, tool.category.lower(), f"{tool_rank:02d}", tool.name.lower()

    def _is_root_tool(self, tool: ToolboxTool) -> bool:
        return tool.id in ROOT_TOOL_IDS

    def _tool_display_name(self, tool: ToolboxTool) -> str:
        if tool.category == VOC_CATEGORY and tool.id in VOC_TOOL_NUMBERS:
            return f"{VOC_TOOL_NUMBERS[tool.id]}. {tool.name}"
        return tool.name

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def _on_tree_selection_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        toolbox, tool = self._item_tool(current)
        self.btn_open.setEnabled(toolbox is not None and tool is not None and tool.runnable)

    @Slot(QTreeWidgetItem, int)
    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        self._open_tool_from_item(item)

    @Slot()
    def _open_selected_tool(self) -> None:
        self._open_tool_from_item(self.tree.currentItem())

    def _open_tool_from_item(self, item: QTreeWidgetItem | None) -> None:
        toolbox, tool = self._item_tool(item)
        if toolbox is None or tool is None:
            return
        if not tool.runnable:
            QMessageBox.information(
                self,
                self.tr("Toolbox"),
                self.tr("This tool is installed, but its GUI parameters are not available yet."),
            )
            return
        dialog = ToolParameterDialog(toolbox, tool, self)
        dialog.exec()

    def _item_tool(self, item: QTreeWidgetItem | None) -> tuple[Toolbox | None, ToolboxTool | None]:
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(data, dict):
            return None, None
        toolbox = data.get("toolbox")
        tool = data.get("tool")
        return (
            toolbox if isinstance(toolbox, Toolbox) else None,
            tool if isinstance(tool, ToolboxTool) else None,
        )


class ToolParameterDialog(QDialog):
    """Parameter and execution dialog for one toolbox tool."""

    def __init__(self, toolbox: Toolbox, tool: ToolboxTool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tool.name)
        self.resize(760, 620)
        self._toolbox = toolbox
        self._tool = tool
        self._runner = ToolRunner(self)
        self._editors: dict[str, QWidget] = {}
        self._parameter_widgets: dict[str, tuple[QWidget, ...]] = {}
        self._setup_ui()
        self._connect_signals()
        self._render_tool()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(6)

        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(max(title_font.pointSize(), 11))
        self.title_label.setFont(title_font)
        root_layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        root_layout.addWidget(self.description_label)

        self.form_host = QWidget()
        self.form_layout = QFormLayout(self.form_host)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.form_scroll.setWidget(self.form_host)
        root_layout.addWidget(self.form_scroll, 1)

        button_row = QHBoxLayout()
        self.btn_run = QPushButton(self.tr("Run"))
        self.btn_stop = QPushButton(self.tr("Stop"))
        self.btn_stop.setEnabled(False)
        self.btn_close = QPushButton(self.tr("Close"))
        button_row.addWidget(self.btn_run)
        button_row.addWidget(self.btn_stop)
        button_row.addStretch()
        button_row.addWidget(self.btn_close)
        root_layout.addLayout(button_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root_layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)
        self.log.setVisible(False)
        root_layout.addWidget(self.log)

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_stop.clicked.connect(self._runner.stop)
        self.btn_close.clicked.connect(self.close)
        self._runner.started.connect(self._on_runner_started)
        self._runner.outputLine.connect(self._append_log)
        self._runner.eventReceived.connect(self._on_tool_event)
        self._runner.finished.connect(self._on_runner_finished)
        self._runner.errorOccurred.connect(self._on_runner_error)

    def _render_tool(self) -> None:
        self.title_label.setText(self._tool.name)
        self.description_label.setText(self._tool.description)
        self.btn_run.setEnabled(self._tool.runnable and not self._runner.is_running())

        if not self._tool.parameters:
            self._add_readonly_message(self.tr("No parameters required."))
            return

        for direction, title in (
            ("input", self.tr("Inputs")),
            ("output", self.tr("Outputs")),
            ("option", self.tr("Options")),
        ):
            params = [param for param in self._tool.parameters if param.direction == direction]
            if not params:
                continue
            self._add_section_label(title)
            if direction == "option":
                self._add_option_parameter_rows(params)
            else:
                self._add_full_parameter_rows(params)
        self._connect_condition_controllers()
        self._refresh_parameter_visibility()

    def _add_readonly_message(self, message: str) -> None:
        label = QLabel(message)
        label.setWordWrap(True)
        self.form_layout.addRow(label)

    def _add_section_label(self, message: str) -> None:
        label = QLabel(message)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        self.form_layout.addRow(label)

    def _add_full_parameter_rows(self, params: list[ToolboxParameter]) -> None:
        self._add_full_parameter_rows_to_layout(params, self.form_layout)

    def _add_full_parameter_rows_to_layout(self, params: list[ToolboxParameter], layout: QFormLayout) -> None:
        for param in params:
            label = QLabel(param.label)
            label.setWordWrap(True)
            editor = self._create_editor(param)
            self._editors[param.name] = editor
            self._parameter_widgets[param.name] = (label, editor)
            layout.addRow(label, editor)

    def _add_option_parameter_rows(self, params: list[ToolboxParameter]) -> None:
        basic_params = [param for param in params if not param.advanced]
        advanced_params = [param for param in params if param.advanced]
        if basic_params:
            self._add_compact_option_rows_to_layout(basic_params, self.form_layout)
        if advanced_params:
            toggle = QCheckBox(self.tr("Advanced options"))
            advanced_host = QWidget()
            advanced_layout = QFormLayout(advanced_host)
            advanced_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            self._add_compact_option_rows_to_layout(advanced_params, advanced_layout)
            advanced_host.setVisible(False)
            toggle.toggled.connect(advanced_host.setVisible)
            self.form_layout.addRow(toggle)
            self.form_layout.addRow(advanced_host)

    def _add_compact_option_rows_to_layout(self, params: list[ToolboxParameter], layout: QFormLayout) -> None:
        compact_params: list[ToolboxParameter] = []
        for param in params:
            if self._is_compact_parameter(param):
                compact_params.append(param)
                continue
            if compact_params:
                self._add_compact_parameter_grid(compact_params, layout)
                compact_params.clear()
            self._add_full_parameter_rows_to_layout([param], layout)
        if compact_params:
            self._add_compact_parameter_grid(compact_params, layout)

    def _add_compact_parameter_grid(self, params: list[ToolboxParameter], layout: QFormLayout) -> None:
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        for index, param in enumerate(params):
            row = index // 2
            column = (index % 2) * 2
            label = QLabel(param.label)
            label.setWordWrap(True)
            editor = self._create_editor(param)
            self._editors[param.name] = editor
            self._parameter_widgets[param.name] = (label, editor)
            grid.addWidget(label, row, column)
            grid.addWidget(editor, row, column + 1)
            grid.setColumnStretch(column + 1, 1)
        layout.addRow(host)

    def _is_compact_parameter(self, param: ToolboxParameter) -> bool:
        return param.type not in {"directory", "file", "string_list"}

    def _create_editor(self, param: ToolboxParameter) -> QWidget:
        if param.type in ("directory", "file"):
            host = QWidget()
            layout = QHBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setText("" if param.default is None else str(param.default))
            browse = QPushButton(self.tr("Browse"))
            if param.type == "file":
                if param.direction == "output":
                    browse.clicked.connect(lambda _checked=False, target=edit: self._browse_save_file(target))
                else:
                    browse.clicked.connect(lambda _checked=False, target=edit: self._browse_file(target))
            else:
                browse.clicked.connect(lambda _checked=False, target=edit: self._browse_directory(target))
            layout.addWidget(edit, 1)
            layout.addWidget(browse)
            host.setProperty("line_edit", edit)
            return host
        if param.type == "integer":
            spin = QSpinBox()
            spin.setRange(-2147483648, 2147483647)
            spin.setValue(int(param.default or 0))
            return spin
        if param.type == "float":
            spin = QDoubleSpinBox()
            spin.setRange(-1000000.0, 1000000.0)
            spin.setDecimals(4)
            spin.setSingleStep(0.1)
            spin.setValue(float(param.default or 0.0))
            return spin
        if param.type == "enum":
            combo = QComboBox()
            combo.addItems(list(param.choices))
            if param.default is not None:
                index = combo.findText(str(param.default))
                if index >= 0:
                    combo.setCurrentIndex(index)
            return combo
        if param.type == "boolean":
            check = QCheckBox()
            check.setChecked(bool(param.default))
            return check
        edit = QLineEdit()
        edit.setText("" if param.default is None else str(param.default))
        return edit

    def _connect_condition_controllers(self) -> None:
        controller_names = {
            name
            for param in self._tool.parameters
            for name in param.visible_when
        }
        for name in controller_names:
            editor = self._editors.get(name)
            if isinstance(editor, QComboBox):
                editor.currentTextChanged.connect(self._refresh_parameter_visibility)
            elif isinstance(editor, QCheckBox):
                editor.toggled.connect(self._refresh_parameter_visibility)

    def _refresh_parameter_visibility(self, *_args) -> None:
        for param in self._tool.parameters:
            visible = self._parameter_is_visible(param)
            for widget in self._parameter_widgets.get(param.name, ()):
                widget.setVisible(visible)

    def _parameter_is_visible(self, param: ToolboxParameter) -> bool:
        for controller_name, expected in param.visible_when.items():
            actual = self._editor_value(self._editors.get(controller_name))
            if isinstance(expected, (list, tuple, set)):
                if str(actual) not in {str(item) for item in expected}:
                    return False
                continue
            if str(actual) != str(expected):
                return False
        return True

    @Slot()
    def _on_run_clicked(self) -> None:
        values = self._collect_values()
        try:
            self._runner.start(self._toolbox, self._tool, values)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("Toolbox"), str(exc))

    def _collect_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name, editor in self._editors.items():
            values[name] = self._editor_value(editor)
        return values

    def _editor_value(self, editor: QWidget | None) -> object:
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        if isinstance(editor, QComboBox):
            return editor.currentText()
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, QLineEdit):
            return editor.text()
        if editor is not None:
            line_edit = editor.property("line_edit")
            if isinstance(line_edit, QLineEdit):
                return line_edit.text()
        return ""

    def _browse_directory(self, target: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(self, self.tr("Select Directory"), target.text())
        if selected:
            target.setText(selected)

    def _browse_file(self, target: QLineEdit) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, self.tr("Select File"), target.text())
        if selected:
            target.setText(selected)

    def _browse_save_file(self, target: QLineEdit) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, self.tr("Select Output File"), target.text())
        if selected:
            target.setText(selected)

    @Slot(str)
    def _on_runner_started(self, tool_id: str) -> None:
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.log.clear()
        self.log.setVisible(True)
        self._append_log(f"Started: {tool_id}")

    @Slot(str)
    def _append_log(self, line: str) -> None:
        self.log.setVisible(True)
        self.log.append(line)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(dict)
    def _on_tool_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "progress":
            current = int(event.get("current") or 0)
            total = int(event.get("total") or 0)
            if total > 0:
                self.progress.setVisible(True)
                self.progress.setValue(int(current * 100 / total))
        elif event_type == "result":
            status = event.get("status", "unknown")
            self._append_log(f"Result: {status}")
            if status == "success":
                self.progress.setValue(100)
        elif event_type == "error":
            self._append_log(f"Error: {event.get('message', '')}")

    @Slot(int)
    def _on_runner_finished(self, exit_code: int) -> None:
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(self._tool.runnable)
        self._append_log(f"Finished with exit code {exit_code}")

    @Slot(str)
    def _on_runner_error(self, message: str) -> None:
        self._append_log(f"Process error: {message}")

    def closeEvent(self, event) -> None:
        if self._runner.is_running():
            self._runner.stop()
        super().closeEvent(event)
