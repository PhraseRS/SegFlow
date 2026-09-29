"""命令行参数辅助工具。

各脚本采用统一模式：
- argparse 的 default 设置为脚本内的 DEMO 路径（兜底）
- 无参运行：argparse 取 default，并由 hint_if_no_args 打印提示
- 传参运行：CLI 参数覆盖 default

这样可同时满足：
1. 保留 `python xxx.py` 直接运行的便利性（用 demo 默认）
2. 提供 `--help` 与显式参数化 CLI（生产环境/复用）
"""
from __future__ import annotations

import os
import sys


def hint_if_no_args(script_name: str | None = None) -> bool:
    """无 CLI 参数时打印提示，提醒用户脚本走了内置 DEMO 默认值。

    :param script_name: 脚本文件名（不含目录），用于提示文本。None 时尝试从 sys.argv[0] 推断。
    :return: True 表示当前调用未传入任何 CLI 参数（命中默认）；False 表示有参数。
    """
    if script_name is None:
        script_name = os.path.basename(sys.argv[0]) if sys.argv else '<script>'

    if len(sys.argv) <= 1:
        print(
            f"[提示] 未传入命令行参数，将使用 {script_name} 的内置 DEMO 默认配置。\n"
            f"       使用 python {script_name} --help 查看可配置参数。\n"
        )
        return True
    return False
