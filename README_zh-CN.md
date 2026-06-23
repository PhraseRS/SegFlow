<p align="center">
  <img src="docs/picture/SegFlow.png" alt="SegFlow" width="800">
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-3776AB" alt="Python 3.9+"></a>
  <a href="https://doc.qt.io/qtforpython-6/"><img src="https://img.shields.io/badge/GUI-PySide6-41CD52" alt="PySide6"></a>
  <a href="https://docs.opencv.org/4.x/"><img src="https://img.shields.io/badge/OpenCV-4.8%2B-5C3EE8" alt="OpenCV"></a>
  <a href="https://rasterio.readthedocs.io/"><img src="https://img.shields.io/badge/Rasterio-1.3%2B-3A7D44" alt="Rasterio"></a>
  <a href="https://gdal.org/"><img src="https://img.shields.io/badge/GDAL-GeoTIFF-5CAE58" alt="GDAL"></a>
</p>

<p align="center">
  <a href="https://pytorch.org/docs/stable/"><img src="https://img.shields.io/badge/PyTorch-2.0%2B-EE4C2C" alt="PyTorch"></a>
  <a href="https://mmcv.readthedocs.io/"><img src="https://img.shields.io/badge/MMCV-2.0%2B-005BAC" alt="MMCV"></a>
  <a href="https://mmsegmentation.readthedocs.io/"><img src="https://img.shields.io/badge/MMSegmentation-1.x-005BAC" alt="MMSegmentation"></a>
  <a href="docs/ENVIRONMENT_REQUIREMENTS_zh-CN.md"><img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555555" alt="支持的平台"></a>
  <a href="https://github.com/xicheng79/segflow/releases"><img src="https://img.shields.io/badge/version-v0.1.0-E0B52D" alt="版本 v0.1.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3%2B-blue" alt="GPLv3+ 许可证"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>简体中文</strong>
</p>

# SegFlow

SegFlow 是一个用于遥感影像语义分割的图形化工作平台。项目基于 [OpenMMLab / MMSegmentation](https://github.com/open-mmlab/mmsegmentation)，集成了数据集管理、样本分析、配置生成、模型训练、模型评估、项目状态恢复和大图推理等可视化工作流程。

---

## 1.主要功能

- **数据集管理**：导入 VOC 格式数据集、浏览样本、延迟加载缩略图以及重新划分数据集
- **样本分析**：类别分布统计、覆盖率分析、元数据查看和数据集健康检查
- **可视化画布**：基于 `rasterio` 的 GeoTIFF 金字塔/LOD 加载、多波段显示和伪彩色掩膜叠加
- **训练配置**：可视化编辑超参数、Advisor 参数建议、预训练权重选择和一键生成 MMSeg 配置
- **模型训练**：通过指定的 Conda 环境运行训练，实时解析日志、绘制损失和指标曲线、保存检查点并预览实时预测结果
- **模型测试**：通过 MMSegmentation 测试运行器评估检查点，并显示总体指标和各类别指标
- **项目文件**：使用 `.rsgproj` 文件保存和恢复数据集、模型、推理配置、任务配置、界面状态及自定义模块路径
- **大图推理**：使用 GDAL 对大型遥感影像进行分块和滑窗推理，并通过 Qt 信号反馈进度

---

## 2.双层环境设计（重要）

> SegFlow 将依赖划分为两个相互独立的环境，请在安装前了解这一设计。

| 环境层 | 用途 | 安装方式 | 是否必需 |
|---|---|---|---|
| **A 层：GUI 主环境** | 运行桌面应用、数据集工具、可视化和配置生成 | `pip install -r requirements.txt` | 是 |
| **B 层：训练/运行环境** | 提供 PyTorch、MMEngine、MMCV 和 MMSegmentation，用于训练、测试和真实推理 | 独立 Conda 环境（`environment_train.yml`） | 训练、测试和真实推理时必需 |

两个环境通过相互隔离的子进程通信。GUI 主环境不需要安装训练框架；如需训练、测试或推理，请在软件的“环境配置”面板中选择已经配置好的运行环境 Python 解释器。

项目生成的 `custom_rs_dataset.py`、`custom_live_pred_hook.py` 等模块会记录在项目文件中，并在测试和推理时通过对应文件路径显式加载。

更详细的依赖分析请参阅 [`docs/ENVIRONMENT_REQUIREMENTS_zh-CN.md`](docs/ENVIRONMENT_REQUIREMENTS_zh-CN.md)。

---

## 3.快速安装

### 方式一：使用安装脚本（推荐）

**Windows：**

```bat
install.bat
```

**Linux / macOS：**

```bash
chmod +x install.sh
./install.sh
```

安装脚本会安装 GUI 依赖、根据 `environment_train.yml` 创建 Conda 训练/运行环境，并安装支持 GPU 的 PyTorch、MMCV 和 MMSegmentation。可以手动指定 CUDA 和 Torch 标签，默认值为 `cu118` / `torch2.1`：

```bat
REM Windows：使用 CUDA 12.1
install.bat cu121 torch2.1
```

```bash
# Linux / macOS：使用 CUDA 12.1
./install.sh cu121 torch2.1
```

> ⚠️ 训练/运行环境需要安装与所选 CUDA 构建版本兼容的 NVIDIA 驱动程序。

### 方式二：手动安装

```bash
# A 层：GUI 主环境
pip install -r requirements.txt

# B 层：训练/测试/推理环境
conda env create -f environment_train.yml
conda activate gui-mmseg

# 安装支持 GPU 的 PyTorch（以下以 CUDA 11.8 为例）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装匹配的 MMCV
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html

# 安装 MMEngine 和 MMSegmentation
pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
```

> 请根据本机环境和 PyTorch 构建版本，将 `cu118` / `torch2.1` 替换为相互兼容的版本。

---

## 4.启动

```bash
python main.py
```

启动后即可使用数据集管理和可视化功能。进行模型训练、测试或真实推理前，请在“环境配置”面板中选择并验证运行环境的 Python 解释器。

使用 **File > Save Project** 创建 `.rsgproj` 项目文件，使用 **File > Open Project** 恢复已保存的数据集、模型、自定义模块、任务设置、推理设置和最后打开的标签页。

---

## 5.文档

- [软件用户手册](docs/Software_User_Manual_zh-CN.md) — 安装、数据准备、模型训练、推理和常见问题说明
- [环境要求](docs/ENVIRONMENT_REQUIREMENTS_zh-CN.md) — 依赖分层、安装要求和兼容性说明

---

## 6.联系我们

- 如需报告错误或提出功能建议，请[创建 Issue](https://github.com/xicheng79/segflow/issues)。
- 如需讨论项目或咨询问题，请使用 [GitHub Discussions](https://github.com/xicheng79/segflow/discussions)。

---

## 许可证

SegFlow 使用 [GNU General Public License v3.0 或更高版本](LICENSE)。
