"""
创建测试影像和标签数据
用于测试数据源管理和影像显示功能
"""

import os
from PIL import Image, ImageDraw, ImageFont
import random

def create_test_data():
    """创建VOC格式测试数据"""
    base_dir = "example_data"
    
    # VOC格式目录结构
    dirs = [
        os.path.join(base_dir, "JPEGImages"),
        os.path.join(base_dir, "SegmentationClass"),
        os.path.join(base_dir, "ImageSets", "Segmentation"),
    ]
    
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"📁 创建目录: {d}")
    
    # 移动txt文件到VOC格式位置
    txt_files = ['train.txt', 'val.txt', 'test.txt']
    for txt_file in txt_files:
        src = os.path.join(base_dir, txt_file)
        dst = os.path.join(base_dir, "ImageSets", "Segmentation", txt_file)
        if os.path.exists(src) and not os.path.exists(dst):
            import shutil
            shutil.copy(src, dst)
            print(f"📄 复制 {txt_file} 到 ImageSets/Segmentation/")
    
    # 读取样本列表
    datasets = {
        'train': os.path.join(base_dir, "ImageSets", "Segmentation", 'train.txt'),
        'val': os.path.join(base_dir, "ImageSets", "Segmentation", 'val.txt'),
        'test': os.path.join(base_dir, "ImageSets", "Segmentation", 'test.txt'),
    }
    
    # 备用：根目录下的txt
    for key in datasets:
        if not os.path.exists(datasets[key]):
            datasets[key] = os.path.join(base_dir, f'{key}.txt')
    
    for dataset_type, txt_path in datasets.items():
        if not os.path.exists(txt_path):
            print(f"⚠️ 文件不存在: {txt_path}")
            continue
        
        with open(txt_path, 'r') as f:
            sample_ids = [line.strip() for line in f if line.strip()]
        
        for sample_id in sample_ids:
            # VOC格式：所有影像在 JPEGImages/ 下
            img_path = os.path.join(base_dir, "JPEGImages", f"{sample_id}.jpg")
            create_sample_image(img_path, sample_id, dataset_type)
            
            # VOC格式：所有标签在 SegmentationClass/ 下
            label_path = os.path.join(base_dir, "SegmentationClass", f"{sample_id}.png")
            create_sample_label(label_path, sample_id)
        
        print(f"✅ 已创建 {dataset_type} 数据集: {len(sample_ids)} 个样本")


def create_sample_image(path, sample_id, dataset_type):
    """创建示例影像"""
    # 创建 256x256 的 RGB 影像
    width, height = 256, 256
    
    # 根据数据集类型使用不同的背景色
    bg_colors = {
        'train': (50, 100, 50),   # 绿色调
        'val': (50, 50, 100),     # 蓝色调
        'test': (100, 50, 50),    # 红色调
    }
    bg_color = bg_colors.get(dataset_type, (100, 100, 100))
    
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 添加一些随机形状模拟遥感影像
    random.seed(hash(sample_id))
    
    for _ in range(10):
        x1 = random.randint(0, width - 50)
        y1 = random.randint(0, height - 50)
        x2 = x1 + random.randint(20, 50)
        y2 = y1 + random.randint(20, 50)
        
        color = (
            random.randint(50, 200),
            random.randint(50, 200),
            random.randint(50, 200)
        )
        
        if random.random() > 0.5:
            draw.rectangle([x1, y1, x2, y2], fill=color)
        else:
            draw.ellipse([x1, y1, x2, y2], fill=color)
    
    # 添加样本ID文字
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    draw.text((10, 10), f"{sample_id}", fill=(255, 255, 255), font=font)
    draw.text((10, 25), f"[{dataset_type}]", fill=(200, 200, 200), font=font)
    
    img.save(path)


def create_sample_label(path, sample_id):
    """创建VOC格式示例标签影像（像素值为类别索引）"""
    # 创建 256x256 的灰度标签影像
    width, height = 256, 256
    
    # 使用灰度模式，像素值代表类别索引
    img = Image.new('L', (width, height), 0)  # 背景为0
    draw = ImageDraw.Draw(img)
    
    # 类别索引 (1-20 对应VOC的20个类别)
    class_indices = list(range(1, 21))
    
    random.seed(hash(sample_id) + 1)
    
    # 绘制一些随机区域作为标签
    for _ in range(5):
        x1 = random.randint(0, width - 60)
        y1 = random.randint(0, height - 60)
        x2 = x1 + random.randint(30, 60)
        y2 = y1 + random.randint(30, 60)
        
        # 随机选择一个类别索引
        class_idx = random.choice(class_indices)
        
        if random.random() > 0.5:
            draw.rectangle([x1, y1, x2, y2], fill=class_idx)
        else:
            draw.ellipse([x1, y1, x2, y2], fill=class_idx)
    
    img.save(path)


if __name__ == "__main__":
    try:
        create_test_data()
        print("\n✅ 测试数据创建完成！")
        print("现在可以运行 data_source_tree_example.py 测试功能")
    except ImportError:
        print("⚠️ 需要安装 Pillow 库: pip install Pillow")
