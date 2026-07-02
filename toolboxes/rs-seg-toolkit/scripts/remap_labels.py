"""
将标签图按用户指定的 {old_value: new_value} 映射做像素值重映射。

特性：
- 参数化的 mapping 字典，不再硬编码
- unmapped='keep' 保留未映射值（向后兼容旧行为）
       'set'  把所有未映射值统一为 unmapped_value（清洗杂色）
- 用 numpy LUT（查找表）实现，对 uint8/uint16 都可向量化
- 使用 IMREAD_UNCHANGED 保留 16 位标签的 dtype
- 后缀大小写不敏感，支持 .png/.tif 等
"""
import os
import cv2
import numpy as np
from tqdm import tqdm
from typing import Dict, Optional

# 公共安全 IO（中文路径、IMREAD_UNCHANGED）由 utils 统一提供
from utils import imread_unchanged as cv2_imread_unchanged
from utils import imwrite_safe as cv2_imwrite_safe


# OpenCV imencode 支持的常见标签后缀
_SUPPORTED_EXTS = {'.png', '.tif', '.tiff', '.bmp'}


def _build_lut(mapping: Dict[int, int], dtype: np.dtype,
               unmapped: str, unmapped_value: int) -> Optional[np.ndarray]:
    """
    为整数 dtype 构造查找表 LUT[v] = mapping.get(v, default)。
    仅在 dtype 是较小的整数（uint8/uint16/int8）时有意义；更大的整数返回 None
    让上层走逐值替换。
    """
    if dtype == np.uint8:
        lut_size = 256
        lut_dtype = np.uint8
    elif dtype == np.uint16:
        lut_size = 65536
        lut_dtype = np.uint16
    elif dtype == np.int8:
        lut_size = 256
        lut_dtype = np.int8
    else:
        return None

    if unmapped == 'keep':
        lut = np.arange(lut_size, dtype=np.int64)
    elif unmapped == 'set':
        lut = np.full(lut_size, unmapped_value, dtype=np.int64)
    else:
        raise ValueError(f"unmapped 必须是 'keep' 或 'set'，得到: {unmapped!r}")

    for old, new in mapping.items():
        if not (0 <= int(old) < lut_size):
            raise ValueError(
                f"mapping 中的旧值 {old} 超出 dtype {dtype} 的范围 [0,{lut_size})")
        lut[int(old)] = int(new)

    # 范围检查：new 值是否能装进 lut_dtype
    info = np.iinfo(lut_dtype)
    if lut.min() < info.min or lut.max() > info.max:
        raise ValueError(
            f"mapping 的新值超出 dtype {lut_dtype} 范围 [{info.min},{info.max}]")

    return lut.astype(lut_dtype)


def _remap_fallback(img: np.ndarray, mapping: Dict[int, int],
                    unmapped: str, unmapped_value: int) -> np.ndarray:
    """LUT 不适用时（如 int32 标签）的逐值替换。"""
    if unmapped == 'set':
        out = np.full_like(img, unmapped_value)
    else:
        out = img.copy()
    for old, new in mapping.items():
        out[img == old] = new
    return out


def remap_image(img: np.ndarray, mapping: Dict[int, int],
                unmapped: str = 'keep', unmapped_value: int = 0) -> np.ndarray:
    """对单张标签图做重映射，返回与输入同 dtype 的新数组。"""
    lut = _build_lut(mapping, img.dtype, unmapped, unmapped_value)
    if lut is not None:
        return lut[img]
    return _remap_fallback(img, mapping, unmapped, unmapped_value)


def process_labels(src_dir: str, dst_dir: str,
                   mapping: Dict[int, int],
                   ext: str = '.png',
                   unmapped: str = 'keep',
                   unmapped_value: int = 0) -> None:
    """
    批量重映射目录下所有标签。

    :param src_dir: 输入目录
    :param dst_dir: 输出目录（自动创建）
    :param mapping: {旧值: 新值} 字典，例如 {30: 1} 或 {0: 0, 255: 1}
    :param ext: 处理的标签后缀（不区分大小写）
    :param unmapped: 'keep' 保留未映射值（默认）；'set' 改为 unmapped_value
    :param unmapped_value: unmapped='set' 时使用的填充值
    """
    if ext.lower() not in _SUPPORTED_EXTS:
        print(f"[警告] 后缀 {ext} 不在常见标签格式 {_SUPPORTED_EXTS} 中，仍会尝试处理。")

    if not os.path.isdir(src_dir):
        print(f"错误: 输入目录不存在: {src_dir}")
        return

    os.makedirs(dst_dir, exist_ok=True)

    files = [f for f in os.listdir(src_dir)
             if f.lower().endswith(ext.lower())]
    print(f"开始处理 {len(files)} 个 {ext} 文件，"
          f"映射 {len(mapping)} 条，未映射策略={unmapped}")

    success, fail = 0, 0
    for fn in tqdm(files):
        src_path = os.path.join(src_dir, fn)
        dst_path = os.path.join(dst_dir, fn)
        img = cv2_imread_unchanged(src_path)
        if img is None:
            fail += 1
            continue
        try:
            out = remap_image(img, mapping, unmapped, unmapped_value)
        except ValueError as e:
            print(f"\n[错误] {fn}: {e}")
            fail += 1
            continue
        if cv2_imwrite_safe(dst_path, out):
            success += 1
        else:
            fail += 1

    print(f"完成。成功: {success}, 失败: {fail}")


if __name__ == '__main__':
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    def _parse_mapping(s: str):
        """将 '30:1,50:2' 解析为 {30:1, 50:2}。"""
        result = {}
        for pair in s.split(','):
            pair = pair.strip()
            if not pair:
                continue
            if ':' not in pair:
                raise argparse.ArgumentTypeError(
                    f"映射项必须形如 'old:new'，得到: {pair!r}"
                )
            old, new = pair.split(':', 1)
            try:
                result[int(old.strip())] = int(new.strip())
            except ValueError as e:
                raise argparse.ArgumentTypeError(
                    f"映射项 {pair!r} 的键值必须是整数: {e}"
                ) from e
        if not result:
            raise argparse.ArgumentTypeError("映射不能为空")
        return result

    parser = argparse.ArgumentParser(
        description=("按 {old:new} 映射对标签图做像素值重映射，"
                     "支持 8/16 位、LUT 加速、unmapped 策略。")
    )
    parser.add_argument('--src', default=r"E:\Samples-Water\chengdu\label-png",
                        help='源标签目录（DEMO 默认）')
    parser.add_argument('--dst', default=r"E:\Samples-Water\chengdu\label-png-new",
                        help='输出目录（DEMO 默认）')
    parser.add_argument('--mapping', type=_parse_mapping, default={30: 1},
                        help=("映射字典字符串，形如 '30:1,50:2,100:3'；"
                              "默认 '30:1'（旧版兼容：前景 30 -> 1）"))
    parser.add_argument('--ext', default='.png', help='标签后缀（默认 .png）')
    parser.add_argument('--unmapped', choices=['keep', 'set'], default='keep',
                        help="未映射值策略：keep 保留原值；set 改为 --unmapped-value")
    parser.add_argument('--unmapped-value', type=int, default=0,
                        help='当 --unmapped=set 时使用的填充值（默认 0）')
    args = parser.parse_args()

    process_labels(args.src, args.dst, args.mapping,
                   ext=args.ext, unmapped=args.unmapped,
                   unmapped_value=args.unmapped_value)