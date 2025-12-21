import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config_editor import ConfigEditor
from mmseg_params import mmseg_params as DEFAULT_CONFIG


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MMSeg Config Editor")

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(6, 6, 6, 6)

        self.editor = ConfigEditor(DEFAULT_CONFIG, self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)

        central_layout.addWidget(scroll)
        self.setCentralWidget(central)

        self.editor.export_btn.clicked.connect(self.export_config)

    def export_config(self):
        data = self.editor.export_to_dict()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Config",
            str(Path.cwd() / "mmseg_config.json"),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save file:\n{exc}")
            return
        QMessageBox.information(self, "Exported", f"Configuration saved to:\n{path}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(640, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()