# 遥感影像处理代码系统性分析与重构工作方案

## 1. 代码梳理：按功能分类

### 1.1 影像读取（Open / Read）

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| R1 | `core/inference_engine.py:329` | `large_image_block_inference` | GDAL | `gdal.Open(image_path, GA_ReadOnly)` 打开遥感大图 |
| R2 | `core/inference_engine.py:375,407,436,458` | `large_image_block_inference` | GDAL | `dataset.ReadAsArray(x, y, w, h)` 分块读取像素 |
| R3 | `ui/widgets/smart_canvas.py:232,367` | `MetadataLoaderWorker.load` / `ImageLayerInfo._load_metadata` | rasterio | `rasterio.open(path)` 读取元数据 |
| R4 | `ui/widgets/smart_canvas.py:433,454` | `DynamicImageReader.read_at_level` / `read_center_preview` | rasterio | `rasterio.open(path)` + `src.read()` 读取影像 |
| R5 | `ui/widgets/smart_canvas.py:820` | `_load_viewport_at_native` | rasterio | `rasterio.open(path)` + window 读取原始分辨率视口 |
| R6 | `ui/widgets/gis_canvas.py:465` | `_read_profile` | rasterio | `rasterio.open(path)` 读取 CRS/transform 等元数据 |
| R7 | `ui/inference_panel.py:1724` | `_export_results` | rasterio | `rasterio.open(src_path)` 读取源图像地理信息用于导出 |
| R8 | `ui/inference_panel.py:1899` | `_build_visualization_metadata` | GDAL | `gdal.Open(output_path)` 采样读取掩码类别 |
| R9 | `utils/pyramid_builder.py:39,68` | `check_has_pyramids` / `get_pyramid_info` | GDAL | `gdal.Open(file_path, GA_ReadOnly)` 检查金字塔 |
| R10 | `skills/skill_sample_analysis.py:112-113` | `analyze_sample_fully` | cv2 | `cv2.imdecode(np.fromfile(...))` 读取样本图像+标签 |
| R11 | `ui/widgets/smart_canvas.py:258,385,573` | `_load_metadata_opencv` / `_read_with_opencv` | cv2 | `cv2.imdecode()` 回退读取非 TIFF 图像 |

### 1.2 影像写入（Write / Create）

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| W1 | `core/inference_engine.py:486-494` | `large_image_block_inference` | GDAL | `driver.Create()` 创建 GeoTIFF 输出 |
| W2 | `core/inference_engine.py:608` | `_stitch_blocks` | GDAL | `dst_ds.GetRasterBand(1).WriteArray()` 写入拼接结果 |
| W3 | `core/inference_engine.py:384,414,443,465` | `large_image_block_inference` | cv2 | `cv2.imwrite()` 保存分块中间结果 PNG |
| W4 | `ui/inference_panel.py:1729-1730` | `_export_results` | rasterio | `rasterio.open(path, 'w', **profile)` 导出 GeoTIFF |
| W5 | `core/framework_adapters/mmseg_trainer.py:67,71` | `LivePredictionHook` | cv2 | `cv2.imencode().tofile()` 保存训练中间预测结果 |

### 1.3 元数据 / 投影读取

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| M1 | `core/inference_engine.py:484-485` | `large_image_block_inference` | GDAL | `GetProjection()` / `GetGeoTransform()` |
| M2 | `core/inference_engine.py:336-337` | `large_image_block_inference` | GDAL | `RasterXSize` / `RasterYSize` |
| M3 | `ui/widgets/smart_canvas.py:232-237` | `MetadataLoaderWorker.load` | rasterio | `src.width/height/count/overviews()` |
| M4 | `ui/widgets/smart_canvas.py:367-372` | `ImageLayerInfo._load_metadata` | rasterio | 同上 |
| M5 | `ui/widgets/gis_canvas.py:465-471` | `_read_profile` | rasterio | `src.crs/transform/width/height` |
| M6 | `ui/inference_panel.py:1724-1726` | `_export_results` | rasterio | `src.crs/transform` |
| M7 | `ui/inference_panel.py:1901-1902` | `_build_visualization_metadata` | GDAL | `dataset.RasterXSize/YSize` |

### 1.4 坐标与投影转换

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| C1 | `core/inference_engine.py:493-494` | `large_image_block_inference` | GDAL | `SetGeoTransform()` / `SetProjection()` 复制投影 |
| C2 | `ui/widgets/gis_canvas.py:476-485` | `_calculate_offset` | rasterio | Affine 反变换计算叠加层像素偏移 |
| C3 | `ui/widgets/gis_canvas.py:487-490` | `_check_crs_match` | rasterio | CRS 一致性检查 |

### 1.5 波段读写 / 多波段操作

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| B1 | `ui/widgets/smart_canvas.py:471-509` | `_read_raster_display_data` | rasterio | 多波段→RGB 组合显示（含自定义波段映射） |
| B2 | `ui/widgets/smart_canvas.py:820-831` | `_load_viewport_at_native` | rasterio | 视口区域多波段读取 |
| B3 | `core/inference_engine.py:608` | `_stitch_blocks` | GDAL | `GetRasterBand(1).WriteArray()` 单波段写入 |
| B4 | `ui/inference_panel.py:1904` | `_build_visualization_metadata` | GDAL | `band.ReadAsArray()` 采样读取 |
| B5 | `utils/pyramid_builder.py:43,72` | `check_has_pyramids` / `get_pyramid_info` | GDAL | `GetRasterBand(1)` 读取概览信息 |

### 1.6 金字塔 / 重采样

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| P1 | `utils/pyramid_builder.py:24-49` | `PyramidBuilder.check_has_pyramids` | GDAL | 检查 Overview |
| P2 | `utils/pyramid_builder.py:53-95` | `PyramidBuilder.get_pyramid_info` | GDAL | 读取 Overview 详情 |
| P3 | `utils/pyramid_builder.py:97-149` | `PyramidBuilder.build_pyramids` | GDAL | `BuildOverviews()` 构建金字塔 |
| P4 | `utils/pyramid_builder.py:151-185` | `PyramidBuilder.ensure_pyramids` | GDAL | 检查+构建一体 |
| P5 | `ui/widgets/smart_canvas.py:511-522` | `DynamicImageReader._get_best_level` | rasterio | 选择最优 overview 级别 |

### 1.7 格式转换 / 数据类型映射

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| F1 | `skills/skill_geodata_utils.py:21-52` | `gdal_data_to_opencv_data` | numpy | GDAL (BxHxW) → OpenCV (HxWxC) |
| F2 | `core/inference_engine.py:263-265` | `_gdal_data_to_opencv_data` | — | 委托给 F1 |
| F3 | `ui/widgets/smart_canvas.py:500,506,829` | `_read_raster_display_data` / `_load_viewport_at_native` | cv2 | `cv2.merge([b,g,r])` 波段合并 |

### 1.8 伪彩色 / 掩码渲染（与影像I/O紧密相关）

| # | 文件路径 : 行号 | 函数/方法 | 库 | 说明 |
|---|---|---|---|---|
| V1 | `ui/widgets/smart_canvas.py:623-646` | `apply_label_colormap` | numpy/cv2 | 类别索引→BGRA 伪彩色 |
| V2 | `skills/skill_image_processing.py:40-69` | `apply_colormap` | QImage | 标签图→伪彩色 QImage |
| V3 | `core/mask_renderer.py:88-108` | `MaskRenderer.apply_palette` | numpy | 索引掩码→RGB 彩色图 |

---

## 2. 重复代码识别与接口抽象设计

### 2.1 重复模式 A：影像打开与元数据读取

**重复位置：** R1/M2, R3/M3/R4, M4, M5/M6, R8/M7, R9/B5

当前系统中存在 **GDAL** 和 **rasterio** 两套并行的影像打开逻辑，且元数据读取（宽/高/波段数/CRS/GeoTransform/金字塔）分散在多处。

> [!NOTE]
> 项目保留 rasterio 依赖，现有 rasterio 调用不做移除。Skill 内部实现仅使用 GDAL+cv2，但设计的接口需能**覆盖 GDAL 和 rasterio 两类调用点**，使项目各模块可统一通过 skill 接口完成影像操作。对于 UI 层（smart_canvas / gis_canvas）中已稳定运行的 rasterio 调用，可选择性迁移或保持现状。

**抽象接口：**

```python
def open_raster(path: str, mode: str = 'r') -> RasterHandle:
    """
    统一打开遥感栅格影像（内部使用 GDAL 实现）。

    Args:
        path: 影像文件路径
        mode: 'r' 只读 | 'w' 读写（用于构建金字塔等）

    Returns:
        RasterHandle: 封装 GDAL Dataset 的上下文管理器对象，包含：
            .width, .height, .band_count
            .projection (WKT str), .geo_transform (tuple)
            .crs_wkt (str), .overviews (list[int])
            .dataset (原始 gdal.Dataset 引用)
    
    可替换位置（GDAL 侧）: R1, R8, R9, M1, M2, M7
    可替换位置（rasterio 侧，按需迁移）: R3, R4, R5, R6, R7, M3-M6
    """
```

### 2.2 重复模式 B：分块/窗口读取

**重复位置：** R2 (4处), R4, R5, B2, B4

```python
def read_block(handle: RasterHandle,
               x: int, y: int, width: int, height: int,
               band_indices: list[int] | None = None,
               out_width: int | None = None,
               out_height: int | None = None,
               resample: str = 'nearest') -> np.ndarray:
    """
    从已打开的影像中读取指定矩形区域的像素数据。

    Args:
        handle: open_raster 返回的句柄
        x, y: 左上角像素坐标
        width, height: 读取区域像素尺寸
        band_indices: 读取的波段索引列表 (1-based)，None 表示全部
        out_width, out_height: 输出尺寸（None=原始尺寸，用于降采样）
        resample: 重采样方法 'nearest' | 'bilinear' | 'cubic'

    Returns:
        np.ndarray: shape=(H, W) 或 (H, W, C)，已转为 HxWxC 格式

    替换位置: R2(4处), R4, R5, B2, B4
    """
```

### 2.3 重复模式 C：影像创建与写入

**重复位置：** W1+C1, W2, W4

```python
def create_raster(path: str,
                  width: int, height: int,
                  band_count: int = 1,
                  dtype: str = 'uint8',
                  projection: str | None = None,
                  geo_transform: tuple | None = None,
                  compress: str = 'lzw') -> RasterWriter:
    """
    创建新的 GeoTIFF 栅格文件。

    Args:
        path: 输出文件路径
        width, height: 影像像素尺寸
        band_count: 波段数
        dtype: 数据类型 'uint8' | 'uint16' | 'float32'
        projection: WKT 投影字符串 (可从源影像复制)
        geo_transform: 仿射变换6元组 (可从源影像复制)
        compress: 压缩方式

    Returns:
        RasterWriter: 上下文管理器，支持 .write_band() / .write_block() / .flush()

    替换位置: W1, W2, W4
    """
```

```python
def write_block(writer: RasterWriter,
                data: np.ndarray,
                x: int, y: int,
                band: int = 1) -> None:
    """
    向已创建的栅格文件写入数据块。

    Args:
        writer: create_raster 返回的写入器
        data: 2D 数组
        x, y: 写入起始像素坐标
        band: 目标波段号 (1-based)

    替换位置: W2, W4
    """
```

### 2.4 重复模式 D：金字塔操作

**重复位置：** P1-P5

> 已由 `PyramidBuilder` 类封装，结构良好，无需重构。仅需将其内部 GDAL 调用改为使用统一的 `open_raster`。

### 2.5 重复模式 E：波段→显示 RGB 转换

**重复位置：** B1, B2, F1, F3

```python
def bands_to_rgb(data: np.ndarray,
                 band_indices: tuple[int, int, int] = (1, 2, 3),
                 layout: str = 'hwc') -> np.ndarray:
    """
    将多波段数据转换为 RGB 显示数组 (BGR 格式，兼容 OpenCV)。

    Args:
        data: 输入数组 (BxHxW 或 HxWxC)
        band_indices: RGB 波段索引 (1-based)
        layout: 输入布局 'bhw' (GDAL) | 'hwc' (已转换)

    Returns:
        np.ndarray: (H, W, 3) BGR 格式 uint8 数组

    替换位置: F1, F3, B1, B2
    """
```

### 2.6 重复模式 F：元数据复制（源→目标）

**重复位置：** M1+C1, M5+M6

```python
def copy_geo_metadata(src_path: str, dst_path: str) -> bool:
    """
    将源影像的地理元数据（投影+仿射变换）复制到目标影像。

    Args:
        src_path: 源影像路径
        dst_path: 目标影像路径

    Returns:
        bool: 是否成功

    替换位置: M1+C1 组合, M6+W4 组合
    """
```

---

## 3. 函数接口清单

| 接口名称 | 功能说明 | 输入 | 输出 | 原始代码位置 |
|---|---|---|---|---|
| `open_raster` | 统一打开栅格影像 | `path, mode` | `RasterHandle` (上下文管理器) | R1,R3-R9,M1-M7 |
| `read_block` | 分块/窗口读取 | `handle, x, y, w, h, bands, out_size, resample` | `np.ndarray (HxW 或 HxWxC)` | R2(×4),R4,R5,B2,B4 |
| `create_raster` | 创建 GeoTIFF | `path, w, h, bands, dtype, proj, geo_tf, compress` | `RasterWriter` (上下文管理器) | W1,W4 |
| `write_block` | 写入数据块 | `writer, data, x, y, band` | `None` | W2,W4 |
| `bands_to_rgb` | 多波段→显示RGB | `data, band_indices, layout` | `np.ndarray (H,W,3) BGR` | F1,F3,B1,B2 |
| `copy_geo_metadata` | 复制地理元数据 | `src_path, dst_path` | `bool` | M1+C1,M6+W4 |
| `get_raster_info` | 快速获取影像摘要 | `path` | `dict {width,height,bands,crs,has_pyramid,...}` | M3,M4,M5 |
| `build_pyramids` | 构建金字塔 | `path, levels, resampling, callback` | `bool` | P1-P4（已存在，需对接） |
| `sample_band_stats` | 采样读取波段统计 | `path, band, sample_size` | `dict {min,max,class_count}` | R8+B4 |

---

## 4. 遥感影像处理 Skills 方案设计

### 4.1 设计目标

将上述接口统一封装为一个 **`skill_raster_io`** 技能模块，**skill 内部仅依赖 `gdal` + `cv2`**（不引入 rasterio），但项目整体**保留 rasterio 依赖**，现有 rasterio 调用继续正常工作。实现：

- 新增代码和核心模块（推理引擎、金字塔等）通过 skill 接口完成影像操作
- UI 层已有的 rasterio 调用（smart_canvas、gis_canvas）保持现状，可**渐进式迁移**
- 可被 AI 编程工具（Claude Code 等）**直接调用和理解**
- 与现有 `skills/` 目录下的其他 skill 保持一致的组织风格

### 4.2 组织结构

```
skills/
├── skill_raster_io.py          # 【新增】核心栅格 I/O 技能（本方案重点）
├── skill_geodata_utils.py      # 【保留→逐步迁移】格式转换（bands_to_rgb 迁入新 skill）
├── skill_image_processing.py   # 【保留】伪彩色/拉伸等 QImage 层操作（不涉及 GDAL）
├── skill_sample_analysis.py    # 【保留】样本质检分析（cv2 层，不变）
└── __init__.py
```

### 4.3 `skill_raster_io.py` 内部结构

```python
"""
---
name: skill_raster_io
description: >
  遥感栅格影像统一读写技能。内部仅依赖 GDAL（osgeo）和 cv2，不引入 rasterio。
  提供影像打开、分块读取、创建写入、元数据操作、金字塔管理、
  波段组合显示等全套接口。供新增代码和核心模块统一调用。
---
"""

# ===== 类定义 =====
class RasterHandle:
    """只读栅格句柄（上下文管理器）"""
    # 属性: width, height, band_count, projection, geo_transform, overviews, dataset

class RasterWriter:
    """栅格写入器（上下文管理器）"""
    # 方法: write_band(), write_block(), flush(), close()

# ===== 核心函数 =====
def open_raster(path, mode='r') -> RasterHandle           # 统一打开
def read_block(handle, x, y, w, h, ...) -> np.ndarray      # 分块读取
def create_raster(path, w, h, ...) -> RasterWriter          # 创建输出
def write_block(writer, data, x, y, band=1) -> None         # 写入块
def get_raster_info(path) -> dict                           # 快速摘要
def copy_geo_metadata(src, dst) -> bool                     # 元数据复制
def bands_to_rgb(data, indices, layout) -> np.ndarray       # 波段→RGB
def sample_band_stats(path, band, size) -> dict             # 采样统计
def build_pyramids(path, levels, resampling, cb) -> bool    # 金字塔
def check_has_pyramids(path) -> bool                        # 检查金字塔
```

### 4.4 各 Skill 职责边界

| Skill | 职责 | 依赖 | 不负责 |
|---|---|---|---|
| **skill_raster_io** | 所有栅格文件的打开/读/写/元数据/金字塔 | `gdal`, `numpy`, `cv2` | GUI 渲染、QImage 转换 |
| **skill_geodata_utils** | ⚠️ 逐步废弃，`bands_to_rgb` 迁入 raster_io | `numpy` | 独立 I/O |
| **skill_image_processing** | QImage 级伪彩色、线性拉伸（缩略图用） | `PySide6.QImage` | 栅格文件 I/O |
| **skill_sample_analysis** | 样本质检（文件检查/统计/噪点） | `cv2`, `numpy` | 地理信息处理 |
| *(项目层保留)* **rasterio** | UI 画布（smart_canvas/gis_canvas）中的影像显示与元数据读取 | `rasterio` | 不纳入 skill，保持现有调用 |

### 4.5 调用方式与对接

**对接现有代码的改造路径：**

| 现有调用者 | 当前方式 | 改造后 | 迁移优先级 |
|---|---|---|---|
| `core/inference_engine.py` | 直接调 `gdal.Open` + `ReadAsArray` | `from skills.skill_raster_io import open_raster, read_block, create_raster, write_block` | **高** - GDAL 侧，直接迁移 |
| `utils/pyramid_builder.py` | 直接调 `gdal.Open` + `BuildOverviews` | `from skills.skill_raster_io import open_raster, build_pyramids` | **高** - GDAL 侧，直接迁移 |
| `ui/inference_panel.py` | 混用 rasterio + gdal | GDAL 部分迁移至 skill；rasterio 导出部分**保留不动** | **中** - 仅迁移 GDAL 调用 |
| `ui/widgets/smart_canvas.py` | 直接调 `rasterio.open` + `src.read` | **暂不迁移**，保留 rasterio（LOD/金字塔显示已稳定） | **低** - 可选，渐进式 |
| `ui/widgets/gis_canvas.py` | `rasterio.open` 读 profile | **暂不迁移**，保留 rasterio | **低** - 可选，渐进式 |

### 4.6 依赖策略

| 项目 | 说明 |
|---|---|
| **保留 `rasterio`** | 项目 `requirements.txt` 中继续保留 `rasterio>=1.3.0`，UI 画布层继续使用 |
| **保留 `gdal (osgeo)`** | 作为 skill 内部的栅格 I/O 后端 |
| **保留 `cv2`** | 用于非地理格式图像读写（PNG/JPG 等）和图像处理 |
| **skill 内部不引入 rasterio** | `skill_raster_io.py` 仅 import `gdal` 和 `cv2`，确保 skill 可在无 rasterio 环境下独立运行 |
| **`requirements.txt` 不变** | 无需修改现有依赖配置 |

### 4.7 实施优先级建议

| 阶段 | 内容 | 影响范围 |
|---|---|---|
| **Phase 1** | 创建 `skill_raster_io.py`，实现 `open_raster` / `read_block` / `get_raster_info` | 新文件，无破坏 |
| **Phase 2** | 实现 `create_raster` / `write_block` / `copy_geo_metadata` / `bands_to_rgb` | 新文件，无破坏 |
| **Phase 3** | 改造 `inference_engine.py`（GDAL 调用），替换为新接口 | 核心推理模块 |
| **Phase 4** | 改造 `pyramid_builder.py`（GDAL 调用），废弃 `skill_geodata_utils.py` | 工具模块 |
| **Phase 5** | 改造 `inference_panel.py` 中的 GDAL 调用部分（rasterio 部分保留） | 导出模块 |
| **Phase 6** | *（可选）* 渐进式迁移 `smart_canvas.py` / `gis_canvas.py` 中的 rasterio 调用 | UI 显示模块，不强制 |

---

> [!IMPORTANT]
> 本文档为**分析与设计方案**，不包含任何代码实现。所有接口签名为设计稿，待确认后进入实施阶段。
