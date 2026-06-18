# -*- coding: utf-8 -*-
"""
Backbone 注册表 (Backbone Registry)

遵循"单一数据源"原则，集中管理每个 (Method, Backbone) 组合的完整配置信息，
包括内部 key、MMSeg 配置映射、训练尺寸约束以及公共预训练权重。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from collections import defaultdict


@dataclass
class BackboneEntry:
    """描述一个 (Method, Backbone) 组合的完整配置信息。"""
    
    # --- 标识 ---
    method: str            # e.g. 'SegFormer'
    backbone_display: str  # e.g. 'MiT-B2'（UI显示名）
    backbone_key: str      # e.g. 'mit_b2'（传给训练器的内部标识）
    
    # --- MMSeg 配置查找 ---
    config_subdir: str     # e.g. 'segformer'
    config_pattern: str    # e.g. 'segformer_mit-b2*512x512.py'
    
    # --- 训练尺寸约束 ---
    valid_crop_sizes: List[int] # 合法尺寸列表（均满足32整除性）
    default_crop_size: int      # 默认选择的尺寸
    
    # --- 预训练权重（可选）---
    pretrain_dataset: str = ''           # e.g. 'ImageNet-1K'
    pretrain_url: Optional[str] = None   # 公共下载链接


BACKBONE_REGISTRY = [
    # --- SegFormer ---
    BackboneEntry('SegFormer', 'MiT-B0', 'mit_b0', 'segformer', 'segformer_mit-b0*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b0_20220624-7e0fe6dd.pth'),
    BackboneEntry('SegFormer', 'MiT-B1', 'mit_b1', 'segformer', 'segformer_mit-b1*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b1_20220624-02e5a6a1.pth'),
    BackboneEntry('SegFormer', 'MiT-B2', 'mit_b2', 'segformer', 'segformer_mit-b2*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b2_20220624-66e8bf70.pth'),
    BackboneEntry('SegFormer', 'MiT-B3', 'mit_b3', 'segformer', 'segformer_mit-b3*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b3_20220624-13b1141c.pth'),
    BackboneEntry('SegFormer', 'MiT-B4', 'mit_b4', 'segformer', 'segformer_mit-b4*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b4_20220624-d588d980.pth'),
    BackboneEntry('SegFormer', 'MiT-B5', 'mit_b5', 'segformer', 'segformer_mit-b5*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b5_20220624-658746d9.pth'),

    # --- Swin-Transformer ---
    BackboneEntry('Swin-Transformer', 'Swin-Tiny', 'swin_tiny', 'swin', 'swin-tiny*upernet*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth'),
    BackboneEntry('Swin-Transformer', 'Swin-Small', 'swin_small', 'swin', 'swin-small*upernet*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_small_patch4_window7_224_20220317-7ba6d6dd.pth'),
    BackboneEntry('Swin-Transformer', 'Swin-Base', 'swin_base', 'swin', 'swin-base*upernet*512x512.py', [512], 512, 'ImageNet-22K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_base_patch4_window12_384_20220317-55b0104a.pth'),
    BackboneEntry('Swin-Transformer', 'Swin-Large', 'swin_large', 'swin', 'swin-large*upernet*512x512.py', [512], 512, 'ImageNet-22K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_large_patch4_window12_384_22k_20220412-6580f57d.pth'),

    # --- UperNet ---
    BackboneEntry('UperNet', 'Swin-Tiny', 'swin_tiny', 'swin', 'upernet_swin-tiny*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth'),
    BackboneEntry('UperNet', 'Swin-Base', 'swin_base', 'swin', 'upernet_swin-base*512x512.py', [512], 512, 'ImageNet-22K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_base_patch4_window12_384_20220317-55b0104a.pth'),
    BackboneEntry('UperNet', 'ResNet-50', 'resnet50', 'upernet', 'upernet_r50*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),
    BackboneEntry('UperNet', 'ConvNeXt-Tiny', 'convnext_tiny', 'convnext', 'upernet_convnext-tiny*512x512*.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/convnext/convnext-t_3rdparty_32xb128-noema_in1k_20220301-795e9634.pth'),

    # --- Mask2Former ---
    # 注意：Mask2Former 官方 ADE20K 配置文件的命名尺寸因 Backbone 而异：
    #   Swin-Tiny / ResNet-50 → 512x512
    #   Swin-Base / Swin-Large → 640x640（官方不提供 512 版本）
    # config_pattern 必须与官方文件名中的实际尺寸保持一致，
    # default_crop_size 也应与之对齐，以保证 Resize.scale 等 pipeline 字段的一致性。
    BackboneEntry('Mask2Former', 'Swin-Tiny',  'swin_tiny',  'mask2former', 'mask2former_swin-t*512x512*.py', [512],      512, 'ImageNet-1K',  'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth'),
    BackboneEntry('Mask2Former', 'Swin-Base',  'swin_base',  'mask2former', 'mask2former_swin-b*640x640*.py', [640],      640, 'ImageNet-22K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_base_patch4_window12_384_20220317-55b0104a.pth'),
    BackboneEntry('Mask2Former', 'Swin-Large', 'swin_large', 'mask2former', 'mask2former_swin-l*640x640*.py', [640],      640, 'ImageNet-22K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_large_patch4_window12_384_22k_20220412-6580f57d.pth'),
    BackboneEntry('Mask2Former', 'ResNet-50',  'resnet50',   'mask2former', 'mask2former_r50*512x512*.py',   [512],      512, 'ImageNet-1K',  'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),

    # --- PSPNet ---
    BackboneEntry('PSPNet', 'ResNet-50', 'resnet50', 'pspnet', 'pspnet_r50*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),
    BackboneEntry('PSPNet', 'ResNet-101', 'resnet101', 'pspnet', 'pspnet_r101*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth'),

    # --- DeepLabV3+ ---
    BackboneEntry('DeepLabV3+', 'ResNet-50', 'resnet50', 'deeplabv3plus', 'deeplabv3plus_r50*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),
    BackboneEntry('DeepLabV3+', 'ResNet-101', 'resnet101', 'deeplabv3plus', 'deeplabv3plus_r101*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth'),
    BackboneEntry('DeepLabV3+', 'MobileNetV2', 'mobilenet_v2', 'mobilenet_v2', 'deeplabv3plus_m-v2*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/mobilenet_v2/mobilenet_v2_batch256_imagenet-ff34753d.pth'),
    BackboneEntry('DeepLabV3+', 'MobileNetV3', 'mobilenet_v3_large', 'mobilenet_v3', 'deeplabv3plus_m-v3*512x512*.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/mobilenet_v3/lraspp_m-v3-d8_8xb4-320k_ade20k-512x512_20221109_214317-0e0e4dfd.pth'),

    # --- FCN ---
    BackboneEntry('FCN', 'ResNet-18', 'resnet18', 'fcn', 'fcn_r18*d8*512x512*.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet18_v1c-b5776b93.pth'),
    BackboneEntry('FCN', 'ResNet-50', 'resnet50', 'fcn', 'fcn_r50*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),
    BackboneEntry('FCN', 'ResNet-101', 'resnet101', 'fcn', 'fcn_r101*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth'),
    BackboneEntry('FCN', 'HRNet-W32', 'hrnet_w32', 'hrnet', 'fcn_hr32*512x512*.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/hrnetv2_w32_imagenet_pretrained-dc9eeb4f.pth'),
    BackboneEntry('FCN', 'HRNet-W48', 'hrnet_w48', 'hrnet', 'fcn_hr48*512x512.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/hrnetv2_w48_imagenet_pretrained-e0af9343.pth'),

    # --- HRNet+OCR ---
    BackboneEntry('HRNet+OCR', 'HRNet-W32', 'hrnet_w32', 'ocrnet', 'ocrnet_hr32*512x512*.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/hrnetv2_w32_imagenet_pretrained-dc9eeb4f.pth'),
    BackboneEntry('HRNet+OCR', 'HRNet-W48', 'hrnet_w48', 'ocrnet', 'ocrnet_hr48*512x512*.py', [512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/hrnetv2_w48_imagenet_pretrained-e0af9343.pth'),

    # --- UNet ---
    BackboneEntry('UNet', 'ResNet-50', 'resnet50', 'unet', 'unet_s5*d16_fcn*r50*d8*512x512.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),

    # --- UNet++ ---
    BackboneEntry('UNet++', 'ResNet-50', 'resnet50', 'unet', 'unet-s5-d16_fcn*512x512*.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth'),
    BackboneEntry('UNet++', 'ResNet-101', 'resnet101', 'unet', 'unet-s5-d16_fcn*512x512*.py', [256, 512], 512, 'ImageNet-1K', 'https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth'),
]


# ==============================================================================
# 动态派生视图 (供各组件消费)
# ==============================================================================

# 1. (Method) -> [Backbone 显示名] (保持字母顺序)
METHOD_BACKBONE_MAP = defaultdict(list)
for entry in BACKBONE_REGISTRY:
    if entry.backbone_display not in METHOD_BACKBONE_MAP[entry.method]:
        METHOD_BACKBONE_MAP[entry.method].append(entry.backbone_display)

for k in METHOD_BACKBONE_MAP:
    METHOD_BACKBONE_MAP[k].sort()


# 2. Backbone 显示名 -> backbone_key
BACKBONE_CHOICES = {}
for entry in BACKBONE_REGISTRY:
    BACKBONE_CHOICES[entry.backbone_display] = entry.backbone_key


# 3. Backbone 显示名 -> [预训练数据集名称]
PRETRAINED_MODELS = defaultdict(list)
for entry in BACKBONE_REGISTRY:
    if entry.pretrain_dataset and entry.pretrain_dataset not in PRETRAINED_MODELS[entry.backbone_display]:
        PRETRAINED_MODELS[entry.backbone_display].append(entry.pretrain_dataset)

# COCO 等其他特殊数据集如果是额外需求，通常需要自定义，但在新的单源配置中，我们统一按预设 url 走
# 为了兼容以前的一些选项，如果想加上如 'ADE20K' 等，其实我们在新的表里面都只有 1 个官方 ImageNet，这是因为原版有些只是硬编码并没有下载链接。
# 这里遵循我们新建的注册表。


# 4. (Method, backbone_key) -> (config_subdir, config_pattern)
CONFIG_MAP = {}
for entry in BACKBONE_REGISTRY:
    CONFIG_MAP[(entry.method, entry.backbone_key)] = (entry.config_subdir, entry.config_pattern)


# 5. (Backbone 显示名, pretrain_dataset) -> url
WEIGHT_URL_MAP = {}
for entry in BACKBONE_REGISTRY:
    if entry.pretrain_dataset and entry.pretrain_url:
        WEIGHT_URL_MAP[(entry.backbone_display, entry.pretrain_dataset)] = entry.pretrain_url

