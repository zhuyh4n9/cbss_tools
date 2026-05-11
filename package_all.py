#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CBSS Tool 统一打包脚本
整合所有打包流程：开发版、轻量版、可执行文件版、便携版、安装版
"""

import os
import sys
import shutil
import subprocess
import platform
import zipfile
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime

class CBSSPackager:
    """CBSS工具打包器"""

    def __init__(self):
        self.project_root = Path.cwd()
        self.version = "3.1.7"
        self.build_date = datetime.now().strftime("%Y-%m-%d")

        # 打包目录
        self.build_dirs = {
            'dev': 'package/TheCube_Dev',
            'lite': 'package/TheCube_Lite',
            'portable': 'package/TheCube_Portable',
            'installer': 'package/TheCube_Installer',
            'release': 'package/TheCube_Release',
            'quick': 'package/TheCube_Quick'
        }

        # 核心文件列表
        self.core_files = [
            'main.py',
            'README.md',
            'requirements.txt',
            'changelog/CHANGELOG.md'
        ]

        # 核心目录列表
        self.core_dirs = [
            'src',
            'config',
            'adb'
        ]

        # 可选目录
        self.optional_dirs = [
            'stress_test'
        ]

    def log(self, message, level="INFO"):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def check_environment(self):
        """检查构建环境"""
        self.log("检查构建环境...")

        # 检查Python版本
        if sys.version_info < (3, 7):
            self.log("错误：需要Python 3.7或更高版本", "ERROR")
            return False

        # 检查必要文件
        for file in self.core_files:
            if not (self.project_root / file).exists():
                self.log(f"错误：缺少核心文件 {file}", "ERROR")
                return False

        # 检查必要目录
        for dir_name in self.core_dirs:
            if not (self.project_root / dir_name).exists():
                self.log(f"错误：缺少核心目录 {dir_name}", "ERROR")
                return False

        self.log("环境检查通过", "SUCCESS")
        return True

    def install_dependencies(self):
        """安装打包依赖"""
        self.log("检查并安装依赖...")

        dependencies = ['pyinstaller>=4.0']

        for dep in dependencies:
            try:
                self.log(f"安装 {dep}...")
                subprocess.run([
                    sys.executable, "-m", "pip", "install", dep
                ], check=True, capture_output=True)
                self.log(f"✓ {dep} 安装成功")
            except subprocess.CalledProcessError as e:
                self.log(f"✗ {dep} 安装失败: {e}", "ERROR")
                return False

        return True

    def check_build_dependencies(self):
        """检查构建与运行时关键依赖"""
        self.log("检查编译依赖...")

        required_modules = {
            'PyInstaller': 'pip install pyinstaller',
            'cryptography': 'pip install cryptography',
        }
        missing_modules = []

        for module_name, install_hint in required_modules.items():
            if importlib.util.find_spec(module_name) is None:
                missing_modules.append((module_name, install_hint))

        if missing_modules:
            for module_name, install_hint in missing_modules:
                self.log(f"✗ 缺少依赖模块: {module_name} ({install_hint})", "ERROR")
            return False

        try:
            import tkinter  # noqa: F401
        except Exception:
            self.log("✗ 缺少依赖模块: tkinter (请安装包含tkinter的Python发行版)", "ERROR")
            return False

        required_files = [
            'config/default_config.ini',
            'config/prompt_chn.ini',
            'main.py',
        ]
        for file_name in required_files:
            if not (self.project_root / file_name).exists():
                self.log(f"✗ 缺少构建所需文件: {file_name}", "ERROR")
                return False

        self.log("✓ 编译依赖检查通过")
        return True

    def clean_build(self, keep_dirs=None):
        """清理构建文件"""
        self.log("清理构建文件...")

        # 要清理的目录
        clean_dirs = ['build', 'dist', '__pycache__']
        clean_dirs.extend(self.build_dirs.values())

        # 保留指定目录
        if keep_dirs:
            clean_dirs = [d for d in clean_dirs if d not in keep_dirs]

        for dir_name in clean_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                self.log(f"删除目录: {dir_name}")
                shutil.rmtree(dir_path)

        # 清理spec文件
        for spec_file in self.project_root.glob("*.spec"):
            self.log(f"删除文件: {spec_file.name}")
            spec_file.unlink()

        # 清理压缩包
        for zip_file in self.project_root.glob("TheCube_*.zip"):
            self.log(f"删除压缩包: {zip_file.name}")
            zip_file.unlink()

        for rar_file in self.project_root.glob("TheCube_*.rar"):
            self.log(f"删除压缩包: {rar_file.name}")
            rar_file.unlink()

    def create_pyinstaller_spec(self, simple=False, optimize_level=2):
        """创建PyInstaller配置文件"""
        self.log("创建PyInstaller配置文件...")

        spec_name = "cbss_simple.spec" if simple else "TheCube.spec"

        # 基础配置
        binaries = []
        datas = [
            ('config/default_config.ini', 'config'),
            ('config/prompt_chn.ini', 'config'),
            ('changelog/CHANGELOG.md', '.'),
            ('README.md', '.'),
        ]

        # 完整版本包含更多文件
        if not simple:
            binaries.extend([
                ('adb/adb.exe', 'adb'),
                ('adb/AdbWinApi.dll', 'adb'),
                ('adb/AdbWinUsbApi.dll', 'adb'),
            ])
            datas.extend([
                ('stress_test/pubkey/pub.pem', 'stress_test/pubkey'),
            ])

        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries={binaries},
    datas={datas},
    hiddenimports=collect_submodules('src') + [
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'cryptography',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.asymmetric',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.bindings.openssl',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    optimize={optimize_level},
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TheCube',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if __import__('os').path.exists('icon.ico') else None,
)
'''

        with open(spec_name, 'w', encoding='utf-8') as f:
            f.write(spec_content)

        self.log(f"✓ {spec_name} 创建成功")
        return spec_name

    def build_executable(self, simple=True, optimize_level=2):
        """构建可执行文件"""
        self.log("构建可执行文件...")

        if not self.check_build_dependencies():
            self.log("✗ 构建失败：编译依赖检查未通过", "ERROR")
            return False

        spec_file = self.create_pyinstaller_spec(simple=simple, optimize_level=optimize_level)

        try:
            cmd = [
                sys.executable,
                "-m",
                "PyInstaller",
                spec_file,
                "--clean",
                "--noconfirm"
            ]
            self.log(f"执行命令: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                exe_path = self.project_root / "dist" / "TheCube.exe"
                if exe_path.exists():
                    self.log("✓ 可执行文件构建成功", "SUCCESS")
                    return True
                else:
                    self.log("✗ 可执行文件未生成", "ERROR")
                    return False
            else:
                self.log("✗ 构建失败:", "ERROR")
                self.log(result.stdout)
                self.log(result.stderr)
                return False

        except Exception as e:
            self.log(f"✗ 构建异常: {e}", "ERROR")
            return False

    def create_dev_package(self):
        """创建开发环境包"""
        self.log("创建开发环境包...")

        dev_dir = self.project_root / self.build_dirs['dev']
        dev_dir.mkdir(parents=True, exist_ok=True)

        # 复制核心文件
        for file_name in self.core_files:
            src = self.project_root / file_name
            if src.exists():
                dst = dev_dir / file_name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # 复制脚本文件
        script_files = ['package_all.py']
        for script in script_files:
            src = self.project_root / script
            if src.exists():
                dst = dev_dir / script
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # 复制目录
        all_dirs = self.core_dirs + self.optional_dirs
        for dir_name in all_dirs:
            src_dir = self.project_root / dir_name
            if src_dir.exists():
                dst_dir = dev_dir / dir_name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)

        # 创建开发环境脚本
        self._create_dev_scripts(dev_dir)

        # 创建说明文档
        self._create_dev_readme(dev_dir)

        self.log(f"✓ 开发环境包创建完成: {dev_dir}")
        return dev_dir

    def create_lite_package(self):
        """创建轻量版本"""
        self.log("创建轻量版本...")

        lite_dir = self.project_root / self.build_dirs['lite']
        lite_dir.mkdir(parents=True, exist_ok=True)

        # 复制核心文件
        core_files = ['main.py', 'requirements.txt']
        for file_name in core_files:
            src = self.project_root / file_name
            if src.exists():
                shutil.copy2(src, lite_dir / file_name)

        # 复制核心目录
        for dir_name in self.core_dirs:
            src_dir = self.project_root / dir_name
            if src_dir.exists():
                dst_dir = lite_dir / dir_name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)

        # 创建启动脚本
        self._create_simple_launcher(lite_dir)

        self.log(f"✓ 轻量版本创建完成: {lite_dir}")
        return lite_dir

    def create_portable_package(self):
        """创建便携版本"""
        self.log("创建便携版本...")

        # 首先构建可执行文件
        if not self.build_executable(simple=True):
            self.log("✗ 便携版本创建失败：可执行文件构建失败", "ERROR")
            return None

        portable_dir = self.project_root / self.build_dirs['portable']
        portable_dir.mkdir(parents=True, exist_ok=True)

        # 复制可执行文件
        exe_src = self.project_root / "dist" / "TheCube.exe"
        if exe_src.exists():
            shutil.copy2(exe_src, portable_dir / "TheCube.exe")
        else:
            self.log("✗ 找不到可执行文件", "ERROR")
            return None

        # 复制必要文件和目录
        files_to_copy = ['README.md', 'CHANGELOG.md']
        for file_name in files_to_copy:
            src = self.project_root / file_name
            if src.exists():
                shutil.copy2(src, portable_dir / file_name)

        # 复制目录
        dirs_to_copy = ['adb', 'config']
        for dir_name in dirs_to_copy:
            src_dir = self.project_root / dir_name
            if src_dir.exists():
                dst_dir = portable_dir / dir_name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)

        # 创建便携版脚本和文档
        self._create_portable_scripts(portable_dir)
        self._create_portable_readme(portable_dir)

        self.log(f"✓ 便携版本创建完成: {portable_dir}")
        return portable_dir

    def create_installer_package(self):
        """创建安装程序包"""
        self.log("创建安装程序包...")

        # 首先构建可执行文件
        if not self.build_executable(simple=False):
            self.log("✗ 安装程序包创建失败：可执行文件构建失败", "ERROR")
            return None

        installer_dir = self.project_root / self.build_dirs['installer']
        installer_dir.mkdir(parents=True, exist_ok=True)
        (installer_dir / "changelog").mkdir(exist_ok=True)
        # 复制可执行文件
        exe_src = self.project_root / "dist" / "TheCube.exe"
        if exe_src.exists():
            shutil.copy2(exe_src, installer_dir / "TheCube.exe")

        # 复制所有文件和目录
        all_files = self.core_files
        for file_name in all_files:
            src = self.project_root / file_name
            if src.exists():
                dst = installer_dir / file_name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        all_dirs = self.core_dirs + self.optional_dirs
        for dir_name in all_dirs:
            src_dir = self.project_root / dir_name
            if src_dir.exists():
                dst_dir = installer_dir / dir_name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)

        # 创建安装脚本
        self._create_installer_scripts(installer_dir)

        self.log(f"✓ 安装程序包创建完成: {installer_dir}")
        return installer_dir

    def create_release_package(self):
        """创建最终发布包"""
        self.log("创建最终发布包...")

        # 首先构建可执行文件
        if not self.build_executable(simple=True):
            self.log("✗ 最终发布包创建失败：可执行文件构建失败", "ERROR")
            return None

        release_dir = self.project_root / self.build_dirs['release']
        release_dir.mkdir(parents=True, exist_ok=True)
        (release_dir / "changelog").mkdir(exist_ok=True)
        # 复制可执行文件
        exe_src = self.project_root / "dist" / "TheCube.exe"
        if exe_src.exists():
            shutil.copy2(exe_src, release_dir / "TheCube.exe")

        # 复制文档文件
        doc_files = ['README.md', 'changelog/CHANGELOG.md']
        for file_name in doc_files:
            src = self.project_root / file_name
            if src.exists():
                dst = release_dir / file_name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # 复制必要目录
        essential_dirs = ['adb', 'config']
        for dir_name in essential_dirs:
            src_dir = self.project_root / dir_name
            if src_dir.exists():
                dst_dir = release_dir / dir_name
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)

        # 创建日志目录
        (release_dir / 'logs').mkdir(exist_ok=True)

        # 创建最终版本脚本和文档
        self._create_release_scripts(release_dir)
        self._create_release_docs(release_dir)

        self.log(f"✓ 最终发布包创建完成: {release_dir}")
        return release_dir

    def create_archives(self, dirs_to_archive):
        """创建压缩包"""
        self.log("创建压缩包...")

        archives_created = []

        for dir_path in dirs_to_archive:
            if not dir_path or not dir_path.exists():
                continue
            archive_name = f"{dir_path.name}.zip"
            archive_path = self.project_root / "package" / archive_name
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in dir_path.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(dir_path.parent)
                            zipf.write(file_path, arcname)

                self.log(f"✓ 压缩包创建完成: {archive_name}")
                archives_created.append(archive_path)

            except Exception as e:
                self.log(f"✗ 压缩包创建失败 {archive_name}: {e}", "ERROR")

        return archives_created

    def _create_dev_scripts(self, dev_dir):
        """创建开发环境脚本"""
        # 虚拟环境设置脚本
        setup_script = '''@echo off
title TheCube工具开发环境
echo ====================================
echo TheCube工具 开发环境
echo ====================================
echo.

if not exist "venv" (
    echo 创建Python虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo 错误：创建虚拟环境失败
        echo 请确保Python已正确安装
        pause
        exit /b 1
    )
)

echo 激活虚拟环境...
call venv\\Scripts\\activate.bat

echo 安装依赖包...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ====================================
echo 开发环境已准备就绪！
echo ====================================
echo.
echo 可用命令：
echo   python main.py                 - 启动GUI程序
echo   python stress_test\\quick_stress_test.py - 运行压力测试
echo   python package_all.py --type portable - 打包可执行文件
echo.
echo 输入 'deactivate' 退出虚拟环境
echo 输入 'exit' 关闭此窗口
echo.

cmd /k
'''

        with open(dev_dir / "setup_dev.bat", 'w', encoding='gbk') as f:
            f.write(setup_script)

        setup_venv_script = '''@echo off
call setup_dev.bat
'''
        with open(dev_dir / "setup_venv.bat", 'w', encoding='gbk') as f:
            f.write(setup_venv_script)

        # 快速运行脚本
        run_script = '''@echo off
title TheCube - AC8267
if exist "venv\\Scripts\\python.exe" (
    venv\\Scripts\\python.exe main.py
) else (
    echo 虚拟环境未设置，请先运行 setup_dev.bat
    pause
)
'''

        with open(dev_dir / "run.bat", 'w', encoding='gbk') as f:
            f.write(run_script)

    def _create_dev_readme(self, dev_dir):
        """创建开发环境说明"""
        readme_content = f'''# TheCube - AC8267授权工具 开发环境包

版本：{self.version}
构建日期：{self.build_date}

## 目录说明
- src/: 源代码目录
- config/: 配置文件
- stress_test/: 压力测试模块
- adb/: ADB工具
- main.py: 主程序入口
- requirements.txt: Python依赖列表

## 快速开始
1. 运行 setup_dev.bat 设置开发环境
2. 运行 run.bat 启动程序
3. 或者手动激活虚拟环境后运行 python main.py

## 开发说明
- 使用 Python 3.7+
- 主要依赖：tkinter, cryptography
- 支持Windows平台

## 打包说明
- 运行 package_all.py --type portable 可生成可执行文件
- 或使用 pyinstaller 手动打包

## 注意事项
- 首次运行需要设置虚拟环境
- 确保Python已正确安装
- 设备连接问题请检查ADB驱动
'''

        with open(dev_dir / "开发说明.txt", 'w', encoding='utf-8') as f:
            f.write(readme_content)

    def _create_simple_launcher(self, lite_dir):
        """创建简单启动脚本"""
        launcher_script = '''@echo off
echo 安装依赖...
pip install -r requirements.txt
echo 启动程序...
python main.py
pause
'''

        with open(lite_dir / "启动.bat", 'w', encoding='gbk') as f:
            f.write(launcher_script)

    def _create_portable_scripts(self, portable_dir):
        """创建便携版脚本"""
        launcher_script = '''@echo off
title TheCube - AC8267授权工具
echo 启动TheCube - AC8267授权工具
TheCube.exe
if errorlevel 1 (
    echo.
    echo 程序执行出错，按任意键退出...
    pause >nul
)
'''

        with open(portable_dir / "TheCube.bat", 'w', encoding='gbk') as f:
            f.write(launcher_script)

    def _create_portable_readme(self, portable_dir):
        """创建便携版说明"""
        readme_content = f'''# TheCube - AC8267授权工具

版本：{self.version}
构建日期：{self.build_date}

## 文件说明
- TheCube.exe: 主程序
- 启动TheCube.bat: 启动脚本
- adb/: ADB工具目录
- config/: 配置文件目录

## 使用方法
1. 双击"TheCube.bat"或直接运行"TheCube.exe"
2. 连接认证器设备和待认证设备
3. 按照界面提示进行操作

## 注意事项
- 确保设备已正确连接并被Windows识别
- 首次使用可能需要安装设备驱动
- 如遇问题请查看logs/目录下的日志文件

## 技术支持
请参考README.md文件或联系技术支持人员。
'''

        with open(portable_dir / "使用说明.txt", 'w', encoding='utf-8') as f:
            f.write(readme_content)

    def _create_installer_scripts(self, installer_dir):
        """创建安装程序脚本"""
        install_script = '''@echo off
title TheCube - AC8267授权工具安装程序
echo ====================================
echo TheCube - AC8267授权工具安装程序
echo ====================================
echo.

set INSTALL_DIR=%ProgramFiles%\\TheCube
echo 安装目录: %INSTALL_DIR%
echo.

if not exist "%INSTALL_DIR%" (
    echo 创建安装目录...
    mkdir "%INSTALL_DIR%"
)

echo 正在复制文件...
xcopy /E /I /Y "*" "%INSTALL_DIR%\\"

echo 创建桌面快捷方式...
set DESKTOP=%USERPROFILE%\\Desktop
echo Set oWS = WScript.CreateObject("WScript.Shell") > temp_shortcut.vbs
echo sLinkFile = "%DESKTOP%\\TheCube.lnk" >> temp_shortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> temp_shortcut.vbs
echo oLink.TargetPath = "%INSTALL_DIR%\\TheCube.exe" >> temp_shortcut.vbs
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> temp_shortcut.vbs
echo oLink.Description = "TheCube - AC8267授权工具" >> temp_shortcut.vbs
echo oLink.Save >> temp_shortcut.vbs
cscript temp_shortcut.vbs >nul
del temp_shortcut.vbs

echo.
echo ====================================
echo 安装完成！
echo ====================================
echo 程序已安装到: %INSTALL_DIR%
echo 桌面快捷方式已创建
echo.
pause
'''

        with open(installer_dir / "install.bat", 'w', encoding='gbk') as f:
            f.write(install_script)

        # 卸载脚本
        uninstall_script = '''@echo off
title TheCube - AC8267授权工具卸载程序
echo ====================================
echo TheCube - AC8267授权工具 卸载程序
echo ====================================
echo.

set INSTALL_DIR=%ProgramFiles%\\TheCube
echo 安装目录: %INSTALL_DIR%
echo.

set /p CONFIRM=确定要卸载TheCube - AC8267授权工具工具吗？ (Y/N):
if /i "%CONFIRM%" neq "Y" goto :end

echo 正在删除文件...
if exist "%INSTALL_DIR%" (
    rmdir /S /Q "%INSTALL_DIR%"
    echo 程序文件已删除
)

echo 删除桌面快捷方式...
set DESKTOP=%USERPROFILE%\\Desktop
if exist "%DESKTOP%\\TheCube.lnk" (
    del "%DESKTOP%\\TheCube.lnk"
    echo 快捷方式已删除
)

echo.
echo ====================================
echo 卸载完成！
echo ====================================

:end
pause
'''

        with open(installer_dir / "uninstall.bat", 'w', encoding='gbk') as f:
            f.write(uninstall_script)

    def _create_release_scripts(self, release_dir):
        """创建最终版本脚本"""
        launcher_script = f'''@echo off
title TheCube - AC8267授权工具
echo TheCube - AC8267授权工具...
    echo 版本：v{self.version}
echo.
TheCube.exe
if errorlevel 1 (
    echo.
    echo 程序异常退出，请查看日志文件
    echo 日志位置: logs\\TheCube.log
    echo.
    pause
)
'''

        with open(release_dir / "TheCube.bat", 'w', encoding='gbk') as f:
            f.write(launcher_script)

    def _create_release_docs(self, release_dir):
        """创建最终版本文档"""
        # 版本信息
        version_info = f'''TheCube - AC8267授权工具
================

版本信息：{self.version}
构建日期：{self.build_date}
平台支持：Windows 10/11
Python版本：{sys.version}

主要功能：
- 认证器设备管理
- AC8267设备激活
- 压力测试
- 诊断日志
- WiFi配置

技术特性：
- 隐藏ADB命令行窗口
- 友好的图形界面
- 完整的日志记录
- 多种打包方式

开发信息：
- 构建工具：PyInstaller
- GUI框架：tkinter
- 加密库：cryptography
- 通信协议：ADB

支持联系：
请参考README.md或联系技术支持团队
'''

        with open(release_dir / "版本信息.txt", 'w', encoding='utf-8') as f:
            f.write(version_info)

        # 用户指南
        user_guide = f'''# TheCube - AC8267授权工具 用户指南

## 系统要求
- Windows 10/11 (64位)
- USB端口用于设备连接
- 管理员权限（首次安装驱动时需要）

## 快速开始

### 1. 设备连接
- 将认证器设备通过USB连接到电脑
- 将待认证设备通过USB连接到电脑
- 确保设备被Windows正确识别

### 2. 启动程序
- 双击"TheCube.bat"或直接运行"TheCube.exe"
- 程序启动后会自动检测连接的设备

### 3. AC8267设备激活
- 连接网络，等待时间状态为Ready
- 在"待认证设备列表"中选择要认证的设备
- 双击设备或点击"认证"按钮
- 选择要使用的认证器
- 等待认证完成

## 主要功能

### 认证器管理
- 查看认证器状态和信息
- 锁定/解锁认证器
- 激活认证器
- 配置认证器

### AC8267设备激活
- 单个AC8267设备激活
- 批量AC8267设备激活
- 认证状态监控

### 系统功能
- WiFi配置
- 诊断日志导出
- 压力测试
- 日志查看

## 故障排除

### 设备未识别
1. 检查USB连接是否正常
2. 检查设备驱动是否已安装
3. 尝试重新连接设备
4. 点击"刷新设备"按钮

### 认证失败
1. 检查认证器状态是否正常
2. 确认认证器未被锁定
3. 检查认证器剩余激活次数
4. 查看日志文件获取详细错误信息

### 程序无法启动
1. 确保Windows系统为64位
2. 检查是否有杀毒软件阻止
3. 以管理员权限运行
4. 查看日志文件：logs/TheCube.log

## 日志文件
- 位置：logs/TheCube.log
- 包含详细的操作记录和错误信息
- 用于问题诊断和技术支持

## 技术支持
如遇问题请：
1. 查看用户指南和FAQ
2. 检查日志文件
3. 联系技术支持团队

版本：{self.version}
更新日期：{self.build_date}
'''

        with open(release_dir / "用户指南.md", 'w', encoding='utf-8') as f:
            f.write(user_guide)

    def package_all(self):
        """执行完整打包流程"""
        self.log("=" * 60)
        self.log("开始完整打包流程")
        self.log("=" * 60)

        # 检查环境
        if not self.check_environment():
            return False

        # 安装依赖
        if not self.install_dependencies():
            return False

        # 清理构建文件
        self.clean_build()

        created_dirs = []

        try:
            # 1. 创建开发环境包
            self.log("\n[1/5] 创建开发环境包")
            dev_dir = self.create_dev_package()
            if dev_dir:
                created_dirs.append(dev_dir)

            # 2. 创建轻量版本
            self.log("\n[2/5] 创建轻量版本")
            lite_dir = self.create_lite_package()
            if lite_dir:
                created_dirs.append(lite_dir)

            # 3. 创建便携版本
            self.log("\n[3/5] 创建便携版本")
            portable_dir = self.create_portable_package()
            if portable_dir:
                created_dirs.append(portable_dir)

            # 4. 创建安装程序包
            self.log("\n[4/5] 创建安装程序包")
            installer_dir = self.create_installer_package()
            if installer_dir:
                created_dirs.append(installer_dir)

            # 5. 创建最终发布包
            self.log("\n[5/5] 创建最终发布包")
            release_dir = self.create_release_package()
            if release_dir:
                created_dirs.append(release_dir)

            # 创建压缩包
            self.log("\n创建压缩包...")
            archives = self.create_archives(created_dirs)

            # 打包完成总结
            self.log("\n" + "=" * 60)
            self.log("打包完成！", "SUCCESS")
            self.log("=" * 60)

            self.log("\n生成的包：")
            for dir_path in created_dirs:
                if dir_path.exists():
                    self.log(f"  ✓ {dir_path.name}/ - {self._get_package_description(dir_path.name)}")

            self.log("\n生成的压缩包：")
            for archive_path in archives:
                if archive_path.exists():
                    size_mb = archive_path.stat().st_size / (1024 * 1024)
                    self.log(f"  ✓ {archive_path.name} ({size_mb:.1f} MB)")

            self.log(f"\n总计：{len(created_dirs)} 个包，{len(archives)} 个压缩包")

            return True

        except Exception as e:
            self.log(f"✗ 打包过程中发生错误: {e}", "ERROR")
            return False

    def _get_package_description(self, package_name):
        """获取包的描述"""
        descriptions = {
            'TheCube_Dev': '完整开发环境',
            'TheCube_Lite': '轻量版本',
            'TheCube_Portable': '便携版可执行文件',
            'TheCube_Installer': '安装程序包',
            'TheCube_Release': '最终发布版'
        }
        return descriptions.get(package_name, '未知类型')

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='TheCube统一打包脚本')
    parser.add_argument('--type', choices=['all', 'dev', 'lite', 'portable', 'installer', 'release'],
                       default='all', help='指定打包类型')
    parser.add_argument('--clean', action='store_true', help='只执行清理操作')
    parser.add_argument('--no-archive', action='store_true', help='不创建压缩包')

    args = parser.parse_args()

    packager = CBSSPackager()

    if args.clean:
        packager.clean_build()
        packager.log("清理完成")
        return

    if not packager.check_environment():
        sys.exit(1)

    if not packager.install_dependencies():
        sys.exit(1)

    success = False
    created_dirs = []

    if args.type == 'all':
        success = packager.package_all()
    else:
        packager.clean_build()

        if args.type == 'dev':
            created_dirs.append(packager.create_dev_package())
        elif args.type == 'lite':
            created_dirs.append(packager.create_lite_package())
        elif args.type == 'portable':
            created_dirs.append(packager.create_portable_package())
        elif args.type == 'installer':
            created_dirs.append(packager.create_installer_package())
        elif args.type == 'release':
            created_dirs.append(packager.create_release_package())

        # 创建压缩包
        if not args.no_archive and created_dirs:
            packager.create_archives([d for d in created_dirs if d])

        success = any(d is not None for d in created_dirs)

    if success:
        packager.log("打包任务完成", "SUCCESS")
    else:
        packager.log("打包任务失败", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
