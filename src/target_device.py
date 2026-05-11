import copy
import secrets
from abc import ABC, abstractmethod
from typing import Optional

from .adb_manager import ADBManager, CommandResult, DeviceInfo


SUPPORTED_TARGET_STATUSES = {"authorized", "unauthorized", "pirated", "unknown", "authorizationfailure"}


def _normalize_status(status: str) -> str:
    normalized_status = (status or "").strip().lower()
    if normalized_status in SUPPORTED_TARGET_STATUSES:
        if normalized_status == "authorizationfailure":
            return "AuthorizationFailure"
        return normalized_status.capitalize()
    return "Unknown"


class ITargetDevice(ABC):
    @staticmethod
    def CreateSimulation(status: str, serial_number: str = "", uuid: Optional[str] = None,
                         simulate_activate_failure: bool = False):
        serial = (serial_number or "").strip() or "SIM-0000"
        normalized_status = _normalize_status(status)
        simulation_uuid = uuid or secrets.token_hex(32)
        return SimulatorDevice(
            detection_method="Simulation",
            serial_number=serial,
            is_simulation=True,
            uuid=simulation_uuid,
            status=normalized_status,
            usb_port="SIM",
            simulate_activate_failure=simulate_activate_failure,
        )

    @staticmethod
    def CreateAdbDevice(serial_number: str, adb_manager: ADBManager, usb_port: str = ""):
        serial = str(serial_number or "").strip()
        uuid_result = adb_manager.get_device_uuid(serial)
        state_result = adb_manager.get_device_state(serial)

        uuid_success = uuid_result.success
        state_success = state_result.success
        uuid = uuid_result.result_data.strip() if uuid_success and uuid_result.result_data else ""
        status = state_result.result_data.strip() if state_success and state_result.result_data else "Unknown"

        if uuid_success or state_success:
            return AC8267Device(
                serial_number=serial,
                adb_manager=adb_manager,
                uuid=uuid,
                status=status,
                usb_port=usb_port,
            )

        return UnknownAdbDevice(serial_number=serial, adb_manager=adb_manager, usb_port=usb_port, status="Unknown")

    @abstractmethod
    def getType(self) -> str:
        pass

    @abstractmethod
    def getUuid(self) -> str:
        pass

    @abstractmethod
    def activate(self, signature: str) -> CommandResult:
        pass

    @abstractmethod
    def getStatus(self) -> str:
        pass

    @abstractmethod
    def getConnectedUsbPort(self) -> str:
        pass

    @abstractmethod
    def getSerialNumber(self) -> str:
        pass

    @abstractmethod
    def to_device_info(self) -> DeviceInfo:
        pass

    @abstractmethod
    def refreshDeviceMeta(self) -> None:
        """获取设备元信息（uuid/status/port），完成后清除dirty标记"""
        pass

    @abstractmethod
    def markDirty(self, parser_kick=None) -> None:
        """标记设备状态不可信，若未锁定则设为dirty并kick parser刷新"""
        pass

    @abstractmethod
    def lock(self) -> bool:
        """锁定设备，返回是否成功"""
        pass

    @abstractmethod
    def unlock(self, parser_kick=None) -> None:
        """解锁设备，检查待处理dirty事件并kick parser"""
        pass

    @abstractmethod
    def isDirty(self) -> bool:
        pass

    @abstractmethod
    def isLocked(self) -> bool:
        pass


class TargetDeviceAbstract(ITargetDevice, ABC):
    def __init__(
        self,
        detection_method: str,
        serial_number: str,
        is_simulation: bool = False,
        uuid: str = "",
        status: str = "Unknown",
        usb_port: str = "",
    ):
        self.detection_method = str(detection_method or "Unknown")
        self.serial_number = str(serial_number or "")
        self.is_simulation = bool(is_simulation)
        self.uuid = str(uuid or "")
        self.status = _normalize_status(status)
        self.usb_port = str(usb_port or "")
        self._dirty = False
        self._locked = False
        self._pending_dirty = False

    def getType(self) -> str:
        return self.__class__.__name__

    def getUuid(self) -> str:
        return self.uuid

    def getStatus(self) -> str:
        return _normalize_status(self.status)

    def getConnectedUsbPort(self) -> str:
        return self.usb_port

    def getSerialNumber(self) -> str:
        return self.serial_number

    def getDetectionMethod(self) -> str:
        return self.detection_method

    def setUuid(self, uuid: str):
        self.uuid = str(uuid or "")

    def setStatus(self, status: str):
        self.status = _normalize_status(status)

    def setConnectedUsbPort(self, usb_port: str):
        self.usb_port = str(usb_port or "")

    def clone(self):
        return copy.deepcopy(self)

    # ---- Dirty / Lock 状态管理 ----

    def markDirty(self, parser_kick=None) -> None:
        """标记设备状态不可信，若未锁定则设为dirty并kick parser刷新"""
        if self._locked:
            self._pending_dirty = True
            return
        self._dirty = True
        if parser_kick is not None:
            parser_kick()

    def lock(self) -> bool:
        if self._locked:
            return False
        self._locked = True
        return True

    def unlock(self, parser_kick=None) -> None:
        self._locked = False
        if self._pending_dirty:
            self._pending_dirty = False
            self.markDirty(parser_kick)

    def isDirty(self) -> bool:
        return self._dirty

    def isLocked(self) -> bool:
        return self._locked

    def refreshDeviceMeta(self) -> None:
        """默认空实现，子类覆盖"""
        self._dirty = False

    # ---- 原有方法 ----

    def to_device_info(self) -> DeviceInfo:
        device_type = "unknown"
        if isinstance(self, (AC8267Device, SimulatorDevice)):
            device_type = "target_device"
        display_status = (self.status or "").strip() or self.getStatus()
        return DeviceInfo(
            serial=self.getSerialNumber(),
            status=display_status,
            device_type=device_type,
            uuid=self.getUuid() if device_type != "unknown" else "",
            usb_port=self.getConnectedUsbPort(),
            detection_method=self.getDetectionMethod(),
            is_simulation=self.is_simulation,
        )


class IAdbDevice(TargetDeviceAbstract, ABC):
    def __init__(self, serial_number: str, adb_manager: ADBManager, uuid: str = "", status: str = "Unknown", usb_port: str = ""):
        super().__init__(detection_method="Adb", serial_number=serial_number, is_simulation=False, uuid=uuid, status=status, usb_port=usb_port)
        self.adb_manager = adb_manager

    def activate(self, signature: str) -> CommandResult:
        return self.adb_manager.activate_device(self.getSerialNumber(), signature)


class AC8267Device(IAdbDevice):
    def refreshDeviceMeta(self) -> None:
        """通过ADB获取设备元信息"""
        uuid_result = self.adb_manager.get_device_uuid(self.getSerialNumber())
        state_result = self.adb_manager.get_device_state(self.getSerialNumber())
        if uuid_result.success and uuid_result.result_data:
            self.setUuid(uuid_result.result_data.strip())
        if state_result.success and state_result.result_data:
            self.setStatus(state_result.result_data.strip())
        self._dirty = False

    def activate(self, signature: str) -> CommandResult:
        """锁定→激活→markDirty→解锁。失败时标记AuthorizationFailure"""
        if self.isDirty():
            return CommandResult(False, 1, error_message="设备状态不可信，请等待刷新后重试")
        if self.getStatus().lower() == "authorizationfailure":
            return CommandResult(False, 1, error_message="设备处于AuthorizationFailure状态，无法激活")
        if not self.lock():
            return CommandResult(False, 1, error_message="设备已被锁定，请重试")
        try:
            result = super().activate(signature)
            if result.success:
                self.markDirty()
            else:
                self.setStatus("AuthorizationFailure")
            return result
        finally:
            self.unlock()


class UnknownAdbDevice(IAdbDevice):
    def refreshDeviceMeta(self) -> None:
        self._dirty = False

    def activate(self, signature: str) -> CommandResult:
        if self.isDirty():
            return CommandResult(False, 1, error_message="设备状态不可信，请等待刷新后重试")
        return CommandResult(
            success=False,
            status_code=1,
            error_message="UnknownAdbDevice cannot be activated",
            raw_output="",
        )


class SimulatorDevice(TargetDeviceAbstract):
    def __init__(self, detection_method: str, serial_number: str, is_simulation: bool = False,
                 uuid: str = "", status: str = "Unknown", usb_port: str = "",
                 simulate_activate_failure: bool = False):
        super().__init__(
            detection_method=detection_method,
            serial_number=serial_number,
            is_simulation=is_simulation,
            uuid=uuid,
            status=status,
            usb_port=usb_port,
        )
        self.simulate_activate_failure = bool(simulate_activate_failure)

    def refreshDeviceMeta(self) -> None:
        """模拟设备在__init__中已完成元信息设置，此方法不操作"""
        self._dirty = False

    def activate(self, signature: str) -> CommandResult:
        """激活模拟设备"""
        if self.isDirty():
            return CommandResult(False, 1, error_message="设备状态不可信，请等待刷新后重试")
        if self.getStatus().lower() == "authorizationfailure":
            return CommandResult(False, 1, error_message="设备处于AuthorizationFailure状态，无法激活")
        if not self.lock():
            return CommandResult(False, 1, error_message="设备已被锁定，请重试")
        try:
            if self.simulate_activate_failure:
                self.setStatus("AuthorizationFailure")
                return CommandResult(False, 1, error_message="模拟设备激活失败（simulate_activate_failure）", raw_output="")
            if self.getStatus().lower() != "unauthorized":
                return CommandResult(
                    success=False,
                    status_code=1,
                    error_message=f"模拟设备状态非Unauthorized，无法激活: {self.getStatus()}",
                    raw_output="",
                )
            self.setStatus("Authorized")
            return CommandResult(success=True, status_code=0, result_data="Authorized", raw_output="")
        finally:
            self.unlock()


class UnknownDevice(TargetDeviceAbstract):
    def __init__(self, detection_method: str, serial_number: str, is_simulation: bool = False, usb_port: str = ""):
        super().__init__(
            detection_method=detection_method,
            serial_number=serial_number,
            is_simulation=is_simulation,
            uuid="",
            status="Unknown",
            usb_port=usb_port,
        )

    def getUuid(self) -> str:
        return "UnknownDevice"

    def refreshDeviceMeta(self) -> None:
        self._dirty = False

    def activate(self, signature: str) -> CommandResult:
        if self.isDirty():
            return CommandResult(False, 1, error_message="设备状态不可信，请等待刷新后重试")
        return CommandResult(
            success=False,
            status_code=1,
            error_message="UnknownDevice cannot be activated",
            raw_output="",
        )
