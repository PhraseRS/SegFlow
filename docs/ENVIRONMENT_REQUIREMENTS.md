# RS-Seg-GUI 运行环境需求分析

> 本文档对项目的最小运行环境进行全面分析，包括依赖包分层、可优化点识别以及面向开源发布的环境管理方案建议。

---

## 一、依赖分层架构总览

RS-Seg-GUI 的依赖体系天然存在**两个独立层次**，设计上已有一定的解耦意识（体现在 `try/except ImportError` 的可选导入模式），但尚未形成清晰的文档化分层。

```
┌────────────────────────────────────────────────────────────┐
│                    Layer A：GUI 宿主环境                    │
│  (运行 RS-Seg-GUI 本体所需，必须在启动 Python 环境中安装)   │
│                                                            │
│  PySide6 · NumPy · OpenCV · Pillow · Matplotlib           │
│  Jinja2 · rasterio (可选/强推荐)                          │
└──────────────────────────┬─────────────────────────────────┘
                           │ 通过 subprocess 隔离调用
┌──────────────────────────▼─────────────────────────────────┐
│                 Layer B：训练/推理 conda 环境               │
│  (由用户在"环境配置"面板中自行选择，可与 Layer A 不同)      │
│                                                            │
│  PyTorch · MMCV · MMEngine · MMSegmentation               │
│  GDAL (osgeo) · CUDA Toolkit                              │
└────────────────────────────────────────────────────────────┘
```

---

## 二、Layer A：GUI 宿主环境依赖清单

### 2.1 硬性必须依赖（缺失则无法启动）

| 包名 | 用途 | 引用位置 |
|------|------|----------|
| `PySide6` | 整个 GUI 框架，所有 Widget/信号/线程 | 全项目 |
| `numpy` | 图像数组操作、掩码计算、样本统计 | `smart_canvas`, `mask_renderer`, `inference_engine`, `skills/` 等 |
| `opencv-python` (cv2) | 图像读写、缩放、颜色空间转换 | `smart_canvas`, `mask_renderer`, `inference_engine` |
| `Pillow` (PIL) | 大图打开（`Image.MAX_IMAGE_PIXELS`）、PNG/JPEG 读取 | `inference_engine` |
| `matplotlib` | 类别分布图、训练曲线绘制 | `class_distribution_widget`, `metrics_plot_widget` |
| `jinja2` | 配置文件模板生成 | `core/logic_engine.py` |

### 2.2 可选但强推荐依赖（缺失时功能降级）

| 包名 | 用途 | 缺失后的后果 |
|------|------|-------------|
| `rasterio` | GeoTIFF 多波段读取、图像金字塔（LOD）、视口裁剪 | 大图画布无法读取 `.tif`，回退到 OpenCV（单波段/无金字塔） |

### 2.3 标准库（无需安装，已随 Python 自带）

`os`, `sys`, `re`, `json`, `sqlite3`, `subprocess`, `multiprocessing`, `hashlib`, `math`, `csv`, `ast`, `copy`, `time`, `signal`, `datetime`, `pathlib`, `dataclasses`, `enum`, `typing`, `abc`, `collections`

---

## 三、Layer B：训练/推理专用环境依赖清单

> 此层由用户在"环境配置"面板中选择独立 conda 环境，**不要求与 GUI 宿主环境合并**。

### 3.1 训练功能核心依赖

| 包名 | 版本约束 | 用途 |
|------|---------|------|
| `torch` (PyTorch) | `>=2.0` 推荐 | 模型张量计算基础 |
| `mmengine` | `>=0.7.0` | OpenMMLab 统一训练引擎 |
| `mmcv` | `>=2.0.0` | 底层算子加速库 |
| `mmsegmentation` | `>=1.0.0, <2.0.0` | 语义分割框架本体 |
| `CUDA Toolkit` | 与 PyTorch 版本匹配 | GPU 加速（CPU 下可选） |

### 3.2 大图推理扩展依赖

| 包名 | 用途 | 缺失后的后果 |
|------|------|-------------|
| `gdal` (osgeo) | 超大遥感影像分块读取、GeoTIFF 写出（含地理参考信息） | 大图分块推理功能不可用 |

---

## 四、依赖优化分析

### 4.1 可立即优化项

#### ① `matplotlib` 的使用范围较窄，但无法移除
- **现状**：仅用于 `class_distribution_widget.py` 的类别饼图/柱图，以及 `metrics_plot_widget.py` 中原本预留的绘图区（当前实现已用 `QLabel` 占位，实际尚未用到 matplotlib）。  
- **建议**：`metrics_plot_widget.py` 中可将 matplotlib 改为 PySide6 原生 `QPainter` 绘制，减少一个重型依赖（matplotlib 安装包约 50 MB）。但 `class_distribution_widget` 的复杂图表仍需保留。

#### ② ~~`tqdm` 可用标准库替代~~（已实施）
- **现状**：原先在 `inference_engine.py` 的滑窗与分块循环中使用 `tqdm` 打印进度到 stdout。
- **已实施**：考虑到 GUI 应用的进度反馈应通过 Qt Signal 传递给 UI 而非打印到 stdout，已**彻底移除 tqdm**。推理进度现统一经由 `InferenceEngine._progress_callback` → worker 的 `progress` Signal → `QProgressBar` 链路反馈，与 Qt 架构保持一致。

#### ③ `rasterio` 与 `gdal` 的职责重叠
- **现状**：`smart_canvas.py` 使用 `rasterio` 读取展示，`inference_engine.py` 使用 `gdal (osgeo)` 进行分块推理写出。两者都面向 GeoTIFF，但分属不同层次。  
- **建议**：Layer A（GUI）统一使用 `rasterio`（Python 友好，无需编译），Layer B（推理子进程）中 `gdal` 保留以获得完整地理参考写出能力。保持现有分层，不必合并。

#### ④ `Pillow` 与 `OpenCV` 功能重叠
- **现状**：两者同时存在，`Pillow` 负责大图 crop（利用其懒加载特性），`OpenCV` 负责 BGR 格式操作与缩放。  
- **建议**：当前的分工合理，不建议移除任何一方，但应在文档中说明各自职责以防止未来混用。

### 4.2 潜在的隐性依赖（需注意）

| 隐性依赖 | 来源 | 风险 |
|---------|------|------|
| `sqlite3` | `core/dataset_metadata.py`，用于样本元数据缓存 | Python 标准库，通常已内置；但部分精简 Python 发行版可能缺失 |
| `conda` | `utils/mmseg_env_manager.py` 环境探测 | 如果用户使用 venv/pyenv 而非 conda，环境列表功能将降级（返回空列表），已有容错处理 |
| 系统字体 | `QFont` 在 `main.py` 中有 pointSize 检测 | Linux 无桌面环境时 Qt 可能无法初始化 |

---

## 五、最小启动环境规格汇总

### 5.1 Layer A 最小安装命令（GUI 宿主）

```bash
# Python 版本要求：>= 3.9（__pycache__ 中同时存在 cp39 和 cp313 字节码）
pip install PySide6 numpy opencv-python Pillow matplotlib jinja2 rasterio
```

### 5.2 Layer B 最小安装（训练/推理，建议独立 conda 环境）

```bash
# 1. 创建独立 conda 环境（Python 3.9 或 3.10）
conda create -n mmseg python=3.9 -y
conda activate mmseg

# 2. 安装 PyTorch（根据 CUDA 版本选择）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 3. 安装 OpenMMLab 组件
pip install mmengine
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html
pip install mmsegmentation

# 4. 安装 GDAL（大图推理扩展，可选）
conda install gdal -c conda-forge
```

---

## 六、面向开源项目的环境管理方案建议

### 6.1 推荐方案：双文件分层提供

鉴于本项目**两层依赖结构清晰、使用场景不同**，建议提供两个独立的依赖文件：

```
RSegGUI/
├── requirements.txt              # Layer A：GUI 宿主环境（pip 安装）
└── environment_train.yml         # Layer B：训练/推理环境（conda 安装）
```

**`requirements.txt`（建议内容）**：
```
PySide6>=6.5.0
numpy>=1.24.0
opencv-python>=4.8.0
Pillow>=10.0.0
matplotlib>=3.7.0
Jinja2>=3.1.0
rasterio>=1.3.0
```

**`environment_train.yml`（建议内容）**：
```yaml
name: mmseg
channels:
  - pytorch
  - conda-forge
  - defaults
dependencies:
  - python=3.9
  - gdal
  - pip:
    - torch>=2.0
    - mmengine>=0.7.0
    - mmcv>=2.0.0
    - mmsegmentation>=1.0.0,<2.0.0
```

### 6.2 README 中应明确说明的要点

| 要点 | 说明 |
|------|------|
| **双环境设计** | 明确告知用户：GUI 本体环境与训练环境是分开的，训练时只需在 GUI 中选择已配置好的 conda 环境 |
| **conda 非强制** | GUI 本体不强依赖 conda（已有容错），但训练环境推荐使用 conda 管理 |
| **CUDA 可选** | 无 GPU 环境下 GUI 的所有数据管理/可视化功能完全可用；推理和训练功能在 CPU 下可降速运行 |
| **rasterio 强推荐** | 不安装仍可启动，但 `.tif` 大图将无法正确显示；应在 README 中突出提示 |
| **Python 版本** | 建议 >= 3.9，项目中已有 3.9 和 3.13 的字节码记录，3.9 为推荐最低版本 |

### 6.3 发布方式建议（开源项目最佳实践）

```
优先级 1：源码 + requirements.txt + environment_train.yml
  ✅ 最轻量，用户自行配置环境
  ✅ 适合有 Python/ML 背景的开发者用户群体
  ✅ 无需维护打包构建流程

优先级 2：提供一键安装脚本（install.bat / install.sh）
  ✅ 降低使用门槛，自动执行 conda create + pip install
  ⚠️ 需要用户已安装 conda

优先级 3：PyInstaller 或 cx_Freeze 打包为可执行文件
  ⚠️ 不适合本项目：深度学习训练框架体积极大（>5GB），
     且需要用户自己配置 CUDA/conda 训练环境，
     打包意义有限，反而增加维护成本
```

**结论：对于本项目，"源码 + 分层 requirements + 安装脚本"是最适合开源发布的方式。**

---

## 七、Python 版本兼容性说明

| Python 版本 | 兼容状态 | 说明 |
|------------|---------|------|
| 3.8 | ⚠️ 存疑 | PySide6 6.5+ 已放弃 3.8 支持 |
| 3.9 | ✅ 推荐 | 项目 `__pycache__` 中有 cp39 字节码，验证过 |
| 3.10 | ✅ 支持 | 主流 MMSeg 安装指南使用 3.10 |
| 3.11 | ✅ 支持 | PySide6/PyTorch 均已支持 |
| 3.12/3.13 | ⚠️ 谨慎 | 项目中有 cp313 字节码，但 MMSeg 生态对新版本支持滞后 |

**建议锁定 Python 3.9 或 3.10 作为官方支持版本。**

---

*文档生成时间：基于代码静态分析，未运行实际安装测试。版本号约束为分析推断值，建议在实际测试后以真实兼容版本为准。*
