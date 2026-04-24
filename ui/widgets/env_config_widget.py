from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.mmseg_env_manager import MMSegEnvManager


class EnvConfigWidget(QWidget):
    """Environment monitor/configuration widget for Task Config."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.env_manager = MMSegEnvManager()
        self._envs = []
        self._current_framework = ""
        self._last_validated_path = ""
        self._last_validation_result = None
        self._init_ui()
        self.refresh_envs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        select_label = QLabel("Conda environments")
        select_label.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(select_label)

        select_row = QHBoxLayout()
        select_row.setSpacing(8)

        self.env_select = QComboBox()
        self.env_select.setMinimumWidth(220)
        self.env_select.currentIndexChanged.connect(self._on_env_changed)
        select_row.addWidget(self.env_select, stretch=1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_envs)
        select_row.addWidget(self.refresh_button)

        layout.addLayout(select_row)

        path_label = QLabel("Python executable")
        path_label.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(path_label)

        self.custom_path = QLineEdit()
        self.custom_path.setPlaceholderText("e.g. D:\\anaconda3\\envs\\mmseg\\python.exe")
        self.custom_path.textEdited.connect(self._on_custom_path_edited)
        layout.addWidget(self.custom_path)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.use_selected_button = QPushButton("Use Selected")
        self.use_selected_button.clicked.connect(self._fill_selected_env_path)
        button_row.addWidget(self.use_selected_button)

        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self.validate_env)
        button_row.addWidget(self.validate_button)

        layout.addLayout(button_row)

        self.summary_label = QLabel("Select an environment or enter a Python path.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #6C757D;")
        layout.addWidget(self.summary_label)

        self.framework_hint_label = QLabel("")
        self.framework_hint_label.setWordWrap(True)
        self.framework_hint_label.setStyleSheet(
            "background-color: #EEF4FF; border: 1px solid #CFE0FF; "
            "border-radius: 6px; padding: 8px; color: #315E9E;"
        )
        self.framework_hint_label.setVisible(False)
        layout.addWidget(self.framework_hint_label)

        self.status_label = QLabel("Status: waiting for environment selection")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet(
            "background-color: #F8F9FA; border: 1px solid #DEE2E6; "
            "border-radius: 6px; padding: 8px; color: #495057;"
        )
        layout.addWidget(self.status_label)

    def refresh_envs(self):
        self._envs = self.env_manager.list_all_envs()
        self.env_select.blockSignals(True)
        self.env_select.clear()

        for env in self._envs:
            self.env_select.addItem(env["display_name"], env["path"])

        if not self._envs:
            self.env_select.addItem("No conda environments detected", "")
            self.env_select.setEnabled(False)
            self.use_selected_button.setEnabled(False)
            self.summary_label.setText(
                "Conda environment auto-discovery is unavailable. "
                "You can still validate a Python interpreter manually."
            )
        else:
            self.env_select.setEnabled(True)
            self.use_selected_button.setEnabled(True)
            self.summary_label.setText(f"Detected {len(self._envs)} environment(s).")

        self.env_select.blockSignals(False)
        self._invalidate_validation_cache()
        self._fill_selected_env_path()
        self._sync_status_preview()

    def _fill_selected_env_path(self):
        path = self._selected_env_path()
        if path and not self.custom_path.text().strip():
            self.custom_path.setText(path)
        elif not path and not self.custom_path.text().strip():
            self.custom_path.clear()
        self._update_selection_summary()

    def _selected_env_path(self) -> str:
        return (self.env_select.currentData() or "").strip()

    def _on_env_changed(self, _index: int):
        if not self.custom_path.text().strip():
            self._fill_selected_env_path()
        else:
            self._update_selection_summary()
            self._sync_status_preview()

    def _on_custom_path_edited(self, _text: str):
        self._invalidate_validation_cache()
        self._update_selection_summary()
        self._sync_status_preview()

    def _update_selection_summary(self):
        manual_path = self.custom_path.text().strip()
        selected_path = self._selected_env_path()

        if manual_path:
            self.summary_label.setText(f"Using manual path: {manual_path}")
        elif selected_path:
            self.summary_label.setText(f"Using selected environment: {selected_path}")
        else:
            self.summary_label.setText(
                "Select an environment or enter a Python path."
            )

    def _sync_status_preview(self):
        python_path = self.custom_path.text().strip() or self._selected_env_path()
        if python_path:
            self.status_label.setStyleSheet(
                "background-color: #F8F9FA; border: 1px solid #DEE2E6; "
                "border-radius: 6px; padding: 8px; color: #495057;"
            )
            self.status_label.setText(f"Selected interpreter: {python_path}")
        else:
            self.status_label.setStyleSheet(
                "background-color: #FFF8E1; border: 1px solid #FFE082; "
                "border-radius: 6px; padding: 8px; color: #8D6E63;"
            )
            self.status_label.setText(
                "No interpreter selected yet. Pick a detected environment or enter a Python path."
            )

    def set_framework(self, framework_name: str):
        self._current_framework = (framework_name or "").strip()
        requires_env = self.requires_environment_check()

        if requires_env:
            self.framework_hint_label.setText(
                f"{self._current_framework} uses the selected Python environment at train time. "
                "It is worth checking interpreter readiness while you configure the model."
            )
            self.framework_hint_label.setVisible(True)
        else:
            self.framework_hint_label.setVisible(False)

    def requires_environment_check(self) -> bool:
        framework = self._current_framework.lower()
        return "mmseg" in framework

    def _invalidate_validation_cache(self):
        self._last_validated_path = ""
        self._last_validation_result = None

    def get_selected_python_path(self) -> str:
        return self.custom_path.text().strip() or self._selected_env_path()

    def validate_env(self):
        is_valid, message = self.validate_selected_environment(force_refresh=True)
        self._set_status(is_valid, message)

    def validate_selected_environment(self, force_refresh: bool = False):
        python_path = self.get_selected_python_path()
        if not python_path:
            return (
                False,
                "No Python interpreter selected. Choose a detected environment or enter a path manually.",
            )

        if (
            not force_refresh
            and self._last_validation_result is not None
            and python_path == self._last_validated_path
        ):
            return self._last_validation_result

        is_valid, message = self.env_manager.validate_environment(python_path)
        self._last_validated_path = python_path
        self._last_validation_result = (is_valid, message)
        return is_valid, message

    def ensure_ready_for_training(self):
        if not self.requires_environment_check():
            return True, ""

        is_valid, message = self.validate_selected_environment(force_refresh=False)
        self._set_status(is_valid, message)
        return is_valid, message

    def _set_status(self, is_valid: bool, message: str):
        if is_valid:
            style = (
                "background-color: #E8F5E9; border: 1px solid #A5D6A7; "
                "border-radius: 6px; padding: 8px; color: #2E7D32;"
            )
        else:
            style = (
                "background-color: #FFEBEE; border: 1px solid #EF9A9A; "
                "border-radius: 6px; padding: 8px; color: #C62828;"
            )
        self.status_label.setStyleSheet(style)
        self.status_label.setText(message)
