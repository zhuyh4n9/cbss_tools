import copy
import secrets
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

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


# 保留兼容别名
DeviceSource = IDeviceDetector


class AdbDeviceDetector(IDeviceDetector):
    """ADB设备探测器"""

    def __init__(self, adb_manager: ADBManager):
        self._adb_manager = adb_manager

    def get_name(self) -> str:
        return "Adb"

    def poll_devices(self) -> List[DeviceInfo]:
        out: List[DeviceInfo] = []
        for device in self._adb_manager.get_connected_devices():
            copied = copy.deepcopy(device)
            copied.detection_method = copied.detection_method or self.get_name()
            out.append(copied)
        return out


# 保留兼容别名
AdbDeviceSource = AdbDeviceDetector


class SimulatorDeviceDetector(IDeviceDetector):
    """模拟设备探测器，管理所有模拟设备"""

    def __init__(self):
        self._devices: Dict[str, SimulatorDevice] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def get_name(self) -> str:
        return "Simulator"

    def poll_devices(self) -> List[DeviceInfo]:
        with self._lock:
            return [d.to_device_info() for d in self._devices.values()]

    def add_device(self, status: str) -> DeviceInfo:
        """创建并添加一个模拟设备"""
        normalized_status = _normalize_sim_status(status)
        with self._lock:
            self._counter += 1
            serial = f"SIM-{self._counter:04d}"
            device = ITargetDevice.CreateSimulation(
                status=normalized_status,
                serial_number=serial,
                uuid=secrets.token_hex(32),
            )
            if not isinstance(device, SimulatorDevice):
                raise RuntimeError("模拟设备创建失败")
            self._devices[serial] = device

        return device.to_device_info()

    def get_device(self, serial: str) -> Optional[SimulatorDevice]:
        with self._lock:
            return self._devices.get(str(serial or ""))

    def update_device_status(self, serial: str, new_status: str):
        with self._lock:
            device = self._devices.get(str(serial or ""))
            if device is not None:
                device.setStatus(new_status)


def _normalize_sim_status(status: str) -> str:
    from .build_options import SIMULATED_DEVICE_STATUS_OPTIONS
    status_input = (status or "").strip().lower()
    status_map = {item.lower(): item for item in SIMULATED_DEVICE_STATUS_OPTIONS}
    return status_map.get(status_input, "Unauthorized")
