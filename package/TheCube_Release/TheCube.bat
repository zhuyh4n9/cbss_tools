@echo off
title TheCube - AC8267授权工具
echo TheCube - AC8267授权工具...
echo 版本：v2.2.0
echo.
TheCube.exe
if errorlevel 1 (
    echo.
    echo 程序异常退出，请查看日志文件
    echo 日志位置: logs\TheCube.log
    echo.
    pause
)
