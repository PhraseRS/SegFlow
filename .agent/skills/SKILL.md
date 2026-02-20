---
name: project_skills_registry
description: 项目可复用技能注册表 — 在编写任何涉及图像处理、遥感数据、GDAL 转换的代码前必须优先使用已定义的 Skill
---

# 项目技能注册表（强制优先使用）

> **规则：在编写或修改任何 `core/`、`ui/`、`scripts/` 中的代码之前，必须先检查下方的 Skill 清单。如果已有 Skill 能实现所需功能，禁止重新实现，必须 `from skills.xxx import ...` 调用。**

## 可用 Skills（位于 `skills/` 目录）

### 1. `skill_image_processing.py` — 图像处理工具集

| 导出 | 类型 | 用途 |
|---|---|---|
| `VOC_PALETTE` | `list[tuple]` | PASCAL VOC 标准 22 色调色板 |
| `apply_colormap(label_image, palette=None)` | `function` | 将单通道标签 QImage 转为伪彩色 ARGB32 图像 |
| `apply_linear_stretch(image, percent=2)` | `function` | 对 QImage 做线性 percent% 拉伸（遥感影像增强） |

**适用场景**：缩略图渲染、画布显示、标签可视化、遥感影像对比度增强

```python
from skills.skill_image_processing import VOC_PALETTE, apply_colormap, apply_linear_stretch
```

---

### 2. `skill_sample_analysis.py` — 遥感样本质检分析

| 导出 | 类型 | 用途 |
|---|---|---|
| `ISSUE_*` 常量 | `str` | 问题类型标识（9 种） |
| `LEVEL_FATAL`, `LEVEL_WARNING` | `str` | 问题级别 |
| `ISSUE_LEVELS` | `dict` | 问题类型→级别映射 |
| `NOISE_AREA_THRESHOLD` | `int` | 噪点面积阈值（5 像素） |
| `NODATA_COVERAGE_THRESHOLD` | `float` | 无数据覆盖率阈值（80%） |
| `VALID_CLASS_IDS` | `set` | 有效类别 ID 范围（0-255） |
| `analyze_sample_fully(args)` | `function` | 一次 I/O 完成统计+质检 |

**适用场景**：数据集质量检查、样本统计、健康报告生成

```python
from skills.skill_sample_analysis import analyze_sample_fully, ISSUE_FILE_MISSING, ISSUE_LEVELS
```

---

### 3. `skill_geodata_utils.py` — 遥感地理数据工具

| 导出 | 类型 | 用途 |
|---|---|---|
| `gdal_data_to_opencv_data(gdal_img_data)` | `function` | GDAL (BxHxW) → OpenCV (HxWxC) 格式转换 |

**适用场景**：GDAL 读取后的数据预处理、遥感影像波段操作

```python
from skills.skill_geodata_utils import gdal_data_to_opencv_data
```

---

## 强制使用规则

1. **新增遥感影像增强逻辑** → 先检查 `skill_image_processing.py` 是否已有实现
2. **新增数据集质检/统计** → 先检查 `skill_sample_analysis.py`
3. **新增 GDAL 数据转换** → 先检查 `skill_geodata_utils.py`
4. **如果需要新功能** → 优先扩展现有 Skill 文件，而非在业务模块中内联实现
5. **新建 Skill 文件** → 命名为 `skill_[功能].py`，必须包含 YAML Docstring，放入 `skills/` 目录，并更新本文件
