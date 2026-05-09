# cbss_tools 维护 Skill

## 目标
用于指导维护 `cbss_tools/cbss_host_tool` 相关 PC 端代码（The Cube）时的分析与改动路径，确保新增能力可落在现有架构中。

## 一、先理解的数据流（必须）
1. 设备发现：`DeviceMonitor` 轮询 `adb devices -l`。
2. 设备分类：`DeviceParser` 将序列号分流为 authenticator / target，维护 `await/ready` 队列。
3. 认证器快照：`CubeManager` 周期刷新 `snapshot`，并通过回调更新 UI。
4. 授权流程：`AuthenticationManager._perform_authentication()` 执行
   `acquire_secure_uuid -> sign -> activate_device2 -> state校验`。

关键文件：
- `src/device_monitor.py`
- `src/device_parser.py`
- `src/cube_manager.py`
- `src/auth_manager.py`
- `src/main_gui.py`

## 二、cbss_tools 相关改动的标准落点
凡是新增/修改设备能力，按以下顺序改：
1. 在 `config/default_config.ini` 的 `[ADB_Commands]` 新增命令模板。
2. 在 `src/adb_manager.py` 增加同名封装方法（只走 `execute_adb_command()`）。
3. 在 `src/main_gui.py` 或 `src/diaglog/` 接入 UI 入口（菜单/对话框/进度反馈）。
4. 如涉及文案，更新 `config/prompt_chn.ini`，通过 `PromptManager.get()` 取文案。

禁止：在 UI 层直接写 `subprocess` 或硬编码 ADB 命令。

## 三、输出解析规则（易踩坑）
- 命令成功判定依赖工具输出中的：
  - `[status] <code>[, message]`
  - `[result] <payload>`
- 解析逻辑在 `ADBManager._parse_command_output()`。
- 若 `status_code != 0`，错误文案优先来自 `[status]`，其次回落到 `Status_Messages` 配置。

## 四、并发与 UI 更新规则
- 长耗时操作必须放在线程中执行。
- 线程内更新 UI 必须使用 `root.after(...)` 或 `dialog.after(...)` 回主线程。
- 设备分类误判修复依赖 `DeviceParser.sync_connected_devices()` 与 `_worker_loop()` 的重分类逻辑，不要轻易删除重试队列。

## 五、联调与回归清单
- 本地运行：`python main.py`
- 打包：`python package_all.py --type release`
- 清理：`python package_all.py --clean`
- 压测/签名验证：`python stress_test/quick_stress_test.py`

回归重点：
1. 认证器不会出现在 target 列表中（尤其 snapshot 瞬时失败时）。
2. 单设备授权与批量授权流程均可闭环。
3. Wi-Fi 连接后 `time_status` / 网络连通性状态更新正常。
4. 日志写入 `logs/cbss_tool.log`，异常可定位。

## 六、平台与依赖边界
- Windows 优先，ADB 默认路径：`adb/adb.exe`。
- 设备侧依赖：`cbss_tools`、`cbss_host_tool`。
- 诊断与网络相关能力依赖 `default_config.ini` 中的命令模板与 `Network` 配置。

## 七、维护建议（针对本项目）
- 做新功能先扩展配置，再扩展 `ADBManager`，最后接 UI。
- 保持 `DeviceMonitor -> DeviceParser -> CubeManager` 边界清晰，避免把分类与快照逻辑挪回 UI。
- 对外行为变化（菜单、提示、错误）一律走 `prompt_chn.ini`，避免硬编码中文。

## 八、TargetDevice Management（按当前实现）
1. **来源与同步**
   - 设备来源走 `DeviceSource` 抽象，默认实现为 `AdbDeviceSource`。
   - `DeviceMonitor._update_device_info()` 只做“连接设备同步”，并调用 `device_parser.sync_connected_devices()`。
2. **队列模型**
   - `DeviceParser` 维护 `_await_queue`（检查中）与 `_ready_queue`（可展示）双队列，以及 `_classify_queue` 分类队列。
   - UI 展示列表来自 `DeviceParser.get_devices()`，且只返回 `target_device/unknown`。
3. **分类策略**
   - 分类入口是 `DeviceClassificationStrategy.classify_device()`：
     - `CreateAdbDevice()` 成功识别为 `AC8267Device` → 目标设备；
     - ADB 识别失败但 `snapshot` 成功 → 视为 Cube（转交 `CubeManager.add_cube`）；
     - 两者都失败 → 标记 Unknown（保留在目标设备列表）。
4. **刷新行为**
   - `refresh_device(serial)`：ready 设备回退到 await；若该 serial 不在目标队列，则转发到 `cube_manager.refresh_cube(serial)`。
   - `refresh_all_device()`：将 ready 全量回退 await，触发重新解析。
5. **状态与回调**
   - await 设备显示 `Checking...`，unknown 设备显示 `Unknown`，uuid 为空。
   - await 解析完成后若状态为 `unauthorized` 且有 uuid，会触发 `unauthorized_ready` 事件给自动授权流程。

## 九、Cube Management（按当前实现）
1. **职责**
   - `CubeManager` 只管理 authenticator（Cube）及其 `snapshot` 刷新，不处理 target 设备解析。
2. **状态集合**
   - `_cubes`：已确认的 Cube 快照；
   - `_pending_cubes`：待确认/待重试；
   - `_refresh_queue`：立即刷新队列。
3. **刷新机制**
   - `add_cube/refresh_cube` 会将 serial 放入 pending + refresh_queue，后台线程优先立即刷新。
   - 即时刷新失败时会保留 pending 并重试，避免误降级。
   - 线程按 `refresh_interval` 周期刷新全部已确认 Cube。
4. **回调传播**
   - Cube 快照有变化才发 `authenticator_update`，由 `DeviceParser._on_cube_update()` 继续向上透传到 UI。
5. **边界要求**
   - 不要在 `DeviceMonitor` 或 UI 层直接维护 Cube 缓存；统一通过 `CubeManager`。

## 十、自动授权与并发注意事项
1. **自动授权入口**
   - `AuthenticationManager` 监听 `device_parser` 的 `unauthorized_ready` 回调并入队。
2. **串行执行与去重**
   - 自动授权队列使用 `_queued_serials/_in_progress_serials` 去重，避免并发重复激活同一设备。
3. **授权后刷新**
   - 自动授权完成后调用 `refresh_all_cube()` + `refresh_device(serial)`：前者刷新全部 Cube 快照，后者仅触发当前目标设备重解析。
4. **线程约束**
   - `DeviceMonitor/DeviceParser/CubeManager/AuthenticationManager` 后台线程均为 `daemon=True`。
   - 涉及 UI 更新仍必须回主线程（`root.after(...)`）。
