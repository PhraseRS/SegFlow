# MMSeg 配置文件尺寸对齐规范

> **适用场景**：当为 `BACKBONE_REGISTRY` 新增或修正 `(Method, Backbone)` 组合时，
> 以及在 `generate_config()` 中扩展 pipeline 参数覆盖逻辑时，均需参照本文档。

---
 
## 1. 核心问题：配置文件尺寸不是单纯的文件名标识

一份 MMSeg 官方配置文件（`.py`）中，与训练尺寸相关的字段**分散在 5 处**：

| 字段 | 示例值（640 配置） | 作用 |
|------|-----------------|------|
| `crop_size` 顶层变量 | `(640, 640)` | 整个配置的尺寸基准，其他字段往往引用它 |
| `train_pipeline.RandomCrop.crop_size` | `(640, 640)` | 训练时随机裁剪的目标尺寸 |
| `train/val/test_pipeline.Resize.scale` | `(2560, 640)` | 等比缩放目标（短边=crop短边，长边=4倍） |
| `data_preprocessor.size` | `(640, 640)` | batch 内图像 padding 的目标尺寸（Mask2Former 等使用） |
| `test_cfg.crop_size` / `stride` | `(640, 640)` / `(427, 427)` | 滑窗推理的裁剪尺寸和步长 |

**结论**：选择不同尺寸的 base config 文件，会导致上述 5 处中的大多数字段持有不同的值。
若只覆盖其中 1-2 处，其余字段将与实际 `crop_size` 不一致，产生以下风险：

- `Resize.scale` 与 `crop_size` 不匹配 → 图像 Resize 后尺寸不足以完成裁剪 → 训练期间 padding 异常或 shape 报错
- `data_preprocessor.size` 与 `crop_size` 不匹配 → batch 组合时维度不一致 → 训练直接崩溃（Mask2Former 尤其敏感）

---

## 2. 规范一：`config_pattern` 必须与官方文件中的实际尺寸对齐

### 2.1 不同 Backbone 的实际官方尺寸

并非所有组合都使用 512×512。以下是已确认的非 512 情况（需持续更新）：

| Method | Backbone | 官方 ADE20K 配置尺寸 | 备注 |
|--------|----------|---------------------|------|
| Mask2Former | Swin-Tiny | 512×512 | — |
| Mask2Former | ResNet-50 | 512×512 | — |
| **Mask2Former** | **Swin-Base** | **640×640** | 官方无 512 版本 |
| **Mask2Former** | **Swin-Large** | **640×640** | 官方无 512 版本 |

### 2.2 注册表填写规则

在 `config/backbone_registry.py` 的 `BACKBONE_REGISTRY` 中，每条 `BackboneEntry` 需满足：

```
config_pattern 中的尺寸  ==  default_crop_size  ==  官方文件名中的实际尺寸
```

**正确示例**：

```python
# Swin-Base 在 Mask2Former 下官方尺寸为 640，三者必须一致
BackboneEntry(
    'Mask2Former', 'Swin-Base', 'swin_base',
    config_subdir  = 'mask2former',
    config_pattern = 'mask2former_swin-b*640x640*.py',  # ← 与官方文件名匹配
    valid_crop_sizes = [640],
    default_crop_size = 640,                             # ← 与 pattern 中的尺寸一致
    ...
)
```

**错误示例（会导致 glob 找不到文件）**：

```python
BackboneEntry(
    'Mask2Former', 'Swin-Base', 'swin_base',
    config_pattern = 'mask2former_swin-b*512x512*.py',  # ← 官方不存在此文件
    default_crop_size = 512,
    ...
)
```

### 2.3 新增组合时的核实步骤

1. 在 MMSeg 安装目录（或 GitHub 仓库）中，进入对应的 `configs/<subdir>/` 目录
2. 查看该 Backbone 对应的 `.py` 文件名，确认其中的尺寸字符串（如 `512x512` 或 `640x640`）
3. 将确认后的尺寸填入 `config_pattern` 和 `default_crop_size`

---

## 3. 规范二：`generate_config()` 必须覆盖 5 处尺寸字段

当用户设定的 `crop_size` 与 base config 的默认尺寸不同时（包括用户主动修改，
或因 valid_crop_sizes 包含多个选项），`mmseg_trainer.py` 的 `generate_config()`
中需同步修正所有 5 处字段，确保 pipeline 内部一致。

### 3.1 当前实现（`mmseg_trainer.py` L345 起）

```python
crop_size = advisor_params.get('crop_size')
if crop_size:
    h, w = int(crop_size[0]), int(crop_size[1])
    size_tuple = (h, w)

    # ① 顶层 crop_size 变量
    cfg.crop_size = size_tuple

    # ② train_pipeline 中的 RandomCrop
    for t in cfg.get('train_pipeline', []):
        if isinstance(t, dict) and t.get('type') == 'RandomCrop':
            t['crop_size'] = size_tuple

    # ③ train / val / test pipeline 中的 Resize.scale
    long_side = max(h, w) * 4
    for pipeline_key in ('train_pipeline', 'val_pipeline', 'test_pipeline'):
        for t in cfg.get(pipeline_key, []):
            if isinstance(t, dict) and t.get('type') == 'Resize':
                t['scale'] = (long_side, min(h, w))

    # ④ data_preprocessor.size（Mask2Former 等算法）
    if hasattr(cfg, 'data_preprocessor') and isinstance(cfg.data_preprocessor, dict):
        if 'size' in cfg.data_preprocessor:
            cfg.data_preprocessor['size'] = size_tuple

    # ⑤ test_cfg 中的滑窗推理参数
    if hasattr(cfg, 'test_cfg') and isinstance(cfg.test_cfg, dict):
        if 'crop_size' in cfg.test_cfg:
            cfg.test_cfg['crop_size'] = size_tuple
        if 'stride' in cfg.test_cfg:
            cfg.test_cfg['stride'] = (h * 2 // 3, w * 2 // 3)
```

### 3.2 各字段的算法适用范围

| 字段 | 影响算法 | 无此字段时 |
|------|---------|-----------|
| `crop_size` | 所有 | 安全跳过 |
| `RandomCrop.crop_size` | 所有（训练时） | 安全跳过 |
| `Resize.scale` | 所有 | 安全跳过（无 Resize 则不做缩放） |
| `data_preprocessor.size` | Mask2Former、部分新架构 | 安全跳过（字段不存在则不操作） |
| `test_cfg.crop_size/stride` | 开启滑窗推理的算法 | 安全跳过（`whole_mode` 下无此字段） |

所有字段的覆盖逻辑均有存在性判断，不会因字段缺失而报错。

---

## 4. 为什么不修改 MMSeg 源码

`generate_config()` 的工作原理是**只读 + 内存修改 + 另存**：

```
MMSeg 安装目录（只读，永远不动）
  └── configs/mask2former/mask2former_swin-b*640x640*.py
              │
              │  mmengine.Config.fromfile(base_config)   ← 只读取
              ▼
          cfg 对象（Python 内存中修改）
              │
              │  cfg.crop_size = (512, 512)
              │  cfg.data_preprocessor['size'] = ...
              ▼
      工作目录/generated_config.py                       ← 写到新文件
              │
              │  mim train mmseg generated_config.py
              ▼
          训练进程（使用生成的副本）
```

MMSeg 安装目录中的原始 `.py` 文件从未被写入，所有修改均在内存中完成后
另存到用户工作目录。**无需修改 MMSeg 源码，也不受安装方式（pip/conda）影响**。

---

## 5. 快速检查清单

新增或修改 `BACKBONE_REGISTRY` 条目时：

- [ ] 已在官方配置目录中确认实际文件名中的尺寸
- [ ] `config_pattern` 中的尺寸字符串与官方文件名匹配
- [ ] `default_crop_size` 与 `config_pattern` 中的尺寸一致
- [ ] `valid_crop_sizes` 包含了 `default_crop_size`（官方推荐尺寸必须在合法列表内）
- [ ] 如允许多个合法尺寸，确认 `generate_config()` 的 5 处覆盖逻辑能正确处理非默认尺寸
