@echo off
setlocal

rem ============================================================
rem 重新生成「一键部署.exe」
rem 用法：双击本脚本，自动检查 Python、安装依赖、生成 exe
rem ============================================================

cd /d "%~dp0"

echo ===============================================
echo   重新生成 一键部署.exe
echo ===============================================
echo.

python --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+ 并勾选 Add to PATH
    echo        下载：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Python 已就绪：
python --version
echo.
echo 正在生成 exe（如缺少依赖会自动安装）...
echo.

python build_deploy.py

echo.
if errorlevel 1 (
    echo [错误] 生成失败，请查看上方错误信息
) else (
    echo [成功] 已生成 一键部署.exe
    echo        提示：首次运行如被杀毒软件拦截闪退，请加入信任后重试
)
echo.
pause
