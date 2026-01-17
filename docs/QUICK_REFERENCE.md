# GIS 大图像加载 - 快速参考

## 🚀 快速开始

```python
from ui.widgets.gis_canvas import GISCanvasWidget

canvas = GISCanvasWidget()
canvas.on_set_base_image()  # 自动处理大图像
```

## 📊 加载策略决策树

```
文件大小 < 1GB?
├─ Yes → 有金字塔?
│         ├─ Yes → 读取金字塔 (0.5s) ⚡
│         └─ No  → Decimated Read (1-2s) ✓
└─ No  → 有金字塔?
          ├─ Yes → 读取金字塔 (0.5s) ⚡
          └─ No  → 询问用户
                   ├─ 生成金字塔 → 后台生成 → 读取金字塔 ⚡
                   └─ 不生成 → Decimated Read (慢) ⚠️
```

## 🔧 常用命令

### 预生成金字塔（推荐）
```bash
# 单个文件
gdaladdo -r bilinear image.tif 2 4 8 16 32

# 批量处理
for file in *.tif; do gdaladdo -r bilinear "$file" 2 4 8 16 32; done
```

### Python 生成金字塔
```python
import rasterio
from rasterio.enums import Resampling

with rasterio.open('image.tif', 'r+') as src:
    src.build_overviews([2, 4, 8, 16, 32], Resampling.bilinear)
```

## ⚙️ 配置参数

```python
# 在 ui/widgets/gis_canvas.py 中修改
class GeoUtils:
    SIZE_THRESHOLD_GB = 1.0   # 超大文件阈值
    TARGET_MAX_SIZE = 2048    # 预览图尺寸
```

## 📈 性能参考

| 尺寸 | 无优化 | Decimated | 金字塔 |
|------|--------|-----------|--------|
| 5k×5k | 3s | 1s | 0.4s |
| 10k×10k | OOM | 2s | 0.5s |
| 20k×20k | OOM | 8s | 0.5s |

## 💡 最佳实践

1. ✅ **预生成金字塔** - 一次生成，永久受益
2. ✅ **使用 COG 格式** - 内置优化
3. ✅ **SSD 存储** - 减少 IO 瓶颈
4. ❌ **避免同时加载多个超大图层**
5. ❌ **不要在循环中重复加载**

## 🐛 常见问题

### Q: 金字塔生成失败？
A: 检查文件写权限和磁盘空间

### Q: 加载仍然很慢？
A: 
- 确认金字塔已生成（检查 .ovr 文件）
- 使用 SSD
- 减小 TARGET_MAX_SIZE

### Q: 空间对齐不正确？
A: 确保代码中有 `item.setScale(1.0 / scale_factor)`

## 📝 代码示例

### 完整加载流程
```python
# 读取图像
data, profile, scale_factor = GeoUtils.read_image(
    path="large.tif",
    target_max_size=2048,
    parent_widget=self
)

# 转换为 Pixmap
pixmap = self._numpy_to_pixmap(data)

# 创建图层
item = QGraphicsPixmapItem(pixmap)
item.setPos(0, 0)

# 关键：应用缩放以匹配原始地理范围
if scale_factor < 1.0:
    item.setScale(1.0 / scale_factor)

self._scene.addItem(item)
```

### 批量生成金字塔
```python
from pathlib import Path
import rasterio
from rasterio.enums import Resampling

def batch_build_pyramids(directory):
    for tif_file in Path(directory).glob("*.tif"):
        print(f"处理: {tif_file.name}")
        try:
            with rasterio.open(str(tif_file), 'r+') as src:
                if len(src.overviews(1)) == 0:
                    src.build_overviews([2, 4, 8, 16, 32], Resampling.bilinear)
                    print(f"  ✅ 金字塔已生成")
                else:
                    print(f"  ⏭️ 已有金字塔，跳过")
        except Exception as e:
            print(f"  ❌ 失败: {e}")

# 使用
batch_build_pyramids("./data/images")
```

## 🔍 调试技巧

### 检查金字塔
```python
import rasterio

with rasterio.open('image.tif') as src:
    overviews = src.overviews(1)
    if overviews:
        print(f"金字塔层级: {overviews}")
    else:
        print("无金字塔")
```

### 查看文件信息
```bash
gdalinfo image.tif | grep -i overview
```

### 监控内存使用
```python
import psutil
import os

process = psutil.Process(os.getpid())
print(f"内存使用: {process.memory_info().rss / 1024**2:.1f} MB")
```

## 📚 相关文档

- 详细文档: `docs/GIS_LARGE_IMAGE_LOADING.md`
- 实现总结: `IMPLEMENTATION_SUMMARY.md`
- 源代码: `ui/widgets/gis_canvas.py`
