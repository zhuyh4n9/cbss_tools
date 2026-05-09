import json
import tempfile
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from src.adb_manager import CommandResult, AuthenticatorInfo
from src.auth_manager import AuthenticationManager
from src.cube import SimulateCube, SimulateCubeConfig


class _FakeConfig:
    def getboolean(self, section, key, default=False):
        return False


class _FakeDeviceParser:
    def add_callback(self, event_type, callback):
        pass


class _FakeDeviceMonitor:
    def __init__(self):
        self.config = _FakeConfig()
        self.device_parser = _FakeDeviceParser()
        self.authenticators = {"REAL-001": AuthenticatorInfo(serial="REAL-001", time_status="Ready")}
        self.refresh_all_cube_calls = 0

    def refresh_all_cube(self):
        self.refresh_all_cube_calls += 1

    def refresh_device(self, serial: str):
        pass

    def get_ready_devices(self):
        return []

    def get_device_by_serial(self, serial: str):
        return None

    def get_authenticator_by_serial(self, serial: str):
        return self.authenticators.get(serial)


class _FakeAdbManager:
    def __init__(self):
        self.sign_calls = 0

    def get_device_uuid(self, serial: str):
        return CommandResult(success=True, status_code=0, result_data="ab" * 32, raw_output="")

    def activate_device(self, serial: str, signature: str):
        return CommandResult(success=True, status_code=0, result_data="ok", raw_output="")

    def get_device_state(self, serial: str):
        return CommandResult(success=True, status_code=0, result_data="Authorized", raw_output="")

    def authenticator_sign(self, authenticator_serial: str, uuid: str):
        self.sign_calls += 1
        return CommandResult(success=True, status_code=0, result_data="00" * 64, raw_output="")


class TestSimulateCube(unittest.TestCase):
    def test_simulate_cube_signs_uuid_with_p256_raw_signature(self):
        private_key = ec.generate_private_key(ec.SECP256R1())
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/p256.pem"
            persist_path = f"{tmpdir}/cube.json"
            with open(key_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )

            cube = SimulateCube.create(
                SimulateCubeConfig(
                    serial="SIM-CUBE-0001",
                    cube_id="CUBE-1",
                    oem_id="OEM-A",
                    expired_date="2099-12-31",
                    counter=2,
                    private_key_path=key_path,
                    persist_path=persist_path,
                )
            )
            uuid_hex = "11" * 32
            before_info = cube.to_authenticator_info()
            result = cube.sign_uuid(uuid_hex)

            self.assertTrue(result.success)
            self.assertEqual(len(result.result_data), 128)

            sig_raw = bytes.fromhex(result.result_data)
            der_sig = encode_dss_signature(
                int.from_bytes(sig_raw[:32], byteorder="big"),
                int.from_bytes(sig_raw[32:], byteorder="big"),
            )
            private_key.public_key().verify(
                der_sig,
                bytes.fromhex(uuid_hex),
                ec.ECDSA(utils.Prehashed(hashes.SHA256())),
            )

            with open(persist_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self.assertEqual(payload["counter"], before_info.counter - 1)
            self.assertEqual(payload["authorized_device_num"], before_info.authorized_device_num + 1)

    def test_auth_manager_can_create_load_and_use_simulated_cube(self):
        private_key = ec.generate_private_key(ec.SECP256R1())
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/p256.pem"
            persist_path = f"{tmpdir}/cube.json"
            with open(key_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )

            manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=_FakeDeviceMonitor())
            serial = manager.create_simulated_cube(
                expired_date="2099-12-31",
                counter=3,
                private_key_path=key_path,
                cube_id="CUBE-2",
                oem_id="OEM-B",
                persist_path=persist_path,
            )
            self.assertIn(serial, manager.get_available_authenticators())
            self.assertTrue(manager.perform_cube_operation("activate", serial, "deadbeef").success)

            result = manager._perform_authentication("DEV-001", serial)
            self.assertTrue(result["success"])

            manager2 = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=_FakeDeviceMonitor())
            loaded_serial = manager2.load_simulated_cube(persist_path=persist_path, private_key_path=key_path)
            self.assertIn(loaded_serial, manager2.get_simulated_cube_infos())


if __name__ == "__main__":
    unittest.main()
