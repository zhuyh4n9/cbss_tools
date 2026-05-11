import unittest

from src.device_parser import DeviceParser
from src.target_device import ITargetDevice


class _FakeAdbManager:
    pass


class TestDeviceParserAwaitDevice(unittest.TestCase):
    def test_make_await_device_keeps_simulator_status_and_uuid(self):
        parser = DeviceParser(adb_manager=_FakeAdbManager())
        simulated = ITargetDevice.CreateSimulation(
            status="Unauthorized",
            serial_number="SIM-PARSER-0001",
            uuid="UUID-PARSER-0001",
        )
        simulated.activate("dummy")

        await_device = parser._make_await_device(simulated)

        self.assertEqual(await_device.getUuid(), "UUID-PARSER-0001")
        self.assertEqual(await_device.getStatus(), "Authorized")


if __name__ == "__main__":
    unittest.main()
