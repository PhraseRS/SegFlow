import os
import numpy as np
import cv2
from osgeo import gdal
from osgeo import gdal_array
from tqdm import tqdm

# 公共安全 IO（中文路径、GDAL None 检查）由 utils 统一提供
from utils import imwrite_safe as cv2_imwrite_safe
from utils import gdal_open

# 支持的输出扩展名集合。'auto' 表示根据 dtype/波段自动选择。
SUPPORTED_EXTS = {'auto', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.npy'}
# 小图（W<crop_size 或 H<crop_size）处理策略
SMALL_IMAGE_POLICIES = {'skip', 'pad'}
# 波段顺序处理策略：
#   'auto' 从 GDAL ColorInterp 推断；只对 3 波段有意义，其他波段自动按 keep 处理
#   'rgb'  断言输入是 RGB（写 PNG/JPG 时翻转为 cv2 期望的 BGR）
#   'bgr'  断言输入已是 BGR（不翻转）
#   'keep' 不做任何颜色变换
BAND_ORDERS = {'auto', 'rgb', 'bgr', 'keep'}
# 末尾不齐时的边缘块策略（仅对常规大图分支生效；小图走 small_image 策略）
#   'append' 当前/默认：补一个左上角 = (W-crop_size) 的边缘块，可能与上一块高度重叠
#   'drop'   丢掉末尾不齐的条带，避免边缘块与正常块产生重复样本（训练数据集推荐）
#   'pad'    保留末尾条带原始位置，按真实尺寸读出后右/下补 0 到 crop_size（不重复样本）
EDGE_POLICIES = {'append', 'drop', 'pad'}

# --- 核心转换函数 ---
def gdal_to_opencv(gdal_data, bgr_swap=False):
    """
    将 GDAL ReadAsArray 的 (Bands, Height, Width) 转为 OpenCV 的 (Height, Width, Bands)。

    :param gdal_data: GDAL 读出的 ndarray，(C,H,W) 或单波段 (H,W)
    :param bgr_swap: 仅当输入恰好是 3 波段，且你确定波段顺序是 RGB、需要保存为 OpenCV BGR
                     才设为 True。默认 False（保持原波段顺序，不做颜色翻转）。
                     注意：遥感影像第 1/2/3 波段不一定就是 R/G/B，盲目翻转会破坏数据语义。
    """
    # 维度转换：(C, H, W) -> (H, W, C)
    if len(gdal_data.shape) == 3:
        opencv_data = np.transpose(gdal_data, (1, 2, 0))

        # 仅在用户明确要求时做 RGB <-> BGR 翻转
        if bgr_swap and opencv_data.shape[2] == 3:
            opencv_data = cv2.cvtColor(opencv_data, cv2.COLOR_RGB2BGR)
    else:
        # 单波段
        opencv_data = gdal_data

    return opencv_data


def _pick_auto_ext(dtype, bands):
    """
    根据 GDAL 影像 dtype 与波段数自动选择安全的输出扩展名。

    规则：
      - uint8 + 1/3/4 波段 -> .png（语义分割训练最常见）
      - uint16 + 1 波段     -> .png（PNG 16-bit 灰度，标签场景）
      - 其他（float、≥5 波段、uint16 多通道等）-> .tif（GDAL 无压缩 GeoTIFF，不丢精度）
    """
    if dtype == np.uint8 and bands in (1, 3, 4):
        return '.png'
    if dtype == np.uint16 and bands == 1:
        return '.png'
    return '.tif'


def _is_cv_writable(ext, dtype, bands):
    """
    判断 (ext, dtype, bands) 是否能用 cv2.imencode 安全写出。
    用于在切块循环外提前判断，避免逐 patch 静默失败。
    """
    ext = ext.lower()
    if ext in ('.tif', '.tiff', '.npy'):
        return True   # 走 GDAL / np.save 路径，无格式限制
    if ext in ('.png',):
        if dtype == np.uint8 and bands in (1, 3, 4):
            return True
        if dtype == np.uint16 and bands == 1:
            return True
        return False
    if ext in ('.jpg', '.jpeg'):
        return dtype == np.uint8 and bands in (1, 3)
    return False


def _save_patch_as_tif(save_path, gdal_data, src_dataset, x_off, y_off):
    """
    将 GDAL 风格 (C,H,W) 或 (H,W) 的 ndarray 保存为无压缩 GeoTIFF。
    会从源 dataset 复制投影信息，并把 GeoTransform 平移到 patch 的左上角。
    返回 True/False。
    """
    try:
        if gdal_data.ndim == 2:
            bands, h, w = 1, gdal_data.shape[0], gdal_data.shape[1]
            arr = gdal_data[np.newaxis, :, :]
        else:
            bands, h, w = gdal_data.shape
            arr = gdal_data

        gdal_dtype = gdal_array.NumericTypeCodeToGDALTypeCode(arr.dtype)
        if gdal_dtype is None:
            print(f"[clip] 不支持的 dtype 写 TIFF: {arr.dtype} -> {save_path}")
            return False

        driver = gdal.GetDriverByName('GTiff')
        out_ds = driver.Create(save_path, w, h, bands, gdal_dtype)
        if out_ds is None:
            print(f"[clip] GDAL Create 失败: {save_path}")
            return False

        # 复制投影 + 平移 GeoTransform 到 patch 左上角
        proj = src_dataset.GetProjection()
        gt = src_dataset.GetGeoTransform(can_return_null=True)
        if proj:
            out_ds.SetProjection(proj)
        if gt is not None:
            new_gt = (
                gt[0] + x_off * gt[1] + y_off * gt[2],
                gt[1], gt[2],
                gt[3] + x_off * gt[4] + y_off * gt[5],
                gt[4], gt[5],
            )
            out_ds.SetGeoTransform(new_gt)

        for b in range(bands):
            out_ds.GetRasterBand(b + 1).WriteArray(arr[b])
        out_ds.FlushCache()
        out_ds = None
        return True
    except Exception as e:
        print(f"[clip] 写 TIFF 异常: {save_path} - {e}")
        return False


def _save_patch(save_path, gdal_data, src_dataset, x_off, y_off, bgr_swap):
    """
    根据 save_path 的扩展名写出 patch。返回 True/False。
      - .png/.jpg/.jpeg: 走 cv2.imencode（中文路径安全），需要 (H,W) 或 (H,W,C)
      - .tif/.tiff:      走 GDAL，保留 dtype/坐标
      - .npy:            走 np.save，原样保存（C,H,W）
    """
    ext = os.path.splitext(save_path)[1].lower()
    if ext in ('.tif', '.tiff'):
        return _save_patch_as_tif(save_path, gdal_data, src_dataset, x_off, y_off)
    if ext == '.npy':
        try:
            np.save(save_path, gdal_data)
            return True
        except Exception as e:
            print(f"[clip] np.save 失败: {save_path} - {e}")
            return False
    # PNG / JPG：转为 OpenCV 排布
    img_cv = gdal_to_opencv(gdal_data, bgr_swap=bgr_swap)
    return cv2_imwrite_safe(save_path, img_cv)


def _pad_to_crop(gdal_data, crop_size):
    """
    将 (C,H,W) 或 (H,W) 的小块右下补 0，到 crop_size×crop_size。
    用于 small_image='pad' 策略。
    """
    if gdal_data.ndim == 2:
        h, w = gdal_data.shape
        out = np.zeros((crop_size, crop_size), dtype=gdal_data.dtype)
        out[:h, :w] = gdal_data
    else:
        c, h, w = gdal_data.shape
        out = np.zeros((c, crop_size, crop_size), dtype=gdal_data.dtype)
        out[:, :h, :w] = gdal_data
    return out


def _compute_steps(length, crop_size, stride, edge_policy):
    """
    生成单个轴上的切片左上角坐标列表。

    适用于"length >= crop_size"的常规情况；length < crop_size 由外层 small_image 分支处理。

    :param length:      该轴长度（width 或 height）
    :param crop_size:   patch 边长
    :param stride:      步长（已 max(1, ...)）
    :param edge_policy: 'append' / 'drop' / 'pad'

    :return: (steps, edge_idx)
        - steps:    左上角坐标 list[int]
        - edge_idx: list[int]，steps 中"边缘块"的下标（pad 时该索引对应的块需要补 0）
                    append/drop 下 edge_idx 为空（append 把边缘块当普通块处理，
                    pad 才需要标记哪些块要 _pad_to_crop）
    """
    if length < crop_size:
        # 防御性：理论上 too_small 分支已拦截，这里返回单块兜底
        return [0], []

    # 常规网格：左上角从 0 开始，每步前进 stride，要求块整体落在 [0, length]
    steps = list(range(0, length - crop_size + 1, stride))
    if not steps:
        # crop_size > length 时上面已 return；这里 length == crop_size 也会得 [0]
        steps = [0]

    last = steps[-1]
    # P0 改造：直接看最后一块的右沿是否到边，避免 "% stride" 的 corner case
    if last + crop_size >= length:
        # 已经贴到边，无需任何处理
        return steps, []

    # 末尾不齐，按策略处理
    if edge_policy == 'append':
        # 旧行为：补一个左上角 = length - crop_size 的边缘块；可能与上一块高度重叠
        steps.append(length - crop_size)
        return steps, []
    if edge_policy == 'drop':
        # 直接丢掉末尾不齐的条带
        return steps, []
    if edge_policy == 'pad':
        # 保留下一个 stride 起点（last + stride），让该位置成为边缘块；
        # 该块按真实可读尺寸读出后由 _pad_to_crop 补 0，不与上一块产生大重叠
        edge_x = last + stride
        # 安全边界：edge_x 必须严格在 [0, length) 之内才算合法
        if 0 <= edge_x < length:
            steps.append(edge_x)
            return steps, [len(steps) - 1]
        return steps, []
    # 不会到这里（_validate_clip_args 已校验）
    return steps, []


def _validate_clip_args(crop_size, overlap_ratio, dst_ext, small_image,
                        band_order='keep', edge_policy='append'):
    """参数校验，越界直接抛 ValueError，避免静默生成错误数据。"""
    if not isinstance(crop_size, int) or crop_size <= 0:
        raise ValueError(f"crop_size 必须为正整数，得到 {crop_size!r}")
    if not (0.0 <= overlap_ratio < 1.0):
        raise ValueError(
            f"overlap_ratio 必须在 [0, 1)，得到 {overlap_ratio}。"
            "0 表示不重叠，例如 0.1 表示 10%。"
        )
    ext_norm = dst_ext.lower() if isinstance(dst_ext, str) else dst_ext
    if ext_norm not in SUPPORTED_EXTS:
        raise ValueError(
            f"dst_ext 必须是 {sorted(SUPPORTED_EXTS)} 之一，得到 {dst_ext!r}"
        )
    if small_image not in SMALL_IMAGE_POLICIES:
        raise ValueError(
            f"small_image 必须是 {sorted(SMALL_IMAGE_POLICIES)} 之一，得到 {small_image!r}"
        )
    if band_order not in BAND_ORDERS:
        raise ValueError(
            f"band_order 必须是 {sorted(BAND_ORDERS)} 之一，得到 {band_order!r}"
        )
    if edge_policy not in EDGE_POLICIES:
        raise ValueError(
            f"edge_policy 必须是 {sorted(EDGE_POLICIES)} 之一，得到 {edge_policy!r}"
        )


def _detect_band_order(dataset):
    """
    从 GDAL ColorInterpretation 推断 3 波段影像的波段顺序。

    :return: 'rgb' / 'bgr' / 'keep'（未知或非 3 波段时返回 'keep'）
    """
    if dataset.RasterCount != 3:
        return 'keep'
    interps = [dataset.GetRasterBand(i + 1).GetColorInterpretation()
               for i in range(3)]
    rgb = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand)
    bgr = (gdal.GCI_BlueBand, gdal.GCI_GreenBand, gdal.GCI_RedBand)
    if tuple(interps) == rgb:
        return 'rgb'
    if tuple(interps) == bgr:
        return 'bgr'
    return 'keep'


def _resolve_bgr_swap(dataset, band_order, bgr_swap_legacy):
    """
    根据 band_order 决定写 PNG/JPG 时是否需要做 RGB->BGR 翻转。

    band_order='auto' -> 用 ColorInterp 推断
    band_order='rgb'  -> 输入是 RGB，cv2 要 BGR，需翻转
    band_order='bgr'  -> 输入已是 BGR，不翻转
    band_order='keep' -> 退化到 legacy bgr_swap（向后兼容旧调用）

    :return: 最终的 bool bgr_swap，仅 3 波段时生效
    """
    if dataset.RasterCount != 3:
        return False  # 非 3 波段时 cv2.cvtColor 路径根本不会触发，返回什么都行

    if band_order == 'auto':
        detected = _detect_band_order(dataset)
        if detected == 'rgb':
            return True
        if detected == 'bgr':
            return False
        # 未知 -> 退化到 legacy
        print("[clip] band_order=auto 但未能从 ColorInterp 推断 (可能是未设置元数据)，"
              f"回退到 bgr_swap={bgr_swap_legacy}")
        return bool(bgr_swap_legacy)
    if band_order == 'rgb':
        return True
    if band_order == 'bgr':
        return False
    # band_order='keep'
    return bool(bgr_swap_legacy)


def _resolve_nodata(dataset, nodata_value):
    """显式 nodata_value 优先；否则取 band1 的 GetNoDataValue()，可能为 None。"""
    if nodata_value is not None:
        return float(nodata_value)
    nd = dataset.GetRasterBand(1).GetNoDataValue()
    return None if nd is None else float(nd)


def _valid_ratio(data, nodata):
    """
    计算 patch 中"有效像素"占比。

    - 多波段 (C,H,W)：要求所有波段都不等于 nodata 才算有效；nodata=None 时再检查 NaN
    - 单波段 (H,W)：直接判等
    nodata is None 时仅统计 NaN（float）；无 NaN 即全有效。
    """
    if data.ndim == 3:
        c, h, w = data.shape
        total = h * w
        if nodata is None:
            if np.issubdtype(data.dtype, np.floating):
                # 任一波段为 NaN 视为无效
                invalid = np.isnan(data).any(axis=0)
                return float((~invalid).sum()) / total
            return 1.0
        # 整数/浮点 nodata 比较：每个像素全部波段都 == nodata 才算无效
        if np.issubdtype(data.dtype, np.floating):
            invalid_per_band = (data == nodata) | np.isnan(data)
        else:
            invalid_per_band = (data == nodata)
        invalid = invalid_per_band.all(axis=0)
        return float((~invalid).sum()) / total

    # 单波段
    h, w = data.shape
    total = h * w
    if nodata is None:
        if np.issubdtype(data.dtype, np.floating):
            return float((~np.isnan(data)).sum()) / total
        return 1.0
    if np.issubdtype(data.dtype, np.floating):
        invalid = (data == nodata) | np.isnan(data)
    else:
        invalid = (data == nodata)
    return float((~invalid).sum()) / total


def _foreground_ratio(label_data, ignore_value=0):
    """
    label patch 中前景像素占比。默认背景值为 0。

    :param label_data: (H, W) 或 (1, H, W)
    :param ignore_value: 视为背景的像素值（默认 0）
    """
    if label_data.ndim == 3:
        # 单波段标签也可能被 GDAL 读成 (1, H, W)；取第 0 个
        label_data = label_data[0]
    total = label_data.size
    if total == 0:
        return 0.0
    return float((label_data != ignore_value).sum()) / total


def clip_image_gdal(src_path, dst_dir, crop_size=1024, overlap_ratio=0.1,
                    dst_ext='auto', bgr_swap=False, small_image='skip',
                    band_order='keep', nodata_value=None, min_valid_ratio=0.0,
                    edge_policy='append'):
    """
    使用 GDAL 分块读取并裁剪为语义分割训练用的 patch。

    :param src_path:        输入 GeoTIFF / IMG / VRT 等 GDAL 可读栅格
    :param dst_dir:         输出目录（不存在则自动创建）
    :param crop_size:       patch 尺寸（正方形）
    :param overlap_ratio:   重叠率，[0, 1)，0.1 表示重叠 10%
    :param dst_ext:         输出扩展名。'auto' 根据 dtype/波段自动选择；
                            也可显式传入 '.png'/'.jpg'/'.tif'/'.npy'
    :param bgr_swap:        旧参数；仅当 band_order='keep' 时生效。默认 False
    :param small_image:     小图策略：'skip' 跳过（默认）；'pad' 右下补 0
    :param band_order:      波段顺序处理：
                            'keep' 不动（默认，向后兼容旧调用）
                            'auto' 从 GDAL ColorInterp 推断（仅 3 波段有效）
                            'rgb'  显式声明输入是 RGB（写 PNG/JPG 时翻转给 cv2）
                            'bgr'  显式声明输入是 BGR（不翻转）
    :param nodata_value:    nodata 值；None 则尝试从 GDAL band 元数据读取
    :param min_valid_ratio: patch 中非 nodata 像素占比下限；低于则跳过。
                            0.0（默认）表示不过滤
    :param edge_policy:     大图末尾不齐时的边缘块策略：
                            'append' 补一个贴边的边缘块，可能与上一块高度重叠（默认；
                                     适合推理拼接，全图覆盖）
                            'drop'   丢掉末尾不齐的条带（适合训练数据集，避免重复样本）
                            'pad'    保留末尾位置，按真实尺寸读出后右/下补 0 到 crop_size
                                     （保留边缘信息但不重复）
    :return: dict(total, success, failed, skipped, filtered, ext)
    """
    # 0. 参数校验（fail loudly）
    _validate_clip_args(crop_size, overlap_ratio, dst_ext, small_image,
                        band_order, edge_policy)
    if not (0.0 <= min_valid_ratio <= 1.0):
        raise ValueError(f"min_valid_ratio 必须在 [0, 1]，得到 {min_valid_ratio}")

    # 1. 打开影像
    dataset = gdal_open(src_path)
    if dataset is None:
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0,
                'filtered': 0, 'ext': None}

    try:
        os.makedirs(dst_dir, exist_ok=True)

        width = dataset.RasterXSize
        height = dataset.RasterYSize
        bands = dataset.RasterCount
        gdal_band_dtype = dataset.GetRasterBand(1).DataType
        np_dtype = np.dtype(gdal_array.GDALTypeCodeToNumericTypeCode(gdal_band_dtype))

        ext = _pick_auto_ext(np_dtype, bands) if dst_ext == 'auto' else dst_ext.lower()
        if not _is_cv_writable(ext, np_dtype, bands):
            raise ValueError(
                f"{os.path.basename(src_path)}: dtype={np_dtype}, bands={bands} "
                f"无法写为 {ext}。建议改用 dst_ext='auto' 或 '.tif'。"
            )

        # band_order 决定最终 bgr_swap（band_order 优先于 legacy 参数）
        effective_bgr_swap = _resolve_bgr_swap(dataset, band_order, bgr_swap)

        # nodata 解析（用户显式传 > GDAL 元数据 > None）
        nodata = _resolve_nodata(dataset, nodata_value)
        do_filter = min_valid_ratio > 0.0

        filename = os.path.splitext(os.path.basename(src_path))[0]

        too_small = (width < crop_size) or (height < crop_size)
        if too_small and small_image == 'skip':
            print(f"[clip] 跳过小图: {filename} ({width}x{height} < {crop_size})")
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 1,
                    'filtered': 0, 'ext': ext}

        stride = max(1, int(crop_size * (1 - overlap_ratio)))

        if too_small:
            # 小图分支独立走 small_image 策略，不参与 edge_policy
            x_steps, y_steps = [0], [0]
            x_edge_idx = y_edge_idx = []
        else:
            x_steps, x_edge_idx = _compute_steps(width, crop_size, stride, edge_policy)
            y_steps, y_edge_idx = _compute_steps(height, crop_size, stride, edge_policy)
        x_edge_set = set(x_edge_idx)
        y_edge_set = set(y_edge_idx)

        total = len(x_steps) * len(y_steps)
        success = failed = filtered = 0

        for yi, y in enumerate(y_steps):
            for xi, x in enumerate(x_steps):
                # 实际可读尺寸：常规块 = crop_size；edge_policy=pad 的边缘块按真实尺寸读，
                # 后面再补 0；append/drop 模式下边缘块的 x/y 已经回退到贴边位置，
                # 此处也 = crop_size
                curr_w = min(crop_size, width - x)
                curr_h = min(crop_size, height - y)

                data = dataset.ReadAsArray(x, y, curr_w, curr_h)
                if data is None:
                    failed += 1
                    print(f"[clip] ReadAsArray 返回 None: {filename} @ ({x},{y})")
                    continue

                # 过滤判定（基于原始读取数据，不含 pad 区域）
                if do_filter:
                    vr = _valid_ratio(data, nodata)
                    if vr < min_valid_ratio:
                        filtered += 1
                        continue

                # 小图 pad
                if too_small and small_image == 'pad' and (curr_w < crop_size or curr_h < crop_size):
                    data = _pad_to_crop(data, crop_size)
                # 边缘 pad（edge_policy='pad'）：仅当该位置被标为边缘块且实际不足 crop_size
                elif (edge_policy == 'pad'
                      and (xi in x_edge_set or yi in y_edge_set)
                      and (curr_w < crop_size or curr_h < crop_size)):
                    data = _pad_to_crop(data, crop_size)

                save_name = f"{filename}_x{x:06d}_y{y:06d}{ext}"
                save_path = os.path.join(dst_dir, save_name)

                ok = _save_patch(save_path, data, dataset, x, y, bgr_swap=effective_bgr_swap)
                if ok:
                    success += 1
                else:
                    failed += 1

        if failed or filtered:
            print(f"[clip] {filename}: 成功 {success}/{total}，"
                  f"失败 {failed}，过滤 {filtered}")

        return {'total': total, 'success': success, 'failed': failed,
                'skipped': 0, 'filtered': filtered, 'ext': ext}
    finally:
        # 即使中途异常也要释放 GDAL 数据集，避免 Windows 上文件句柄锁定
        dataset = None


def process_folder(src_dir, crop_size=1024, bgr_swap=False, dst_dir=None,
                   overlap_ratio=0.1, dst_ext='auto', small_image='skip',
                   band_order='keep', nodata_value=None, min_valid_ratio=0.0,
                   edge_policy='append'):
    """
    批量处理 src_dir 下所有遥感影像。

    :param dst_dir: 输出目录；None 时默认建在 src_dir/crop_{crop_size}
    :return: 汇总 dict(files, total, success, failed, skipped, filtered)
    """
    if dst_dir is None:
        dst_dir = os.path.join(src_dir, f"crop_{crop_size}")
    os.makedirs(dst_dir, exist_ok=True)

    files = [f for f in os.listdir(src_dir)
             if f.lower().endswith(('.tif', '.tiff', '.img', '.vrt'))]

    print(f"找到 {len(files)} 个影像文件，输出目录: {dst_dir}")

    summary = {'files': len(files), 'total': 0, 'success': 0,
               'failed': 0, 'skipped': 0, 'filtered': 0}
    for f in tqdm(files):
        src_path = os.path.join(src_dir, f)
        stat = clip_image_gdal(
            src_path, dst_dir,
            crop_size=crop_size, overlap_ratio=overlap_ratio,
            dst_ext=dst_ext, bgr_swap=bgr_swap, small_image=small_image,
            band_order=band_order, nodata_value=nodata_value,
            min_valid_ratio=min_valid_ratio,
            edge_policy=edge_policy,
        )
        for k in ('total', 'success', 'failed', 'skipped', 'filtered'):
            summary[k] += stat.get(k, 0)

    print(
        f"[summary] files={summary['files']}, patches_total={summary['total']}, "
        f"success={summary['success']}, failed={summary['failed']}, "
        f"filtered={summary['filtered']}, skipped_files={summary['skipped']}"
    )
    return summary


def clip_pair(src_image, src_label, dst_image_dir, dst_label_dir,
              crop_size=1024, overlap_ratio=0.1,
              image_dst_ext='auto', label_dst_ext='auto',
              bgr_swap=False, band_order='keep',
              small_image='skip',
              nodata_value=None, min_valid_ratio=0.0,
              min_foreground_ratio=0.0, label_ignore_value=0,
              edge_policy='append'):
    """
    成对裁剪 image / label，保证 patch 严格同位置。

    image 和 label 必须同 W/H（不强制同投影，但建议同 GeoTransform 才能保证
    像素级对齐）。任一过滤条件不通过，两边都不写。

    :param src_image / src_label:       输入影像 / 标签路径
    :param dst_image_dir / dst_label_dir: 输出目录
    :param image_dst_ext / label_dst_ext: 各自的输出扩展名（默认 'auto'）
    :param bgr_swap / band_order:        仅作用于 image，不影响 label 语义
    :param min_valid_ratio:              image 端非 nodata 像素占比下限
    :param min_foreground_ratio:         label 端非 ignore_value 像素占比下限
    :param label_ignore_value:           label 中视为背景的像素值（默认 0）
    :param edge_policy:                  边缘块策略，见 clip_image_gdal 同名参数
    :return: dict(total, success, failed, skipped, filtered, image_ext, label_ext)
    """
    _validate_clip_args(crop_size, overlap_ratio, image_dst_ext, small_image,
                        band_order, edge_policy)
    _validate_clip_args(crop_size, overlap_ratio, label_dst_ext, small_image,
                        'keep', edge_policy)
    if not (0.0 <= min_valid_ratio <= 1.0):
        raise ValueError(f"min_valid_ratio 必须在 [0, 1]，得到 {min_valid_ratio}")
    if not (0.0 <= min_foreground_ratio <= 1.0):
        raise ValueError(f"min_foreground_ratio 必须在 [0, 1]，得到 {min_foreground_ratio}")

    img_ds = gdal_open(src_image)
    if img_ds is None:
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0,
                'filtered': 0, 'image_ext': None, 'label_ext': None}
    lbl_ds = gdal_open(src_label)
    if lbl_ds is None:
        img_ds = None
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0,
                'filtered': 0, 'image_ext': None, 'label_ext': None}

    try:
        # 强制校验：W/H 必须一致；不一致直接报错（语义分割成对数据的前提）
        if (img_ds.RasterXSize, img_ds.RasterYSize) != (lbl_ds.RasterXSize, lbl_ds.RasterYSize):
            raise ValueError(
                f"image 与 label 栅格尺寸不一致：image="
                f"{img_ds.RasterXSize}x{img_ds.RasterYSize}, "
                f"label={lbl_ds.RasterXSize}x{lbl_ds.RasterYSize}。"
                " 成对裁剪要求像素级对齐，请先用 GDAL warp/AlignExtents 对齐。"
            )

        os.makedirs(dst_image_dir, exist_ok=True)
        os.makedirs(dst_label_dir, exist_ok=True)

        width = img_ds.RasterXSize
        height = img_ds.RasterYSize

        # image / label 各自决定 ext
        img_bands = img_ds.RasterCount
        img_dtype = np.dtype(gdal_array.GDALTypeCodeToNumericTypeCode(
            img_ds.GetRasterBand(1).DataType))
        img_ext = (_pick_auto_ext(img_dtype, img_bands)
                   if image_dst_ext == 'auto' else image_dst_ext.lower())
        if not _is_cv_writable(img_ext, img_dtype, img_bands):
            raise ValueError(
                f"{os.path.basename(src_image)}: dtype={img_dtype}, bands={img_bands} "
                f"无法写为 {img_ext}。建议改用 image_dst_ext='auto' 或 '.tif'。"
            )

        lbl_bands = lbl_ds.RasterCount
        lbl_dtype = np.dtype(gdal_array.GDALTypeCodeToNumericTypeCode(
            lbl_ds.GetRasterBand(1).DataType))
        lbl_ext = (_pick_auto_ext(lbl_dtype, lbl_bands)
                   if label_dst_ext == 'auto' else label_dst_ext.lower())
        if not _is_cv_writable(lbl_ext, lbl_dtype, lbl_bands):
            raise ValueError(
                f"{os.path.basename(src_label)}: dtype={lbl_dtype}, bands={lbl_bands} "
                f"无法写为 {lbl_ext}。建议改用 label_dst_ext='auto' 或 '.tif'。"
            )

        effective_bgr_swap = _resolve_bgr_swap(img_ds, band_order, bgr_swap)
        nodata = _resolve_nodata(img_ds, nodata_value)
        do_valid_filter = min_valid_ratio > 0.0
        do_fg_filter = min_foreground_ratio > 0.0

        # patch 同名（仅扩展名不同）：保证 image/label 配对一目了然
        img_basename = os.path.splitext(os.path.basename(src_image))[0]
        lbl_basename = os.path.splitext(os.path.basename(src_label))[0]

        too_small = (width < crop_size) or (height < crop_size)
        if too_small and small_image == 'skip':
            print(f"[clip_pair] 跳过小图: {img_basename} ({width}x{height} < {crop_size})")
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 1,
                    'filtered': 0, 'image_ext': img_ext, 'label_ext': lbl_ext}

        stride = max(1, int(crop_size * (1 - overlap_ratio)))
        if too_small:
            x_steps, y_steps = [0], [0]
            x_edge_idx = y_edge_idx = []
        else:
            x_steps, x_edge_idx = _compute_steps(width, crop_size, stride, edge_policy)
            y_steps, y_edge_idx = _compute_steps(height, crop_size, stride, edge_policy)
        x_edge_set = set(x_edge_idx)
        y_edge_set = set(y_edge_idx)

        total = len(x_steps) * len(y_steps)
        success = failed = filtered = 0

        for yi, y in enumerate(y_steps):
            for xi, x in enumerate(x_steps):
                curr_w = min(crop_size, width - x)
                curr_h = min(crop_size, height - y)

                img_data = img_ds.ReadAsArray(x, y, curr_w, curr_h)
                lbl_data = lbl_ds.ReadAsArray(x, y, curr_w, curr_h)
                if img_data is None or lbl_data is None:
                    failed += 1
                    print(f"[clip_pair] ReadAsArray 返回 None @ ({x},{y})")
                    continue

                # 过滤：image 有效率 + label 前景比，任一不过则两边都跳过
                if do_valid_filter and _valid_ratio(img_data, nodata) < min_valid_ratio:
                    filtered += 1
                    continue
                if do_fg_filter and _foreground_ratio(lbl_data, label_ignore_value) < min_foreground_ratio:
                    filtered += 1
                    continue

                # 小图 pad（image 与 label 必须同步 pad）
                if too_small and small_image == 'pad' and (curr_w < crop_size or curr_h < crop_size):
                    img_data = _pad_to_crop(img_data, crop_size)
                    lbl_data = _pad_to_crop(lbl_data, crop_size)
                # 边缘 pad（edge_policy='pad'）：仅当该位置是边缘块且实际不足 crop_size
                elif (edge_policy == 'pad'
                      and (xi in x_edge_set or yi in y_edge_set)
                      and (curr_w < crop_size or curr_h < crop_size)):
                    img_data = _pad_to_crop(img_data, crop_size)
                    lbl_data = _pad_to_crop(lbl_data, crop_size)

                # image 和 label 用同一基名（与各自源文件 basename 对应），同坐标
                img_save = os.path.join(
                    dst_image_dir, f"{img_basename}_x{x:06d}_y{y:06d}{img_ext}")
                lbl_save = os.path.join(
                    dst_label_dir, f"{lbl_basename}_x{x:06d}_y{y:06d}{lbl_ext}")

                ok_i = _save_patch(img_save, img_data, img_ds, x, y,
                                   bgr_swap=effective_bgr_swap)
                ok_l = _save_patch(lbl_save, lbl_data, lbl_ds, x, y, bgr_swap=False)
                if ok_i and ok_l:
                    success += 1
                else:
                    failed += 1
                    # 任一失败：删除已写出的另一半，保证 image/label 不孤儿
                    if ok_i and not ok_l and os.path.exists(img_save):
                        try: os.remove(img_save)
                        except OSError: pass
                    if ok_l and not ok_i and os.path.exists(lbl_save):
                        try: os.remove(lbl_save)
                        except OSError: pass

        if failed or filtered:
            print(f"[clip_pair] {img_basename}: 成功 {success}/{total}，"
                  f"失败 {failed}，过滤 {filtered}")

        return {'total': total, 'success': success, 'failed': failed,
                'skipped': 0, 'filtered': filtered,
                'image_ext': img_ext, 'label_ext': lbl_ext}
    finally:
        img_ds = None
        lbl_ds = None


def process_pair_folder(src_image_dir, src_label_dir,
                        dst_image_dir=None, dst_label_dir=None,
                        crop_size=1024, overlap_ratio=0.1,
                        image_dst_ext='auto', label_dst_ext='auto',
                        bgr_swap=False, band_order='keep',
                        small_image='skip',
                        nodata_value=None, min_valid_ratio=0.0,
                        min_foreground_ratio=0.0, label_ignore_value=0,
                        edge_policy='append'):
    """
    批量成对裁剪：按文件 stem 匹配 image_dir / label_dir 下同名的影像与标签。

    匹配规则：image 文件 stem 必须与 label 文件 stem 相同（扩展名可不同）。
    任一目录缺对应文件 -> 跳过并打印 warning。

    :return: 汇总 dict(pairs, matched, total, success, failed, skipped, filtered)
    """
    if dst_image_dir is None:
        dst_image_dir = os.path.join(src_image_dir, f"crop_{crop_size}")
    if dst_label_dir is None:
        dst_label_dir = os.path.join(src_label_dir, f"crop_{crop_size}")

    valid_exts = ('.tif', '.tiff', '.img', '.vrt', '.png')
    img_files = {os.path.splitext(f)[0]: f for f in os.listdir(src_image_dir)
                 if f.lower().endswith(valid_exts)}
    lbl_files = {os.path.splitext(f)[0]: f for f in os.listdir(src_label_dir)
                 if f.lower().endswith(valid_exts)}

    common = sorted(set(img_files) & set(lbl_files))
    only_image = sorted(set(img_files) - set(lbl_files))
    only_label = sorted(set(lbl_files) - set(img_files))
    if only_image:
        print(f"[clip_pair] {len(only_image)} 个影像缺对应标签（已跳过）：{only_image[:5]}{'...' if len(only_image)>5 else ''}")
    if only_label:
        print(f"[clip_pair] {len(only_label)} 个标签缺对应影像（已跳过）：{only_label[:5]}{'...' if len(only_label)>5 else ''}")

    print(f"找到 {len(common)} 对 image/label，输出: {dst_image_dir} / {dst_label_dir}")

    summary = {'pairs': len(img_files) + len(lbl_files), 'matched': len(common),
               'total': 0, 'success': 0, 'failed': 0, 'skipped': 0, 'filtered': 0}
    for stem in tqdm(common):
        stat = clip_pair(
            os.path.join(src_image_dir, img_files[stem]),
            os.path.join(src_label_dir, lbl_files[stem]),
            dst_image_dir, dst_label_dir,
            crop_size=crop_size, overlap_ratio=overlap_ratio,
            image_dst_ext=image_dst_ext, label_dst_ext=label_dst_ext,
            bgr_swap=bgr_swap, band_order=band_order,
            small_image=small_image,
            nodata_value=nodata_value, min_valid_ratio=min_valid_ratio,
            min_foreground_ratio=min_foreground_ratio,
            label_ignore_value=label_ignore_value,
            edge_policy=edge_policy,
        )
        for k in ('total', 'success', 'failed', 'skipped', 'filtered'):
            summary[k] += stat.get(k, 0)

    print(
        f"[summary-pair] matched={summary['matched']}, total={summary['total']}, "
        f"success={summary['success']}, failed={summary['failed']}, "
        f"filtered={summary['filtered']}, skipped_files={summary['skipped']}"
    )
    return summary


if __name__ == "__main__":
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    parser = argparse.ArgumentParser(
        description="对目录下所有遥感影像进行滑窗裁剪，输出语义分割训练用 patch。"
                    " 默认保留 GDAL 原波段语义、自动按 dtype/波段选择安全的输出格式。"
                    " 支持单端模式（仅 --src）和成对模式（--src-image + --src-label）。"
    )
    # 单端模式（向后兼容）
    parser.add_argument('--src', default=None,
                        help='单端模式：输入影像目录（与 --src-image/--src-label 互斥）')
    parser.add_argument('--dst', default=None,
                        help='单端模式输出目录；不指定则建在 src/crop_{crop_size}/')

    # 成对模式
    parser.add_argument('--src-image', default=None,
                        help='成对模式：输入影像目录')
    parser.add_argument('--src-label', default=None,
                        help='成对模式：输入标签目录（按 stem 匹配 image）')
    parser.add_argument('--dst-image', default=None, help='成对模式影像输出目录')
    parser.add_argument('--dst-label', default=None, help='成对模式标签输出目录')

    parser.add_argument('--crop-size', type=int, default=1024, help='裁剪尺寸（默认 1024）')
    parser.add_argument('--overlap-ratio', type=float, default=0.1,
                        help='重叠率，[0, 1)，默认 0.1 表示重叠 10%%')
    parser.add_argument('--dst-ext', default='auto',
                        choices=sorted(SUPPORTED_EXTS),
                        help='单端模式输出扩展名（成对模式下作用于 image，'
                             '若需为 label 单独指定见 --label-dst-ext）')
    parser.add_argument('--label-dst-ext', default='auto',
                        choices=sorted(SUPPORTED_EXTS),
                        help='成对模式下 label 的输出扩展名（默认 auto）')
    parser.add_argument('--small-image', default='skip',
                        choices=sorted(SMALL_IMAGE_POLICIES),
                        help='小图策略：skip 跳过（默认）；pad 右下补 0。')
    parser.add_argument('--edge-policy', default='append',
                        choices=sorted(EDGE_POLICIES),
                        help='大图末尾不齐的边缘块策略：append 贴边补块（默认，'
                             '保证全图覆盖，可能与上一块高度重叠）；'
                             'drop 丢弃末尾条带（训练数据集推荐，避免重复样本）；'
                             'pad 保留末尾位置并右/下补 0 到 crop_size。')
    parser.add_argument('--band-order', default='keep',
                        choices=sorted(BAND_ORDERS),
                        help="波段顺序：keep 不动（默认）；auto 从 ColorInterp 推断；"
                             "rgb/bgr 显式声明。仅 3 波段且写 PNG/JPG 时生效。")
    parser.add_argument('--bgr-swap', action='store_true',
                        help='旧参数；仅在 --band-order=keep 时生效。默认不翻转。')
    parser.add_argument('--nodata-value', type=float, default=None,
                        help='nodata 数值；不指定则使用 GDAL band 元数据。')
    parser.add_argument('--min-valid-ratio', type=float, default=0.0,
                        help='patch 中非 nodata 像素占比下限，低于则跳过。0 表示不过滤。')
    parser.add_argument('--min-foreground-ratio', type=float, default=0.0,
                        help='成对模式：label patch 中非背景像素占比下限。0 表示不过滤。')
    parser.add_argument('--label-ignore-value', type=int, default=0,
                        help='成对模式：label 中视为背景的像素值（默认 0）。')

    args = parser.parse_args()

    pair_mode = bool(args.src_image and args.src_label)
    single_mode = bool(args.src)
    if pair_mode and single_mode:
        parser.error("--src 与 --src-image/--src-label 互斥，请二选一。")
    if not pair_mode and not single_mode:
        # 保留一个兼容默认（旧 DEMO 行为）
        args.src = r"E:\Samples-Water\chengdu\image"
        single_mode = True

    if pair_mode:
        process_pair_folder(
            args.src_image, args.src_label,
            dst_image_dir=args.dst_image, dst_label_dir=args.dst_label,
            crop_size=args.crop_size, overlap_ratio=args.overlap_ratio,
            image_dst_ext=args.dst_ext, label_dst_ext=args.label_dst_ext,
            bgr_swap=args.bgr_swap, band_order=args.band_order,
            small_image=args.small_image,
            nodata_value=args.nodata_value,
            min_valid_ratio=args.min_valid_ratio,
            min_foreground_ratio=args.min_foreground_ratio,
            label_ignore_value=args.label_ignore_value,
            edge_policy=args.edge_policy,
        )
    else:
        process_folder(
            args.src,
            crop_size=args.crop_size,
            bgr_swap=args.bgr_swap,
            dst_dir=args.dst,
            overlap_ratio=args.overlap_ratio,
            dst_ext=args.dst_ext,
            small_image=args.small_image,
            band_order=args.band_order,
            nodata_value=args.nodata_value,
            min_valid_ratio=args.min_valid_ratio,
            edge_policy=args.edge_policy,
        )
    print("所有处理完成。")
