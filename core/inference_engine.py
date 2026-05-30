# -*- coding: utf-8 -*-
"""
推理引擎 (Inference Engine)
负责执行语义分割模型的推理任务
支持超大遥感影像的分块推理
"""

import os
import sys
import math
import numpy as np
from typing import Dict, Tuple, Optional
from PIL import Image
import cv2
import time

# 针对大尺寸遥感影像，提高PIL的像素限制
# 默认限制约为178MB像素，这里提高到10GB像素
Image.MAX_IMAGE_PIXELS = 10000000000

# --- 从 skill_geodata_utils 导入可复用的数据转换逻辑 ---
from skills.skill_geodata_utils import gdal_data_to_opencv_data as _gdal_data_to_opencv_func

try:
    from osgeo import gdal
    from osgeo.gdalconst import GA_ReadOnly
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False
    print("[推理引擎] ⚠️  GDAL 未安装，大图像分块推理功能将受限")


class Block:
    """分块信息类，用于大图像分块推理"""
    def __init__(self, file, idx_row, idx_col, top_overlap, top_overlap_pic, 
                 left_overlap, left_overlap_pic, start_x, start_y):
        self.file = file  # 对应分块的文件路径  
        self.idx_row = idx_row      # 行序号
        self.idx_col = idx_col      # 列序号
        self.top_overlap = top_overlap              # 与上一行重叠的像素
        self.top_overlap_pic = top_overlap_pic      # 与上一行有重叠的分块序号
        self.left_overlap = left_overlap            # 与左一列重叠的像素
        self.left_overlap_pic = left_overlap_pic    # 与左一列有重叠的分块序号
        self.start_x = start_x                      # 在整幅影像x方向起点
        self.start_y = start_y                      # 在整幅影像y方向起点


class InferenceEngine:
    """推理引擎类"""
    
    def __init__(self, model_info: dict):
        """
        初始化推理引擎
        
        Args:
            model_info: 模型信息字典，包含config, checkpoint, device等
        """
        self.model_info = model_info
        self.model = None
        
        # 取消和进度回调支持
        self._cancel_requested = False
        self._progress_callback = None
        
        self._init_model()
    
    def set_progress_callback(self, callback):
        """
        设置进度回调函数
        
        Args:
            callback: 接受 (current, total) 参数的回调函数
        """
        self._progress_callback = callback
    
    def request_cancel(self):
        """请求取消当前推理任务"""
        self._cancel_requested = True
        print("[推理引擎] 🛑 收到取消请求")
    
    def reset_cancel(self):
        """重置取消请求状态"""
        self._cancel_requested = False
    
    def _init_model(self):
        """初始化模型"""
        try:
            # === 添加下面这两行即可精准打印源码绝对路径 ===
            import mmseg
            print(f"\n[推理排查] 🚨 当前正在使用此目录下的 MMSeg 代码: {mmseg.__file__}\n")

            # ====== 将配置文件所在目录加入 sys.path（修复 BUG-INFER-01） ======
            # train_config.py 中的 custom_imports（custom_live_pred_hook、custom_rs_dataset 等）
            # 模块文件位于 work_dir/，需要把该目录注入 sys.path 才能被 import
            config_path = self.model_info.get('config')
            if config_path:
                config_dir = os.path.dirname(os.path.abspath(config_path))
                if config_dir and config_dir not in sys.path:
                    sys.path.insert(0, config_dir)
                    print(f"[推理引擎] 已将 work_dir 加入 sys.path: {config_dir}")

            # 尝试使用 MMSegmentation API 加载真实模型
            from mmseg.apis import init_model
            
            print(f"[推理引擎] 正在加载模型...")
            print(f"[推理引擎] 配置文件: {self.model_info['config']}")
            print(f"[推理引擎] 权重文件: {self.model_info['checkpoint']}")
            print(f"[推理引擎] 设备: {self.model_info['device']}")
            
            self.model = init_model(
                self.model_info['config'],
                self.model_info['checkpoint'],
                device=self.model_info['device']
            )
            
            print("="*60)
            print(f"[推理引擎] ✅ 模型加载成功（真实模型）")
            print(f"[推理引擎] 🎯 推理模式: 真实神经网络推理")
            print("="*60)
            self.use_real_model = True
            
        except ImportError as e:

            import mmseg
            print(f"\n[推理排查] 🚨 当前正在使用此目录下的 MMSeg 代码: {mmseg.__file__}\n")
            
            # MMSegmentation 未安装，使用模拟模式
            print(f"[推理引擎] ⚠️  MMSegmentation 未安装，使用模拟模式")
            print(f"[推理引擎] 错误: {e}")
            self.model = {
                'config': self.model_info['config'],
                'checkpoint': self.model_info['checkpoint'],
                'device': self.model_info['device'],
                'classes': self.model_info.get('classes', []),
                'palette': self.model_info.get('palette', [])
            }
            self.use_real_model = False
            
        except Exception as e:
            # 模型加载失败，使用模拟模式
            print(f"[推理引擎] ⚠️  模型加载失败，使用模拟模式")
            print(f"[推理引擎] 错误: {e}")
            self.model = {
                'config': self.model_info['config'],
                'checkpoint': self.model_info['checkpoint'],
                'device': self.model_info['device'],
                'classes': self.model_info.get('classes', []),
                'palette': self.model_info.get('palette', [])
            }
            self.use_real_model = False
    
    def _real_sliding_window_inference(
        self,
        image_path: str,
        crop_size: int,
        stride: int,
        img_width: int,
        img_height: int
    ) -> np.ndarray:
        """
        真实的滑窗推理实现（优化版 - 不加载完整图像）
        
        Args:
            image_path: 图像路径
            crop_size: 窗口大小
            stride: 步长
            img_width: 图像宽度
            img_height: 图像高度
            
        Returns:
            预测掩码数组
        """
        from mmseg.apis import inference_model
        from PIL import Image
        import numpy as np
        
        print(f"[推理引擎] 开始滑窗推理: {img_width}x{img_height}")
        
        # 打开图像（不加载到内存）
        image = Image.open(image_path)
        w, h = image.size
        
        # 检查图像大小
        total_pixels = w * h
        if total_pixels > 100000000:  # 超过1亿像素
            print(f"[推理引擎] ⚠️  超大图像 ({total_pixels/1000000:.1f}M像素)")
            print(f"[推理引擎] 为避免内存溢出，将使用轻量级模式")
            print(f"[推理引擎] 建议：使用专业的遥感影像处理工具进行推理")
            
            # 返回None，让调用者知道这是超大图像
            return None
        
        # 创建结果掩码 - 使用 uint8 节省内存 (原 float32 的 1/4)
        result_mask = np.zeros((h, w), dtype=np.uint8)
        
        # 计算窗口数量
        num_windows_h = max(1, (h - crop_size) // stride + 1) if h > crop_size else 1
        num_windows_w = max(1, (w - crop_size) // stride + 1) if w > crop_size else 1
        total_windows = num_windows_h * num_windows_w
        
        print(f"[推理引擎] 窗口数量: {num_windows_h} x {num_windows_w} = {total_windows}")
        
        window_count = 0
        
        # 重置取消状态
        self._cancel_requested = False
        
        # 滑窗推理
        for y in range(0, h, stride):
            # 检查取消请求
            if self._cancel_requested:
                print("[推理引擎] 🛑 推理已取消")
                return None
            
            for x in range(0, w, stride):
                window_count += 1
                
                # 检查取消请求 (内层循环也检查，响应更快)
                if self._cancel_requested:
                    print("[推理引擎] 🛑 推理已取消")
                    return None
                
                # 计算窗口边界
                y_end = min(y + crop_size, h)
                x_end = min(x + crop_size, w)
                
                # 如果窗口太小，调整起始位置
                if y_end - y < crop_size and y > 0:
                    y = max(0, y_end - crop_size)
                if x_end - x < crop_size and x > 0:
                    x = max(0, x_end - crop_size)
                
                # 提取窗口（只加载这一小块）
                window_pil = image.crop((x, y, x_end, y_end))
                window = np.array(window_pil)
                
                # 转换为BGR格式（MMSeg期望BGR）
                if len(window.shape) == 3 and window.shape[2] == 3:
                    window = window[:, :, ::-1]  # RGB -> BGR
                
                # 推理窗口
                try:
                    result = inference_model(self.model, window)
                    
                    # 获取预测掩码
                    if hasattr(result, 'pred_sem_seg'):
                        window_mask = result.pred_sem_seg.data.cpu().numpy()[0]
                    else:
                        window_mask = result[0]
                    
                    # 将结果直接覆盖到完整掩码
                    # 注意：语义分割输出的是类别ID (0, 1, 2...)，不能累加！
                    # 对于重叠区域，使用最后一次预测的结果
                    result_mask[y:y_end, x:x_end] = window_mask[:y_end-y, :x_end-x].astype(np.uint8)
                    
                    # 细粒度进度反馈 (每个窗口都回调)
                    if self._progress_callback:
                        self._progress_callback(window_count, total_windows)
                    
                    # 控制台进度 (每10个窗口打印一次)
                    if window_count % 10 == 0:
                        progress = (window_count / total_windows) * 100
                        print(f"[推理引擎] 进度: {window_count}/{total_windows} ({progress:.1f}%)")
                
                except Exception as e:
                    print(f"[推理引擎] ⚠️  窗口 ({x},{y}) 推理失败: {e}")
                    continue
        
        print(f"[推理引擎] ✅ 滑窗推理完成")
        
        return result_mask
    
    def _gdal_data_to_opencv_data(self, gdal_img_data):
        """将GDAL数据格式转换为OpenCV格式（委托给 skill_geodata_utils）"""
        return _gdal_data_to_opencv_func(gdal_img_data)
    
    def _predict_single_block(self, img_block):
        """
        预测单个分块
        
        Args:
            img_block: 图像分块数据
            
        Returns:
            预测结果
        """
        from mmseg.apis import inference_model
        
        result = inference_model(self.model, img_block)
        
        if hasattr(result, 'pred_sem_seg'):
            logits = result.pred_sem_seg.data[0].cpu().numpy()
        else:
            logits = result[0]
        
        return logits
    
    def large_image_block_inference(
        self,
        image_path: str,
        output_path: str,
        crop_size: int = 1024,
        overlap_rate: float = 0.2,
        enable_tta: bool = False
    ) -> Dict:
        """
        超大图像分块推理（使用GDAL处理遥感影像）
        
        Args:
            image_path: 输入图像路径
            output_path: 输出结果路径
            crop_size: 分块大小
            overlap_rate: 重叠率（0-1之间）
            enable_tta: 是否启用TTA增强
            
        Returns:
            推理结果字典
        """
        if not GDAL_AVAILABLE:
            return {
                'success': False,
                'error': 'GDAL未安装，无法进行大图像分块推理。请安装GDAL: pip install gdal'
            }
        
        if not self.use_real_model:
            return {
                'success': False,
                'error': '大图像分块推理需要真实模型，请确保MMSegmentation已正确安装并加载模型'
            }
        
        try:
            print(f"[推理引擎] 🚀 开始大图像分块推理...")
            print(f"[推理引擎] 输入图像: {image_path}")
            print(f"[推理引擎] 分块大小: {crop_size}, 重叠率: {overlap_rate}")
            
            t0 = time.time()
            
            # 打开GDAL数据集
            dataset = gdal.Open(image_path, GA_ReadOnly)
            if dataset is None:
                return {
                    'success': False,
                    'error': f'无法打开图像文件: {image_path}'
                }
            
            img_width = dataset.RasterXSize
            img_height = dataset.RasterYSize
            
            print(f"[推理引擎] 图像尺寸: {img_width} x {img_height}")
            
            # 计算分块参数
            stride = crop_size - int(crop_size * overlap_rate)
            x_num = math.ceil((img_width - crop_size) / stride) + 1
            y_num = math.ceil((img_height - crop_size) / stride) + 1
            total_blocks = x_num * y_num
            
            print(f"[推理引擎] 分块数量: {x_num} x {y_num} = {total_blocks}")
            
            # 重置取消状态
            self._cancel_requested = False
            
            # 创建临时目录保存分块结果
            temp_dir = output_path + '_blocks'
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            # 创建分块信息数组
            dst_blocks = [[None for _ in range(x_num)] for _ in range(y_num)]
            overlap = int(crop_size * overlap_rate)
            
            # 分块预测
            block_count = 0
            
            # 左上部分
            for j in range(y_num - 1):
                # 检查取消请求
                if self._cancel_requested:
                    print("[推理引擎] 🛑 分块推理已取消")
                    return {'success': False, 'error': '用户取消'}
                
                for i in range(x_num - 1):
                    x_start = stride * i
                    y_start = stride * j
                    
                    img_block = dataset.ReadAsArray(x_start, y_start, crop_size, crop_size)
                    img_block_cv = self._gdal_data_to_opencv_data(img_block)
                    
                    # 预测
                    predict_out = self._predict_single_block(img_block_cv)
                    predict_out = np.uint8(predict_out * 255)
                    
                    # 保存分块结果
                    save_file = os.path.join(temp_dir, f'{j}+{i}.png')
                    cv2.imwrite(save_file, predict_out)
                    
                    # 创建Block对象
                    block = Block(save_file, j, i, overlap, "", overlap, "", x_start, y_start)
                    dst_blocks[j][i] = block
                    block_count += 1
                    
                    # 更新进度 (分块预测占 0-80%)
                    if self._progress_callback and block_count % 3 == 0:
                        progress_pct = int((block_count / total_blocks) * 80)
                        self._progress_callback(progress_pct, 100)
            
            # 下侧边缘
            cur_y = y_num - 1
            y_start = img_height - crop_size
            overlap_y = stride * (cur_y - 1) + crop_size - y_start if cur_y > 0 else 0
            
            for i in range(x_num - 1):
                if self._cancel_requested:
                    return {'success': False, 'error': '用户取消'}
                    
                x_start = stride * i
                
                img_block = dataset.ReadAsArray(x_start, y_start, crop_size, crop_size)
                img_block_cv = self._gdal_data_to_opencv_data(img_block)
                
                predict_out = self._predict_single_block(img_block_cv)
                predict_out = np.uint8(predict_out * 255)
                
                save_file = os.path.join(temp_dir, f'{cur_y}+{i}.png')
                cv2.imwrite(save_file, predict_out)
                
                block = Block(save_file, cur_y, i, overlap_y, "", overlap, "", x_start, y_start)
                dst_blocks[cur_y][i] = block
                block_count += 1
                
                # 更新进度
                if self._progress_callback and block_count % 3 == 0:
                    progress_pct = int((block_count / total_blocks) * 80)
                    self._progress_callback(progress_pct, 100)
            
            # 右侧边缘
            cur_x = x_num - 1
            x_start = img_width - crop_size
            overlap_x = stride * (cur_x - 1) + crop_size - x_start if cur_x > 0 else 0
            
            for j in range(y_num - 1):
                if self._cancel_requested:
                    return {'success': False, 'error': '用户取消'}
                    
                y_start = stride * j
                
                img_block = dataset.ReadAsArray(x_start, y_start, crop_size, crop_size)
                img_block_cv = self._gdal_data_to_opencv_data(img_block)
                
                predict_out = self._predict_single_block(img_block_cv)
                predict_out = np.uint8(predict_out * 255)
                
                save_file = os.path.join(temp_dir, f'{j}+{cur_x}.png')
                cv2.imwrite(save_file, predict_out)
                
                block = Block(save_file, j, cur_x, overlap, "", overlap_x, "", x_start, y_start)
                dst_blocks[j][cur_x] = block
                block_count += 1
                
                # 更新进度
                if self._progress_callback and block_count % 3 == 0:
                    progress_pct = int((block_count / total_blocks) * 80)
                    self._progress_callback(progress_pct, 100)
            
            # 右下角
            if self._cancel_requested:
                return {'success': False, 'error': '用户取消'}
                
            img_block = dataset.ReadAsArray(img_width - crop_size, img_height - crop_size, crop_size, crop_size)
            img_block_cv = self._gdal_data_to_opencv_data(img_block)
            
            predict_out = self._predict_single_block(img_block_cv)
            predict_out = np.uint8(predict_out * 255)
            
            save_file = os.path.join(temp_dir, f'{cur_y}+{cur_x}.png')
            cv2.imwrite(save_file, predict_out)
            
            block = Block(save_file, cur_y, cur_x, overlap_y, "", overlap_x, "", 
                         img_width - crop_size, img_height - crop_size)
            dst_blocks[cur_y][cur_x] = block
            block_count += 1
            
            # 进度: 分块预测完成 (80%)
            if self._progress_callback:
                self._progress_callback(80, 100)
            
            print(f'[推理引擎] 分块预测完成，耗时: {(time.time() - t0) / 60:.2f} 分钟')
            
            # 构建分块索引
            self._build_block_index(dst_blocks)
            
            # 创建输出GeoTIFF
            print(f'[推理引擎] 开始拼接分块结果...')
            
            projinfo = dataset.GetProjection()
            geotransform = dataset.GetGeoTransform()
            driver = gdal.GetDriverByName("GTiff")
            
            # 确保输出路径有正确的扩展名
            if not output_path.endswith('.tif'):
                output_path = output_path + '.tif'
            
            dst_ds = driver.Create(output_path, img_width, img_height, 1, gdal.GDT_Byte)
            dst_ds.SetGeoTransform(geotransform)
            dst_ds.SetProjection(projinfo)
            
            # 拼接分块
            self._stitch_blocks(dst_blocks, dst_ds, crop_size)
            
            dst_ds.FlushCache()
            dst_ds = None
            dataset = None

            # 【关键】为输出结果构建金字塔，确保快速预览
            print(f'[推理引擎] 正在为输出结果构建金字塔...')
            from utils.pyramid_builder import PyramidBuilder
            pyramid_ok = PyramidBuilder.build_pyramids(
                output_path,
                levels=[2, 4, 8, 16, 32],
                resampling='NEAREST'
            )
            if pyramid_ok:
                print(f'[推理引擎] ✅ 金字塔构建成功')
            else:
                print(f'[推理引擎] ⚠️ 金字塔构建失败，但不影响结果')

            print(f'[推理引擎] ✅ 大图像分块推理完成！')
            print(f'[推理引擎] 总耗时: {(time.time() - t0) / 60:.2f} 分钟')
            print(f'[推理引擎] 输出文件: {output_path}')

            return {
                'success': True,
                'output_path': output_path,
                'temp_dir': temp_dir,
                'image_shape': (img_height, img_width),
                'strategy': 'large_image_block',
                'use_real_model': True,
                'image_path': image_path,  # 新增：原始图像路径（用于后续读取渲染）
                'params': {
                    'crop_size': crop_size,
                    'overlap_rate': overlap_rate,
                    'total_blocks': total_blocks,
                    'x_num': x_num,
                    'y_num': y_num
                },
                'classes': self.model_info.get('classes', []),
                'palette': self.model_info.get('palette', [])
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[推理引擎] 大图像分块推理失败: {e}")
            print(f"[推理引擎] 详细错误:\n{error_details}")
            return {
                'success': False,
                'error': f'大图像分块推理失败: {str(e)}\n\n详细信息:\n{error_details}'
            }
    
    def _build_block_index(self, dst_blocks):
        """构建分块索引，记录相邻分块信息"""
        for j in dst_blocks:
            for block in j:
                if block is None:
                    continue
                
                # 第0行没有top_overlap
                if block.idx_row == 0:
                    block.top_overlap = 0
                else:
                    top_y = block.idx_row - 1
                    top_x = block.idx_col
                    if dst_blocks[top_y][top_x] is not None:
                        block.top_overlap_pic = dst_blocks[top_y][top_x].file
                
                # 第0列没有left_overlap
                if block.idx_col == 0:
                    block.left_overlap = 0
                else:
                    left_x = block.idx_col - 1
                    left_y = block.idx_row
                    if dst_blocks[left_y][left_x] is not None:
                        block.left_overlap_pic = dst_blocks[left_y][left_x].file
    
    def _stitch_blocks(self, dst_blocks, dst_ds, target_size):
        """拼接分块结果，重叠区各取一半"""
        # 计算总分块数
        total_blocks = sum(1 for row in dst_blocks for block in row if block is not None)
        processed_blocks = 0
        
        for j in dst_blocks:
            for block in j:
                if block is None:
                    continue
                
                # 检查取消请求
                if self._cancel_requested:
                    print("[推理引擎] 🛑 拼接已取消")
                    return
                
                # 读取分块
                block_img = cv2.imread(block.file, cv2.IMREAD_GRAYSCALE)
                
                # 处理上侧重叠区
                if block.top_overlap > 0:
                    top_block = cv2.imread(block.top_overlap_pic, cv2.IMREAD_GRAYSCALE)
                    overlap = block.top_overlap
                    half_overlap = top_block[target_size - overlap:target_size - int(overlap * 0.5), 0:target_size]
                    block_img[0:overlap - int(overlap * 0.5), 0:target_size] = half_overlap
                
                # 处理左侧重叠区
                if block.left_overlap > 0:
                    left_block = cv2.imread(block.left_overlap_pic, cv2.IMREAD_GRAYSCALE)
                    overlap = block.left_overlap
                    half_overlap = left_block[0:target_size, target_size - overlap:target_size - int(overlap * 0.5)]
                    block_img[0:target_size, 0:overlap - int(overlap * 0.5)] = half_overlap
                
                # 写入输出数据集
                dst_ds.GetRasterBand(1).WriteArray(block_img, block.start_x, block.start_y)
                
                # 更新分块文件
                cv2.imwrite(block.file, block_img)
                
                # 更新进度
                processed_blocks += 1
                if self._progress_callback and processed_blocks % 5 == 0:
                    # 拼接阶段占 80%-95% 的进度
                    base_progress = 80
                    stitch_progress = int((processed_blocks / total_blocks) * 15)
                    self._progress_callback(base_progress + stitch_progress, 100)
    
    def sliding_window_inference(
        self,
        image_path: str,
        crop_size: int = 1024,
        stride: int = 512,
        batch_size: int = 1,
        enable_tta: bool = False
    ) -> Dict:
        """
        滑窗推理（适用于中等大小图像）
        
        Args:
            image_path: 输入图像路径
            crop_size: 窗口大小
            stride: 步长
            batch_size: 批大小
            enable_tta: 是否启用TTA增强
            
        Returns:
            推理结果字典
        """
        try:
            # 读取图像（只获取尺寸，不加载到内存）
            image = Image.open(image_path)
            w, h = image.size  # 注意：PIL的size是(width, height)
            
            print(f"[推理引擎] 图像尺寸: {w} x {h}")
            print(f"[推理引擎] 窗口大小: {crop_size}, 步长: {stride}")
            
            # 计算滑窗数量
            num_windows_h = max(1, (h - crop_size) // stride + 1) if h > crop_size else 1
            num_windows_w = max(1, (w - crop_size) // stride + 1) if w > crop_size else 1
            total_windows = num_windows_h * num_windows_w
            
            print(f"[推理引擎] 窗口数量: {num_windows_h} x {num_windows_w} = {total_windows}")
            
            # 执行推理
            if self.use_real_model:
                # 使用真实的 MMSegmentation 推理
                print("="*60)
                print(f"[推理引擎] 🚀 使用真实模型进行推理...")
                print(f"[推理引擎] 📊 推理参数: crop={crop_size}, stride={stride}")
                print("="*60)
                result_mask = self._real_sliding_window_inference(
                    image_path, crop_size, stride, w, h
                )
                
                if result_mask is None:
                    # 超大图像，无法处理
                    print(f"[推理引擎] ⚠️  图像过大，无法生成完整掩码")
                else:
                    print("="*60)
                    print(f"[推理引擎] ✅ 真实推理完成")
                    print("="*60)
            else:
                # 模拟推理结果
                print("="*60)
                print(f"[推理引擎] ⚠️  使用模拟推理（MMSegmentation未安装或模型加载失败）")
                print(f"[推理引擎] ⚠️  这不是真正的神经网络推理！")
                print("="*60)
                if w * h > 100000000:  # 超过1亿像素
                    print(f"[推理引擎] 检测到超大图像，使用轻量级模式")
                    result_mask = None  # 不创建完整掩码，节省内存
                else:
                    result_mask = np.zeros((h, w), dtype=np.uint8)
            
            # 读取原始图像用于渲染
            image_array = None
            if result_mask is not None:
                try:
                    image_pil = Image.open(image_path)
                    image_array = np.array(image_pil)
                    if image_array.ndim == 2:  # 灰度图转RGB
                        image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)
                    elif image_array.shape[2] == 4:  # RGBA转RGB
                        image_array = cv2.cvtColor(image_array, cv2.COLOR_RGBA2RGB)
                except Exception as e:
                    print(f"[推理引擎] ⚠️  读取原始图像失败: {e}")

            return {
                'success': True,
                'mask': result_mask,
                'image': image_array,  # 新增：原始图像数组
                'image_shape': (h, w),
                'strategy': 'sliding_window',
                'use_real_model': self.use_real_model,  # 标识是否使用真实模型
                'params': {
                    'crop_size': crop_size,
                    'stride': stride,
                    'batch_size': batch_size,
                    'enable_tta': enable_tta,
                    'total_windows': total_windows
                },
                'classes': self.model_info.get('classes', []),
                'palette': self.model_info.get('palette', [])
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[推理引擎] 滑窗推理失败: {e}")
            print(f"[推理引擎] 详细错误:\n{error_details}")
            return {
                'success': False,
                'error': f'滑窗推理失败: {str(e)}\n\n详细信息:\n{error_details}'
            }
    
    def resize_inference(
        self,
        image_path: str,
        enable_tta: bool = False
    ) -> Dict:
        """
        全图缩放推理
        
        Args:
            image_path: 输入图像路径
            enable_tta: 是否启用TTA增强
            
        Returns:
            推理结果字典
        """
        try:
            # 读取图像（只获取尺寸）
            image = Image.open(image_path)
            w, h = image.size
            
            print(f"[推理引擎] 图像尺寸: {w} x {h}")
            print(f"[推理引擎] 使用全图缩放推理")
            
            # 执行推理
            if self.use_real_model:
                # 使用真实的 MMSegmentation 推理
                print(f"[推理引擎] 🚀 使用真实模型进行推理...")
                from mmseg.apis import inference_model
                
                result = inference_model(self.model, image_path)
                
                # 获取预测掩码 - MMSeg 1.x 返回 PixelData 对象
                if hasattr(result, 'pred_sem_seg'):
                    result_mask = result.pred_sem_seg.data.cpu().numpy()[0]
                else:
                    result_mask = result[0]
                
                print(f"[推理引擎] ✅ 真实推理完成")
            else:
                # 模拟推理结果
                print(f"[推理引擎] ⚠️  使用模拟推理（MMSegmentation未安装或模型加载失败）")
                if w * h > 100000000:  # 超过1亿像素
                    print(f"[推理引擎] 检测到超大图像，使用轻量级模式")
                    result_mask = None
                else:
                    result_mask = np.zeros((h, w), dtype=np.uint8)
            
            # 读取原始图像用于渲染
            image_array = None
            if result_mask is not None:
                try:
                    image_pil = Image.open(image_path)
                    image_array = np.array(image_pil)
                    if image_array.ndim == 2:  # 灰度图转RGB
                        image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)
                    elif image_array.shape[2] == 4:  # RGBA转RGB
                        image_array = cv2.cvtColor(image_array, cv2.COLOR_RGBA2RGB)
                except Exception as e:
                    print(f"[推理引擎] ⚠️  读取原始图像失败: {e}")

            return {
                'success': True,
                'mask': result_mask,
                'image': image_array,  # 新增：原始图像数组
                'image_shape': (h, w),
                'strategy': 'resize',
                'use_real_model': self.use_real_model,  # 标识是否使用真实模型
                'params': {
                    'enable_tta': enable_tta
                },
                'classes': self.model_info.get('classes', []),
                'palette': self.model_info.get('palette', [])
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[推理引擎] 全图缩放推理失败: {e}")
            print(f"[推理引擎] 详细错误:\n{error_details}")
            return {
                'success': False,
                'error': f'全图缩放推理失败: {str(e)}\n\n详细信息:\n{error_details}'
            }
        img_array = np.array(image)
        h, w = img_array.shape[:2]
        
        # TODO: 实际项目中使用 MMSegmentation 推理
        # from mmseg.apis import inference_segmentor
        # result = inference_segmentor(self.model, image_path)
        
        # 模拟推理结果
        result_mask = np.zeros((h, w), dtype=np.uint8)
        
        return {
            'success': True,
            'mask': result_mask,
            'image_shape': (h, w),
            'strategy': 'resize',
            'params': {
                'enable_tta': enable_tta
            },
            'classes': self.model_info.get('classes', []),
            'palette': self.model_info.get('palette', [])
        }
    
    def run_inference(
        self,
        image_path: str,
        strategy: str = 'sliding_window',
        **kwargs
    ) -> Dict:
        """
        运行推理（策略模式）
        
        Args:
            image_path: 输入图像路径
            strategy: 推理策略 ('sliding_window' 或 'resize')
            **kwargs: 其他推理参数
            
        Returns:
            推理结果字典
        """
        if not os.path.exists(image_path):
            return {
                'success': False,
                'error': f'图像文件不存在: {image_path}'
            }
        
        try:
            if strategy == 'sliding_window':
                return self.sliding_window_inference(
                    image_path,
                    crop_size=kwargs.get('crop_size', 1024),
                    stride=kwargs.get('stride', 512),
                    batch_size=kwargs.get('batch_size', 1),
                    enable_tta=kwargs.get('enable_tta', False)
                )
            elif strategy == 'resize':
                return self.resize_inference(
                    image_path,
                    enable_tta=kwargs.get('enable_tta', False)
                )
            else:
                return {
                    'success': False,
                    'error': f'未知的推理策略: {strategy}'
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
