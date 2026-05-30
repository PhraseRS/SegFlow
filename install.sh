#!/usr/bin/env bash
# ============================================================
# RS-Seg-GUI 一键安装脚本 (Linux / macOS)
# ------------------------------------------------------------
# 该脚本会：
#   1) 安装 GUI 宿主环境依赖 (requirements.txt)
#   2) 通过 conda 创建训练/推理环境 (environment_train.yml)
#
# 前置条件：
#   - 已安装 Python >= 3.9
#   - 已安装 conda (Miniconda / Anaconda)
#
# 用法：
#   chmod +x install.sh
#   ./install.sh
# ============================================================

set -e
cd "$(dirname "$0")"

# 选择 python 命令（优先 python3）
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

echo
echo "============================================================"
echo " RS-Seg-GUI 安装程序 (Linux / macOS)"
echo "============================================================"
echo

# ---------- 步骤 1: 安装 GUI 宿主环境 ----------
echo "[1/2] 正在安装 GUI 宿主环境依赖 (requirements.txt) ..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt
echo "[完成] GUI 宿主环境依赖安装成功。"
echo

# ---------- 步骤 2: 创建训练/推理 conda 环境 ----------
echo "[2/2] 正在创建训练/推理 conda 环境 (environment_train.yml) ..."
if command -v conda >/dev/null 2>&1; then
    if conda env create -f environment_train.yml; then
        echo "[完成] 训练/推理环境 'mmseg' 创建成功。"
    else
        echo "[警告] 训练环境创建失败（可能已存在同名环境 mmseg）。"
        echo "       如需更新，可执行：conda env update -f environment_train.yml"
    fi
else
    echo "[警告] 未检测到 conda，已跳过训练环境创建。"
    echo "       GUI 本体可正常启动；如需训练/真实推理，"
    echo "       请安装 conda 后手动执行："
    echo "           conda env create -f environment_train.yml"
fi

echo
echo "============================================================"
echo " 安装流程结束。"
echo " 启动 GUI： $PY main.py"
echo " 训练前请在\"环境配置\"面板中选择 mmseg 环境的解释器。"
echo "============================================================"
echo
