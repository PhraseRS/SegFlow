"""
统一的安全 IO 工具：

- imread_unchanged / imread_with_flag：
    支持中文路径的 OpenCV 读取，使用 np.fromfile + cv2.imdecode 绕开 cv2.imread 的
    Windows 中文路径乱码问题，并默认 IMREAD_UNCHANGED 保留原 dtype/通道数。

- imwrite_safe：
    支持中文路径的 OpenCV 写入，使用 cv2.imencode + tofile。返回是否成功。

- gdal_open：
    GDAL 安全打开，None 检查 + 友好错误提示。可选只读模式。

注意：
- 单波段 16 位标签必须用 IMREAD_UNCHANGED 才不会被压成 8 位。
- 遥感多波段 GeoTIFF 建议用 GDAL，OpenCV 对 4 波段以上支持有限。
"""
from __future__ import annotations

import os
from typing import Optional

import cv2
import numpy as np


def imread_unchanged(file_path: str) -> Optional[np.ndarray]:
    """
    支持中文路径的 OpenCV 读取，IMREAD_UNCHANGED 保留原 dtype/通道数。

    :return: 读取成功返回 ndarray；失败（路径错误/解码失败）返回 None
    """
    return imread_with_flag(file_path, cv2.IMREAD_UNCHANGED)


def imread_with_flag(file_path: str, flag: int) -> Optional[np.ndarray]:
    """
    指定读取 flag 的中文路径安全读取。

    :param flag: cv2.IMREAD_UNCHANGED / IMREAD_GRAYSCALE / IMREAD_COLOR ...
    :return: 读取成功返回 ndarray；失败返回 None
    """
    if not os.path.exists(file_path):
        print(f"[io_safe] 文件不存在: {file_path}")
        return None
    try:
        buf = np.fromfile(file_path, dtype=np.uint8)
        if buf.size == 0:
            print(f"[io_safe] 文件为空: {file_path}")
            return None
        img = cv2.imdecode(buf, flag)
        if img is None:
            print(f"[io_safe] 解码失败: {file_path}")
        return img
    except Exception as e:
        print(f"[io_safe] 读取错误: {file_path} - {e}")
        return None


def imwrite_safe(save_path: str, img: np.ndarray) -> bool:
    """
    支持中文路径的 OpenCV 写入。

    :return: True 表示写入成功；False 表示 imencode 返回 False、IO 异常等。
    """
    try:
        ext = os.path.splitext(save_path)[1]
        if not ext:
            print(f"[io_safe] 写入失败：无扩展名 {save_path}")
            return False
        ok, buf = cv2.imencode(ext, img)
        if not ok:
            print(f"[io_safe] imencode 返回 False: {save_path}")
            return False
        buf.tofile(save_path)
        return True
    except Exception as e:
        print(f"[io_safe] 写入错误: {save_path} - {e}")
        return False


def gdal_open(file_path: str, mode: str = 'ro'):
    """
    GDAL 安全打开。

    :param mode: 'ro' 只读（默认）/ 'update' 可写
    :return: gdal.Dataset 对象；失败返回 None 并打印错误。
             调用方负责设置 ds = None 释放。
    :raises ImportError: 当环境未安装 GDAL 时
    """
    try:
        from osgeo import gdal
    except ImportError as e:
        raise ImportError(
            "未安装 GDAL。请使用 conda install -c conda-forge gdal "
            "或参考 SegFlow 主项目环境说明安装。"
        ) from e

    if mode == 'ro':
        gdal_mode = gdal.GA_ReadOnly
    elif mode == 'update':
        gdal_mode = gdal.GA_Update
    else:
        raise ValueError(f"mode 必须是 'ro' 或 'update'，得到: {mode!r}")

    ds = gdal.Open(file_path, gdal_mode)
    if ds is None:
        print(f"[io_safe] GDAL 无法打开: {file_path}")
    return ds
