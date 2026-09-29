"""
计算数据集每个波段的均值与标准差，用于深度学习输入归一化。

特性：
- 优先使用 GDAL 读取，支持任意波段数与 dtype（uint8/uint16/float32 等）
- 自动从 GDAL 元数据读取 NoData，并支持用户显式指定 nodata 值
- 数据 dtype 不同时按 dtype 选择合适的归一化最大值（uint8 -> 255, uint16 -> 65535 等）
"""
import os
import cv2
import numpy as np
from tqdm import tqdm
from prettytable import PrettyTable

# 公共安全 IO（中文路径、GDAL None 检查）由 utils 统一提供
from utils import imread_unchanged, gdal_open

try:
    from osgeo import gdal
    HAS_GDAL = True
except ImportError:
    HAS_GDAL = False


# 不同 dtype 默认归一化最大值
DEFAULT_MAX_VALUE = {
    'uint8': 255.0,
    'int8': 127.0,
    'uint16': 65535.0,
    'int16': 32767.0,
    'uint32': 4294967295.0,
    'int32': 2147483647.0,
    'float32': 1.0,   # 浮点常已归一或表达反射率
    'float64': 1.0,
}


class DatasetStats:
    def __init__(self, path, img_ext='.tif', is_norm=True, nodata=None,
                 use_gdal=True, max_norm_value=None):
        """
        :param path: 图像目录
        :param img_ext: 文件后缀（不区分大小写）
        :param is_norm: 是否将结果归一化到 [0,1]
        :param nodata: 显式 NoData 值；像素全波段等于该值时排除（None=按数据集元数据）
        :param use_gdal: True 使用 GDAL（推荐用于 .tif 多波段），False 强制 OpenCV
        :param max_norm_value: 归一化最大值；None 时按 dtype 自动选择
        """
        self.path = path
        self.img_ext = img_ext.lower()
        self.is_norm = is_norm
        self.nodata = nodata
        self.use_gdal = use_gdal and HAS_GDAL
        self.max_norm_value = max_norm_value

        if use_gdal and not HAS_GDAL:
            print("[警告] 未检测到 GDAL，自动回退到 OpenCV。")

    def cv2_imread_safe(self, file_path):
        """OpenCV 读取，IMREAD_UNCHANGED 保留原 dtype/通道数。返回 (HWC array, None)。"""
        img = imread_unchanged(file_path)
        if img is None:
            return None, None
        if img.ndim == 2:
            img = img[:, :, np.newaxis]
        else:
            # OpenCV 默认 BGR/BGRA，转为 RGB/RGBA 与 GDAL 行为一致
            if img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            elif img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        return img, None

    def gdal_imread(self, file_path):
        """GDAL 读取，返回 (HWC array, nodata_value)。"""
        try:
            ds = gdal_open(file_path)
            if ds is None:
                return None, None
            arr = ds.ReadAsArray()  # (C,H,W) 或 (H,W)
            band1 = ds.GetRasterBand(1)
            ds_nodata = band1.GetNoDataValue()
            ds = None

            if arr is None:
                return None, None
            if arr.ndim == 2:
                arr = arr[np.newaxis, :, :]
            arr = np.transpose(arr, (1, 2, 0))  # -> (H,W,C)
            return arr, ds_nodata
        except Exception as e:
            print(f"GDAL 读取错误: {file_path} - {e}")
            return None, None


    def calculate(self):
        """扫描目录、累加像素、计算 mean/std。"""
        file_list = [f for f in os.listdir(self.path)
                     if f.lower().endswith(self.img_ext)]

        if not file_list:
            print(f"未找到 {self.img_ext} 文件。")
            return None

        print(f"开始处理 {len(file_list)} 张图像（{'GDAL' if self.use_gdal else 'OpenCV'} 模式）...")

        cumulative_sum = None
        cumulative_sq_sum = None
        total_pixel_count = 0
        first_dtype = None
        first_bands = None
        skipped = 0

        for file_name in tqdm(file_list):
            file_path = os.path.join(self.path, file_name)

            if self.use_gdal:
                img, ds_nodata = self.gdal_imread(file_path)
            else:
                img, ds_nodata = self.cv2_imread_safe(file_path)

            if img is None:
                skipped += 1
                continue

            # NoData 优先级：用户参数 > 数据集元数据
            nodata = self.nodata if self.nodata is not None else ds_nodata

            h, w, c = img.shape
            if cumulative_sum is None:
                cumulative_sum = np.zeros(c, dtype=np.float64)
                cumulative_sq_sum = np.zeros(c, dtype=np.float64)
                first_bands = c
                first_dtype = img.dtype.name
            elif c != first_bands:
                print(f"\n[跳过] {file_name} 波段数 {c} 与首张 {first_bands} 不一致。")
                skipped += 1
                continue

            arr = img.reshape(-1, c).astype(np.float64)

            # 排除 NoData：所有波段都为 NoData 视为无效像素
            if nodata is not None:
                mask_valid = ~np.all(np.isclose(arr, float(nodata)), axis=1)
                arr = arr[mask_valid]
                if arr.size == 0:
                    continue

            cumulative_sum += arr.sum(axis=0)
            cumulative_sq_sum += (arr ** 2).sum(axis=0)
            total_pixel_count += arr.shape[0]

        if total_pixel_count == 0 or cumulative_sum is None:
            print("未找到有效像素，请检查路径或 NoData 设置。")
            return None

        mean = cumulative_sum / total_pixel_count
        variance = (cumulative_sq_sum / total_pixel_count) - (mean ** 2)
        # 防止浮点误差产生极小负数
        variance = np.maximum(variance, 0)
        std = np.sqrt(variance)

        # 归一化
        if self.is_norm:
            max_val = self.max_norm_value
            if max_val is None:
                max_val = DEFAULT_MAX_VALUE.get(first_dtype, 255.0)
            if max_val and max_val != 0:
                mean = mean / max_val
                std = std / max_val

        self.print_table(mean, std, first_bands, first_dtype, total_pixel_count, skipped)
        return {
            'mean': mean.tolist(),
            'std': std.tolist(),
            'bands': first_bands,
            'dtype': first_dtype,
            'pixel_count': int(total_pixel_count),
            'skipped': skipped,
        }

    def print_table(self, mean, std, bands, dtype, pixel_count, skipped):
        # 自动列名：1 通道 'V'；3 -> R/G/B；4 -> R/G/B/A；其他 B1..Bn
        if bands == 3:
            band_names = ['R', 'G', 'B']
        elif bands == 4:
            band_names = ['R', 'G', 'B', 'A']
        elif bands == 1:
            band_names = ['V']
        else:
            band_names = [f'B{i + 1}' for i in range(bands)]

        table = PrettyTable()
        table.field_names = ['Type'] + band_names
        table.add_row(['Mean'] + [f'{v:.4f}' for v in mean])
        table.add_row(['Std'] + [f'{v:.4f}' for v in std])

        print(f"\n计算结果（dtype={dtype}, bands={bands}, "
              f"valid_pixels={pixel_count}, skipped_files={skipped}）:")
        print(table)

        print(f"\n[Copy for Config]\nMean: {mean.tolist()}\nStd:  {std.tolist()}")


if __name__ == '__main__':
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    parser = argparse.ArgumentParser(
        description=("计算数据集每个波段的均值与标准差（深度学习输入归一化）。"
                     "支持任意波段数、dtype、NoData。")
    )
    parser.add_argument('--path', default=r'E:\Samples-Water\chengdu\image',
                        help='图像目录（DEMO 默认）')
    parser.add_argument('--ext', default='.tif', help='图像后缀（默认 .tif）')
    parser.add_argument('--no-normalize', dest='normalize', action='store_false',
                        help='输出原始像素值统计（不按 dtype 最大值归一化）')
    parser.set_defaults(normalize=True)
    parser.add_argument('--nodata', type=float, default=None,
                        help='显式 NoData 值（例如 0 排除全黑填充区）；不传则尝试 GDAL 元数据')
    parser.add_argument('--no-gdal', dest='use_gdal', action='store_false',
                        help='改用 OpenCV 读取（仅适合 8 位 1/3 通道；遥感 .tif 必须用 GDAL）')
    parser.set_defaults(use_gdal=True)
    args = parser.parse_args()

    stats_tool = DatasetStats(
        path=args.path,
        img_ext=args.ext,
        is_norm=args.normalize,
        nodata=args.nodata,
        use_gdal=args.use_gdal,
    )
    stats_tool.calculate()