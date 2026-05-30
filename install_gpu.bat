@echo off
REM ============================================================
REM RS-Seg-GUI GPU 加速安装脚本 (Windows) —— 可选
REM ------------------------------------------------------------
REM 在已创建的训练 conda 环境 (默认名 mmseg) 中，按指定 CUDA
REM 版本重装 GPU 版 PyTorch 与匹配的 MMCV。
REM
REM 用法：
REM   install_gpu.bat [CUDA_TAG] [TORCH_TAG] [ENV_NAME]
REM
REM 参数 (均可省略，使用默认值)：
REM   CUDA_TAG   CUDA 版本标记，如 cu118 / cu121   (默认 cu118)
REM   TORCH_TAG  MMCV 索引用的 torch 标记，如 torch2.1 (默认 torch2.1)
REM   ENV_NAME   目标 conda 环境名               (默认 mmseg)
REM
REM 示例：
REM   install_gpu.bat                 (CUDA 11.8 + torch2.1 + mmseg)
REM   install_gpu.bat cu121 torch2.1  (CUDA 12.1)
REM
REM 前置条件：
REM   - 已通过 environment_train.yml 创建训练环境
REM   - 已安装与目标 CUDA 版本兼容的 NVIDIA 驱动
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---------- 解析参数 ----------
set "CUDA_TAG=%~1"
if "%CUDA_TAG%"=="" set "CUDA_TAG=cu118"

set "TORCH_TAG=%~2"
if "%TORCH_TAG%"=="" set "TORCH_TAG=torch2.1"

set "ENV_NAME=%~3"
if "%ENV_NAME%"=="" set "ENV_NAME=mmseg"

echo.
echo ============================================================
echo  RS-Seg-GUI GPU 加速安装 (Windows)
echo   CUDA 标记 : %CUDA_TAG%
echo   Torch 标记: %TORCH_TAG%
echo   目标环境  : %ENV_NAME%
echo ============================================================
echo.

REM ---------- 检测 conda ----------
where conda >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 conda，无法定位训练环境。
    echo        请先安装 conda 并创建环境：conda env create -f environment_train.yml
    pause
    exit /b 1
)

REM ---------- 安装 GPU 版 PyTorch ----------
echo [1/2] 正在安装 GPU 版 PyTorch (%CUDA_TAG%) ...
call conda run -n %ENV_NAME% pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [错误] PyTorch 安装失败，请检查 CUDA 标记是否正确、环境是否存在。
    pause
    exit /b 1
)
echo [完成] GPU 版 PyTorch 安装成功。
echo.

REM ---------- 安装匹配的 MMCV ----------
echo [2/2] 正在安装匹配的 MMCV (%CUDA_TAG%/%TORCH_TAG%) ...
call conda run -n %ENV_NAME% pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/%CUDA_TAG%/%TORCH_TAG%/index.html
if errorlevel 1 (
    echo [错误] MMCV 安装失败，请确认 CUDA/torch 标记组合在 OpenMMLab 源中存在。
    pause
    exit /b 1
)
echo [完成] MMCV 安装成功。

echo.
echo ============================================================
echo  GPU 加速安装结束。
echo  可在 GUI 的"环境配置"面板验证：CUDA 应显示为 Available。
echo ============================================================
echo.
pause
endlocal
