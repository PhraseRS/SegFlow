"""Optional training output directory; empty means the existing automatic path."""
import os
from PySide6.QtCore import QEvent, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog


class WorkDirectoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self)
        self.edit = QLineEdit(self)
        self.edit.setObjectName('lineEdit_trainingWorkDir')
        self.edit.setClearButtonEnabled(True)
        self.label.setBuddy(self.edit)
        self.browse = QPushButton(self)
        self.browse.clicked.connect(self.choose_directory)
        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse)
        layout.addWidget(self.label)
        layout.addLayout(row)
        self.retranslate()

    def retranslate(self):
        self.label.setText(self.tr('Training work directory'))
        self.edit.setPlaceholderText(self.tr('Automatic (current default directory)'))
        self.edit.setToolTip(self.tr('Training runs are saved in backbone_iterations subdirectories of this directory.'))
        self.browse.setText(self.tr('Browse...'))

    def changeEvent(self, event):
        if event.type() == QEvent.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    def set_dataset_root(self, root):
        default = os.path.abspath(os.path.join(root, 'work_dirs'))
        previous = getattr(self, '_default_path', '')
        if not self.edit.text().strip() or self.edit.text() == previous:
            self.edit.setText(default)
        self._default_path = default

    @Slot()
    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr('Select training work directory'), self.edit.text().strip())
        if path:
            self.edit.setText(path)

    def resolve(self, default_path):
        selected = self.edit.text().strip()
        if not selected:
            selected = os.path.dirname(default_path)
            self.edit.setText(os.path.abspath(selected))
        # Preserve the existing per-model/per-iteration run organization.
        return os.path.join(os.path.abspath(os.path.expanduser(selected)),
                            os.path.basename(default_path))
