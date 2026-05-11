import copy
from abc import ABC, abstractmethod
from typing import Callable, List

from .adb_manager import ADBManager, DeviceInfo


class DeviceSource(ABC):
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


class AdbDeviceSource(DeviceSource):
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


class SimulationDeviceSource(DeviceSource):
    """DeviceSource that polls simulated target devices from a callback provider."""

    def __init__(self, provider: Callable[[], List[DeviceInfo]]):
        self._provider = provider

    def get_name(self) -> str:
        return "Simulation"

    def poll_devices(self) -> List[DeviceInfo]:
        out: List[DeviceInfo] = []
        devices = self._provider() if self._provider else []
        for device in devices or []:
            copied = copy.deepcopy(device)
            copied.detection_method = copied.detection_method or self.get_name()
            copied.is_simulation = True
            out.append(copied)
        return out
