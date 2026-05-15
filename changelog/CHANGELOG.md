# CBSS工具更新日志

## v3.2.3 (2026-05-15)

### 问题修复
1. **设备列表颜色配置生效**
   - 修复 Windows ttk 主题覆盖 `Treeview` 行 tag 颜色的问题
   - 加载配置后重新应用授权设备列表样式
2. **异常设备默认颜色调整**
   - 将 `color_pirated` 默认值从低对比度黄色调整为褐色 `#8B4513`
   - 启动时自动迁移历史默认黄色 `#FFD700`，保留用户自定义颜色

## v3.2.2 (2026-05-11)

### 架构优化
1. **增量设备同步**
   - `DeviceMonitor._update_device_info` 仅将 Detector 上报的增删变化同步到 parser
   - `sync_connected_devices` 改为接收 `added_devices`/`removed_serials`，不再全量 diff
   - `AdbDeviceDetector.poll_changes` 对比上次 serial 列表，仅上报变化
2. **刷新统一为 markDirty 机制**
   - 新增 `mark_device_dirty(serial)`：标记单个设备 dirty 并 kick parser 刷新
   - 用户刷新按钮：全部设备 `markDirty` + `kick`
   - 授权完成/失败：仅 `mark_device_dirty` 该设备
   - `refresh_all_cube` 不再刷新 target 设备（仅刷新 Cube 快照）
3. **`_submitted` 标记防止重复入队**
   - 设备首次 `unauthorized_ready` 后设置 `_submitted=True`，避免重复加入自动授权队列
   - 设备移除后重新添加时重置
4. **`classify_device` 仅在分类策略中处理 sim 设备**
   - `_to_target_device` 不再区分 sim/adb 类型
   - `DeviceClassificationStrategy.classify_device` 通过 `SimulatorDeviceDetector._sim_failure_flags` 获取 `simulate_activate_failure` 标志
5. **`get_target_device` 统一查找路径**
   - 仅通过 parser 查找 `TargetDeviceAbstract`，不区分模拟/真实设备

### 问题修复
1. **自动授权队列重复添加** — 通过 `_submitted` 标记防止
2. **`_mark_all_devices_dirty` 缺失** — 修复手动刷新按钮报错
3. **`SimulatorDeviceDetector.get_device` 缺失** — 恢复 `_devices` 字典和 `get_device()` 方法

## v3.2.1 (2026-05-11)

### 问题修复
1. **修复 `_perform_authentication` sign_uuid 不执行的问题**
   - 缩进错误导致 sign_uuid 及后续步骤在状态检查返回后无法执行
2. **修复所有设备提示"已被锁定"的问题**
   - 移除 `_perform_authentication` 外层 lock，activate 内部已处理 lock/unlock
3. **activate 失败后 UI 状态更新**
   - 激活失败时立即调用 `update_device_status` 同步 AuthorizationFailure 到 UI
4. **AuthorizationFailure 设备防止状态刷新覆盖**
   - `refreshDeviceMeta` 对 AuthorizationFailure 设备跳过 ADB 调用，仅清除 dirty
5. **移除认证流程中模拟设备的特殊处理**
   - `_perform_authentication` 不再区分模拟/真实设备的返回标签

### 功能增强
1. **模拟设备创建弹窗增强**
   - 新增自定义 UUID、Serial ID 输入（可选）
   - 新增 Simulation activate Failure 勾选框，模拟激活失败场景
2. **模拟设备右键移除**
   - 右键 SIM- 前缀设备可移除，模拟设备重新插拔
3. **授权日志分离**
   - 所有记录 → `detailed_info/all/`，失败记录 → `detailed_info/failure/`
   - 失败记录额外包含 cube_status、cube_expire
   - 日志目录可通过配置 `auth_log_all_dir` / `auth_log_failure_dir` 指定
4. **授权流程优化**
   - sign_uuid 前先确认设备状态为 Unauthorized，避免浪费 Cube 授权数
   - double check 设备状态后再执行 activate
   - AuthorizationFailure 状态禁止再次激活
5. **DEBUG 日志增强**
   - device_parser kick 时记录 refreshDeviceMeta 开始/完成的 INFO 日志

## v3.2.0 (2026-05-11)

### 逻辑优化
1. **TargetDevice 增加 dirty/lock 状态管理**
   - `ITargetDevice` 增加 `refreshDeviceMeta`、`markDirty`、`lock`、`unlock`、`isDirty`、`isLocked` 接口
   - `markDirty` 标记设备状态不可信，kick `DeviceParser` 重新获取元信息（UUID/status/port）
   - `lock`/`unlock` 保护关键操作（如 `activate`），lock 状态下 `markDirty` 延迟到 unlock 执行
   - `activate` 内部自动执行 lock→activate→markDirty→unlock 流程
2. **DeviceParser 增加 kick 操作**
   - `kick()` 遍历所有 dirty 设备，调用 `refreshDeviceMeta` 获取最新元信息
   - 分类完成后自动 `markDirty` 触发初次刷新
3. **认证流程统一**
   - `_perform_authentication` 不再区分模拟/真实设备状态验证
   - `activate` 内部自动触发 parser 刷新
4. **DeviceMonitor 统一管理全部设备**
   - ADB 设备与模拟设备通过统一的探测器列表管理
   - 模拟设备不再单独合并到 `target_devices`

### 日志增强
- `logs/detailed_info/all/` 目录记录授权详情
- 每条记录包含：成功/失败、时间、serial_id、uuid、signature、Cube Id、错误原因
- 每个文件限制 200 条记录，自动轮转

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
