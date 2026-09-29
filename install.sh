#!/usr/bin/env bash
# ============================================================
# SegFlow 一键安装脚本 (Linux / macOS)
# ------------------------------------------------------------
# 该脚本会：
#   1) 安装 GUI 宿主环境依赖 (requirements.txt)
#   2) 通过 conda 创建训练/推理环境 (environment_train.yml)
#   3) 在该环境中安装 GPU 版 PyTorch + MMCV + MMSegmentation
#
# 用法：
#   chmod +x install.sh
#   ./install.sh [CUDA_TAG] [TORCH_TAG]
#
# 参数 (均可省略，使用默认值)：
#   CUDA_TAG   CUDA 版本标记，如 cu118 / cu121      (默认 cu118)
#   TORCH_TAG  MMCV 索引用的 torch 标记，如 torch2.1 (默认 torch2.1)
#
# 前置条件：
#   - 已安装 Python >= 3.9
#   - 已安装 conda (Miniconda / Anaconda)
#   - 已安装与目标 CUDA 版本兼容的 NVIDIA 驱动
# ============================================================

set -e
cd "$(dirname "$0")"

# ---------- 解析参数 ----------
CUDA_TAG="${1:-cu118}"
TORCH_TAG="${2:-torch2.1}"

# 选择 python 命令（优先 python3）
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

echo
echo "============================================================"
echo " SegFlow 安装程序 (Linux / macOS)"
echo "  CUDA 标记 : ${CUDA_TAG}"
echo "  Torch 标记: ${TORCH_TAG}"
echo "============================================================"
echo

# ---------- 环境检测 ----------
echo "正在检测基础环境..."

# 1. 检查 Python 版本
if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>/dev/null; then
    echo "[错误] 当前 Python 解释器 ($PY) 版本低于 3.9，无法满足 SegFlow 运行需求。"
    exit 1
fi

# 2. 检查 nvidia-smi (如果选择了 CUDA )
if [ "$CUDA_TAG" != "cpu" ]; then
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        echo "[警告] 未检测到 'nvidia-smi' 命令，当前指定需要 GPU ($CUDA_TAG) 运算环境！"
        echo "       若您的设备不支持 GPU，推荐按 Ctrl+C 终止，并带上 cpu 参数重试，例如："
        echo "       ./install.sh cpu"
        echo "============================================================"
        read -p "按回车键继续强制安装..." </dev/tty || true
    fi
fi

echo "环境检测完毕，即将开始安装流程。"
echo

# ---------- 步骤 1: 安装 GUI 宿主环境 ----------
echo "[1/3] 正在安装 GUI 宿主环境依赖 (requirements.txt) ..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt
echo "[完成] GUI 宿主环境依赖安装成功。"
echo

# ---------- 步骤 2: 创建训练/推理 conda 环境 ----------
echo "[2/3] 正在创建训练/推理 conda 环境 (environment_train.yml) ..."
if ! command -v conda >/dev/null 2>&1; then
    echo "[错误] 未检测到 conda，无法创建 GPU 训练环境。"
    echo "       GUI 本体已可启动；如需训练/真实推理，"
    echo "       请安装 conda 后重新运行本脚本。"
    exit 1
fi
if conda env create -f environment_train.yml; then
    echo "[完成] 训练环境 'mmseg' 创建成功。"
else
    echo "[警告] 训练环境创建失败（可能已存在同名环境 mmseg）。"
    echo "       如需更新，可执行：conda env update -f environment_train.yml"
    echo "       将继续尝试在现有 mmseg 环境中安装 GPU 依赖..."
fi
echo

# ---------- 步骤 3: 安装 GPU 版深度学习框架 ----------
echo "[3/3] 正在安装 GPU 版 PyTorch + MMCV + MMSegmentation (${CUDA_TAG}) ..."
conda run -n mmseg pip install torch torchvision \
    --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"
conda run -n mmseg pip install mmcv==2.1.0 \
    -f "https://download.openmmlab.com/mmcv/dist/${CUDA_TAG}/${TORCH_TAG}/index.html"
conda run -n mmseg pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
echo "[完成] GPU 训练/推理环境 'mmseg' 安装成功。"

echo
echo "============================================================"
echo " 安装流程结束。"
echo " 启动 GUI： $PY main.py"
echo " 训练前请在\"环境配置\"面板中选择 mmseg 环境的解释器。"
echo " 可在该面板验证：CUDA 应显示为 Available。"
echo "============================================================"
echo
