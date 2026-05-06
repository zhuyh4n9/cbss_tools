# 修复打包后CMD窗口闪现问题

## 问题描述
使用PyInstaller打包后的exe程序在运行时，每次调用ADB命令都会反复弹出CMD黑窗口，影响用户体验。

## 根本原因
在Windows平台下使用`subprocess.run()`执行外部命令时，如果不指定`creationflags`参数，默认会创建一个可见的控制台窗口。

## 解决方案

### 1. 添加Windows平台检测和标志定义
在`src/adb_manager.py`文件开头添加：

```python
import sys

# Windows平台下隐藏CMD窗口
if sys.platform == 'win32':
    import subprocess
    # 设置创建标志以隐藏CMD窗口
    CREATE_NO_WINDOW = 0x08000000
    SUBPROCESS_FLAGS = CREATE_NO_WINDOW
else:
    SUBPROCESS_FLAGS = 0
```

### 2. 修改所有subprocess.run调用
为所有的`subprocess.run()`调用添加`creationflags`参数：

**修改前：**
```python
result = subprocess.run(
    [self.adb_path, 'devices', '-l'],
    capture_output=True,
    text=True,
    timeout=10
)
```

**修改后：**
```python
result = subprocess.run(
    [self.adb_path, 'devices', '-l'],
    capture_output=True,
    text=True,
    timeout=10,
    creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
)
```

### 3. 修改位置列表
已修复`src/adb_manager.py`中的所有5处subprocess.run调用：

1. **execute_adb_command()** (第80行) - 主要的ADB命令执行方法
2. **get_connected_devices()** (第159行) - 获取设备列表
3. **list_diagnostic_files()** (第690行) - 列出诊断文件
4. **pull_file()** (第717行) - 拉取文件
5. **remove_file()** (第737行) - 删除文件

## 技术说明

### CREATE_NO_WINDOW标志
- 值：`0x08000000`
- 作用：在Windows上创建进程时不显示控制台窗口
- 仅在Windows平台有效

### 跨平台兼容性
通过`sys.platform == 'win32'`判断，确保：
- Windows平台：使用`CREATE_NO_WINDOW`标志
- 其他平台（Linux/Mac）：使用0（无影响）

## 测试验证

### 打包前测试
```powershell
python main.py
```
不应看到任何CMD窗口闪现。

### 打包后测试
```powershell
cd package
pyinstaller cbss_simple.spec
.\dist\CBSS_Tool.exe
```

运行exe程序时：
- ✅ 不应出现CMD黑窗口
- ✅ ADB命令正常执行
- ✅ 功能完全正常

## 影响范围
- **文件修改**：`src/adb_manager.py`
- **影响功能**：所有ADB命令调用
- **兼容性**：Windows/Linux/Mac全平台兼容

## 参考
- [subprocess.CREATE_NO_WINDOW](https://docs.python.org/3/library/subprocess.html#subprocess.CREATE_NO_WINDOW)
- [PyInstaller Windows Console](https://pyinstaller.org/en/stable/spec-files.html#spec-file-options-for-a-windows-exe)

## 版本信息
- 修复日期：2025-10-30
- 修复版本：v2.2
- 相关Issue：打包后UI反复弹出CMD窗口

---

**注意**：此修复仅针对subprocess调用。如果还有其他地方使用os.system()或其他方式调用外部命令，也需要类似处理。
