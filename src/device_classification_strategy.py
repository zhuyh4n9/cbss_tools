from dataclasses import dataclass
from typing import Optional

from .adb_manager import ADBManager
from .target_device import AC8267Device, ITargetDevice, TargetDeviceAbstract, UnknownAdbDevice, UnknownDevice


@dataclass
class ClassificationDecision:
    ready_device: Optional[TargetDeviceAbstract]
    should_add_cube: bool = False
    should_mark_unknown: bool = False


class DeviceClassificationStrategy:
    def __init__(self, adb_manager: ADBManager):
        self._adb_manager = adb_manager

    def classify_device(self, serial: str, base_device: TargetDeviceAbstract, known_cube: bool, parser_kick=None) -> ClassificationDecision:
        if known_cube:
            return ClassificationDecision(ready_device=None, should_add_cube=False, should_mark_unknown=False)

        if base_device.getDetectionMethod().lower() == "adb" and not base_device.is_simulation:
            detected_device = ITargetDevice.CreateAdbDevice(
                serial_number=serial,
                adb_manager=self._adb_manager,
                usb_port=base_device.getConnectedUsbPort(),
            )
            if isinstance(detected_device, AC8267Device):
                return ClassificationDecision(ready_device=detected_device)

            if isinstance(detected_device, UnknownAdbDevice):
                snapshot = self._adb_manager.get_authenticator_snapshot(serial)
                if snapshot.success:
                    return ClassificationDecision(ready_device=None, should_add_cube=True)
                return ClassificationDecision(ready_device=None, should_add_cube=False, should_mark_unknown=True)

        # 模拟设备：创建SimulatorDevice，从detector获取simulate_activate_failure标志
        if base_device.is_simulation:
            from .device_source import SimulatorDeviceDetector
            failure_flag = SimulatorDeviceDetector._sim_failure_flags.get(serial, False)
            sim_device = ITargetDevice.CreateSimulation(
                status=base_device.getStatus() or "Unauthorized",
                serial_number=serial,
                uuid=base_device.getUuid() if base_device.getUuid() else None,
                simulate_activate_failure=failure_flag,
            )
            return ClassificationDecision(ready_device=sim_device)

        return ClassificationDecision(ready_device=UnknownDevice(
            detection_method=base_device.getDetectionMethod(),
            serial_number=base_device.getSerialNumber(),
            is_simulation=base_device.is_simulation,
            usb_port=base_device.getConnectedUsbPort(),
        ))

    def refresh_await_device(self, serial: str, current_device: TargetDeviceAbstract) -> TargetDeviceAbstract:
        if current_device.getDetectionMethod().lower() == "adb" and not current_device.is_simulation:
            return ITargetDevice.CreateAdbDevice(
                serial_number=serial,
                adb_manager=self._adb_manager,
                usb_port=current_device.getConnectedUsbPort(),
            )
        return current_device.clone()
