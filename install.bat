@echo off
REM ============================================================
REM RS-Seg-GUI 一键安装脚本 (Windows)
REM ------------------------------------------------------------
REM 该脚本会：
REM   1) 安装 GUI 宿主环境依赖 (requirements.txt)
REM   2) 通过 conda 创建训练/推理环境 (environment_train.yml)
REM
REM 前置条件：
REM   - 已安装 Python >= 3.9 并在 PATH 中
REM   - 已安装 conda (Miniconda / Anaconda) 并在 PATH 中
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo  RS-Seg-GUI 安装程序 (Windows)
echo ============================================================
echo.

REM ---------- 步骤 1: 安装 GUI 宿主环境 ----------
echo [1/2] 正在安装 GUI 宿主环境依赖 (requirements.txt) ...
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
echo [2/2] 正在创建训练/推理 conda 环境 (environment_train.yml) ...
where conda >nul 2>nul
if errorlevel 1 (
    echo.
    echo [警告] 未检测到 conda，已跳过训练环境创建。
    echo        GUI 本体可正常启动；如需训练/真实推理，
    echo        请安装 conda 后手动执行：
    echo            conda env create -f environment_train.yml
) else (
    conda env create -f environment_train.yml
    if errorlevel 1 (
        echo.
        echo [警告] 训练环境创建失败（可能已存在同名环境 mmseg）。
        echo        如需更新，可执行：conda env update -f environment_train.yml
    ) else (
        echo [完成] 训练/推理环境 'mmseg' 创建成功。
    )
)

echo.
echo ============================================================
echo  安装流程结束。
echo  启动 GUI： python main.py
echo  训练前请在"环境配置"面板中选择 mmseg 环境的解释器。
echo ============================================================
echo.
pause
endlocal
