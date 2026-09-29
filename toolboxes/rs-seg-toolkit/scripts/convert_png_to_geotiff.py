import os
import cv2
import numpy as np
from osgeo import gdal

# 公共安全 IO（中文路径、GDAL None 检查）由 utils 统一提供
from utils import imread_with_flag as cv2_imread_safe
from utils import gdal_open

# 防止超大图导致 OpenCV 报错（解压炸弹保护）
os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = str(pow(2, 40))

def write_geotiff(save_path, img_data, transform, projection):
    """
    将图像数据写入 GeoTIFF
    :param save_path: 保存路径
    :param img_data: 图像数据 (H, W) 或 (H, W, C) - OpenCV 格式
    :param transform: GDAL GeoTransform 数组
    :param projection: GDAL Projection 字符串
    """
    
    # 1. 维度处理与标准化
    # OpenCV 读入通常是 (H, W) 或 (H, W, C)
    # GDAL 需要 (Band, H, W)
    
    if len(img_data.shape) == 2:
        img_height, img_width = img_data.shape
        img_bands = 1
        # 统一转为 (Band, H, W) 方便后续处理
        img_data = img_data[np.newaxis, :, :]
    else:
        img_height, img_width, img_bands = img_data.shape
        # (H, W, C) -> (C, H, W)
        img_data = np.transpose(img_data, (2, 0, 1))

    # 2. 映射数据类型
    # 建立 Numpy dtype 到 GDAL dtype 的映射字典
    dtype_map = {
        'uint8': gdal.GDT_Byte,
        'int8': gdal.GDT_Byte,
        'uint16': gdal.GDT_UInt16,
        'int16': gdal.GDT_Int16,
        'float32': gdal.GDT_Float32,
        'float64': gdal.GDT_Float64
    }
    
    current_dtype = img_data.dtype.name
    gdal_dtype = dtype_map.get(current_dtype, gdal.GDT_Float32) # 默认 Float32

    # 3. 创建文件
    driver = gdal.GetDriverByName('GTiff')
    # 注意：Create 参数顺序是 (Path, Width, Height, Bands, Type)
    dataset = driver.Create(save_path, img_width, img_height, img_bands, gdal_dtype)

    if dataset is None:
        print(f"创建 TIF 文件失败: {save_path}")
        return

    # 4. 写入地理信息
    dataset.SetGeoTransform(transform)
    dataset.SetProjection(projection)

    # 5. 写入数据
    for i in range(img_bands):
        # GDAL Band 索引从 1 开始
        dataset.GetRasterBand(i + 1).WriteArray(img_data[i])
    
    # 刷新缓存并释放资源
    dataset.FlushCache()
    del dataset
    print(f"保存成功: {save_path}")

def process_georeference(ref_tif_path, mask_png_path, output_tif_path, force=False):
    """
    将 PNG 结果挂上参考影像的地理坐标，输出为 GeoTIFF。

    :param ref_tif_path: 参考影像路径（提供 GeoTransform 和 Projection）
    :param mask_png_path: 待处理 PNG 路径
    :param output_tif_path: 输出 GeoTIFF 路径
    :param force: 当 PNG 与参考影像尺寸不一致时，True 仍强制写入（坐标会偏移），
                  False（默认）拒绝写入并返回。
    """
    # 1. 读取参考影像信息
    ds_ref = gdal_open(ref_tif_path)
    if ds_ref is None:
        return

    geo_transform = ds_ref.GetGeoTransform()
    projection = ds_ref.GetProjection()
    ref_w = ds_ref.RasterXSize
    ref_h = ds_ref.RasterYSize

    # 释放参考影像
    ds_ref = None

    print(f"参考影像信息:\nGeoTransform: {geo_transform}\nProjection: Found")

    # 2. 读取待处理 PNG
    # 注意：这里根据需求选择读取模式。Mask 通常是灰度图 (GRAYSCALE)
    # 如果是彩色预测结果，请改用 IMREAD_COLOR
    mask_data = cv2_imread_safe(mask_png_path, cv2.IMREAD_GRAYSCALE)

    if mask_data is None:
        return

    # 3. 尺寸一致性检查 (重要!)
    # OpenCV shape 是 (H, W)
    h, w = mask_data.shape[:2]

    if h != ref_h or w != ref_w:
        msg = (f"尺寸不匹配!\n"
               f"  参考影像: {ref_w} x {ref_h}\n"
               f"  PNG影像 : {w} x {h}")
        if not force:
            print(f"\n[错误] {msg}")
            print("       直接赋予坐标会导致地理位置偏移。已拒绝写入。")
            print("       如确认要强制继续，请传入 force=True。")
            return
        else:
            print(f"\n[警告] {msg}")
            print("       force=True 已启用，将继续写入，但坐标可能偏移。")

    # 4. 写入
    write_geotiff(output_tif_path, mask_data, geo_transform, projection)

if __name__ == "__main__":
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    parser = argparse.ArgumentParser(
        description="将无坐标 PNG 结果挂上参考影像的地理坐标，输出为 GeoTIFF。"
    )
    parser.add_argument('--ref', default=r"E:/chengdu/google_earth_maps/Level20/H48F019017.tif",
                        help='参考影像（提供 GeoTransform/Projection）')
    parser.add_argument('--mask', default=r"D:/WorkSpace/mmsegmentation/data/VacantLand-Chengdu-1024/Result/segformer/H48F019017-vtland-0505.png",
                        help='待挂坐标的 PNG')
    parser.add_argument('--out', default=r"D:/WorkSpace/mmsegmentation/data/VacantLand-Chengdu-1024/Result/segformer/H48F019017-vtland-0505.tif",
                        help='输出 GeoTIFF 路径')
    parser.add_argument('--force', action='store_true',
                        help='PNG 与参考影像尺寸不一致时仍强制写入（默认拒绝）')
    args = parser.parse_args()

    process_georeference(args.ref, args.mask, args.out, force=args.force)
