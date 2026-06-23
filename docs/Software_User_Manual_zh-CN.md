<p align="center">
  <a href="Software_User_Manual.md">English</a> | <strong>简体中文</strong>
</p>

# SegFlow 遥感影像分割系统用户手册

## 1 软件介绍

### 1.1 软件概述

SegFlow 是一个面向遥感影像语义分割的图形化工作平台，提供数据集管理、样本分析、配置生成、模型训练、模型评估和大图推理的一站式可视化操作，后端集成 OpenMMLab/MMSegmentation 框架。

### 1.2 主要核心功能

**数据集管理：** 导入 VOC 结构数据集、浏览样本、延迟加载缩略图和重新划分数据集。

**样本分析：** 类别分布统计、覆盖率分析和数据集健康检查。

**可视化画布：** 基于 Rasterio 对大型 GeoTIFF 进行金字塔/LOD 分层加载、多波段显示和伪彩色掩膜叠加。

**训练配置：** 图形化编辑训练参数、使用 ConfigAdvisor 获取参数建议，并一键生成 MMSeg 配置。

**模型训练：** 在隔离的 Conda 环境中执行训练，实时解析日志、绘制损失和指标曲线，并显示预测预览。

**大图推理：** 基于 GDAL 对超大型遥感影像执行分块或滑窗推理，并通过 Qt 信号实时反馈进度。

### 1.3 目标用户

遥感影像处理人员、深度学习模型训练人员、GIS 分析人员及相关开发者。

## 2 安装与启动

### 2.1 系统和硬件要求

**操作系统：** Windows、Linux 或 macOS。

**推荐硬件：** NVIDIA 独立显卡，建议 RTX 3060 或更高型号，显存不少于 6 GB。

**前置软件：** 建议预先安装 Miniconda 或 Anaconda，并将 Conda 配置到系统环境变量。

详细要求请参阅[运行环境要求](ENVIRONMENT_REQUIREMENTS_zh-CN.md)。

### 2.2 环境安装

**方法一：一键安装脚本（推荐）**

**Windows：**

```bat
install.bat
```

**Linux / macOS：**

```bash
chmod +x install.sh
./install.sh
```

<img src="picture/image1.png" style="width:2in;height:0.45833in" alt="运行安装脚本" />

等待安装完成后，脚本会安装 GUI 主环境依赖、创建 `gui-mmseg` Conda 训练环境，并在该环境中安装 GPU 版本的 PyTorch、MMCV 和 MMSegmentation。

<img src="picture/image2.png" style="width:5.76667in;height:0.98333in" alt="安装过程" />

训练/推理环境需要与所选 CUDA 版本兼容的 NVIDIA 驱动。

**方法二：手动安装**

```bash
# A 层：GUI 主环境
pip install -r requirements.txt

# B 层：训练/推理环境
conda env create -f environment_train.yml
conda activate gui-mmseg

# 安装与本机 CUDA 匹配的 PyTorch（以下以 CUDA 11.8 为例）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装匹配的 MMCV
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html

# 安装 MMEngine 和 MMSegmentation
pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
```

请根据本机驱动和 PyTorch 版本替换 `cu118` 与 `torch2.1`。

**启动软件：**

```bash
conda activate gui-mmseg
python main.py
```

启动后即可使用数据管理和可视化功能。进行训练或真实模型推理前，请先在“环境配置”面板中选择 `gui-mmseg` 环境的 Python 解释器。

<img src="picture/image3.png" style="width:5.75417in;height:3.825in" alt="SegFlow 主界面" />

## 3 核心功能操作

常用菜单功能如下：

| 菜单 | 功能 |
|---|---|
| File | 打开、保存、退出 |
| View | 放大、缩小、适应窗口、详情视图、网格视图 |
| Tools | 训练、推理 |
| Help | 关于软件 |

### 3.1 数据准备

在“数据概览”页面左侧点击“加载数据集”，选择数据集根目录。软件会自动检测目录结构；检测成功后加载数据，并在左侧显示训练集、验证集和测试集的样本数量。

<img src="picture/image4.png" style="width:5.75417in;height:3.825in" alt="加载数据集" />

软件使用标准 PASCAL VOC 数据集结构，请确保目录名称和结构正确：

```text
Data/                         # 数据集根目录
├── ImageSets/
│   └── Segmentation/
│       ├── train.txt
│       ├── val.txt
│       └── test.txt
├── JPEGImages/              # 原始影像
└── SegmentationClass/       # PNG 标签
```

标签应为单通道 PNG 掩膜，像素值表示类别 ID。例如，`0` 表示背景，`1` 表示目标类别，`255` 可作为忽略标签。原图与标签文件名必须一一对应。

<img src="picture/image5.png" style="width:5.76458in;height:1.75in" alt="VOC 数据集目录" />

加载完成后，可点击右上角“重新划分”按钮，自定义训练集、验证集和测试集比例。

<img src="picture/image6.png" style="width:5.75417in;height:3.825in" alt="重新划分数据集" />

### 3.2 模型配置与训练

在“任务配置”页面选择训练框架、模型算法、主干网络、训练权重及相关设置。

<img src="picture/image7.png" style="width:5.19792in;height:3.09375in" alt="模型配置" />

软件会根据数据集统计信息推荐训练超参数。可按训练需求继续调整；请确保配置中的图像和标签后缀与数据集文件一致。

<img src="picture/image8.png" style="width:4.83333in;height:3.5in" alt="训练参数" />

软件支持水平翻转、光度畸变、随机旋转和多尺度增强等策略，ConfigAdvisor 也会推荐适合当前数据集的增强配置。

<img src="picture/image9.png" style="width:4.83333in;height:2.89583in" alt="数据增强" />

高级参数区域面向需要修改底层 MMSeg 配置的用户。

在“环境就绪”区域选择训练环境的 Python 解释器，刷新 Conda 环境并重新检测 `torch`、`mmcv`、`mmseg` 等包。环境检查通过后才能开始训练。

<img src="picture/image10.png" style="width:4.875in;height:2.89583in" alt="环境检查" />

完成模型选择和参数配置后，点击“运行”；确认训练配置后，点击“开始训练”。软件会生成训练配置文件并启动训练。

<img src="picture/image11.png" style="width:5.76806in;height:2.74097in" alt="开始训练" />

训练成功启动后，“实时训练中心”会显示 loss、mIoU 和 mAcc 等指标曲线以及验证指标变化。左下角实时显示训练进度。

日志区域会输出配置生成信息、工作目录、当前迭代次数、损失、学习率、验证指标和错误信息。

训练开始后，软件会在数据集目录下创建 `work_dirs` 文件夹，并根据所选主干网络和训练迭代次数自动生成输出文件。

<img src="picture/image12.png" style="width:5.75417in;height:3.825in" alt="实时训练中心" />

训练过程中可随时点击“停止”。软件会向训练进程发送终止请求，已保存的模型文件不会被自动删除。

训练结束后，点击“导出”可将生成的 `train_config.py` 保存到指定位置。点击“新训练模型 → 发送到推理分析”，软件会自动切换至推理页面并填写配置文件和权重文件。

<img src="picture/image13.png" style="width:5.76319in;height:1.98472in" alt="导出训练结果" />

### 3.3 模型推理与结果导出

#### 3.3.1 加载模型

在推理页面的模型加载区域载入训练完成的模型。目前支持两种方式：

**方法一：从已训练模型库选择。**

1. 加载数据集后，软件扫描 `work_dirs`。
2. 从“已训练模型库”中选择历史训练模型。
3. 软件自动填写配置文件和权重文件。

**方法二：手动指定。**

1. 选择 MMSeg 配置文件（`.py`）。
2. 选择模型权重（`.pth` 或 `.pt`）。
3. 选择计算设备：Auto、CUDA:0 或 CPU。
4. 点击“加载模型”。

<img src="picture/image14.png" style="width:4.38542in;height:2.67708in" alt="加载推理模型" />

#### 3.3.2 选择输入影像

选择需要推理的影像。支持 `png`、`jpg`、`jpeg`、`tif`、`tiff` 和 `bmp` 格式。选择后可将影像同步至 GIS 底图显示。

#### 3.3.3 推理设置

选择推理策略：

| 推理策略 | 适用场景 |
|---|---|
| 大图分块 | 超大型遥感影像，推荐用于大型 GeoTIFF |
| 整图缩放 | 小型影像或快速预览 |
| 滑窗推理 | 中等尺寸影像和标准推理 |

配置推理窗口大小、滑窗步长、大图分块重叠率、批次大小、多尺度翻转增强和置信度阈值等参数。

设置完成后点击“运行推理”。按钮下方会显示推理进度；可随时点击“取消”，但取消后可能需要手动检查生成的中间文件。

<img src="picture/image15.png" style="width:5.76111in;height:2.49444in" alt="推理设置" />

#### 3.3.4 结果显示与导出

推理结果会显示在结果区域，并可将预测图层叠加到 GIS 画布。用户可以调整类别颜色和预测结果透明度，并将颜色配置应用到预览。

- **预览图：** 用于快速查看，保存为 PNG。
- **类别掩膜：** 保存 0、1、2、3 等类别 ID。
- **GeoTIFF 结果：** 输入为 GeoTIFF 时可保留原始 CRS、仿射变换和分辨率。
- **可视化叠加图：** 使用类别颜色将预测掩膜叠加到原始影像。

<img src="picture/image16.png" style="width:5.75972in;height:3.09583in" alt="推理结果" />

## 4 常见问题

| 问题 | 可能原因 | 解决方法 |
|---|---|---|
| 数据集加载失败 | 目录结构不符合要求 | 检查 `JPEGImages`、`SegmentationClass` 和 `ImageSets` |
| 类别数量不正确 | 标签像素值与类别配置不一致 | 检查标签值和 `num_classes` |
| 环境检查失败 | 未安装 `torch`、`mmcv`、`mmseg`，或版本不匹配 | 重新检查 Conda 环境 |
| CUDA 不可用 | 驱动与 PyTorch CUDA 版本不匹配 | 安装相互兼容的版本 |
| 训练显存不足 | batch size 或 crop size 过大 | 减小批次大小或裁剪尺寸 |
| 推理结果错位 | 分块坐标或地理参考写出不正确 | 检查输出 GeoTIFF 的 transform |
| 不显示 mIoU | 验证集为空或日志解析失败 | 检查 `val.txt` 和日志格式 |

# 附录 1 SegFlow 运行环境要求

## 1.1 GUI 主环境依赖

### 1.1.1 必需依赖

| 包名 | 用途 | 主要引用位置 |
|---|---|---|
| PySide6 | GUI 组件、信号和线程 | 整个项目 |
| NumPy | 图像数组、掩膜计算和样本统计 | `smart_canvas`、`mask_renderer`、`inference_engine`、`skills/` |
| OpenCV | 图像读写、缩放和颜色空间转换 | `smart_canvas`、`mask_renderer`、`inference_engine` |
| Pillow | 大图打开及 PNG/JPEG 读取 | `inference_engine` |
| Matplotlib | 类别分布图 | `class_distribution_widget` |
| Jinja2 | 配置文件模板生成 | `core/logic_engine.py` |

### 1.1.2 推荐依赖

| 包名 | 用途 | 缺失后的影响 |
|---|---|---|
| Rasterio | GeoTIFF 多波段读取、图像金字塔和视口裁剪 | 大图画布无法正常读取 `.tif` |
| PyQtGraph | 实时训练曲线 | 无法显示实时 loss/mIoU/mAcc 图表 |
| QtAwesome | 操作按钮图标 | 使用文字或原生样式回退 |

### 1.1.3 Python 标准库

`os`、`sys`、`re`、`json`、`sqlite3`、`subprocess`、`multiprocessing`、`hashlib`、`math`、`csv`、`ast`、`copy`、`time`、`signal`、`datetime`、`pathlib`、`dataclasses`、`enum`、`typing`、`abc`、`collections`。

## 1.2 训练/推理环境依赖

### 1.2.1 核心依赖

| 包名 | 版本约束 | 用途 |
|---|---|---|
| PyTorch | 建议 `>=2.0` | 模型张量计算 |
| TorchVision | 与 PyTorch 匹配 | 视觉组件兼容 |
| MMEngine | `>=0.7.0` | OpenMMLab 训练引擎 |
| MMCV | `>=2.0.0` | 底层算子和模型组件 |
| MMSegmentation | `>=1.0.0,<2.0.0` | 语义分割框架 |
| CUDA | 与 PyTorch 匹配 | GPU 加速 |

### 1.2.2 大图推理扩展

| 包名 | 用途 | 缺失后的影响 |
|---|---|---|
| GDAL (`osgeo`) | 超大遥感影像分块读取和带地理参考的 GeoTIFF 写出 | 大图分块推理不可用 |

更完整的环境说明请参阅[运行环境要求](ENVIRONMENT_REQUIREMENTS_zh-CN.md)。
