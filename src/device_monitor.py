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


class DeviceMonitor:
    def __init__(self, adb_manager: ADBManager, config_manager):
        self.adb_manager = adb_manager
        self.config = config_manager

        self.authenticators: Dict[str, AuthenticatorInfo] = {}
        self.target_devices: List[DeviceInfo] = []
        self.unknown_devices: List[DeviceInfo] = []
        self._connected_index: Dict[str, DeviceInfo] = {}

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

    def start_monitoring(self):
        """开始设备监控"""
        if self._running:
            return
        self.device_parser.start()
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logging.info("设备监控已启动")

    def stop_monitoring(self):
        """停止设备监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        self.device_parser.stop()
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
        self._update_device_info()
    def _update_device_info(self):
        """更新设备信息"""
        try:
            logging.debug("正在更新设备信息...")
            # 获取连接的设备列表
            devices = self.adb_manager.get_connected_devices()
            # 设备监控仅负责插拔同步，设备类型辨别与目标设备解析由device_parser负责
            new_connected_index = {d.serial: d for d in devices}
            self._connected_index = new_connected_index
            self.device_parser.sync_connected_devices(list(new_connected_index.values()))

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
