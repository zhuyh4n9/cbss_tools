import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .adb_manager import ADBManager, AuthenticatorInfo, CommandResult


@dataclass
class SimulateCubeConfig:
    serial: str
    cube_id: str
    oem_id: str
    expired_date: str
    counter: int
    private_key_path: str
    persist_path: str
    authorized_device_num: int = 0


class ICube(ABC):
    @staticmethod
    def CreateSimulation(
        serial: str,
        cube_id: str,
        oem_id: str,
        expired_date: str,
        counter: int,
        private_key_path: str,
        persist_path: str,
        authorized_device_num: int = 0,
    ):
        config = SimulateCubeConfig(
            serial=str(serial or ""),
            cube_id=str(cube_id or ""),
            oem_id=str(oem_id or ""),
            expired_date=str(expired_date or ""),
            counter=max(int(counter or 0), 0),
            private_key_path=str(private_key_path or ""),
            persist_path=str(persist_path or ""),
            authorized_device_num=max(int(authorized_device_num or 0), 0),
        )
        return SimulateCube.create(config)

    @staticmethod
    def LoadSimulation(persist_path: str, private_key_path: str, serial_override: str = ""):
        return SimulateCube.load(
            persist_path=str(persist_path or ""),
            private_key_path=str(private_key_path or ""),
            serial_override=str(serial_override or ""),
        )

    @abstractmethod
    def get_serial(self) -> str:
        pass

    @abstractmethod
    def sign_uuid(self, uuid_hex: str) -> CommandResult:
        pass

    @abstractmethod
    def lock(self, token_hex: str) -> CommandResult:
        pass

    @abstractmethod
    def unlock(self, token_hex: str) -> CommandResult:
        pass

    @abstractmethod
    def activate(self, token_hex: str) -> CommandResult:
        pass

    @abstractmethod
    def config(self, config_hex: str) -> CommandResult:
        pass

    @abstractmethod
    def to_authenticator_info(self) -> AuthenticatorInfo:
        pass


class RealCube(ICube):
    def __init__(self, serial: str, adb_manager: ADBManager):
        self.serial = str(serial)
        self.adb_manager = adb_manager

    def get_serial(self) -> str:
        return self.serial

    def sign_uuid(self, uuid_hex: str) -> CommandResult:
        return self.adb_manager.authenticator_sign(self.serial, uuid_hex)

    def lock(self, token_hex: str) -> CommandResult:
        return self.adb_manager.authenticator_lock(self.serial, token_hex)

    def unlock(self, token_hex: str) -> CommandResult:
        return self.adb_manager.authenticator_unlock(self.serial, token_hex)

    def activate(self, token_hex: str) -> CommandResult:
        return self.adb_manager.authenticator_activate(self.serial, token_hex)

    def config(self, config_hex: str) -> CommandResult:
        return self.adb_manager.authenticator_config(self.serial, config_hex)

    def to_authenticator_info(self) -> AuthenticatorInfo:
        return AuthenticatorInfo(serial=self.serial)


class SimulateCube(ICube):
    def __init__(self, config: SimulateCubeConfig):
        self._config = config

    def get_serial(self) -> str:
        return self._config.serial

    def _read_private_key(self):
        with open(self._config.private_key_path, "rb") as f:
            return load_pem_private_key(f.read(), password=None)

    def _persist(self):
        data = {
            "cube_id": self._config.cube_id,
            "oem_id": self._config.oem_id,
            "expired_date": self._config.expired_date,
            "counter": int(self._config.counter),
            "authorized_device_num": int(self._config.authorized_device_num),
            "serial": self._config.serial,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        parent = os.path.dirname(self._config.persist_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self._config.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def sign_uuid(self, uuid_hex: str) -> CommandResult:
        raw_uuid = (uuid_hex or "").strip().lower()
        if not raw_uuid:
            return CommandResult(False, 1, error_message="UUID is empty")
        if self._config.counter <= 0:
            return CommandResult(False, 1, error_message="No remaining authorization quota")

        try:
            uuid_bytes = bytes.fromhex(raw_uuid)
        except ValueError:
            return CommandResult(False, 1, error_message="UUID must be a valid hex string")

        try:
            key = self._read_private_key()
            # uuid_bytes 在当前协议中即为 32 字节预哈希值，需按 Prehashed 直接签名，避免重复哈希。
            der = key.sign(uuid_bytes, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
            r, s = decode_dss_signature(der)
            signature = (r.to_bytes(32, byteorder="big") + s.to_bytes(32, byteorder="big")).hex()
            self._config.counter -= 1
            self._config.authorized_device_num += 1
            self._persist()
            return CommandResult(True, 0, result_data=signature, raw_output=signature)
        except Exception as e:
            return CommandResult(False, 1, error_message=f"Simulated cube signing failed: {e}")

    def lock(self, token_hex: str) -> CommandResult:
        return CommandResult(True, 0, result_data="ok", raw_output="ok")

    def unlock(self, token_hex: str) -> CommandResult:
        return CommandResult(True, 0, result_data="ok", raw_output="ok")

    def activate(self, token_hex: str) -> CommandResult:
        return CommandResult(True, 0, result_data="ok", raw_output="ok")

    def config(self, config_hex: str) -> CommandResult:
        return CommandResult(True, 0, result_data="ok", raw_output="ok")

    def to_authenticator_info(self) -> AuthenticatorInfo:
        raw_payload = {
            "cube_id": self._config.cube_id,
            "oem_id": self._config.oem_id,
            "counter": self._config.counter,
            "authorized_device_num": self._config.authorized_device_num,
            "expired_date": self._config.expired_date,
            "network_status": "ok",
            "wifi": "SIM-WIFI",
            "mode": "simulate",
        }
        return AuthenticatorInfo(
            serial=self._config.serial,
            expired_date=self._config.expired_date,
            counter=self._config.counter,
            authorized_device_num=self._config.authorized_device_num,
            device_status=0,
            time_status="Ready",
            raw_data=json.dumps(raw_payload, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def create(config: SimulateCubeConfig):
        cube = SimulateCube(config)
        cube._persist()
        return cube

    @staticmethod
    def load(persist_path: str, private_key_path: str, serial_override: str = ""):
        with open(persist_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)

        serial = str(serial_override or data.get("serial") or f"SIM-CUBE-{uuid.uuid4().hex[:8].upper()}")
        config = SimulateCubeConfig(
            serial=serial,
            cube_id=str(data.get("cube_id", "")),
            oem_id=str(data.get("oem_id", "")),
            expired_date=str(data.get("expired_date", "")),
            counter=int(data.get("counter", 0)),
            private_key_path=str(private_key_path),
            persist_path=str(persist_path),
            authorized_device_num=int(data.get("authorized_device_num", 0)),
        )
        cube = SimulateCube(config)
        cube._persist()
        return cube
