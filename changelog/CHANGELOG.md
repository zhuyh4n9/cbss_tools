# CBSS工具更新日志

## v3.1.11 (2026-05-11)

### 问题修复
1. **修复自动授权下 SimulatorTargetDevice 可能重复授权问题**
   - 自动授权成功后先触发 `DeviceMonitor.update_devices()` 同步最新设备状态，再执行后续解析刷新
   - 避免解析层仍持有旧的 Unauthorized 快照导致设备重复入队、重复签名

2. **修复模拟设备自动授权可能触发“状态非Unauthorized”报错**
   - 在重复排队场景下，第二次授权会因设备已变为 Authorized 而失败；本次修复后不再进入第二次授权

3. **补充回归测试**
   - 新增自动授权重复排队场景测试，验证签名仅执行一次（避免额外 Token 消耗）

## v3.1.10 (2026-05-11)

### 问题修复
1. **修复 SimulatorDevice 自动授权失败问题**
   - 统一授权主流程改为通过 `ITargetDevice` 接口获取 UUID 与状态，不再在 `AuthenticationManager` 内按设备来源分支
   - 模拟设备与真实设备统一经过同一授权步骤（获取UUID → 签名 → 激活 → 状态校验）

2. **修复 Simulator 设备解析刷新会重置状态的问题**
   - `DeviceParser` 进入 await 阶段时改为调用设备对象自身的 `to_await_device()` 规则
   - `SimulatorDevice` 保留内部状态与 UUID，不再被解析流程重置为 `Checking...`

3. **补充回归测试**
   - 新增/更新单元测试覆盖模拟设备 await 刷新状态保持与统一授权接口行为

## v3.1.9 (2026-05-11)

### 问题修复
1. **设备定时轮询默认关闭，仅在必要时刷新**
   - 新增 `General.enable_periodic_polling`（默认 `false`）与 `General.polling_interval_seconds`
   - 未开启定时轮询时，不再后台周期拉取设备信息；仅在启动首次刷新、手动刷新、激活后刷新等必要场景执行刷新

2. **模拟Cube激活后计数显示同步修复**
   - 单设备/批量激活完成后，主动触发Cube显示刷新
   - 修复模拟Cube已消耗计数但UI未及时更新的问题

3. **模拟Cube Serial规则优化**
   - 仅在未指定 `serial id` 时自动生成 `SIM-CUBE-xxxx` 前缀序列号
   - 新建/加载模拟Cube支持可选 `serial id`，避免强制覆盖用户指定序列号

4. **弹窗位置修复**
   - 主要弹窗统一校正到主窗口所在屏幕可见区域内，避免多屏场景下弹窗跑到其他屏幕

## v3.1.8 (2026-05-11)

### 问题修复
1. **Simulator Device 与 Real Device 在授权流程中统一抽象处理**
   - `AuthenticationManager` 移除模拟目标设备专用入口，统一通过 `ITargetDevice` 解析与授权
   - 激活流程不再对模拟设备做单独分支处理

2. **模拟设备创建职责收敛到 DeviceMonitor 静态接口**
   - 新增 `DeviceMonitor.create_simulated_device(...)` 静态入口，由 Main UI 调用
   - `DeviceMonitor` 内部统一管理模拟设备新增、移除与状态刷新

3. **补充模拟设备右键移除能力（仅 UI 区分）**
   - 设备列表新增右键菜单，仅当 `ITargetDevice.getType()=="SimulatorDevice"` 时显示“移除模拟设备”
   - 支持移除确认、移除失败提示与状态栏反馈

## v3.1.7 (2026-05-11)

### 问题修复
1. **修复模拟设备开关在环境变量场景下易失效的问题**
   - `CBSS_ENABLE_SIMULATED_DEVICE` 现在支持 `1/true/yes/on` 等常见真值写法
   - 避免因环境变量值格式差异导致模拟 Device 功能无法开启

2. **避免重复触发 TargetDevice 解析**
   - `DeviceMonitor` 仅在设备连接状态发生变化时才触发 `DeviceParser.sync_connected_devices`
   - ADB 设备探测结果补充保留 `adb devices -l` 的状态字段，用于状态变化识别
   - 保留激活完成后的显式刷新路径（单设备刷新/必要时全量刷新），减少对 AC8267 的重复解析冲击

3. **设备探测与模拟设备接入日志增强**
   - 设备探测阶段新增“设备状态变化”日志，记录 serial、status 与 usb_port 变更
   - `add_simulated_device` 新增关键日志，记录模拟设备 serial、status 与 UUID 就绪情况

4. **模拟设备职责归位到 DeviceMonitor/Main UI**
   - 模拟设备新增入口由 Main UI 统一调用 `DeviceMonitor.add_simulated_device`
   - `AuthenticationManager` 不再维护模拟设备新增状态，仅做统一授权流程与设备实例解析

## v3.1.6 (2026-05-11)

### 问题修复
1. **自动授权模式下增加“异常未排队”提示**
   - 当自动授权已启用、设备为 Unauthorized 且 UUID 已就绪，但设备未处于自动授权排队状态时，
     操作列显示 **“工具异常 -- 请提交Bug”**
   - 用于显式提示异常状态，便于现场快速定位并反馈问题

## v3.1.5 (2026-05-11)

### 问题修复
1. **修复自动授权等待Cube时设备未稳定显示在队列中的问题**
   - 自动授权 worker 在等待可用 Cube 时，不再提前清除 queued 标记
   - 避免设备在重试间隙被 UI 误显示为“无法进行激活”
   - 补充单测覆盖“等待 Cube 期间仍保持 queued 状态”的回归场景

## v3.1.4 (2026-05-09)

### 问题修复
1. **修复打包后 exe 启动即退出的问题**
   - PyInstaller spec 增加 `collect_submodules('src')`，确保动态导入的 `src.*` 模块被完整打包
   - 补充 `tkinter.simpledialog` 隐式依赖，避免窗口组件导入失败导致程序启动中止

## v3.1.3 (2026-05-09)

### 问题修复
1. **修复打包后可执行文件运行依赖检查不足问题**
   - 在构建可执行文件前新增关键依赖与关键文件检查（PyInstaller、cryptography、tkinter、prompt配置文件）
   - 打包spec新增 `config/prompt_chn.ini`，避免运行时缺少提示文本配置
2. **修复开发包脚本引用无效构建脚本问题**
   - 开发包改为携带 `package_all.py`
   - `setup_dev.bat` 和开发说明中的打包命令更新为 `python package_all.py --type portable`
   - 新增 `setup_venv.bat` 作为 venv 初始化快捷入口

## v3.1.2 (2026-05-09)

### 问题修复
1. **修复 `src/main_gui.py` 直接运行时报错**
   - 解决 `ImportError: attempted relative import with no known parent package`
   - 现在可兼容包内导入与脚本直接运行两种启动方式

## v3.1.1 (2026-05-09)

### 功能优化
1. **自动授权逻辑优化**
   - 自动授权仅在存在 `time_status=Ready` 的 Cube 时执行，Cube 未 Ready 时队列等待，Ready 后自动继续
2. **设备列表操作文案优化**
   - 自动授权开启时：排队设备显示“等待自动授权”，自动授权完成设备显示“自动授权已完成”
   - 自动授权关闭时：不可激活显示“无法进行激活”，可手动激活显示“双击开始激活”
3. **设备插拔日志增强**
   - 新设备接入/设备移除时，以 INFO 级别记录事件、Serial ID、状态和连接信息

## v3.1 (2026-05-07)

### 功能优化
1. **激活流程完成后立即刷新Cube**
   - 设备激活成功后立即触发一次Cube刷新，确保快照信息及时更新
2. **版本号更新**
   - 配置版本号更新为 **3.1**

## v3.0 (2026-05-06)

### 架构优化
1. **设备探测与解析彻底解耦**
   - `DeviceMonitor` 仅负责设备插拔监控与同步
   - `DeviceParser` 统一管理设备分类、await/ready 队列与外部接口

2. **新增 CubeManager 管理认证器**
   - 认证器设备由 `CubeManager` 独立线程管理
   - 支持认证器按需刷新与定时刷新
   - 认证器更新通过回调直接驱动UI刷新

### 功能增强
1. **设备分类可靠性增强**
   - 增强 authenticator 重分类与重试机制
   - 修复部分场景下 authenticator 误显示在 target_device 列表的问题

2. **未知设备展示优化**
   - 解析失败设备标记为未知设备
   - UI中未知设备 UUID 显示为 `N/A`
   - 新增配置项控制未知设备显示：`[UI] show_na_devices`（默认 `false`）

### 版本
- 配置版本号更新为 **3.0**

## v2.2.1 (2025-10-31)

### 新增功能
1. **WiFi连接支持Open WiFi**
   - WiFi配置对话框新增"open"加密方式选项
   - 选择Open时自动隐藏密码输入框
   - 支持无密码WiFi网络连接

2. **更新日志查看功能**
   - 在"关于"菜单中新增"查看更新日志"选项
   - 点击后在对话框中显示CHANGELOG.md内容
   - 支持滚动查看完整更新历史

### 界面优化
1. **状态信息布局优化**
   - 将"剩余激活数"和"已激活数"合并到同一行显示
   - 将"设备状态"和"时间状态"合并到同一行显示
   - 将"网络状态"和"当前WiFi"合并到同一行显示
   - 界面更加紧凑，节省垂直空间

2. **刷新设备按钮防抖**
   - 添加防抖机制，避免重复点击
   - 刷新过程中禁用按钮
   - 提升用户体验

### 问题修复
1. **修复Windows下CMD窗口频繁弹出**
   - 在所有ADB命令执行时添加CREATE_NO_WINDOW标志
   - 彻底解决CMD窗口闪现问题
   - 详见 readme/BUGFIX_CMD_WINDOW_FLASH.md

## v2.2.0 (2025-10)

### 主要功能
- 激活盒子设备管理
- 设备状态监控
- WiFi扫描和连接
- 批量激活支持
- 诊断日志功能
