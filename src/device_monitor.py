"""
设备监控管理器
负责定期监控和更新设备状态信息
"""
import os
import threading
import time
import logging
from typing import List, Dict, Callable, Optional
from datetime import datetime, timedelta
from .adb_manager import ADBManager, DeviceInfo, AuthenticatorInfo
from .device_parser import DeviceParser
from .device_source import IDeviceDetector, AdbDeviceDetector, SimulatorDeviceDetector, DeviceChange
from .target_device import SimulatorDevice, ITargetDevice, AC8267Device
from .cube import SimulateCube, SimulateCubeConfig


class DeviceMonitor:
    def __init__(self, adb_manager: ADBManager, config_manager):
        self.adb_manager = adb_manager
        self.config = config_manager

        self.authenticators: Dict[str, AuthenticatorInfo] = {}
        self.target_devices: List[DeviceInfo] = []
        self.unknown_devices: List[DeviceInfo] = []
        self._connected_index: Dict[str, DeviceInfo] = {}

        # 统一探测器列表
        self._detectors: List[IDeviceDetector] = [
            AdbDeviceDetector(self.adb_manager),
            SimulatorDeviceDetector(),
        ]

        self.device_parser = DeviceParser(self.adb_manager)
        self.device_parser.add_callback('device_update', self._on_device_parser_update)
        self.device_parser.add_callback('authenticator_update', self._on_authenticator_update)
        self.device_parser.add_callback('authenticator_serials_update', self._on_authenticator_serials_update)
        self.device_parser.add_callback('error', lambda err: self._notify_callbacks('error', err))

        self._running = False
        self._monitor_thread = None
        self._callbacks = {
            'authenticator_update': [],
            'device_update': [],
            'error': [],
            'unauthorized_ready': [],
        }

        self.refresh_rate = self.config.getint('General', 'refresh_rate', 1)
        self.refresh_interval = 1.0 / max(self.refresh_rate, 1)
        self.cube_refresh_interval = max(self.config.getint('General', 'cube_refresh_interval', 5), 1)
        self._last_cube_refresh_time = 0.0

        # 模拟Cube管理
        self._simulated_cubes: Dict[str, SimulateCube] = {}
        self._simulated_cube_counter = 0

    def start_monitoring(self):
        """开始设备监控"""
        if self._running:
            return
        for detector in self._detectors:
            detector.start()
        self.device_parser.start()
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logging.info("设备监控已启动")

    def stop_monitoring(self, join_timeout: float = 2.0):
        """停止设备监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=max(float(join_timeout or 0), 0.0))
        for detector in self._detectors:
            detector.stop()
        self.device_parser.stop(join_timeout=join_timeout)
        logging.info("设备监控已停止")

    def _on_device_parser_update(self, devices: List[DeviceInfo]):
        """接收parser的设备结果，统一透传给UI"""
        self.target_devices = list(devices)
        self._notify_callbacks('device_update', self.target_devices)

    def _on_authenticator_update(self, authenticators: Dict[str, AuthenticatorInfo]):
        """接收CubeManager透传的authenticator信息并更新UI"""
        try:
            merged = dict(authenticators or {})
            # 合并模拟Cube
            merged.update(self.get_simulated_cube_infos())
            if self._has_authenticators_changed(merged):
                self.authenticators = merged
                self._notify_callbacks('authenticator_update', self.authenticators)
            else:
                self.authenticators = merged
        except Exception as e:
            logging.error(f"更新激活盒子信息失败: {e}")
            self._notify_callbacks('error', str(e))

    def _on_authenticator_serials_update(self, serials: List[str]):
        """兼容回调：当前由authenticator_update承载完整数据"""
        return

    def register_device_source(self, source: IDeviceDetector):
        """注册设备探测器"""
        if not source:
            raise ValueError("source cannot be None")
        self._detectors.append(source)

    def add_callback(self, event_type: str, callback: Callable):
        """添加回调函数"""
        if event_type in self._callbacks:
            self._callbacks[event_type].append(callback)

    def remove_callback(self, event_type: str, callback: Callable):
        """移除回调函数"""
        if event_type in self._callbacks and callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)

    def _notify_callbacks(self, event_type: str, data=None):
        """通知回调函数"""
        for callback in self._callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logging.error(f"回调函数执行失败: {e}")

    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                self._update_device_info()

                now = time.time()
                if now - self._last_cube_refresh_time >= self.cube_refresh_interval:
                    self.refresh_all_cube()
                    self._last_cube_refresh_time = now

                time.sleep(self.refresh_interval)
            except Exception as e:
                logging.error(f"设备监控异常: {e}")
                self._notify_callbacks('error', str(e))
                time.sleep(self.refresh_interval)
    def update_devices(self):
        """手动更新设备信息"""
        pass
    def _update_device_info(self):
        """更新设备信息：Detector上报增删，仅将变化同步到parser"""
        try:
            logging.debug("正在更新设备信息...")
            all_added = []
            all_removed = []
            for detector in self._detectors:
                name = detector.get_name()
                try:
                    change = detector.poll_changes()
                except Exception as source_error:
                    logging.error(f"探测器 {name} poll_changes 失败: {source_error}")
                    continue

                if not change.added and not change.removed:
                    continue

                if change.added:
                    logging.info(f"探测器 {name}: +{len(change.added)} 设备: {[d.serial for d in change.added]}")
                if change.removed:
                    logging.info(f"探测器 {name}: -{len(change.removed)} 设备: {change.removed}")

                for d in change.added:
                    if not d.detection_method:
                        d.detection_method = name
                    self._connected_index[d.serial] = d
                    all_added.append(d)
                for serial in change.removed:
                    self._connected_index.pop(serial, None)
                    all_removed.append(serial)

            # 仅将增删变化同步到parser
            if all_added or all_removed:
                self.device_parser.sync_connected_devices(
                    added_devices=all_added,
                    removed_serials=all_removed,
                )

        except Exception as e:
            logging.error(f"更新设备信息失败: {e}")
            raise

    def _get_authenticator_info(self, serial: str) -> Optional[AuthenticatorInfo]:
        """获取激活盒子详细信息"""
        try:
            result = self.adb_manager.get_authenticator_snapshot(serial)
            if result.success:
                auth_info = self.adb_manager.parse_snapshot_data(result.raw_output)
                auth_info.serial = serial
                return auth_info
        except Exception as e:
            logging.error(f"获取激活盒子信息失败 [{serial}]: {e}")
        return None

    def _has_authenticators_changed(self, new_authenticators: Dict[str, AuthenticatorInfo]) -> bool:
        """检查激活盒子信息是否有变化"""
        if set(self.authenticators.keys()) != set(new_authenticators.keys()):
            return True

        for serial, new_info in new_authenticators.items():
            if serial not in self.authenticators:
                return True

            old_info = self.authenticators[serial]
            if (old_info.expired_date != new_info.expired_date or
                old_info.counter != new_info.counter or
                old_info.authorized_device_num != new_info.authorized_device_num or
                old_info.device_status != new_info.device_status):
                return True

        return False

    def _has_devices_changed(self, new_devices: List[DeviceInfo]) -> bool:
        """检查设备列表是否有变化"""
        if len(self.target_devices) != len(new_devices):
            return True

        # 创建设备映射进行比较
        old_devices_map = {d.serial: d for d in self.target_devices}
        new_devices_map = {d.serial: d for d in new_devices}

        if set(old_devices_map.keys()) != set(new_devices_map.keys()):
            return True

        for serial, new_device in new_devices_map.items():
            if serial not in old_devices_map:
                return True

            old_device = old_devices_map[serial]
            logging.warning(f"Comparing device {serial}: old status {old_device.status}, new status {new_device.status}")
            if (old_device.status != new_device.status or
                old_device.uuid != new_device.uuid):
                return True

        return False

    def get_authenticator_status_description(self, device_status: int) -> Dict[str, bool]:
        """获取激活盒子状态描述"""
        status_bits = {
            'locked': bool(device_status & 0x01),        # bit 0: 锁定状态
            'frozen': bool(device_status & 0x02),        # bit 1: 冻结状态
            'temp_lock_support': bool(device_status & 0x04)  # bit 2: 临时锁定支持
        }
        return status_bits

    def get_expiration_status(self, expired_date_str: str) -> str:
        """获取过期状态"""
        try:
            # 假设日期格式为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
            if not expired_date_str:
                return "unknown"

            # 尝试解析不同的日期格式
            date_formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%Y/%m/%d %H:%M:%S']
            expired_date = None

            for fmt in date_formats:
                try:
                    expired_date = datetime.strptime(expired_date_str, fmt)
                    break
                except ValueError:
                    continue

            if expired_date is None:
                return "unknown"

            # 转换为北京时间（假设输入已经是北京时间）
            now = datetime.now()
            time_diff = expired_date - now

            if time_diff.total_seconds() <= 0:
                return "expired"  # 已过期
            elif time_diff.days <= self.config.getint('Expiration_Warning', 'warning_days', 7):
                return "warning"  # 即将过期
            else:
                return "normal"   # 正常

        except Exception as e:
            logging.error(f"解析过期时间失败: {e}")
            return "unknown"

    def refresh_devices(self):
        """手动刷新全部设备（用户按钮触发）"""
        try:
            with self.device_parser._lock:
                devices = (
                    [(serial, dev) for serial, dev in self.device_parser._ready_queue.items()] +
                    [(serial, dev) for serial, dev in self.device_parser._await_queue.items()]
                )
            for _, d in devices:
                d.markDirty()
            self.device_parser.kick_trigger()
        except Exception as e:
            logging.error(f"手动刷新设备失败: {e}")

    def mark_all_devices_dirty(self):
        """标记全部设备dirty并kick parser刷新"""
        self.refresh_devices()

    def mark_device_dirty(self, serial: str):
        """标记单个设备dirty并kick parser刷新"""
        target = self._get_target_from_parser(str(serial))
        if target is not None:
            target.markDirty(lambda serial=str(serial): self.device_parser.kick_trigger(serial))

    def reparse_device(self, serial: str):
        """激活后重新获取设备状态：保留当前状态进入await，解析器重新拉取后更新"""
        self.device_parser.reparse_device(serial)

    def update_device_status(self, serial: str, new_status: str):
        """立即更新设备状态并通知UI"""
        # 同时更新parser中的TargetDeviceAbstract对象
        target = self._get_target_from_parser(str(serial))
        if target is not None:
            target.setStatus(new_status)
        for device in self.target_devices:
            if device.serial == serial:
                device.status = str(new_status or "")
                break
        self._notify_callbacks('device_update', self.target_devices)

    def refresh_all_device(self):
        """刷新所有设备解析状态：ready->await"""
        self.device_parser.refresh_all_device()

    def refresh_all_cube(self):
        """刷新全部authenticator信息"""
        self.device_parser.refresh_all_cube()
        self._on_authenticator_serials_update(self.device_parser.get_authenticator_serials())

    def get_ready_devices(self) -> List[DeviceInfo]:
        """获取已解析完成设备"""
        return self.device_parser.get_ready_devices()

    def get_device_by_serial(self, serial: str) -> Optional[DeviceInfo]:
        """根据序列号获取设备信息"""
        for device in self.target_devices:
            if device.serial == serial:
                return device
        return None

    def get_authenticator_by_serial(self, serial: str) -> Optional[AuthenticatorInfo]:
        """根据序列号获取激活盒子信息"""
        return self.authenticators.get(serial)

    def get_target_device(self, serial: str):
        """根据serial获取ITargetDevice"""
        serial = str(serial or "").strip()
        target = self._get_target_from_parser(serial)
        if target is not None:
            return target
        target = ITargetDevice.CreateAdbDevice(serial, self.adb_manager)
        if isinstance(target, AC8267Device):
            return target
        if target is not None:
            return target
        return AC8267Device(
            serial_number=serial,
            adb_manager=self.adb_manager,
            uuid="",
            status="Unknown",
        )

    def _get_target_from_parser(self, serial: str):
        """从parser的ready/await队列中查找TargetDeviceAbstract"""
        with self.device_parser._lock:
            devices = list(self.device_parser._ready_queue.values()) + list(self.device_parser._await_queue.values())
        for d in devices:
            if d.getSerialNumber() == serial:
                return d
        return None

    def get_device_auth_status(self, serial: str) -> str:
        """获取设备认证状态（统一处理真实/模拟设备）"""
        target = self._get_target_from_parser(str(serial))
        if target is not None:
            return target.getStatus()
        try:
            result = self.adb_manager.get_device_state(serial)
            if result.success:
                return result.result_data
            return "Unknown"
        except Exception:
            return "Error"

    def _find_detector(self, name: str) -> Optional[IDeviceDetector]:
        """按名称查找detector"""
        for d in self._detectors:
            if d.get_name() == name:
                return d
        return None

    def add_simulated_device(self, status: str, uuid: str = "", serial_number: str = "",
                             simulate_activate_failure: bool = False) -> DeviceInfo:
        """创建模拟设备，由SimulatorDetector通过poll_changes上报"""
        sim_det = self._find_detector("Simulator")
        if sim_det is None:
            raise RuntimeError("SimulatorDeviceDetector not found")
        device_info = sim_det.add_device(status, uuid=uuid, serial_number=serial_number,
                                           simulate_activate_failure=simulate_activate_failure)
        return device_info

    def remove_simulated_device(self, serial: str) -> bool:
        """移除模拟设备并同步刷新 detector→parser→UI"""
        serial = str(serial or "").strip()
        if not serial:
            return False
        sim_det = self._find_detector("Simulator")
        if sim_det is None:
            return False
        if hasattr(sim_det, "get_device") and sim_det.get_device(serial) is None:
            return False
        sim_det.remove_device(serial)
        self._update_device_info()
        return True

    def is_simulated_cube(self, serial: str) -> bool:
        return str(serial or "") in self._simulated_cubes

    def get_simulated_cube_infos(self) -> Dict[str, AuthenticatorInfo]:
        return {serial: cube.to_authenticator_info() for serial, cube in self._simulated_cubes.items()}

    def create_simulated_cube(self, expired_date: str, counter: int, private_key_path: str,
                              cube_id: str, oem_id: str, persist_path: str) -> str:
        if not private_key_path or not os.path.exists(private_key_path):
            raise ValueError("P256私钥路径无效")
        if not persist_path:
            raise ValueError("持久化路径不能为空")
        self._simulated_cube_counter += 1
        serial = f"SIM-CUBE-{self._simulated_cube_counter:04d}"
        config = SimulateCubeConfig(
            serial=serial,
            cube_id=str(cube_id or serial),
            oem_id=str(oem_id or ""),
            expired_date=str(expired_date or ""),
            counter=max(int(counter), 0),
            private_key_path=str(private_key_path),
            persist_path=str(persist_path),
        )
        cube = SimulateCube.create(config)
        self._simulated_cubes[serial] = cube
        self.authenticators[serial] = cube.to_authenticator_info()
        return serial

    def load_simulated_cube(self, persist_path: str, private_key_path: str) -> str:
        if not persist_path or not os.path.exists(persist_path):
            raise ValueError("Cube持久化路径无效")
        if not private_key_path or not os.path.exists(private_key_path):
            raise ValueError("P256私钥路径无效")
        self._simulated_cube_counter += 1
        serial = f"SIM-CUBE-{self._simulated_cube_counter:04d}"
        cube = SimulateCube.load(persist_path=persist_path, private_key_path=private_key_path,
                                 serial_override=serial)
        self._simulated_cubes[serial] = cube
        self.authenticators[serial] = cube.to_authenticator_info()
        return serial
