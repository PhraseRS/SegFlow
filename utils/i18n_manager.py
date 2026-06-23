from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QTabWidget,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItemIterator,
    QWidget,
)

from utils.json_translator import JsonTranslator


class _LanguageEventFilter(QObject):
    """Translate top-level widgets, including dialogs created after startup."""

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            I18nManager.translate_widget_tree(watched)
        return super().eventFilter(watched, event)


class I18nManager:
    """Load, switch, and persist the application's UI language."""

    SETTINGS_ORG = "RSegGUI"
    SETTINGS_APP = "RSegGUI"
    DEFAULT_LANG = "en"
    STARTUP_LANG = "en"
    SUPPORTED_LANGUAGES = ("en", "zh_CN")

    _translator = None
    _event_filter = None

    @classmethod
    def get_current_language(cls) -> str:
        settings = QSettings(cls.SETTINGS_ORG, cls.SETTINGS_APP)
        language = str(settings.value("language", cls.DEFAULT_LANG))
        return language if language in cls.SUPPORTED_LANGUAGES else cls.DEFAULT_LANG

    @classmethod
    def set_language(cls, lang_code: str) -> None:
        if lang_code not in cls.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang_code}")
        settings = QSettings(cls.SETTINGS_ORG, cls.SETTINGS_APP)
        settings.setValue("language", lang_code)
        settings.sync()

    @classmethod
    def apply_language(
        cls,
        app: QCoreApplication,
        lang_code: str,
        *,
        persist: bool = True,
    ) -> bool:
        """Apply a language immediately. Return False if its catalog cannot load."""
        if lang_code not in cls.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang_code}")

        new_translator = None
        if lang_code != "en":
            json_path = (
                Path(__file__).resolve().parent.parent
                / "i18n"
                / f"{lang_code}.json"
            )
            new_translator = JsonTranslator(app)
            if not new_translator.load_json(str(json_path)):
                return False

        if cls._translator is not None:
            app.removeTranslator(cls._translator)
            cls._translator.deleteLater()
            cls._translator = None

        if new_translator is not None:
            app.installTranslator(new_translator)
            cls._translator = new_translator

        if persist:
            cls.set_language(lang_code)
        return True

    @classmethod
    def setup_translator(cls, app: QCoreApplication) -> bool:
        """Always start in English before constructing the first window."""
        loaded = cls.apply_language(
            app,
            cls.STARTUP_LANG,
            persist=True,
        )
        cls.install_widget_localizer(app)
        return loaded

    @classmethod
    def install_widget_localizer(cls, app: QCoreApplication) -> None:
        """Install one application-wide filter for windows created at runtime."""
        if cls._event_filter is None:
            cls._event_filter = _LanguageEventFilter(app)
            app.installEventFilter(cls._event_filter)

    @classmethod
    def translate_widget_tree(cls, root: QWidget) -> None:
        """Translate common Qt widget properties, including legacy literals."""
        if cls.get_current_language() == "en":
            return

        def translate(text: str) -> str:
            if not text:
                return text
            return QCoreApplication.translate("UI", text)

        widgets = [root, *root.findChildren(QWidget)]
        for widget in widgets:
            widget.setWindowTitle(translate(widget.windowTitle()))
            if isinstance(widget, (QAbstractButton, QLabel)):
                widget.setText(translate(widget.text()))
            if isinstance(widget, (QGroupBox, QMenu)):
                widget.setTitle(translate(widget.title()))
            if isinstance(widget, QLineEdit):
                widget.setPlaceholderText(translate(widget.placeholderText()))

            widget.setToolTip(translate(widget.toolTip()))
            widget.setStatusTip(translate(widget.statusTip()))
            widget.setWhatsThis(translate(widget.whatsThis()))

            if isinstance(widget, QTabWidget):
                for index in range(widget.count()):
                    widget.setTabText(index, translate(widget.tabText(index)))
                    widget.setTabToolTip(
                        index, translate(widget.tabToolTip(index))
                    )
            elif isinstance(widget, QComboBox):
                for index in range(widget.count()):
                    widget.setItemText(index, translate(widget.itemText(index)))
                    tooltip = widget.itemData(
                        index, Qt.ItemDataRole.ToolTipRole
                    )
                    if isinstance(tooltip, str):
                        widget.setItemData(
                            index,
                            translate(tooltip),
                            Qt.ItemDataRole.ToolTipRole,
                        )
            elif isinstance(widget, QTableWidget):
                for index in range(widget.columnCount()):
                    item = widget.horizontalHeaderItem(index)
                    if item is not None:
                        item.setText(translate(item.text()))
                for index in range(widget.rowCount()):
                    item = widget.verticalHeaderItem(index)
                    if item is not None:
                        item.setText(translate(item.text()))
            elif isinstance(widget, QTreeWidget):
                header = widget.headerItem()
                if header is not None:
                    for index in range(widget.columnCount()):
                        header.setText(index, translate(header.text(index)))
                iterator = QTreeWidgetItemIterator(widget)
                while iterator.value() is not None:
                    item = iterator.value()
                    for index in range(widget.columnCount()):
                        item.setText(index, translate(item.text(index)))
                    iterator += 1
            elif isinstance(widget, QListWidget):
                for index in range(widget.count()):
                    item = widget.item(index)
                    item.setText(translate(item.text()))

        actions = root.findChildren(QAction)
        if isinstance(root, QMenu):
            actions.extend(root.actions())
        for action in dict.fromkeys(actions):
            action.setText(translate(action.text()))
            action.setToolTip(translate(action.toolTip()))
            action.setStatusTip(translate(action.statusTip()))
            action.setWhatsThis(translate(action.whatsThis()))
