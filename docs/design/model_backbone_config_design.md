# 模型 · Backbone · 预训练权重 —— 关系设计文档

> **文档范围**：`ui/widgets/model_selection_widget.py` 中三张静态映射表的现状分析、设计问题，
> 以及基于"单一数据源"原则的重构方案。
> **约束**：仅讨论正确性问题，不涉及 UX 改进。

---

## 1. 现状：三张表的实际调用链

### 1.1 三张表各自的作用

| 表名 | 所在文件 | 实际用途 |
|------|----------|----------|
| `METHOD_BACKBONE_MAP` | `model_selection_widget.py` | UI 联动：选中 Method 后决定 Backbone 下拉框的候选列表 |
| `BACKBONE_CHOICES` | `model_selection_widget.py` | 将 Backbone 显示名（如 `ResNet-50`）转为内部 key（如 `resnet50`），通过 `get_params()['backbone_key']` 传出 |
| `PRETRAINED_MODELS` | `model_selection_widget.py` | 被 `weight_selection_widget.py` 的 `update_backbone()` 导入，决定"公共预训练"Tab 的下拉列表内容 |

### 1.2 数据流全链路

```
用户选择 Method + Backbone
        |
ModelSelectionWidget.get_params()
  -> { method, backbone, backbone_key }    <- 由 BACKBONE_CHOICES 转换
        |
_find_base_config(model_params)           <- data_source_tree_example.py
  -> CONFIG_MAP[(method, backbone_key)]
  -> (sub_dir, glob_pattern)
  -> 在 mmseg 安装目录中查找 .py 配置文件
        |
MMSegTrainer.generate_config(ui_params)
  -> 加载 base_config，注入 num_classes / in_channels / lr 等参数
  -> 写入预训练权重路径 (ui_params['pretrained'])
```

`PRETRAINED_MODELS` 的用途独立于上述主链路，仅用于填充 `WeightSelectionWidget` 的公共预训练下拉框，与配置文件生成流程无直接关联。

### 1.3 CONFIG_MAP（真正决定可训练性的表）

`CONFIG_MAP` 定义在 `scripts/data_source_tree_example.py` 的 `_find_base_config()` 方法内，是系统**实际支持**的所有 (Method, Backbone) 组合的权威来源：

```python
CONFIG_MAP = {
    ('PSPNet',           'resnet50')          : ('pspnet',       'pspnet_r50*d8*512x512.py'),
    ('PSPNet',           'resnet101')         : ('pspnet',       'pspnet_r101*d8*512x512.py'),
    ('DeepLabV3+',       'resnet50')          : ('deeplabv3plus','deeplabv3plus_r50*d8*512x512.py'),
    ('DeepLabV3+',       'resnet101')         : ('deeplabv3plus','deeplabv3plus_r101*d8*512x512.py'),
    ('DeepLabV3+',       'mobilenet_v2')      : ('mobilenet_v2', 'deeplabv3plus_m-v2*d8*512x512.py'),
    ('DeepLabV3+',       'mobilenet_v3_large'): ('mobilenet_v3', 'deeplabv3plus_m-v3*512x512*.py'),
    ('SegFormer',        'mit_b0')            : ('segformer',    'segformer_mit-b0*512x512.py'),
    ('SegFormer',        'mit_b1')            : ('segformer',    'segformer_mit-b1*512x512.py'),
    ('SegFormer',        'mit_b2')            : ('segformer',    'segformer_mit-b2*512x512.py'),
    ('SegFormer',        'mit_b3')            : ('segformer',    'segformer_mit-b3*512x512.py'),
    ('SegFormer',        'mit_b4')            : ('segformer',    'segformer_mit-b4*512x512.py'),
    ('SegFormer',        'mit_b5')            : ('segformer',    'segformer_mit-b5*512x512.py'),
    ('UperNet',          'swin_tiny')         : ('swin',         'upernet_swin-tiny*512x512.py'),
    ('UperNet',          'swin_base')         : ('swin',         'upernet_swin-base*512x512.py'),
    ('UperNet',          'resnet50')          : ('upernet',      'upernet_r50*512x512.py'),
    ('UperNet',          'convnext_tiny')     : ('convnext',     'upernet_convnext-tiny*512x512*.py'),
    ('FCN',              'resnet18')          : ('fcn',          'fcn_r18*d8*512x512*.py'),
    ('FCN',              'resnet50')          : ('fcn',          'fcn_r50*d8*512x512.py'),
    ('FCN',              'resnet101')         : ('fcn',          'fcn_r101*d8*512x512.py'),
    ('FCN',              'hrnet_w48')         : ('hrnet',        'fcn_hr48*512x512.py'),
    ('UNet',             'resnet50')          : ('unet',         'unet_s5*d16_fcn*r50*d8*512x512.py'),
    ('UNet++',           'resnet50')          : ('unet',         'unet-s5-d16_fcn*512x512*.py'),
    ('UNet++',           'resnet101')         : ('unet',         'unet-s5-d16_fcn*512x512*.py'),
    ('Mask2Former',      'swin_tiny')         : ('mask2former',  'mask2former_swin-t*512x512*.py'),
    ('Mask2Former',      'swin_base')         : ('mask2former',  'mask2former_swin-b*512x512*.py'),
    ('Mask2Former',      'swin_large')        : ('mask2former',  'mask2former_swin-l*512x512*.py'),
    ('Mask2Former',      'resnet50')          : ('mask2former',  'mask2former_r50*512x512*.py'),
    ('HRNet+OCR',        'hrnet_w32')         : ('ocrnet',       'ocrnet_hr32*512x512*.py'),
    ('HRNet+OCR',        'hrnet_w48')         : ('ocrnet',       'ocrnet_hr48*512x512*.py'),
    ('Swin-Transformer', 'swin_tiny')         : ('swin',         'swin-tiny*upernet*512x512.py'),
    ('Swin-Transformer', 'swin_small')        : ('swin',         'swin-small*upernet*512x512.py'),
    ('Swin-Transformer', 'swin_base')         : ('swin',         'swin-base*upernet*512x512.py'),
    ('Swin-Transformer', 'swin_large')        : ('swin',         'swin-large*upernet*512x512.py'),
}
```

---

## 2. 现存的正确性问题

### 2.1 三表与 CONFIG_MAP 不一致（静默失效）

`METHOD_BACKBONE_MAP` 中列出的 Backbone 组合，与 `CONFIG_MAP` 中实际有配置文件映射的组合存在差异：

| Method | Backbone（UI 中可选） | CONFIG_MAP 中是否存在 |
|--------|---------------------|----------------------|
| FCN | ResNet-18 | OK |
| FCN | ResNet-50 | OK |
| FCN | ResNet-101 | OK |
| FCN | HRNet-W32 | **缺失** — UI 可选但无配置文件，训练会失败 |
| FCN | HRNet-W48 | OK（通过 FCN 头接 HRNet） |
| UperNet | Swin-Tiny | OK |
| UperNet | Swin-Base | OK |
| UperNet | ResNet-50 | OK |
| UperNet | ConvNeXt-Tiny | OK |
| UNet++ | ResNet-50 | OK（与 UNet 共用配置） |
| UNet++ | ResNet-101 | OK（与 UNet 共用配置） |

**关键缺口**：`('FCN', 'hrnet_w32')` 在 UI 中可选，但 `CONFIG_MAP` 中无对应条目，`_find_base_config()` 会返回空字符串，训练在配置生成阶段静默失败。

### 2.2 训练尺寸约束分析

`CONFIG_MAP` 中所有 glob 模式均包含 `512x512`，这是 MMSeg 官方预训练配置的默认尺寸。
文件名中的尺寸只是**查找过滤器**，不是运行时实际尺寸；实际尺寸由 `MMSegTrainer.generate_config()` 的 `crop_size` 参数覆盖。

但不同 Backbone 的训练尺寸有硬约束：

| Backbone 类型 | 约束规则 | 原因 |
|--------------|---------|------|
| CNN（ResNet、HRNet、MobileNet） | 必须是 **32 的倍数** | 网络最大下采样步长为 32 |
| ViT-based（MiT、Swin、ConvNeXt） | 必须是 **patch_size 的整数倍**，patch_size=4，实际约束为 **32 的倍数** | Window Attention 需整除 |
| Mask2Former | 同 ViT-based，额外建议 **>= 512** | Pixel Decoder 的上采样对小尺寸不稳定 |

系统现有验证（`logic_engine.py` Rule 1：`crop_size % 32 == 0`）已覆盖所有已支持 Backbone 的约束，无需额外分 backbone 类型校验。

### 2.3 PRETRAINED_MODELS 的位置错误

`PRETRAINED_MODELS` 定义在 `model_selection_widget.py`，但本文件内无任何代码读取它，实际消费方是 `weight_selection_widget.py`：

```python
# weight_selection_widget.py, L21
from ui.widgets.model_selection_widget import PRETRAINED_MODELS

def update_backbone(self, backbone_name: str):
    models = PRETRAINED_MODELS.get(backbone_name, [])
    self.combo_pretrained_model.addItems(models)
```

这造成了单向跨模块依赖：`WeightSelectionWidget` 绑定了 `ModelSelectionWidget` 的内部数据，违反了模块封装原则。

---

## 3. 设计方案：合并为单一注册表

### 3.1 核心原则

以 `(Method, backbone_key)` 二元组为主键，将散落在三处的数据合并为一张结构化的 `BACKBONE_REGISTRY`，使每个合法组合成为一个完整的数据记录。

### 3.2 数据结构定义

```python
# 建议放置位置: config/backbone_registry.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class BackboneEntry:
    """描述一个 (Method, Backbone) 组合的完整配置信息。"""

    # --- 标识 ---
    method: str            # e.g. 'SegFormer'
    backbone_display: str  # e.g. 'MiT-B2'（UI 显示名）
    backbone_key: str      # e.g. 'mit_b2'（传给训练器的内部标识）

    # --- MMSeg 配置查找 ---
    config_subdir: str     # e.g. 'segformer'
    config_pattern: str    # e.g. 'segformer_mit-b2*512x512.py'

    # --- 训练尺寸约束 ---
    valid_crop_sizes: list  # 合法尺寸列表（均满足 32 整除性），e.g. [512] or [256, 512]
    default_crop_size: int  # 默认选择的尺寸

    # --- 预训练权重（可选）---
    pretrain_url: Optional[str] = None  # 公共下载链接，None 表示无官方链接
    pretrain_dataset: str = ''          # e.g. 'ImageNet-1K'
```

### 3.3 派生规则

各消费方从 `BACKBONE_REGISTRY` 动态派生，消除手工维护多表的负担：

```python
# MODEL_BACKBONE_MAP: 按 Method 分组
from collections import defaultdict
METHOD_BACKBONE_MAP = defaultdict(list)
for entry in BACKBONE_REGISTRY:
    METHOD_BACKBONE_MAP[entry.method].append(entry.backbone_display)

# BACKBONE_CHOICES: 显示名 -> backbone_key
BACKBONE_CHOICES = {e.backbone_display: e.backbone_key for e in BACKBONE_REGISTRY}

# PRETRAINED_MODELS: backbone_display -> [dataset_name]
PRETRAINED_MODELS = {
    e.backbone_display: [e.pretrain_dataset]
    for e in BACKBONE_REGISTRY if e.pretrain_dataset
}

# CONFIG_MAP: (method, backbone_key) -> (subdir, pattern)
CONFIG_MAP = {
    (e.method, e.backbone_key): (e.config_subdir, e.config_pattern)
    for e in BACKBONE_REGISTRY
}
```

---

## 4. 已支持组合完整参考表

下表为系统当前 `CONFIG_MAP` 中所有合法组合，含建议训练尺寸与已知预训练权重信息。

| Method | Backbone（显示名） | backbone_key | config_subdir | valid_crop_sizes | default | pretrain_dataset | pretrain_url（OpenMMLab）|
|--------|------------------|--------------|---------------|-----------------|---------|------------------|--------------------------|
| SegFormer | MiT-B0 | mit_b0 | segformer | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b0_20220624-7e0fe6dd.pth) |
| SegFormer | MiT-B1 | mit_b1 | segformer | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b1_20220624-02e5a6a1.pth) |
| SegFormer | MiT-B2 | mit_b2 | segformer | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b2_20220624-66e8bf70.pth) |
| SegFormer | MiT-B3 | mit_b3 | segformer | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b3_20220624-13b1141c.pth) |
| SegFormer | MiT-B4 | mit_b4 | segformer | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b4_20220624-d588d980.pth) |
| SegFormer | MiT-B5 | mit_b5 | segformer | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b5_20220624-658746d9.pth) |
| Swin-Transformer | Swin-Tiny | swin_tiny | swin | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth) |
| Swin-Transformer | Swin-Small | swin_small | swin | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_small_patch4_window7_224_20220317-7ba6d6dd.pth) |
| Swin-Transformer | Swin-Base | swin_base | swin | 512 | 512 | ImageNet-22K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_base_patch4_window12_384_20220317-55b0104a.pth) |
| Swin-Transformer | Swin-Large | swin_large | swin | 512 | 512 | ImageNet-22K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_large_patch4_window12_384_22k_20220412-6580f57d.pth) |
| UperNet | Swin-Tiny | swin_tiny | swin | 512 | 512 | ImageNet-1K | 同上 |
| UperNet | Swin-Base | swin_base | swin | 512 | 512 | ImageNet-22K | 同上 |
| UperNet | ResNet-50 | resnet50 | upernet | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth) |
| UperNet | ConvNeXt-Tiny | convnext_tiny | convnext | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/convnext/convnext-t_3rdparty_32xb128-noema_in1k_20220301-795e9634.pth) |
| Mask2Former | Swin-Tiny | swin_tiny | mask2former | 512 | 512 | ImageNet-1K | 同上 |
| Mask2Former | Swin-Base | swin_base | mask2former | 512 | 512 | ImageNet-22K | 同上 |
| Mask2Former | Swin-Large | swin_large | mask2former | 512 | 512 | ImageNet-22K | 同上 |
| Mask2Former | ResNet-50 | resnet50 | mask2former | 512 | 512 | ImageNet-1K | 同上 |
| PSPNet | ResNet-50 | resnet50 | pspnet | 256, 512 | 512 | ImageNet-1K | 同上 |
| PSPNet | ResNet-101 | resnet101 | pspnet | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth) |
| DeepLabV3+ | ResNet-50 | resnet50 | deeplabv3plus | 256, 512 | 512 | ImageNet-1K | 同上 |
| DeepLabV3+ | ResNet-101 | resnet101 | deeplabv3plus | 256, 512 | 512 | ImageNet-1K | 同上 |
| DeepLabV3+ | MobileNetV2 | mobilenet_v2 | mobilenet_v2 | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/mobilenet_v2/mobilenet_v2_batch256_imagenet-ff34753d.pth) |
| DeepLabV3+ | MobileNetV3 | mobilenet_v3_large | mobilenet_v3 | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/mobilenet_v3/lraspp_m-v3-d8_8xb4-320k_ade20k-512x512_20221109_214317-0e0e4dfd.pth) |
| FCN | ResNet-18 | resnet18 | fcn | 256, 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/pretrain/third_party/resnet18_v1c-b5776b93.pth) |
| FCN | ResNet-50 | resnet50 | fcn | 256, 512 | 512 | ImageNet-1K | 同上 |
| FCN | ResNet-101 | resnet101 | fcn | 256, 512 | 512 | ImageNet-1K | 同上 |
| FCN | HRNet-W48 | hrnet_w48 | hrnet | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/pretrain/third_party/hrnetv2_w48_imagenet_pretrained-e0af9343.pth) |
| HRNet+OCR | HRNet-W32 | hrnet_w32 | ocrnet | 512 | 512 | ImageNet-1K | [链接](https://download.openmmlab.com/pretrain/third_party/hrnetv2_w32_imagenet_pretrained-dc9eeb4f.pth) |
| HRNet+OCR | HRNet-W48 | hrnet_w48 | ocrnet | 512 | 512 | ImageNet-1K | 同上 |
| UNet | ResNet-50 | resnet50 | unet | 256, 512 | 512 | ImageNet-1K | 同上 |
| UNet++ | ResNet-50 | resnet50 | unet | 256, 512 | 512 | ImageNet-1K | 同上 |
| UNet++ | ResNet-101 | resnet101 | unet | 256, 512 | 512 | ImageNet-1K | 同上 |

> **遥感场景说明**：遥感影像尺寸通常远大于 512px，推理阶段需配合 `sliding_window` 策略。
> 训练尺寸选 512 是显存与感受野的折中；较大目标场景可尝试 1024（须满足 32 整除性约束且显存充足）。

---

## 5. 正确性问题汇总与修复建议

### 5.1 UI 可选但无法训练的组合

| Method | Backbone | backbone_key | 原因 | 修复方案 |
|--------|----------|--------------|------|----------|
| FCN | HRNet-W32 | hrnet_w32 | CONFIG_MAP 中无条目，`_find_base_config` 返回空字符串 | 方案A：从 `METHOD_BACKBONE_MAP['FCN']` 移除 `HRNet-W32`；方案B：在 CONFIG_MAP 添加 `('FCN', 'hrnet_w32'): ('hrnet', 'fcn_hr32*512x512*.py')` |

注意：`HRNet-W32` 在 `HRNet+OCR` 下已有正确的 CONFIG_MAP 条目，可正常训练。

### 5.2 PRETRAINED_MODELS 缺失的 backbone

以下 backbone 在 CONFIG_MAP 中有对应条目（即可以训练），但在 PRETRAINED_MODELS 中缺失，
导致 `WeightSelectionWidget` 的公共预训练下拉框为空：

| Backbone 显示名 | backbone_key | 建议补充内容 |
|----------------|--------------|------------|
| ResNet-18 | resnet18 | `['ImageNet-1K']` |
| MobileNetV3 | mobilenet_v3_large | `['ImageNet-1K']` |
| ConvNeXt-Tiny | convnext_tiny | `['ImageNet-1K']` |
| MiT-B3 | mit_b3 | `['ImageNet-1K']` |
| MiT-B4 | mit_b4 | `['ImageNet-1K']` |
| Swin-Small | swin_small | `['ImageNet-1K']` |
| HRNet-W32 | hrnet_w32 | `['ImageNet-1K']` |

---

## 6. 重构路径

### Step 1 — 最小修复（正确性，不改变架构）

**改动点：`model_selection_widget.py`**

1. 从 `METHOD_BACKBONE_MAP['FCN']` 中移除 `'HRNet-W32'`
2. 在 `PRETRAINED_MODELS` 中补全第 5.2 节的 7 个条目

### Step 2 — 位置修正（中等改动）

将 `PRETRAINED_MODELS` 从 `model_selection_widget.py` 迁移到 `weight_selection_widget.py`，
使数据紧邻其唯一消费方，消除跨模块依赖。

### Step 3 — 架构合并（较大改动）

新建 `config/backbone_registry.py`，以第 3 节的 `BackboneEntry` 数据类为基础，
将四处分散的数据（`METHOD_BACKBONE_MAP`、`BACKBONE_CHOICES`、`PRETRAINED_MODELS`、`CONFIG_MAP`）
合并为一张单一注册表，各消费方动态派生所需视图。
