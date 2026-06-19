# -*- coding: utf-8 -*-
"""
金字塔构建工具 (Pyramid Builder)
自动检测并为大图构建金字塔，确保快速显示
"""

import os
from typing import Optional, List, Tuple
from pathlib import Path

from skills.skill_raster_io import GDAL_AVAILABLE as HAS_GDAL
from skills.skill_raster_io import build_pyramids as skill_build_pyramids
from skills.skill_raster_io import get_raster_info, open_raster


class PyramidBuilder:
    """金字塔构建器"""

    DEFAULT_LEVELS = [2, 4, 8, 16, 32, 64]
    DEFAULT_RESAMPLING = 'NEAREST'

    @staticmethod
    def check_has_pyramids(file_path: str) -> bool:
        """
        检查文件是否已有金字塔

        Args:
            file_path: 图像文件路径

        Returns:
            bool: 是否已有金字塔
        """
        if not HAS_GDAL:
            return False

        try:
            return bool(get_raster_info(file_path).get('has_pyramids', False))

        except Exception as e:
            print(f"Check pyramid failed: {e}")
            return False

    @staticmethod
    def get_pyramid_info(file_path: str) -> dict:
        """
        获取金字塔信息

        Args:
            file_path: 图像文件路径

        Returns:
            dict: 金字塔信息
        """
        if not HAS_GDAL:
            return {'has_pyramids': False, 'levels': []}

        try:
            with open_raster(file_path) as handle:
                levels = []
                if handle.band_count > 0:
                    band = handle.dataset.GetRasterBand(1)
                    overview_count = band.GetOverviewCount()
                    for i in range(overview_count):
                        overview = band.GetOverview(i)
                        levels.append({
                            'index': i,
                            'width': overview.XSize,
                            'height': overview.YSize,
                            'scale': handle.width / overview.XSize
                        })
                else:
                    overview_count = 0

            return {
                'has_pyramids': overview_count > 0,
                'count': overview_count,
                'levels': levels
            }

        except Exception as e:
            print(f"Get pyramid info failed: {e}")
            return {'has_pyramids': False, 'levels': []}

    @staticmethod
    def build_pyramids(file_path: str,
                      levels: Optional[List[int]] = None,
                      resampling: str = 'NEAREST',
                      progress_callback: Optional[callable] = None) -> bool:
        """
        为图像构建金字塔

        Args:
            file_path: 图像文件路径
            levels: 金字塔级别列表，如 [2, 4, 8, 16]
            resampling: 重采样方法 ('NEAREST', 'AVERAGE', 'BILINEAR', 'CUBIC')
            progress_callback: 进度回调函数 callback(progress: float, message: str)

        Returns:
            bool: 是否构建成功
        """
        if not HAS_GDAL:
            if progress_callback:
                progress_callback(0, "GDAL not installed")
            return False

        if levels is None:
            levels = PyramidBuilder.DEFAULT_LEVELS

        try:
            return skill_build_pyramids(
                file_path,
                levels=levels,
                resampling=resampling,
                callback=progress_callback,
            )

        except Exception as e:
            if progress_callback:
                progress_callback(0, f"Pyramid build failed: {e}")
            print(f"Pyramid build failed: {e}")
            return False

    @staticmethod
    def ensure_pyramids(file_path: str,
                       levels: Optional[List[int]] = None,
                       resampling: str = 'NEAREST',
                       progress_callback: Optional[callable] = None) -> bool:
        """
        确保图像有金字塔，如果没有则自动构建

        Args:
            file_path: 图像文件路径
            levels: 金字塔级别列表
            resampling: 重采样方法
            progress_callback: 进度回调函数

        Returns:
            bool: 是否成功（已有或构建成功）
        """
        if not os.path.exists(file_path):
            if progress_callback:
                progress_callback(0, f"文件Not Found: {file_path}")
            return False

        # 检查是否已有金字塔
        if PyramidBuilder.check_has_pyramids(file_path):
            if progress_callback:
                progress_callback(100, "Pyramid already exists")
            return True

        # 构建金字塔
        if progress_callback:
            progress_callback(0, "No pyramid detected, starting build...")

        return PyramidBuilder.build_pyramids(
            file_path, levels, resampling, progress_callback
        )

    @staticmethod
    def calculate_optimal_levels(width: int, height: int,
                                min_size: int = 256) -> List[int]:
        """
        根据图像尺寸计算最优金字塔级别

        Args:
            width: 图像宽度
            height: 图像高度
            min_size: 最小尺寸阈值

        Returns:
            List[int]: 金字塔级别列表
        """
        max_dim = max(width, height)
        levels = []

        level = 2
        while max_dim / level > min_size:
            levels.append(level)
            level *= 2

        return levels if levels else [2]


def prepare_large_image(file_path: str,
                       progress_callback: Optional[callable] = None) -> bool:
    """
    准备大图：检查并构建金字塔

    这是加载大图前的必要步骤，确保图像能快速显示

    Args:
        file_path: 图像文件路径
        progress_callback: 进度回调函数

    Returns:
        bool: 是否准备成功
    """
    return PyramidBuilder.ensure_pyramids(file_path, progress_callback=progress_callback)
