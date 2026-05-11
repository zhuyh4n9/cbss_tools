import copy
import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .adb_manager import ADBManager, DeviceInfo
from .target_device import ITargetDevice, SimulatorDevice


class IDeviceDetector(ABC):
    """设备探测器抽象基类（替代原DeviceSource）"""

    @abstractmethod
    def get_name(self) -> str:
        pass

    def start(self):
        pass

    def stop(self):
        pass

    @abstractmethod
    def poll_devices(self) -> List[DeviceInfo]:
        pass

    @abstractmethod
    def poll_changes(self) -> 'DeviceChange':
        """返回设备增删变化 (added, removed)，而非全量列表"""
        pass


@dataclass
class DeviceChange:
    added: List[DeviceInfo] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)


# 保留兼容别名
DeviceSource = IDeviceDetector


class AdbDeviceDetector(IDeviceDetector):
    """ADB设备探测器"""

    def __init__(self, adb_manager: ADBManager):
        self._adb_manager = adb_manager
        self._last_serials: Set[str] = set()
        self._initial_poll_done = False

    def get_name(self) -> str:
        return "Adb"

    def poll_devices(self) -> List[DeviceInfo]:
        out: List[DeviceInfo] = []
        for device in self._adb_manager.get_connected_devices():
            copied = copy.deepcopy(device)
            copied.detection_method = copied.detection_method or self.get_name()
            out.append(copied)
        return out

    def poll_changes(self) -> DeviceChange:
        """对比上次轮询结果，返回增删变化"""
        current_devices = self.poll_devices()
        current_serials = {d.serial for d in current_devices}

        if not self._initial_poll_done:
            # 首次轮询：所有当前设备视为新增
            self._initial_poll_done = True
            self._last_serials = current_serials
            return DeviceChange(added=list(current_devices), removed=[])

        added_serials = current_serials - self._last_serials
        removed_serials = self._last_serials - current_serials

        added = [d for d in current_devices if d.serial in added_serials]
        removed = list(removed_serials)

        self._last_serials = current_serials
        return DeviceChange(added=added, removed=removed)


# 保留兼容别名
AdbDeviceSource = AdbDeviceDetector


class SimulatorDeviceDetector(IDeviceDetector):
    """模拟设备探测器，维护增删事件和设备列表"""

    # 模块级存储: serial -> simulate_activate_failure, 供device_parser._to_target_device使用
    _sim_failure_flags: Dict[str, bool] = {}

    def __init__(self):
        self._devices: Dict[str, SimulatorDevice] = {}
        self._counter = 0
        self._lock = threading.Lock()
        self._pending_added: List[DeviceInfo] = []
        self._pending_removed: List[str] = []

    def get_name(self) -> str:
        return "Simulator"

    def poll_devices(self) -> List[DeviceInfo]:
        with self._lock:
            return [d.to_device_info() for d in self._devices.values()]

    def poll_changes(self) -> DeviceChange:
        """返回待处理的增删事件，消费后清空"""
        with self._lock:
            added = list(self._pending_added)
            removed = list(self._pending_removed)
            self._pending_added.clear()
            self._pending_removed.clear()
        return DeviceChange(added=added, removed=removed)

    def add_device(self, status: str, uuid: str = "", serial_number: str = "",
                   simulate_activate_failure: bool = False) -> DeviceInfo:
        """创建模拟设备，加入pending队列和设备列表"""
        normalized_status = _normalize_sim_status(status)
        with self._lock:
            self._counter += 1
            serial = serial_number.strip() if serial_number.strip() else f"SIM-{self._counter:04d}"
            sim_uuid = uuid.strip() if uuid.strip() else secrets.token_hex(32)
            device = ITargetDevice.CreateSimulation(
                status=normalized_status,
                serial_number=serial,
                uuid=sim_uuid,
                simulate_activate_failure=simulate_activate_failure,
            )
            if not isinstance(device, SimulatorDevice):
                raise RuntimeError("模拟设备创建失败")
            self._devices[serial] = device
            SimulatorDeviceDetector._sim_failure_flags[serial] = simulate_activate_failure
            device_info = device.to_device_info()
            self._pending_added.append(device_info)
        return device_info

    def get_device(self, serial: str) -> Optional[SimulatorDevice]:
        with self._lock:
            return self._devices.get(str(serial or ""))

    def remove_device(self, serial: str):
        """上报移除事件"""
        with self._lock:
            if str(serial or "") in self._devices:
                self._devices.pop(str(serial))
                SimulatorDeviceDetector._sim_failure_flags.pop(str(serial), None)
                self._pending_removed.append(str(serial))


def _normalize_sim_status(status: str) -> str:
    from .build_options import SIMULATED_DEVICE_STATUS_OPTIONS
    status_input = (status or "").strip().lower()
    status_map = {item.lower(): item for item in SIMULATED_DEVICE_STATUS_OPTIONS}
    return status_map.get(status_input, "Unauthorized")
