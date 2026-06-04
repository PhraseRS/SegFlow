@echo off
chcp 65001
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



REM ---------- 步骤 1: 创建训练/推理 conda 环境 ----------
echo [1/2] 正在创建训练/推理 conda 环境 (environment_train.yml) ...
echo 正在安装环境，请耐心等待...
where conda >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 conda，无法创建运行环境。
    echo        请安装 Miniconda 或 Anaconda 后重新运行本脚本。
    pause
    exit /b 1
)
call conda env create -f environment_train.yml
if errorlevel 1 (
    echo.
    echo [警告] 环境创建提示异常（可能是 mmseg 环境已存在）。
    echo        将继续尝试在现有 mmseg 环境中更新依赖...
)
echo.

REM ---------- 步骤 2: 安装 GPU 版深度学习框架 ----------
echo [2/2] 正在安装 GPU 版 PyTorch + MMCV + MMSegmentation (%CUDA_TAG%) ...
echo 正在安装学习框架，请耐心等待...

call conda activate mmseg


echo - 正在安装 GUI 界面与辅助工具...
call python -m pip install --upgrade pip
call python -m pip install -r requirements.txt
call python -m pip install pyqtgraph openmim qtawesome
if errorlevel 1 goto install_err


echo - 正在安装 GPU 运算核心 (PyTorch)...
call python -m pip install --force-reinstall --no-cache-dir torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 goto install_err

echo - 正在安装 MMCV...
call python -m pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/%CUDA_TAG%/%TORCH_TAG%/index.html
if errorlevel 1 goto install_err

echo - 正在安装 MMSegmentation 算法库...
call python -m pip install mmengine mmsegmentation==1.2.2
if errorlevel 1 goto install_err

echo - 正在预装完美兼容包 (NumPy 1.x, OpenCV 4.9.x, ftfy, regex)...
call python -m pip install ftfy regex
call python -m pip install "numpy<2.0.0"
call python -m pip install "opencv-python<4.10.0"
if errorlevel 1 goto install_err


call conda deactivate
echo [完成] RS-Seg-GUI 全栈环境 (mmseg) 安装成功！
goto finish

:install_err
echo [错误] 框架安装中途失败，请检查网络或报错信息。
call conda deactivate
pause
exit /b 1

:finish
echo.
echo ============================================================
echo 安装流程结束。
echo 以后启动GUI请在终端运行：
echo 1. conda activate mmseg
echo 2. python main.py
echo 训练前请在"环境配置"面板中选择 mmseg 环境的解释器。
echo 可在该面板验证：CUDA 应显示为 Available。
echo ============================================================
echo.
pause
endlocal
