@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   Agentrust 系统初始化脚本
echo ========================================
echo.

cd /d "%~dp0..\backend"

echo [1/2] 删除旧数据库...
if exist ..\data\agentrust.db (
    del /q ..\data\agentrust.db
    echo   已删除 data\agentrust.db
) else (
    echo   数据库文件不存在，跳过
)

echo.
echo [2/2] 初始化数据库和CA根密钥...
python scripts/init_db.py

echo.
echo ========================================
echo   初始化完成，可以运行 demo.py 了
echo ========================================
pause