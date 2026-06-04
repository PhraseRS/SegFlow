# -*- coding: utf-8 -*-
"""
RS-Seg-GUI 主入口
"""

import sys


from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from scripts.data_source_tree_example import MainWindow


def main():
    app = QApplication(sys.argv)
    
    # 设置默认字体，避免 QFont::setPointSize 警告
    default_font = app.font()
    if default_font.pointSize() <= 0:
        default_font.setPointSize(9)
        app.setFont(default_font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
