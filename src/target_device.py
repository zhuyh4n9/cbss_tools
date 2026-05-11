import copy
import secrets
from abc import ABC, abstractmethod
from typing import Optional

from .adb_manager import ADBManager, CommandResult, DeviceInfo


SUPPORTED_TARGET_STATUSES = {
    "authorized": "Authorized",
    "unauthorized": "Unauthorized",
    "pirated": "Pirated",
    "unknown": "Unknown",
    "authorizationfailure": "AuthorizationFailure",
}


def _normalize_status(status: str) -> str:
    normalized_status = (status or "").strip().lower()
    return SUPPORTED_TARGET_STATUSES.get(normalized_status, "Unknown")


class ITargetDevice(ABC):
    @staticmethod
    def CreateSimulation(
        status: str,
        serial_number: str = "",
        uuid: Optional[str] = None,
        fail_on_activate: bool = False,
        failure_reason: str = "",
    ):
        serial_input = str(serial_number or "").strip()
        serial = serial_input or "SIM-0000"
        normalized_status = _normalize_status(status)
        uuid_input = str(uuid or "").strip()
        simulation_uuid = uuid_input or secrets.token_hex(32)
        return SimulatorDevice(
            detection_method="Simulation",
            serial_number=serial,
            is_simulation=True,
            uuid=simulation_uuid,
            status=normalized_status,
            usb_port="SIM",
            fail_on_activate=bool(fail_on_activate),
            failure_reason=str(failure_reason or ""),
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
    def fetch_uuid(self) -> CommandResult:
        pass

    @abstractmethod
    def fetch_state(self) -> CommandResult:
        pass

    @abstractmethod
    def to_await_device(self):
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

    def fetch_uuid(self) -> CommandResult:
        current_uuid = (self.getUuid() or "").strip()
        if not current_uuid:
            return CommandResult(success=False, status_code=1, error_message="设备UUID为空", raw_output="")
        return CommandResult(success=True, status_code=0, result_data=current_uuid, raw_output=current_uuid)

    def fetch_state(self) -> CommandResult:
        state = (self.getStatus() or "").strip()
        if not state:
            return CommandResult(success=False, status_code=1, error_message="设备状态为空", raw_output="")
        return CommandResult(success=True, status_code=0, result_data=state, raw_output=state)

    def to_await_device(self):
        d = self.clone()
        d.setUuid("")
        d.status = "Checking..."
        return d


class IAdbDevice(TargetDeviceAbstract, ABC):
    def __init__(self, serial_number: str, adb_manager: ADBManager, uuid: str = "", status: str = "Unknown", usb_port: str = ""):
        super().__init__(detection_method="Adb", serial_number=serial_number, is_simulation=False, uuid=uuid, status=status, usb_port=usb_port)
        self.adb_manager = adb_manager

    def activate(self, signature: str) -> CommandResult:
        return self.adb_manager.activate_device(self.getSerialNumber(), signature)

    def fetch_uuid(self) -> CommandResult:
        result = self.adb_manager.get_device_uuid(self.getSerialNumber())
        if result.success and result.result_data:
            self.setUuid(result.result_data)
        return result

    def fetch_state(self) -> CommandResult:
        result = self.adb_manager.get_device_state(self.getSerialNumber())
        if result.success and result.result_data:
            self.setStatus(result.result_data)
        return result


class AC8267Device(IAdbDevice):
    pass


class UnknownAdbDevice(IAdbDevice):
    def activate(self, signature: str) -> CommandResult:
        return CommandResult(
            success=False,
            status_code=1,
            error_message="UnknownAdbDevice cannot be activated",
            raw_output="",
        )


class SimulatorDevice(TargetDeviceAbstract):
    def __init__(
        self,
        detection_method: str,
        serial_number: str,
        is_simulation: bool = True,
        uuid: str = "",
        status: str = "Unknown",
        usb_port: str = "SIM",
        fail_on_activate: bool = False,
        failure_reason: str = "",
    ):
        super().__init__(
            detection_method=detection_method,
            serial_number=serial_number,
            is_simulation=is_simulation,
            uuid=uuid,
            status=status,
            usb_port=usb_port,
        )
        self.fail_on_activate = bool(fail_on_activate)
        self.failure_reason = str(failure_reason or "")

    def activate(self, signature: str) -> CommandResult:
        if self.fail_on_activate:
            reason = self.failure_reason or "模拟设备触发激活失败"
            return CommandResult(
                success=False,
                status_code=2,
                error_message=reason,
                raw_output="SIMULATED_ACTIVATION_FAILURE",
            )
        if self.getStatus().lower() != "unauthorized":
            return CommandResult(
                success=False,
                status_code=1,
                error_message=f"模拟设备状态非Unauthorized，无法激活: {self.getStatus()}",
                raw_output="",
            )
        self.setStatus("Authorized")
        return CommandResult(success=True, status_code=0, result_data="Authorized", raw_output="")

    def to_await_device(self):
        return self.clone()


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

    def activate(self, signature: str) -> CommandResult:
        return CommandResult(
            success=False,
            status_code=1,
            error_message="UnknownDevice cannot be activated",
            raw_output="",
        )

    def fetch_uuid(self) -> CommandResult:
        return CommandResult(
            success=False,
            status_code=1,
            error_message="UnknownDevice UUID unavailable",
            raw_output="",
        )

    def fetch_state(self) -> CommandResult:
        return CommandResult(success=False, status_code=1, error_message="UnknownDevice state unavailable", raw_output="Unknown")
