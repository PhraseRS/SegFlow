# -*- coding: utf-8 -*-
"""
---
name: skill_geodata_utils
description: >
  遥感地理数据格式转换工具。
  提供 GDAL 波段优先格式 (BxHxW) 与 OpenCV 通道末尾格式 (HxWxC) 之间的
  数据转换，自动保持数据类型映射。不依赖任何特定模型架构。
parameters:
  gdal_data_to_opencv_data:
    gdal_img_data: numpy.ndarray - GDAL 格式数组，shape=(bands, height, width)
    returns: numpy.ndarray - OpenCV 格式数组，shape=(height, width, channels)，波段顺序翻转（BGR）
returns:
  gdal_data_to_opencv_data: callable
---
"""

import numpy as np


def gdal_data_to_opencv_data(gdal_img_data):
    """
    将 GDAL 数据格式 (BxHxW) 转换为 OpenCV 格式 (HxWxC)。

    波段顺序会被翻转（例如 RGB → BGR），以匹配 OpenCV 默认的颜色通道顺序。
    数据类型根据输入自动映射：int8→uint8, int16→uint16, 其他→float32。

    Args:
        gdal_img_data (numpy.ndarray): GDAL 格式数组，shape=(bands, height, width)。

    Returns:
        numpy.ndarray: OpenCV 格式数组，shape=(height, width, channels)。
    """
    if 'int8' in gdal_img_data.dtype.name:
        opencv_img_data = np.zeros(
            (gdal_img_data.shape[1], gdal_img_data.shape[2], gdal_img_data.shape[0]),
            np.uint8
        )
    elif 'int16' in gdal_img_data.dtype.name:
        opencv_img_data = np.zeros(
            (gdal_img_data.shape[1], gdal_img_data.shape[2], gdal_img_data.shape[0]),
            np.uint16
        )
    else:
        opencv_img_data = np.zeros(
            (gdal_img_data.shape[1], gdal_img_data.shape[2], gdal_img_data.shape[0]),
            np.float32
        )

    for i in range(gdal_img_data.shape[0]):
        opencv_img_data[:, :, i] = gdal_img_data[gdal_img_data.shape[0] - i - 1, :, :]
    return opencv_img_data
