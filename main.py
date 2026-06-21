# -*- coding: utf-8 -*-
"""
RS-Seg-GUI 主入口
"""

import sys


from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
import os

from scripts.data_source_tree_example import MainWindow


from utils.i18n_manager import I18nManager

def main():
    app = QApplication(sys.argv)
    
    # 设置软件全局图标
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 初始化多语言
    I18nManager.setup_translator(app)
    
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
