"""
设备监控管理器
负责定期监控和更新设备状态信息
"""
import threading
import time
import logging
from typing import List, Dict, Callable, Optional
from datetime import datetime, timedelta
from .adb_manager import ADBManager, DeviceInfo, AuthenticatorInfo
from .device_parser import DeviceParser
from .build_options import ENABLE_SIMULATED_DEVICE, SIMULATED_DEVICE_STATUS_OPTIONS
from .device_source import DeviceSource, AdbDeviceSource, SimulationDeviceSource
from .target_device import ITargetDevice, SimulatorDevice


class DeviceMonitor:
    def __init__(self, adb_manager: ADBManager, config_manager):
        self.adb_manager = adb_manager
        self.config = config_manager

        self.authenticators: Dict[str, AuthenticatorInfo] = {}
        self.target_devices: List[DeviceInfo] = []
        self.unknown_devices: List[DeviceInfo] = []
        self._connected_index: Dict[str, DeviceInfo] = {}
        self._device_sources: Dict[str, DeviceSource] = {
            'Adb': AdbDeviceSource(self.adb_manager)
        }
        self._simulated_devices: Dict[str, SimulatorDevice] = {}
        self._simulated_counter = 0
        self._simulated_lock = threading.Lock()
        if self.is_simulated_device_enabled():
            self.register_device_source(SimulationDeviceSource(self.get_simulated_devices))

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
            'error': []
        }

        self.refresh_rate = self.config.getint('General', 'refresh_rate', 1)
        self.refresh_interval = 1.0 / max(self.refresh_rate, 1)
        self.cube_refresh_interval = max(self.config.getint('General', 'cube_refresh_interval', 5), 1)
        self._last_cube_refresh_time = 0.0

    @staticmethod
    def _device_signature(device: DeviceInfo):
        return (
            device.serial,
            device.status,
            device.usb_port,
            device.detection_method,
            device.is_simulation,
        )

    def _has_connected_index_changed(self, new_connected_index: Dict[str, DeviceInfo]) -> bool:
        if set(self._connected_index.keys()) != set(new_connected_index.keys()):
            return True
        for serial, new_device in new_connected_index.items():
            old_device = self._connected_index.get(serial)
            if old_device is None:
                return True
            if self._device_signature(old_device) != self._device_signature(new_device):
                return True
        return False

    def _collect_connected_changes(self, new_connected_index: Dict[str, DeviceInfo]):
        changed = []
        for serial in sorted(set(self._connected_index.keys()) & set(new_connected_index.keys())):
            old_device = self._connected_index[serial]
            new_device = new_connected_index[serial]
            if self._device_signature(old_device) != self._device_signature(new_device):
                changed.append((old_device, new_device))
        return changed

    def start_monitoring(self):
        """开始设备监控"""
        if self._running:
            return
        for source in self._device_sources.values():
            source.start()
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
        for source in self._device_sources.values():
            source.stop()
        self.device_parser.stop(join_timeout=join_timeout)
        logging.info("设备监控已停止")

    def _on_device_parser_update(self, devices: List[DeviceInfo]):
        """接收设备解析结果并透传给UI"""
        self.target_devices = devices
        self._notify_callbacks('device_update', self.target_devices)

    def _on_authenticator_update(self, authenticators: Dict[str, AuthenticatorInfo]):
        """接收CubeManager透传的authenticator信息并更新UI"""
        try:
            if self._has_authenticators_changed(authenticators):
                self.authenticators = authenticators
                self._notify_callbacks('authenticator_update', self.authenticators)
            else:
                self.authenticators = authenticators
        except Exception as e:
            logging.error(f"更新激活盒子信息失败: {e}")
            self._notify_callbacks('error', str(e))

    def _on_authenticator_serials_update(self, serials: List[str]):
        """兼容回调：当前由authenticator_update承载完整数据"""
        return

    def register_device_source(self, source: DeviceSource):
        """注册设备来源（当前默认支持ADB，可扩展UART等）"""
        if not source:
            raise ValueError("source cannot be None")
        name = str(source.get_name() or "").strip() or "Unknown"
        self._device_sources[name] = source

    def add_callback(self, event_type: str, callback: Callable):
        """添加回调函数"""
        if event_type in self._callbacks:
            self._callbacks[event_type].append(callback)

    def is_simulated_device_enabled(self) -> bool:
        return ENABLE_SIMULATED_DEVICE

    @staticmethod
    def create_simulated_target_device(status: str, serial_number: str = "") -> SimulatorDevice:
        status_input = (status or "").strip().lower()
        status_map = {item.lower(): item for item in SIMULATED_DEVICE_STATUS_OPTIONS}
        normalized_status = status_map.get(status_input, "Unauthorized")
        if status_input and status_input not in status_map:
            logging.warning("收到未知模拟设备状态，已回退为Unauthorized: %s", status)

        serial = (serial_number or "").strip() or "SIM-AUTO"
        device = ITargetDevice.CreateSimulation(
            status=normalized_status,
            serial_number=serial,
        )
        if not isinstance(device, SimulatorDevice):
            raise RuntimeError("模拟设备创建失败")
        return device

    @staticmethod
    def create_simulated_device(monitor: "DeviceMonitor", status: str) -> DeviceInfo:
        if monitor is None:
            raise ValueError("monitor cannot be None")
        return monitor.add_simulated_device(status)

    def is_simulated_device(self, serial: str) -> bool:
        serial = str(serial or "")
        with self._simulated_lock:
            return serial in self._simulated_devices

    def get_simulated_devices(self) -> List[DeviceInfo]:
        with self._simulated_lock:
            return [device.to_device_info() for device in self._simulated_devices.values()]

    def get_simulated_device(self, serial: str) -> Optional[SimulatorDevice]:
        serial = str(serial or "")
        with self._simulated_lock:
            return self._simulated_devices.get(serial)

    def add_simulated_device(self, status: str) -> DeviceInfo:
        if not self.is_simulated_device_enabled():
            raise RuntimeError("模拟设备功能未启用")

        with self._simulated_lock:
            self._simulated_counter += 1
            serial = f"SIM-{self._simulated_counter:04d}"
            device = self.create_simulated_target_device(status=status, serial_number=serial)
            self._simulated_devices[serial] = device
        logging.info(
            "已添加模拟设备: serial=%s, status=%s, uuid_ready=%s",
            serial,
            device.getStatus(),
            bool(device.getUuid()),
        )
        return device.to_device_info()

    def remove_simulated_device(self, serial: str) -> bool:
        serial = str(serial or "").strip()
        if not serial:
            return False

        with self._simulated_lock:
            removed = self._simulated_devices.pop(serial, None)
        if not removed:
            return False

        logging.info("已移除模拟设备: serial=%s", serial)
        self._update_device_info()
        return True

    def get_target_device(self, serial: str):
        serial = str(serial or "").strip()
        if not serial:
            return None
        with self._simulated_lock:
            simulated = self._simulated_devices.get(serial)
            if simulated:
                return simulated.clone()

        getter = getattr(self.device_parser, "get_target_device", None)
        if callable(getter):
            return getter(serial)
        return None

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
        self._update_device_info()
    def _update_device_info(self):
        """更新设备信息"""
        try:
            logging.debug("正在更新设备信息...")
            previous_serials = set(self._connected_index.keys())
            devices = []
            for source_name, source in self._device_sources.items():
                try:
                    source_devices = source.poll_devices() or []
                    if source_devices:
                        logging.info(f"设备探测来源[{source_name}]发现设备: {len(source_devices)}")
                    for device in source_devices:
                        if not device.detection_method:
                            device.detection_method = source_name
                        devices.append(device)
                except Exception as source_error:
                    logging.error(f"设备来源 {source_name} 轮询失败: {source_error}")
            # 设备监控仅负责插拔同步，设备类型辨别与目标设备解析由device_parser负责
            new_connected_index = {d.serial: d for d in devices}
            current_serials = set(new_connected_index.keys())
            added = sorted(current_serials - previous_serials)
            removed = sorted(previous_serials - current_serials)
            changed = self._collect_connected_changes(new_connected_index)
            if added or removed:
                logging.info(
                    "设备连接变化: 新增=%s, 移除=%s, 当前总数=%d",
                    added or "[]",
                    removed or "[]",
                    len(current_serials),
                )
            if changed:
                for old_device, new_device in changed:
                    logging.info(
                        "设备状态变化: serial=%s, status=%s->%s, usb_port=%s->%s, detection=%s",
                        new_device.serial,
                        old_device.status,
                        new_device.status,
                        old_device.usb_port,
                        new_device.usb_port,
                        new_device.detection_method,
                    )
            if self._has_connected_index_changed(new_connected_index):
                self._connected_index = new_connected_index
                self.device_parser.sync_connected_devices(list(new_connected_index.values()))
            else:
                logging.debug("设备连接状态无变化，跳过TargetDevice重新解析")

            # 激活盒子详情由DeviceParser内部CubeManager更新并回调

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
        """手动刷新设备信息"""
        try:
            self._update_device_info()
            self.refresh_all_device()
        except Exception as e:
            logging.error(f"手动刷新设备失败: {e}")

    def refresh_device(self, serial: str):
        """刷新单个设备解析状态：ready->await"""
        self.device_parser.refresh_device(serial)

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
