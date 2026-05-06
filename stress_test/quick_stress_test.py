#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证器快速压力测试脚本
用于快速验证设备的基本功能和性能
"""

import os
import sys
import time
import random
import logging
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key, Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric import utils
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.bindings.openssl import binding

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.adb_manager import ADBManager
    from src.config_manager import ConfigManager
    from src.device_monitor import DeviceMonitor
    from src.log_manager import LogManager
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)


class QuickStressTester:
    """快速压力测试器"""

    def __init__(self):
        self.config = ConfigManager()
        self.adb_manager = ADBManager(self.config)
        self.device_monitor = DeviceMonitor(self.adb_manager, self.config)
        # 快速测试配置
        self.quick_sign_tests = 10000      # 快速测试签名次数
        self.diagnostic_trigger = 0      # 每50次触发诊断（测试用）

        self.log_mgr = LogManager(self.config)
        self.log_mgr.setup_logging()
        self.pubkey_dir = os.path.join(os.path.dirname(__file__), "pubkey")
        self.load_public_key()

    def get_authenticator_devices(self):
        """获取认证器设备"""
        try:
            logging.info("正在刷新设备列表...")
            self.device_monitor.refresh_devices()
            devices = list(self.device_monitor.authenticators.keys())

            if not devices:
                logging.error("未检测到认证器设备")
                logging.info("提示: 如果没有真实设备，可以运行调试版本:")
                logging.info("python stress_test/quick_stress_debug.py")
                return []

            logging.info(f"检测到认证器设备: {devices}")
            return devices
        except Exception as e:
            logging.error(f"获取设备失败: {e}")
            logging.info("建议: 运行调试版本进行功能验证:")
            logging.info("python stress_test/quick_stress_debug.py")
            return []

    def generate_uuid(self):
        """生成随机UUID"""
        return ''.join(random.choices('0123456789abcdef', k=64))
    def load_public_key(self) -> bool:
        """加载P256公钥"""

        pub_key_path = os.path.join(self.pubkey_dir, "pub.pem")

        try:
            with open(pub_key_path, 'rb') as f:
                self.public_key = load_pem_public_key(f.read())
            logging.info(f"成功加载公钥: {pub_key_path}")
            return True
        except Exception as e:
            logging.error(f"加载公钥失败: {e}")
            return False

    def verify_signature(self, uuid_hex: str, signature_hex: str, prehashed = True) -> bool:
        """验证签名（RAW格式，不计算hash）"""
        try:
            # 将hex字符串转换为字节
            uuid_bytes = bytes.fromhex(uuid_hex)
            signature_raw = bytes.fromhex(signature_hex)

            # P256 RAW签名应该是64字节 (32字节r + 32字节s)
            if len(signature_raw) != 64:
                logging.warning(f"RAW签名长度异常: 期望64字节，实际{len(signature_raw)}字节")
                return False

            r = int.from_bytes(signature_raw[:32], byteorder='big')
            s = int.from_bytes(signature_raw[32:], byteorder='big')

            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
            der_signature = encode_dss_signature(r, s)

            if prehashed:
                algo = ec.ECDSA(utils.Prehashed(hashes.SHA256()))
            else:
                algo = ec.ECDSA(hashes.SHA256())
            # 验证签名（使用Prehashed，不计算hash）
            self.public_key.verify(
                der_signature,
                uuid_bytes,
                algo)
            return True
        except Exception as e:
            logging.error(f"signature: {signature_hex}")
            logging.error(f"uuid: {uuid_hex}")
            logging.info(f"签名验证失败: {e}")
            return False

    def test_sign_command(self, device: str, count: int):
        """测试签名命令"""
        logging.info(f"开始测试设备 {device} 的签名命令 ({count} 次)")

        success_count = 0
        total_time = 0

        for i in range(count):
            uuid = self.generate_uuid()
            start_time = time.time()

            # 每10次显示一次进度
            if (i + 1) % 10 == 0:
                logging.info(f"执行签名测试 #{i+1}/{count}: UUID={uuid[:16]}...")

            try:
                result = self.adb_manager.authenticator_sign(device, uuid)
                duration = time.time() - start_time
                total_time += duration
                if result.success:
                    if self.verify_signature(uuid, result.result_data):
                        success_count += 1
                        if i < 5:
                            logging.info(f"签名成功 #{i+1}: 用时 {duration:.3f}s")
                    else:
                        logging.warning(f"签名失败 #{i+1}: {result.error_message}")
                else:
                    logging.warning(f"签名失败 #{i+1}: {result.error_message}")

            except Exception as e:
                duration = time.time() - start_time
                total_time += duration
                logging.error(f"签名异常 #{i+1}: {e}")

            # 每50次报告一次进度
            if (i + 1) % 50 == 0:
                progress = (i + 1) / count * 100
                avg_time = total_time / (i + 1)
                current_success_rate = (success_count / (i + 1)) * 100
                logging.info(f"进度: {progress:.1f}% - 成功: {success_count}/{i+1} ({current_success_rate:.1f}%) - 平均时间: {avg_time:.3f}s")

        # 测试结果
        success_rate = (success_count / count) * 100
        avg_time = total_time / count

        logging.info("=" * 50)
        logging.info(f"签名测试完成:")
        logging.info(f"  总次数: {count}")
        logging.info(f"  成功次数: {success_count}")
        logging.info(f"  成功率: {success_rate:.2f}%")
        logging.info(f"  总时间: {total_time:.2f}s")
        logging.info(f"  平均时间: {avg_time:.3f}s")
        logging.info("=" * 50)

        return success_count, success_rate, avg_time

    def verify_diagnostic_sign(self, device: str, prefix: str) -> bool:
        """验证diagnostic签名"""
        try:
            # 获取diagnostic文件列表
            files = self.adb_manager.list_diagnostic_files(device, prefix)
            if not files:
                logging.error(f"未找到前缀为 {prefix} 的diagnostic文件")
                return False

            # 查找签名文件
            sign_file = None
            data_files = []

            for filename in files:
                if filename.endswith('_prof.sign'):
                    sign_file = filename
                elif '_' in filename and filename.split('_')[-1].isdigit():
                    data_files.append(filename)

            if not sign_file:
                logging.error(f"未找到签名文件 {prefix}_prof.sign")
                return False

            if not data_files:
                logging.error(f"未找到数据文件 {prefix}_0, {prefix}_1 等")
                return False

            # 按序号排序数据文件
            data_files.sort(key=lambda x: int(x.split('_')[-1]))
            logging.info(f"找到数据文件: {data_files}")
            logging.info(f"找到签名文件: {sign_file}")

            # 下载签名文件
            local_sign_path = os.path.join("logs/", sign_file)
            remote_sign_path = f"/sdcard/CbssDiagnostic/{sign_file}"
            logging.info(f"local_sign_path: {local_sign_path}")
            if not self.adb_manager.pull_file(device, remote_sign_path, local_sign_path):
                logging.error(f"下载签名文件失败: {sign_file}")
                return False

            # 读取签名
            try:
                with open(local_sign_path, 'rb') as f:
                    signature_data = f.read()
                signature_hex = signature_data.hex()
                logging.info(f"签名长度: {len(signature_data)} 字节")
            except Exception as e:
                logging.error(f"读取签名文件失败: {e}")
                return False

            # 按顺序计算所有数据文件的hash
            import hashlib
            hasher = hashlib.sha256()

            for data_file in data_files:
                # 下载数据文件
                local_data_path = os.path.join("logs/", data_file)
                remote_data_path = f"/sdcard/CbssDiagnostic/{data_file}"
                logging.info(f"local_data_path: {local_data_path}")
                if not self.adb_manager.pull_file(device, remote_data_path, local_data_path):
                    logging.error(f"下载数据文件失败: {data_file}")
                    return False

                # 读取并添加到hash计算中
                try:
                    with open(local_data_path, 'rb') as f:
                        file_data = f.read()
                    hasher.update(file_data)
                    logging.info(f"添加文件到hash计算: {data_file} ({len(file_data)} 字节)")

                    # 清理临时文件
                    # os.remove(local_data_path)
                except Exception as e:
                    logging.error(f"处理数据文件失败 {data_file}: {e}")
                    return False

            # 获取最终hash
            final_hash = hasher.digest()
            final_hash_hex = final_hash.hex()
            logging.info(f"计算得到的hash: {final_hash_hex}")

            # 验证签名
            result = self.verify_signature(final_hash_hex, signature_hex, prehashed=True)

            # 清理签名文件
            # os.remove(local_sign_path)

            if result:
                logging.info(f"Diagnostic签名验证成功: {prefix}")
            else:
                logging.error(f"Diagnostic签名验证失败: {prefix}")

            return result

        except Exception as e:
            logging.error(f"验证diagnostic签名异常: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False

    def test_diagnostic_command(self, device: str, diag_type: str):
        """测试诊断命令"""
        logging.info(f"测试诊断命令: {diag_type}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"quick_{diag_type}_{timestamp}"

        start_time = time.time()

        try:
            if diag_type == "token":
                result = self.adb_manager.diagnostic_token(device, prefix)
            elif diag_type == "trusted_service":
                result = self.adb_manager.diagnostic_trusted_service(device, prefix)
            elif diag_type == "authorization":
                result = self.adb_manager.diagnostic_authorization(device, prefix)
            else:
                logging.error(f"不支持的诊断类型: {diag_type}")
                return False

            duration = time.time() - start_time

            if result.success:
                logging.info(f"诊断命令 {diag_type} 成功 (用时: {duration:.3f}s)")                # 等待文件生成
                time.sleep(2)

                # 检查生成的文件
                files = self.adb_manager.list_diagnostic_files(device, prefix)
                logging.info(f"生成文件数: {len(files)}")

                # 验证签名
                signature_verified = False
                try:
                    signature_verified = self.verify_diagnostic_sign(device, prefix)
                    if signature_verified:
                        logging.info(f"诊断签名验证成功: {diag_type}")
                    else:
                        logging.warning(f"诊断签名验证失败: {diag_type}")
                except Exception as e:
                    logging.error(f"诊断签名验证异常: {e}")

                # 清理文件
                for filename in files:
                    remote_path = f"/sdcard/CbssDiagnostic/{filename}"
                    self.adb_manager.remove_file(device, remote_path)

                return signature_verified
            else:
                logging.error(f"诊断命令 {diag_type} 失败: {result.error_message}")
                return False

        except Exception as e:
            duration = time.time() - start_time
            logging.error(f"诊断命令 {diag_type} 异常: {e}")
            return False

    def run_quick_test(self):
        """运行快速测试"""
        logging.info("=" * 60)
        logging.info("=== 开始快速压力测试 ===")
        logging.info("=" * 60)
        logging.info(f"测试配置: {self.quick_sign_tests}次签名, 每{self.diagnostic_trigger}次触发诊断")

        # 获取设备
        logging.info("正在检测认证器设备...")
        devices = self.get_authenticator_devices()
        if not devices:
            logging.error("未检测到任何认证器设备，测试终止")
            logging.info("请检查:")
            logging.info("1. 设备是否已连接")
            logging.info("2. ADB是否可以访问设备")
            logging.info("3. 设备是否为认证器类型")
            return

        # 测试每个设备
        for device_idx, device in enumerate(devices, 1):
            logging.info("")
            logging.info("*" * 50)
            logging.info(f"开始测试设备 {device_idx}/{len(devices)}: {device}")
            logging.info("*" * 50)

            try:
                # 1. 签名压力测试
                logging.info("第1步: 执行签名压力测试")
                success_count, success_rate, avg_time = self.test_sign_command(
                    device, self.quick_sign_tests
                )

                # 2. 诊断命令测试
                if success_count >= self.diagnostic_trigger:
                    logging.info("第2步: 执行诊断命令测试")
                    diagnostic_types = ["token", "trusted_service", "authorization"]

                    for diag_type in diagnostic_types:
                        logging.info(f"测试诊断类型: {diag_type}")
                        self.test_diagnostic_command(device, diag_type)
                        time.sleep(1)  # 间隔1秒
                else:
                    logging.warning(f"签名测试成功率过低 ({success_rate:.2f}%)，跳过诊断测试")

            except Exception as e:
                logging.error(f"测试设备 {device} 时发生异常: {e}")
                import traceback
                logging.error(f"异常详情: {traceback.format_exc()}")

        logging.info("")
        logging.info("=" * 60)
        logging.info("=== 快速压力测试完成 ===")
        logging.info("=" * 60)


def main():
    """主函数"""
    print("CBSS认证器快速压力测试")
    print("=" * 40)

    try:
        tester = QuickStressTester()
        tester.run_quick_test()

        print("\n测试完成！查看详细日志请检查 stress_log/ 目录")

    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
