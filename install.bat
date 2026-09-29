@echo off
chcp 65001
REM ============================================================
REM RS-Seg-GUI 一键安装脚本 (Windows)
REM ------------------------------------------------------------
REM 该脚本会：
REM   1) 安装 GUI 宿主环境依赖 (requirements.txt)
REM   2) 通过 conda 创建训练/推理环境 (environment_train.yml)
REM   3) 在该环境中安装 GPU 版 PyTorch + MMCV + MMSegmentation
REM
REM 用法：
REM   install.bat [CUDA_TAG] [TORCH_TAG]
REM
REM 参数 (均可省略，使用默认值)：
REM   CUDA_TAG   CUDA 版本标记，如 cu118 / cu121     (默认 cu118)
REM   TORCH_TAG  MMCV 索引用的 torch 标记，如 torch2.1 (默认 torch2.1)
REM
REM 前置条件：
REM   - 已安装 conda (Miniconda / Anaconda) 并在 PATH 中 (系统 Python 将由脚本自动部署)
REM   - 已安装与目标 CUDA 版本兼容的 NVIDIA 驱动 (仅限选用 GPU 版本时需要)
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
echo SegFlow-GUI 安装程序 (Windows)
echo CUDA 标记 : %CUDA_TAG%
echo Torch 标记: %TORCH_TAG%
echo ============================================================
echo.



REM ---------- 环境检测 ----------
echo 正在检测基础环境...

echo [提示] 强烈建议您在 Anaconda Prompt 终端下运行此脚本！
echo        若直接双击或者在普通 CMD 窗口执行，可能导致后续 Conda 初始化和激活时报告错误。

REM 1. 检查目录是否包含中文或特殊非英文字符
echo "%~dp0" | findstr /R /C:"[^\x00-\x7F]" >nul
if not errorlevel 1 (
    echo.
    echo [警告] 脚本所在路径 "%~dp0" 包含中文字符或特殊符号！
    echo 这极有可能导致后续 Conda 或 pip 安装环境失败。
    echo 强烈建议将整个项目文件夹移动到全英文字符路径后再重试。
    echo ------------------------------------------------------------
    pause
)

REM 2. 检查 conda
where conda >nul 2>nul
if errorlevel 1 (  
    echo.
    echo [错误] 未检测到 conda, 无法创建运行部署环境。
    echo 请安装 Miniconda 或 Anaconda 后重试运行本脚本。
    pause
    exit /b 1
)

REM 3. 检查 nvidia-smi 驱动，如果非 cpu 参数
if not "%CUDA_TAG%"=="cpu" (
    where nvidia-smi >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [警告] 未检测到 'nvidia-smi' 命令，当前指定需要 GPU ^(%CUDA_TAG%^)！
        echo 请确认您的电脑拥有 NVIDIA 显卡并且已正确安装驱动程序。
        echo 若设备本身不支持 GPU，建议中断并在终端提供参数重试，例如：install.bat cpu
        echo ------------------------------------------------------------
        choice /c YN /m "是否继续尝试强制安装?"
        if errorlevel 2 exit /b 1
    )
)
echo 环境检测完毕，即将开始安装流程。
echo.

REM ---------- 步骤 1: 创建训练/推理 conda 环境 ----------
echo [1/2] 正在创建训练/推理 conda 环境 (environment_train.yml) ...
echo 正在安装环境，请耐心等待...
call conda env create -f environment_train.yml
if errorlevel 1 (
echo.
echo [警告] 环境创建提示异常（可能是 gui-mmseg 环境已存在）。
echo 将继续尝试在现有 gui-mmseg 环境中更新依赖...
)
echo.

REM ---------- 步骤 2: 安装 GPU 版深度学习框架 ----------
echo [2/2] 正在安装 GPU 版 PyTorch + MMCV + MMSegmentation (%CUDA_TAG%) ...
echo 正在安装学习框架，请耐心等待...

call conda activate gui-mmseg
if errorlevel 1 (
    echo.
    echo [严重错误] conda 环境激活失败！
    echo 这通常是因为您是在普通的系统 CMD 环境下双击运行的，导致 Conda 未被正确初始化。
    echo 请务必打开 "Anaconda Prompt" 或 "Miniconda Prompt"，通过 cd 命令进入本目录后再执行 install.bat。
    pause
    exit /b 1
)

echo - 正在安装 GUI 界面与辅助工具...
call python -m pip install --upgrade pip
if errorlevel 1 goto install_err
call python -m pip install -r requirements.txt
if errorlevel 1 goto install_err
call python -m pip install pyqtgraph openmim qtawesome
if errorlevel 1 goto install_err


echo - 正在安装 GPU 运算核心 (PyTorch)...
call python -m pip install --force-reinstall --no-cache-dir torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 goto install_err

echo - 正在安装 MMCV...
call python -m pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/%CUDA_TAG%/%TORCH_TAG%/index.html
if errorlevel 1 goto install_err

echo - 正在安装 MMSegmentation 算法库...
call python -m pip install mmdet mmengine mmsegmentation==1.2.2
if errorlevel 1 goto install_err

echo - 正在预装完美兼容包 (NumPy 1.x, OpenCV 4.9.x, ftfy, regex)...
call python -m pip install ftfy regex
call python -m pip install "numpy<2.0.0"
call python -m pip install "opencv-python<4.10.0"
if errorlevel 1 goto install_err


call conda deactivate
echo [完成] SegFlow 全栈环境 (gui-mmseg) 安装成功！
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
echo 以后启动GUI请在终端运行:
echo 1. conda activate gui-mmseg
echo 2. python main.py
echo 训练前请在"环境配置"面板中选择 gui-mmseg 环境的解释器。
echo 可在该面板验证:
echo CUDA 应显示为 Available。
echo ============================================================
echo.
pause
endlocal