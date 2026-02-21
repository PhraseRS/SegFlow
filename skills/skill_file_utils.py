# -*- coding: utf-8 -*-
"""
---
name: skill_file_utils
description: >
  跨平台文件操作工具集。
  提供在系统文件管理器中定位文件、复制路径/文件名到剪贴板等通用函数。
  支持 Windows / macOS / Linux 三平台。
parameters:
  reveal_in_explorer:
    file_path: str - 要定位的文件绝对路径
    returns: bool - 操作是否成功
  copy_path_to_clipboard:
    file_path: str - 要复制的文件绝对路径
    returns: bool - 操作是否成功
  copy_filename_to_clipboard:
    file_path: str - 文件绝对路径，将提取其文件名（无扩展名）
    returns: bool - 操作是否成功
returns:
  reveal_in_explorer: callable
  copy_path_to_clipboard: callable
  copy_filename_to_clipboard: callable
---
"""

import os
import sys
import subprocess
from PySide6.QtWidgets import QApplication


def reveal_in_explorer(file_path: str) -> bool:
    """
    在系统文件管理器中选中并定位文件。

    跨平台实现：
    - Windows: explorer /select,"<path>"
    - macOS: open -R "<path>"
    - Linux: xdg-open "<dir>"

    Args:
        file_path: 要定位的文件绝对路径。

    Returns:
        bool: 操作是否成功。
    """
    if not file_path:
        return False

    file_path = os.path.normpath(file_path)

    if not os.path.exists(file_path):
        parent_dir = os.path.dirname(file_path)
        if os.path.exists(parent_dir):
            file_path = parent_dir
        else:
            return False

    try:
        if sys.platform == 'win32':
            if os.path.isfile(file_path):
                subprocess.run(['explorer', '/select,', file_path], check=False)
            else:
                subprocess.run(['explorer', file_path], check=False)
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', file_path], check=False)
        else:
            if os.path.isfile(file_path):
                subprocess.run(['xdg-open', os.path.dirname(file_path)], check=False)
            else:
                subprocess.run(['xdg-open', file_path], check=False)
        return True
    except Exception as e:
        print(f"⚠️ 打开文件管理器失败: {e}")
        return False


def copy_path_to_clipboard(file_path: str) -> bool:
    """
    复制文件的完整绝对路径到系统剪贴板。

    Args:
        file_path: 文件绝对路径。

    Returns:
        bool: 操作是否成功。
    """
    if not file_path:
        return False

    try:
        clipboard = QApplication.clipboard()
        clipboard.setText(os.path.normpath(file_path))
        return True
    except Exception as e:
        print(f"⚠️ 复制到剪贴板失败: {e}")
        return False


def copy_filename_to_clipboard(file_path: str) -> bool:
    """
    提取文件名（不含扩展名）并复制到系统剪贴板。

    例如: "d:/data/sample_001.png" → 剪贴板内容 "sample_001"

    Args:
        file_path: 文件绝对路径。

    Returns:
        bool: 操作是否成功。
    """
    if not file_path:
        return False

    try:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        clipboard = QApplication.clipboard()
        clipboard.setText(filename)
        return True
    except Exception as e:
        print(f"⚠️ 复制文件名到剪贴板失败: {e}")
        return False
