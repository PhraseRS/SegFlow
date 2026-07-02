"""
分析语义分割标签的类别分布。

特性：
- 自动检测所有类别（不指定 class_values 时）
- 支持多类（不只二分类）
- 支持 16 位标签 / GDAL 读取
- 输出每类像素占比、图片占比，以及 inverse-frequency 类别权重
- 兼容二分类：仍可显式 class_values=[0, 255]
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


class LabelAnalyzer:
    def __init__(self, folder_path, ext='.png', class_values=None,
                 ignore_value=None, use_gdal=False):
        """
        :param folder_path: 标签文件夹路径
        :param ext: 文件后缀（不区分大小写）
        :param class_values: 期望统计的类别 ID 列表；None=自动检测所有类别
        :param ignore_value: 忽略值（如 255 表示未标注），不计入任何类别也不计入总数
        :param use_gdal: True 用 GDAL（推荐 16 位标签），False 用 OpenCV
        """
        self.folder_path = folder_path
        self.ext = ext.lower()
        self.class_values = (sorted(set(class_values))
                             if class_values is not None else None)
        self.ignore_value = ignore_value
        self.use_gdal = use_gdal and HAS_GDAL

    def imread_label(self, file_path):
        """读取标签图像，返回 (H,W) ndarray 或 None。"""
        if self.use_gdal:
            try:
                ds = gdal_open(file_path)
                if ds is None:
                    return None
                arr = ds.GetRasterBand(1).ReadAsArray()
                ds = None
                return arr
            except Exception as e:
                print(f"GDAL 读取错误: {file_path} - {e}")
                return None
        img = imread_unchanged(file_path)
        if img is None:
            return None
        if img.ndim == 3:
            img = img[..., 0]  # 多通道标签取第 0 通道
        return img


    def run(self):
        files = [f for f in os.listdir(self.folder_path)
                 if f.lower().endswith(self.ext)]
        if not files:
            print(f"未找到 {self.ext} 文件。")
            return None

        print(f"开始分析 {len(files)} 张标签图像（{'GDAL' if self.use_gdal else 'OpenCV'} 模式）...")

        pixel_counter = {}      # 类别 -> 像素总数（含 '__noise__' 兜底）
        image_counter = {}      # 类别 -> 含该类的图片数
        total_pixels = 0
        ignore_pixels_total = 0
        empty_imgs = 0
        total_imgs = 0
        auto_classes = self.class_values is None

        for fn in tqdm(files):
            img = self.imread_label(os.path.join(self.folder_path, fn))
            if img is None:
                continue
            total_imgs += 1

            # 处理忽略值
            if self.ignore_value is not None:
                ignore_mask = (img == self.ignore_value)
                ignore_pixels_total += int(ignore_mask.sum())
                valid = img[~ignore_mask]
            else:
                valid = img.ravel()

            total_pixels += valid.size

            unique_vals, counts = np.unique(valid, return_counts=True)
            present_in_img = set()
            for v, c in zip(unique_vals.tolist(), counts.tolist()):
                if (not auto_classes) and v not in self.class_values:
                    pixel_counter['__noise__'] = pixel_counter.get('__noise__', 0) + c
                    continue
                pixel_counter[v] = pixel_counter.get(v, 0) + c
                present_in_img.add(v)

            for v in present_in_img:
                image_counter[v] = image_counter.get(v, 0) + 1

            if not present_in_img:
                empty_imgs += 1

        if total_imgs == 0 or total_pixels == 0:
            print("未检测到有效数据。")
            return None

        if auto_classes:
            shown_classes = sorted(k for k in pixel_counter.keys() if k != '__noise__')
        else:
            shown_classes = self.class_values

        report = self._build_report(shown_classes, pixel_counter, image_counter,
                                    total_pixels, total_imgs, ignore_pixels_total,
                                    empty_imgs)
        self._print_report(report)
        return report

    def _build_report(self, classes, pix, img, total_px, total_im, ignore_px, empty_im):
        rows = []
        for v in classes:
            p = pix.get(v, 0)
            i = img.get(v, 0)
            rows.append({
                'class': int(v) if isinstance(v, (np.integer, int)) else v,
                'pixels': int(p),
                'pixel_ratio': p / total_px if total_px else 0.0,
                'images': int(i),
                'image_ratio': i / total_im if total_im else 0.0,
            })
        # inverse-frequency 权重（基于像素占比），并归一化到平均=1
        ratios = np.array([r['pixel_ratio'] for r in rows], dtype=np.float64)
        with np.errstate(divide='ignore', invalid='ignore'):
            inv = np.where(ratios > 0, 1.0 / ratios, 0.0)
        if inv.size > 0 and inv.mean() > 0:
            inv = inv / inv.mean()
        for r, w in zip(rows, inv.tolist()):
            r['inv_freq_weight'] = float(w)

        return {
            'rows': rows,
            'total_pixels': total_px,
            'total_images': total_im,
            'ignore_pixels': ignore_px,
            'empty_images': empty_im,
            'noise_pixels': pix.get('__noise__', 0),
        }

    def _print_report(self, report):
        table = PrettyTable()
        table.field_names = ['Class', 'Images', 'Img%', 'Pixels', 'Pixel%', 'InvFreqWeight']
        for r in report['rows']:
            table.add_row([
                r['class'], r['images'], f"{r['image_ratio']:.2%}",
                r['pixels'], f"{r['pixel_ratio']:.4%}",
                f"{r['inv_freq_weight']:.4f}",
            ])
        if report['noise_pixels'] > 0:
            ratio = report['noise_pixels'] / report['total_pixels']
            table.add_row(['(noise)', '-', '-', report['noise_pixels'],
                           f"{ratio:.4%}", '-'])

        print("\n=== 数据集分布统计报告 ===")
        print(table)
        print(f"总图片: {report['total_images']}, 总像素(去除ignore): {report['total_pixels']}")
        if report['ignore_pixels']:
            print(f"忽略像素 (ignore_value): {report['ignore_pixels']}")
        if report['empty_images']:
            print(f"无任何已知类别的图片: {report['empty_images']}")

        # 训练建议：极不平衡时给出 Loss / 采样建议
        ratios = [r['pixel_ratio'] for r in report['rows'] if r['pixel_ratio'] > 0]
        if len(ratios) >= 2:
            min_r, max_r = min(ratios), max(ratios)
            if max_r / min_r > 50:
                print("\n[分析建议] 类别极度不平衡（最大/最小 > 50x）:")
                print("  - 使用 Weighted Cross Entropy（参考 InvFreqWeight 列）")
                print("  - 尝试 Dice Loss / Focal Loss 改善小目标")
                print("  - 数据增强中对稀有类做 Oversampling")


if __name__ == "__main__":
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    def _parse_int_list(s: str):
        """将 '0,1,2,3' 解析为 [0,1,2,3]；'auto' 或空 -> None。"""
        s = s.strip()
        if not s or s.lower() == 'auto':
            return None
        try:
            return [int(x.strip()) for x in s.split(',') if x.strip()]
        except ValueError as e:
            raise argparse.ArgumentTypeError(
                f"--classes 必须是逗号分隔整数列表或 'auto'，得到: {s!r} ({e})"
            ) from e

    parser = argparse.ArgumentParser(
        description=("分析语义分割标签的类别分布；支持自动检测、多类、"
                     "ignore_value、inverse-frequency 权重。")
    )
    parser.add_argument('--path', default=r'E:\nets-dataset\water\train_samples\label',
                        help='标签目录（DEMO 默认）')
    parser.add_argument('--ext', default='.png', help='标签后缀（默认 .png）')
    parser.add_argument('--classes', type=_parse_int_list, default=None,
                        help=("期望统计的类别 ID，逗号分隔（如 '0,1,2,3'）；"
                              "默认 'auto' 自动检测所有类别"))
    parser.add_argument('--ignore-value', type=int, default=None,
                        help='忽略值（例如 255 表示未标注），不计入任何类别')
    parser.add_argument('--use-gdal', action='store_true',
                        help='用 GDAL 读取（推荐 16 位标签）')
    args = parser.parse_args()

    analyzer = LabelAnalyzer(
        folder_path=args.path,
        ext=args.ext,
        class_values=args.classes,
        ignore_value=args.ignore_value,
        use_gdal=args.use_gdal,
    )
    analyzer.run()