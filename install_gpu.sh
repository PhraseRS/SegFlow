#!/usr/bin/env bash
# ============================================================
# RS-Seg-GUI GPU 加速安装脚本 (Linux / macOS) —— 可选
# ------------------------------------------------------------
# 在已创建的训练 conda 环境 (默认名 mmseg) 中，按指定 CUDA
# 版本重装 GPU 版 PyTorch 与匹配的 MMCV。
#
# 用法：
#   chmod +x install_gpu.sh
#   ./install_gpu.sh [CUDA_TAG] [TORCH_TAG] [ENV_NAME]
#
# 参数 (均可省略，使用默认值)：
#   CUDA_TAG   CUDA 版本标记，如 cu118 / cu121      (默认 cu118)
#   TORCH_TAG  MMCV 索引用的 torch 标记，如 torch2.1 (默认 torch2.1)
#   ENV_NAME   目标 conda 环境名                    (默认 mmseg)
#
# 示例：
#   ./install_gpu.sh                  # CUDA 11.8 + torch2.1 + mmseg
#   ./install_gpu.sh cu121 torch2.1   # CUDA 12.1
#
# 前置条件：
#   - 已通过 environment_train.yml 创建训练环境
#   - 已安装与目标 CUDA 版本兼容的 NVIDIA 驱动
# ============================================================

set -e
cd "$(dirname "$0")"

# ---------- 解析参数 ----------
CUDA_TAG="${1:-cu118}"
TORCH_TAG="${2:-torch2.1}"
ENV_NAME="${3:-mmseg}"

echo
echo "============================================================"
echo " RS-Seg-GUI GPU 加速安装 (Linux / macOS)"
echo "  CUDA 标记 : ${CUDA_TAG}"
echo "  Torch 标记: ${TORCH_TAG}"
echo "  目标环境  : ${ENV_NAME}"
echo "============================================================"
echo

# ---------- 检测 conda ----------
if ! command -v conda >/dev/null 2>&1; then
    echo "[错误] 未检测到 conda，无法定位训练环境。"
    echo "       请先安装 conda 并创建环境：conda env create -f environment_train.yml"
    exit 1
fi

# ---------- 安装 GPU 版 PyTorch ----------
echo "[1/2] 正在安装 GPU 版 PyTorch (${CUDA_TAG}) ..."
conda run -n "${ENV_NAME}" pip install torch torchvision \
    --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"
echo "[完成] GPU 版 PyTorch 安装成功。"
echo

# ---------- 安装匹配的 MMCV ----------
echo "[2/2] 正在安装匹配的 MMCV (${CUDA_TAG}/${TORCH_TAG}) ..."
conda run -n "${ENV_NAME}" pip install mmcv==2.1.0 \
    -f "https://download.openmmlab.com/mmcv/dist/${CUDA_TAG}/${TORCH_TAG}/index.html"
echo "[完成] MMCV 安装成功。"

echo
echo "============================================================"
echo " GPU 加速安装结束。"
echo " 可在 GUI 的\"环境配置\"面板验证：CUDA 应显示为 Available。"
echo "============================================================"
echo
