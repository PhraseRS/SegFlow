# RS-Seg-GUI

面向遥感影像语义分割的图形化工作台。提供数据集管理、样本分析、配置生成、模型训练与大图推理的一站式可视化操作，底层对接 [OpenMMLab / MMSegmentation](https://github.com/open-mmlab/mmsegmentation) 框架。

---

## ✨ 主要特性

- **数据集管理**：VOC 结构数据集导入、样本浏览、缩略图懒加载、数据集重划分
- **样本分析**：类别分布统计、覆盖度分析、健康检查
- **可视化画布**：基于 `rasterio` 的 GeoTIFF 大图分级加载（金字塔 / LOD）、多波段显示、伪彩色掩码叠加
- **训练配置**：图形化超参数配置、配置顾问（Advisor）智能推荐、一键生成 MMSeg 配置
- **模型训练**：通过独立 conda 环境隔离执行训练，实时解析日志、绘制损失/指标曲线、实时预览预测
- **大图推理**：基于 GDAL 的超大遥感影像分块滑窗推理，进度经 Qt Signal 实时反馈到进度条

---

## 🧱 双层环境设计（重要）

> RS-Seg-GUI 的依赖刻意分为**两个相互独立的环境**，请务必理解这一点再安装。

| 层次 | 作用 | 安装方式 | 是否必须 |
|------|------|---------|---------|
| **Layer A：GUI 宿主环境** | 运行界面本体（数据管理 / 可视化 / 配置生成） | `pip install -r requirements.txt` | 必须 |
| **Layer B：训练/推理环境** | PyTorch + MMSegmentation 全家桶，执行训练与真实推理 | 独立 conda 环境 (`environment_train.yml`) | 训练/真实推理时必须 |

两层通过 **子进程隔离**调用：GUI 不会把训练框架强加到自身环境，你只需在 GUI 的「环境配置」面板中**选择已配置好的 conda 环境**，即可用于训练与推理。

详细的依赖分层与优化分析见 [`docs/ENVIRONMENT_REQUIREMENTS.md`](docs/ENVIRONMENT_REQUIREMENTS.md)。

---

## 🚀 快速安装

### 方式一：一键安装脚本（推荐）

**Windows：**
```bat
install.bat
```

**Linux / macOS：**
```bash
chmod +x install.sh
./install.sh
```

脚本会自动安装 GUI 宿主依赖，创建 conda 训练环境 `mmseg`，并在其中安装 GPU 版 PyTorch + MMCV + MMSegmentation。可通过参数指定 CUDA / torch 版本标记（默认 `cu118` / `torch2.1`）：

```bat
REM Windows，指定 CUDA 12.1
install.bat cu121 torch2.1
```
```bash
# Linux / macOS，指定 CUDA 12.1
./install.sh cu121 torch2.1
```

> ⚠️ 训练/推理环境为 **GPU 环境**，需预先安装与目标 CUDA 版本兼容的 NVIDIA 驱动。

### 方式二：手动安装

```bash
# Layer A：GUI 宿主环境（必须）
pip install -r requirements.txt

# Layer B：训练/推理 GPU 环境（训练/真实推理时）
conda env create -f environment_train.yml
conda activate mmseg
# 按本机 CUDA 版本安装 GPU 版 PyTorch（示例 CUDA 11.8）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
# 安装匹配的 MMCV
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html
# 安装 MMEngine 与 MMSegmentation
pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
```

> 请将 `cu118` / `torch2.1` 替换为与本机驱动匹配的版本。

---

## ▶️ 启动

```bash
python main.py
```

启动后即可使用全部数据管理与可视化功能。如需训练或真实模型推理，请先在「环境配置」面板中选择 `mmseg` 环境的 Python 解释器。

---

## ⚙️ 环境配置须知

安装与使用前，请留意以下要点：

| 要点 | 说明 |
|------|------|
| **双环境设计** | GUI 本体环境与训练环境是分开的。训练时无需把 PyTorch/MMSeg 装进 GUI 环境，只需在 GUI 中选择已配置好的 conda 环境即可。 |
| **conda 非强制** | GUI 本体不强依赖 conda（环境探测有容错，缺失时仅功能降级）。但训练/推理的 GPU 环境**必须**用 conda 管理。 |
| **需要 GPU** | 训练/推理环境为 GPU 环境，需安装与目标 CUDA 版本兼容的 NVIDIA 驱动。GUI 本体的数据管理与可视化功能不需要 GPU，可独立使用。 |
| **rasterio 强推荐** | 不安装仍可启动 GUI，但 `.tif` 大图将无法正确显示（回退到 OpenCV，缺少多波段/金字塔支持）。建议务必安装。 |
| **Python 版本** | 建议 **>= 3.9**，官方支持 3.9 / 3.10。MMSeg 生态对过新版本（3.12+）支持滞后，请谨慎。 |

---

## 📁 项目结构

```
RSegGUI/
├── main.py                      # 程序入口
├── requirements.txt             # Layer A：GUI 宿主环境依赖
├── environment_train.yml        # Layer B：训练/推理 conda 环境
├── install.bat / install.sh     # 一键安装脚本（GUI 依赖 + GPU 训练环境）
├── core/                        # 核心逻辑（推理引擎、配置、训练适配器等）
├── ui/                          # 界面与各类 Widget
├── config/                      # 配置编辑器与参数定义
├── skills/                      # 可复用工具（图像处理、地理数据转换等）
├── utils/                       # 环境管理、金字塔构建等工具
├── docs/                        # 设计与环境需求文档
└── example_data/                # 示例 VOC 数据集
```

---

## 📖 相关文档

- [环境需求分析](docs/ENVIRONMENT_REQUIREMENTS.md) —— 依赖分层、优化分析与发布方案
- [架构图](docs/ARCHITECTURE_DIAGRAM.md)
- [框架支持设计](docs/FRAMEWORK_SUPPORT_DESIGN.md)
- [快速参考](docs/QUICK_REFERENCE.md)
