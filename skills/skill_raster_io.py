# -*- coding: utf-8 -*-
"""
---
name: skill_raster_io
description: >
  遥感栅格影像统一读写技能。内部优先使用 GDAL（osgeo），必要时配合 cv2，
  不引入 rasterio。提供影像打开、窗口读取、摘要元数据等基础接口。
---
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

try:
    from osgeo import gdal
    GDAL_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖环境差异
    gdal = None
    GDAL_AVAILABLE = False


_RESAMPLE_MAP = {
    "nearest": "GRA_NearestNeighbour",
    "bilinear": "GRA_Bilinear",
    "cubic": "GRA_Cubic",
}


@dataclass
class RasterHandle:
    """只读/更新栅格句柄，封装 GDAL Dataset 并支持上下文管理器。"""

    dataset: Any
    path: str
    mode: str = "r"

    @property
    def width(self) -> int:
        return int(self.dataset.RasterXSize)

    @property
    def height(self) -> int:
        return int(self.dataset.RasterYSize)

    @property
    def band_count(self) -> int:
        return int(self.dataset.RasterCount)

    @property
    def projection(self) -> str:
        return self.dataset.GetProjection() or ""

    @property
    def crs_wkt(self) -> str:
        return self.projection

    @property
    def geo_transform(self) -> Optional[tuple]:
        transform = self.dataset.GetGeoTransform(can_return_null=True)
        return tuple(transform) if transform else None

    @property
    def overviews(self) -> List[int]:
        if self.band_count <= 0:
            return []
        band = self.dataset.GetRasterBand(1)
        levels = []
        for idx in range(band.GetOverviewCount()):
            overview = band.GetOverview(idx)
            if overview and overview.XSize:
                levels.append(max(1, round(self.width / overview.XSize)))
        return levels

    def close(self) -> None:
        if self.dataset is not None:
            self.dataset.FlushCache()
            self.dataset = None

    def __enter__(self) -> "RasterHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _require_gdal() -> None:
    if not GDAL_AVAILABLE:
        raise ImportError("GDAL 未安装，无法使用 skill_raster_io 的栅格 I/O 功能")


def _gdal_access_mode(mode: str) -> int:
    _require_gdal()
    return gdal.GA_Update if mode in {"w", "r+", "update"} else gdal.GA_ReadOnly


def open_raster(path: str, mode: str = "r") -> RasterHandle:
    """统一打开遥感栅格影像。"""
    _require_gdal()
    dataset = gdal.Open(path, _gdal_access_mode(mode))
    if dataset is None:
        raise FileNotFoundError(f"无法打开栅格影像: {path}")
    return RasterHandle(dataset=dataset, path=path, mode=mode)


def _normalise_band_indices(handle: RasterHandle, band_indices: Optional[Sequence[int]]) -> Optional[List[int]]:
    if band_indices is None:
        return None
    bands = [int(b) for b in band_indices]
    for band in bands:
        if band < 1 or band > handle.band_count:
            raise ValueError(f"波段索引超出范围: {band}，有效范围 1-{handle.band_count}")
    return bands


def _to_hwc(array: np.ndarray) -> np.ndarray:
    if array.ndim == 3:
        return np.transpose(array, (1, 2, 0))
    return array


def read_block(
    handle: RasterHandle,
    x: int,
    y: int,
    width: int,
    height: int,
    band_indices: Optional[Sequence[int]] = None,
    out_width: Optional[int] = None,
    out_height: Optional[int] = None,
    resample: str = "nearest",
) -> np.ndarray:
    """从已打开影像读取窗口数据，返回 HxW 或 HxWxC 数组。"""
    bands = _normalise_band_indices(handle, band_indices)
    kwargs: Dict[str, Any] = {}
    if out_width is not None and out_height is not None:
        kwargs["buf_xsize"] = int(out_width)
        kwargs["buf_ysize"] = int(out_height)
        resample_key = resample.lower()
        attr_name = _RESAMPLE_MAP.get(resample_key, _RESAMPLE_MAP["nearest"])
        kwargs["resample_alg"] = getattr(gdal, attr_name)

    if bands is None:
        data = handle.dataset.ReadAsArray(int(x), int(y), int(width), int(height), **kwargs)
    else:
        arrays = [
            handle.dataset.GetRasterBand(b).ReadAsArray(int(x), int(y), int(width), int(height), **kwargs)
            for b in bands
        ]
        data = np.stack(arrays, axis=0) if len(arrays) > 1 else arrays[0]

    if data is None:
        raise ValueError(f"读取影像窗口失败: {handle.path} [{x}, {y}, {width}, {height}]")
    return _to_hwc(np.asarray(data))



_DTYPE_MAP = {
    "uint8": "GDT_Byte",
    "byte": "GDT_Byte",
    "uint16": "GDT_UInt16",
    "int16": "GDT_Int16",
    "uint32": "GDT_UInt32",
    "int32": "GDT_Int32",
    "float32": "GDT_Float32",
    "float64": "GDT_Float64",
}


class RasterWriter:
    """栅格写入器，封装 GDAL Dataset 并支持上下文管理器。"""

    def __init__(self, dataset: Any, path: str):
        self.dataset = dataset
        self.path = path

    def write_band(self, data: np.ndarray, band: int = 1) -> None:
        self.write_block(data, 0, 0, band)

    def write_block(self, data: np.ndarray, x: int, y: int, band: int = 1) -> None:
        if self.dataset is None:
            raise RuntimeError("RasterWriter 已关闭")
        self.dataset.GetRasterBand(int(band)).WriteArray(np.asarray(data), int(x), int(y))

    def flush(self) -> None:
        if self.dataset is not None:
            self.dataset.FlushCache()

    def close(self) -> None:
        if self.dataset is not None:
            self.flush()
            self.dataset = None

    def __enter__(self) -> "RasterWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _gdal_dtype(dtype: str) -> int:
    _require_gdal()
    attr_name = _DTYPE_MAP.get(str(dtype).lower())
    if attr_name is None:
        raise ValueError(f"不支持的 GDAL 数据类型: {dtype}")
    return getattr(gdal, attr_name)


def create_raster(
    path: str,
    width: int,
    height: int,
    band_count: int = 1,
    dtype: str = "uint8",
    projection: Optional[str] = None,
    geo_transform: Optional[tuple] = None,
    compress: str = "lzw",
) -> RasterWriter:
    """创建新的 GeoTIFF 栅格文件。"""
    _require_gdal()
    options = []
    if compress:
        options.append(f"COMPRESS={compress.upper()}")
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(str(path), int(width), int(height), int(band_count), _gdal_dtype(dtype), options=options)
    if dataset is None:
        raise IOError(f"创建栅格文件失败: {path}")
    if geo_transform is not None:
        dataset.SetGeoTransform(tuple(geo_transform))
    if projection:
        dataset.SetProjection(projection)
    return RasterWriter(dataset=dataset, path=path)


def write_block(writer: RasterWriter, data: np.ndarray, x: int, y: int, band: int = 1) -> None:
    """向已创建的栅格文件写入数据块。"""
    writer.write_block(data, x, y, band)


def copy_geo_metadata(src_path: str, dst_path: str) -> bool:
    """将源影像的投影和仿射变换复制到目标影像。"""
    try:
        with open_raster(src_path) as src, open_raster(dst_path, mode="update") as dst:
            if src.geo_transform is not None:
                dst.dataset.SetGeoTransform(src.geo_transform)
            if src.projection:
                dst.dataset.SetProjection(src.projection)
            dst.dataset.FlushCache()
        return True
    except Exception as exc:
        print(f"复制地理元数据失败: {exc}")
        return False


def bands_to_rgb(
    data: np.ndarray,
    band_indices: Sequence[int] = (1, 2, 3),
    layout: str = "hwc",
) -> np.ndarray:
    """将多波段数据转换为 OpenCV 兼容的 BGR 显示数组。"""
    array = np.asarray(data)
    if array.ndim == 2:
        return np.dstack([array, array, array]).astype(array.dtype, copy=False)
    if layout.lower() == "bhw":
        array = np.transpose(array, (1, 2, 0))
    if array.ndim != 3:
        raise ValueError(f"不支持的数组维度: {array.shape}")

    selected = []
    channel_count = array.shape[2]
    for idx in band_indices:
        zero_idx = int(idx) - 1
        zero_idx = min(max(zero_idx, 0), channel_count - 1)
        selected.append(array[:, :, zero_idx])
    # 输入 band_indices 表示 RGB，OpenCV 显示使用 BGR，因此反序输出。
    return np.dstack(selected[::-1]).astype(array.dtype, copy=False)


def sample_band_stats(path: str, band: int = 1, sample_size: int = 512) -> Dict[str, Any]:
    """采样读取单波段并返回基础统计信息。"""
    with open_raster(path) as handle:
        sample_w = min(int(sample_size), handle.width)
        sample_h = min(int(sample_size), handle.height)
        sample = read_block(handle, 0, 0, sample_w, sample_h, band_indices=[band])
        if sample.size == 0:
            return {"min": None, "max": None, "class_count": 0}
        return {
            "min": float(np.min(sample)),
            "max": float(np.max(sample)),
            "class_count": int(np.max(sample)) + 1,
            "shape": tuple(sample.shape),
        }


def check_has_pyramids(path: str) -> bool:
    """检查栅格影像是否已有金字塔。"""
    return bool(get_raster_info(path).get("has_pyramids", False))


def build_pyramids(path: str, levels: Optional[Sequence[int]] = None, resampling: str = "NEAREST", callback=None) -> bool:
    """为栅格影像构建金字塔。"""
    if levels is None:
        levels = [2, 4, 8, 16, 32, 64]
    try:
        with open_raster(path, mode="update") as handle:
            if callback:
                callback(0, f"开始构建金字塔: {handle.width}x{handle.height}")
            handle.dataset.BuildOverviews(resampling, [int(level) for level in levels])
            if callback:
                callback(100, "金字塔构建完成")
        return True
    except Exception as exc:
        if callback:
            callback(0, f"构建金字塔失败: {exc}")
        print(f"构建金字塔失败: {exc}")
        return False


def get_raster_info(path: str) -> Dict[str, Any]:
    """快速获取栅格影像摘要信息。"""
    with open_raster(path) as handle:
        return {
            "path": path,
            "width": handle.width,
            "height": handle.height,
            "band_count": handle.band_count,
            "projection": handle.projection,
            "crs_wkt": handle.crs_wkt,
            "geo_transform": handle.geo_transform,
            "overviews": handle.overviews,
            "has_pyramids": len(handle.overviews) > 0,
        }
