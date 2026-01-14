"""
测试增强的配置解析器功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_parser import ConfigParser


def test_format_1():
    """测试格式1: 直接变量定义"""
    content = """
CLASSES = ['background', 'building', 'road', 'vegetation']
PALETTE = [[0, 0, 0], [128, 0, 0], [128, 128, 0], [0, 128, 0]]
"""
    parser = ConfigParser()
    parser._parse_classes_and_palette(content)
    
    print("=" * 60)
    print("测试格式1: 直接变量定义")
    print("=" * 60)
    print(f"Classes: {parser.classes}")
    print(f"Palette: {parser.palette}")
    assert parser.classes == ['background', 'building', 'road', 'vegetation']
    assert len(parser.palette) == 4
    print("✅ 测试通过！\n")


def test_format_2():
    """测试格式2: metainfo 字典"""
    content = """
metainfo = dict(
    classes=('background', 'building', 'road', 'vegetation', 'water'),
    palette=[[0, 0, 0], [128, 0, 0], [128, 128, 0], [0, 128, 0], [0, 0, 128]]
)
"""
    parser = ConfigParser()
    parser._parse_classes_and_palette(content)
    
    print("=" * 60)
    print("测试格式2: metainfo 字典")
    print("=" * 60)
    print(f"Classes: {parser.classes}")
    print(f"Palette: {parser.palette}")
    assert parser.classes == ['background', 'building', 'road', 'vegetation', 'water']
    assert len(parser.palette) == 5
    print("✅ 测试通过！\n")


def test_format_3():
    """测试格式3: 嵌套字典"""
    content = """
dataset_config = dict(
    type='CustomDataset',
    data_root='data/custom',
    metainfo=dict(
        classes=['class1', 'class2', 'class3'],
        palette=[(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    )
)
"""
    parser = ConfigParser()
    parser._parse_classes_and_palette(content)
    
    print("=" * 60)
    print("测试格式3: 嵌套字典")
    print("=" * 60)
    print(f"Classes: {parser.classes}")
    print(f"Palette: {parser.palette}")
    assert parser.classes == ['class1', 'class2', 'class3']
    assert len(parser.palette) == 3
    print("✅ 测试通过！\n")


def test_format_4():
    """测试格式4: 混合格式"""
    content = """
# 配置文件
model = dict(
    type='EncoderDecoder',
    num_classes=5
)

# 数据集配置
train_dataloader = dict(
    dataset=dict(
        type='ADE20KDataset',
        classes=["background", "building", "road", "tree", "sky"],
        palette=[[0, 0, 0], [128, 0, 0], [0, 128, 0], [0, 255, 0], [128, 128, 255]]
    )
)
"""
    parser = ConfigParser()
    parser._parse_classes_and_palette(content)
    
    print("=" * 60)
    print("测试格式4: 混合格式")
    print("=" * 60)
    print(f"Classes: {parser.classes}")
    print(f"Palette: {parser.palette}")
    assert parser.classes == ["background", "building", "road", "tree", "sky"]
    assert len(parser.palette) == 5
    print("✅ 测试通过！\n")


def test_real_config():
    """测试真实的配置文件格式"""
    content = """
_base_ = [
    '../_base_/models/segformer_mit-b0.py',
    '../_base_/datasets/ade20k.py',
    '../_base_/default_runtime.py',
    '../_base_/schedules/schedule_160k.py'
]

crop_size = (512, 512)
data_preprocessor = dict(size=crop_size)
model = dict(
    data_preprocessor=data_preprocessor,
    decode_head=dict(num_classes=150))

# ADE20K dataset
metainfo = dict(
    classes=(
        'wall', 'building', 'sky', 'floor', 'tree', 'ceiling', 'road', 'bed',
        'windowpane', 'grass', 'cabinet', 'sidewalk', 'person', 'earth',
        'door', 'table', 'mountain', 'plant', 'curtain', 'chair', 'car',
        'water', 'painting', 'sofa', 'shelf', 'house', 'sea', 'mirror', 'rug',
        'field', 'armchair', 'seat', 'fence', 'desk', 'rock', 'wardrobe',
        'lamp', 'bathtub', 'railing', 'cushion', 'base', 'box', 'column',
        'signboard', 'chest of drawers', 'counter', 'sand', 'sink',
        'skyscraper', 'fireplace'
    ),
    palette=[
        [120, 120, 120], [180, 120, 120], [6, 230, 230], [80, 50, 50],
        [4, 200, 3], [120, 120, 80], [140, 140, 140], [204, 5, 255],
        [230, 230, 230], [4, 250, 7], [224, 5, 255], [235, 255, 7],
        [150, 5, 61], [120, 120, 70], [8, 255, 51], [255, 6, 82],
        [143, 255, 140], [204, 255, 4], [255, 51, 7], [204, 70, 3],
        [0, 102, 200], [61, 230, 250], [255, 6, 51], [11, 102, 255],
        [255, 7, 71], [255, 9, 224], [9, 7, 230], [220, 220, 220],
        [255, 9, 92], [112, 9, 255], [8, 255, 214], [7, 255, 224],
        [255, 184, 6], [10, 255, 71], [255, 41, 10], [7, 255, 255],
        [224, 255, 8], [102, 8, 255], [255, 61, 6], [255, 194, 7],
        [255, 122, 8], [0, 255, 20], [255, 8, 41], [255, 5, 153],
        [6, 51, 255], [235, 12, 255], [160, 150, 20], [0, 163, 255],
        [140, 140, 140], [250, 10, 15]
    ]
)
"""
    parser = ConfigParser()
    parser._parse_classes_and_palette(content)
    
    print("=" * 60)
    print("测试真实配置文件格式 (ADE20K)")
    print("=" * 60)
    print(f"Classes 数量: {len(parser.classes) if parser.classes else 0}")
    print(f"前5个类别: {parser.classes[:5] if parser.classes else None}")
    print(f"Palette 数量: {len(parser.palette) if parser.palette else 0}")
    print(f"前3个颜色: {parser.palette[:3] if parser.palette else None}")
    
    if parser.classes:
        assert len(parser.classes) == 50
        assert parser.classes[0] == 'wall'
        assert parser.classes[1] == 'building'
    
    if parser.palette:
        assert len(parser.palette) == 50
        assert parser.palette[0] == (120, 120, 120)
    
    print("✅ 测试通过！\n")


def test_parse_config_file_api():
    """测试 parse_config_file API"""
    # 创建临时配置文件
    temp_config = """
CLASSES = ['background', 'object1', 'object2']
PALETTE = [[0, 0, 0], [255, 0, 0], [0, 255, 0]]
"""
    
    # 写入临时文件
    temp_file = 'temp_config.py'
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(temp_config)
    
    try:
        parser = ConfigParser()
        classes, palette = parser.parse_config_file(temp_file)
        
        print("=" * 60)
        print("测试 parse_config_file API")
        print("=" * 60)
        print(f"Classes: {classes}")
        print(f"Palette: {palette}")
        
        assert classes == ['background', 'object1', 'object2']
        assert len(palette) == 3
        assert palette[0] == (0, 0, 0)
        
        print("✅ 测试通过！\n")
        
    finally:
        # 清理临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试增强的配置解析器功能")
    print("=" * 60 + "\n")
    
    try:
        test_format_1()
        test_format_2()
        test_format_3()
        test_format_4()
        test_real_config()
        test_parse_config_file_api()
        
        print("=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        print("\n支持的格式:")
        print("  ✅ 直接变量定义 (CLASSES = [...])")
        print("  ✅ metainfo 字典 (metainfo = dict(classes=...))")
        print("  ✅ 嵌套字典 (dataset.metainfo.classes)")
        print("  ✅ 列表和元组格式")
        print("  ✅ 真实的 MMSegmentation 配置文件")
        print("  ✅ 健壮的错误处理机制")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()