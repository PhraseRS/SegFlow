@echo off
REM ============================================================
REM RS-Seg-GUI 一键安装脚本 (Windows)
REM ------------------------------------------------------------
REM 该脚本会：
REM   1) 安装 GUI 宿主环境依赖 (requirements.txt)
REM   2) 通过 conda 创建训练/推理环境 (environment_train.yml)
REM   3) 在该环境中安装 GPU 版 PyTorch + MMCV + MMSegmentation
REM
REM 用法：
REM   install.bat [CUDA_TAG] [TORCH_TAG]
REM
REM 参数 (均可省略，使用默认值)：
REM   CUDA_TAG   CUDA 版本标记，如 cu118 / cu121     (默认 cu118)
REM   TORCH_TAG  MMCV 索引用的 torch 标记，如 torch2.1 (默认 torch2.1)
REM
REM 前置条件：
REM   - 已安装 Python >= 3.9 并在 PATH 中
REM   - 已安装 conda (Miniconda / Anaconda) 并在 PATH 中
REM   - 已安装与目标 CUDA 版本兼容的 NVIDIA 驱动
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---------- 解析参数 ----------
set "CUDA_TAG=%~1"
if "%CUDA_TAG%"=="" set "CUDA_TAG=cu118"
set "TORCH_TAG=%~2"
if "%TORCH_TAG%"=="" set "TORCH_TAG=torch2.1"

echo.
echo ============================================================
echo  RS-Seg-GUI 安装程序 (Windows)
echo   CUDA 标记 : %CUDA_TAG%
echo   Torch 标记: %TORCH_TAG%
echo ============================================================
echo.

REM ---------- 步骤 1: 安装 GUI 宿主环境 ----------
echo [1/3] 正在安装 GUI 宿主环境依赖 (requirements.txt) ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [错误] GUI 宿主环境依赖安装失败，请检查 Python / pip 配置。
    pause
    exit /b 1
)
echo [完成] GUI 宿主环境依赖安装成功。
echo.

REM ---------- 步骤 2: 创建训练/推理 conda 环境 ----------
echo [2/3] 正在创建训练/推理 conda 环境 (environment_train.yml) ...
where conda >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 conda，无法创建 GPU 训练环境。
    echo        GUI 本体已可启动；如需训练/真实推理，
    echo        请安装 conda 后重新运行本脚本。
    pause
    exit /b 1
)
conda env create -f environment_train.yml
if errorlevel 1 (
    echo.
    echo [警告] 训练环境创建失败（可能已存在同名环境 mmseg）。
    echo        如需更新，可执行：conda env update -f environment_train.yml
    echo        将继续尝试在现有 mmseg 环境中安装 GPU 依赖...
)
echo.

REM ---------- 步骤 3: 安装 GPU 版深度学习框架 ----------
echo [3/3] 正在安装 GPU 版 PyTorch + MMCV + MMSegmentation (%CUDA_TAG%) ...
call conda run -n mmseg pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [错误] GPU 版 PyTorch 安装失败，请检查 CUDA 标记是否正确。
    pause
    exit /b 1
)
call conda run -n mmseg pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/%CUDA_TAG%/%TORCH_TAG%/index.html
if errorlevel 1 (
    echo [错误] MMCV 安装失败，请确认 CUDA/torch 标记组合在 OpenMMLab 源中存在。
    pause
    exit /b 1
)
call conda run -n mmseg pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
if errorlevel 1 (
    echo [错误] MMEngine / MMSegmentation 安装失败。
    pause
    exit /b 1
)
echo [完成] GPU 训练/推理环境 'mmseg' 安装成功。

echo.
echo ============================================================
echo  安装流程结束。
echo  启动 GUI： python main.py
echo  训练前请在"环境配置"面板中选择 mmseg 环境的解释器。
echo  可在该面板验证：CUDA 应显示为 Available。
echo ============================================================
echo.
pause
endlocal
