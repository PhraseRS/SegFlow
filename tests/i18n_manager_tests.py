import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.i18n_manager import I18nManager
from utils.json_translator import JsonTranslator


class TestI18nManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous_language = I18nManager.get_current_language()

    def tearDown(self):
        I18nManager.apply_language(self.app, self.previous_language)

    def test_switches_between_chinese_and_english(self):
        self.assertTrue(I18nManager.apply_language(self.app, "zh_CN"))
        self.assertEqual(
            QCoreApplication.translate("MainWindow", "Language"),
            "语言",
        )
        self.assertEqual(I18nManager.get_current_language(), "zh_CN")

        self.assertTrue(I18nManager.apply_language(self.app, "en"))
        self.assertEqual(
            QCoreApplication.translate("MainWindow", "Language"),
            "Language",
        )
        self.assertEqual(I18nManager.get_current_language(), "en")

    def test_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            I18nManager.apply_language(self.app, "fr_FR")

    def test_startup_always_resets_to_english(self):
        I18nManager.set_language("zh_CN")

        self.assertTrue(I18nManager.setup_translator(self.app))

        self.assertEqual(I18nManager.get_current_language(), "en")
        self.assertEqual(
            QCoreApplication.translate("MainWindow", "Language"),
            "Language",
        )

    def test_missing_translation_keeps_source_text(self):
        translator = JsonTranslator()
        translator.mapping = {"Known": "已知"}

        self.assertEqual(
            translator.translate("UI", "Untranslated visible text"),
            "Untranslated visible text",
        )

    def test_translates_legacy_widget_literals(self):
        self.assertTrue(I18nManager.apply_language(self.app, "zh_CN"))

        root = QWidget()
        layout = QVBoxLayout(root)
        group = QGroupBox("Class Configuration", root)
        label = QLabel("Available Samples:", group)
        combo = QComboBox(group)
        combo.addItems(["Automatic Split", "Custom Split"])
        tabs = QTabWidget(root)
        tabs.addTab(QWidget(), "General")
        layout.addWidget(group)
        layout.addWidget(tabs)

        I18nManager.translate_widget_tree(root)

        self.assertEqual(group.title(), "类别配置")
        self.assertEqual(label.text(), "可用样本:")
        self.assertEqual(combo.itemText(0), "自动划分")
        self.assertEqual(combo.itemText(1), "自定义划分")
        self.assertEqual(tabs.tabText(0), "常规")


if __name__ == "__main__":
    unittest.main()
