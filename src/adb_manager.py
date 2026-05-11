"""
ADB通信模块
负责与设备进行ADB通信，执行各种ADB命令
"""
import subprocess
import logging
import re
import os
import shlex
import sys
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

# Windows平台下隐藏CMD窗口
if sys.platform == 'win32':
    import subprocess
    # 设置创建标志以隐藏CMD窗口
    CREATE_NO_WINDOW = 0x08000000
    SUBPROCESS_FLAGS = CREATE_NO_WINDOW
else:
    SUBPROCESS_FLAGS = 0


@dataclass
class DeviceInfo:
    """设备信息数据类"""
    serial: str
    status: str
    device_type: str = "unknown"  # authenticator, target_device, unknown
    uuid: str = ""
    usb_port: str = ""
    detection_method: str = "Unknown"
    is_simulation: bool = False


@dataclass
class AuthenticatorInfo:
    """激活盒子信息数据类"""
    serial: str
    expired_date: str = ""
    counter: int = 0
    authorized_device_num: int = 0
    device_status: int = 0
    time_status: str = ""
    raw_data: str = ""


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    status_code: int
    result_data: str = ""
    error_message: str = ""
    raw_output: str = ""


class ADBManager:
    def __init__(self, config_manager):
        self.config = config_manager
        self.adb_path = self.config.get('General', 'adb_path', 'adb')
        # 确保ADB路径是绝对路径
        if not os.path.isabs(self.adb_path):
            self.adb_path = os.path.abspath(self.adb_path)

    def execute_adb_command(self, command: str, serial: str = None) -> CommandResult:
        """执行ADB命令"""
        try:
            # 使用shlex.split以保留引号参数（Windows使用posix=False）
            args = shlex.split(command, posix=False)

            # 构建完整的ADB命令
            if serial:
                full_command = [self.adb_path, '-s', serial] + args
            else:
                full_command = [self.adb_path] + args
            
            logging.debug(f"执行ADB命令: {' '.join(full_command)}")

            # 执行命令（Windows下隐藏CMD窗口）
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=240,  # for diagnostic, this operation may extremely long...
                creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
            )

            output = result.stdout + result.stderr
            logging.debug(f"ADB命令输出: {output}")

            return self._parse_command_output(output, result.returncode == 0)

        except subprocess.TimeoutExpired:
            error_msg = "ADB命令执行超时"
            logging.error(error_msg)
            return CommandResult(False, 1, error_message=error_msg)
        except Exception as e:
            error_msg = f"执行ADB命令失败: {str(e)}"
            logging.error(error_msg)
            return CommandResult(False, 1, error_message=error_msg)

    def _parse_command_output(self, output: str, command_success: bool) -> CommandResult:
        """解析命令输出"""
        status_code = 0
        result_data = ""
        error_message = ""

        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('[status]'):
                # 解析状态行
                status_match = re.match(r'\[status\]\s+(-?\d+)(?:,\s*(.+))?', line)
                if status_match:
                    status_code = int(status_match.group(1))
                    if status_match.group(2):
                        error_message = status_match.group(2)
            elif line.startswith('[result]'):
                # 解析结果行
                result_match = re.match(r'\[result\]\s+(.+)', line)
                if result_match:
                    result_data = result_match.group(1)

        # 检测命令执行错误（命令未找到等）
        error_patterns = [
            'not found',
            'No such file',
            'No such command',
            'command not found',
            'can\'t execute',
            'cannot execute',
            'Permission denied'
        ]
        
        output_lower = output.lower()
        for pattern in error_patterns:
            if pattern.lower() in output_lower:
                command_success = False
                if not error_message:
                    error_message = f"命令执行失败: {pattern}"
                break

        success = (status_code == 0) and command_success
        # logging.info(f"命令执行结果 - Success: {success}, Status Code: {status_code}, Result: {result_data}, Error: {error_message}")
        # 如果没有明确的错误消息，使用配置中的状态消息
        if not success and not error_message:
            error_message = self.config.get_status_message(str(status_code))

        return CommandResult(
            success=success,
            status_code=status_code,
            result_data=result_data,
            error_message=error_message,
            raw_output=output
        )

    def get_connected_devices(self) -> List[DeviceInfo]:
        """获取连接的设备列表"""
        try:
            result = subprocess.run(
                [self.adb_path, 'devices', '-l'],
                capture_output=True,
                text=True,
                creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
            )

            devices = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line and not line.startswith('List of devices'):
                    __parts = line.split(' ')
                    parts = []
                    for part in __parts:
                        part = part.strip()
                        if part:
                            parts.append(part)
                    if len(parts) >= 2:
                        serial = parts[0]
                        status = parts[1]
                        usb_port = ""
                        for part in parts[1:]:
                            if part.startswith('usb:'):
                                usb_port = part.split(':', 1)[1].strip()
                                break
                        devices.append(DeviceInfo(serial=serial, status=status, usb_port=usb_port, detection_method="Adb"))
            return devices

        except Exception as e:
            logging.error(f"获取设备列表失败: {str(e)}")
            return []

    def get_device_uuid(self, serial: str) -> CommandResult:
        """获取设备UUID"""
        command = self.config.get_adb_command('device_uuid')
        logging.debug(f"Getting device UUID with command: {command} {serial}")
        return self.execute_adb_command(command, serial)

    def get_device_state(self, serial: str) -> CommandResult:
        """获取设备激活状态"""
        command = self.config.get_adb_command('device_state')
        result = self.execute_adb_command(command, serial)

        # 特殊处理state命令的结果
        if result.success and result.result_data:
            result.result_data  = result.result_data.strip()

        return result

    def activate_device(self, serial: str, sign_hex: str) -> CommandResult:
        """激活设备"""
        command = self.config.get_adb_command('device_activate', sign=sign_hex)
        return self.execute_adb_command(command, serial)

    def get_authenticator_snapshot(self, serial: str) -> CommandResult:
        """获取激活盒子快照信息"""
        command = self.config.get_adb_command('authenticator_snapshot')
        return self.execute_adb_command(command, serial)

    def authenticator_sign(self, serial: str, uuid: str) -> CommandResult:
        """激活盒子签名"""
        command = self.config.get_adb_command('authenticator_sign', uuid=uuid)
        return self.execute_adb_command(command, serial)

    def authenticator_lock(self, serial: str, token_hex: str) -> CommandResult:
        """锁定激活盒子"""
        command = self.config.get_adb_command('authenticator_lock', token=token_hex)
        return self.execute_adb_command(command, serial)

    def authenticator_unlock(self, serial: str, token_hex: str) -> CommandResult:
        """解锁激活盒子"""
        command = self.config.get_adb_command('authenticator_unlock', token=token_hex)
        return self.execute_adb_command(command, serial)

    def authenticator_activate(self, serial: str, token_hex: str) -> CommandResult:
        """激活激活盒子"""
        command = self.config.get_adb_command('authenticator_activate', token=token_hex)
        return self.execute_adb_command(command, serial)

    def authenticator_config(self, serial: str, config_hex: str) -> CommandResult:
        """配置激活盒子"""
        command = self.config.get_adb_command('authenticator_config', config=config_hex)
        return self.execute_adb_command(command, serial)    # ------------------ WiFi 操作 ------------------
    def wifi_enable(self, serial: str) -> CommandResult:
        """开启设备WiFi（station）"""
        command = self.config.get_adb_command('wifi_enable')
        return self.execute_adb_command(command, serial)
    
    def wifi_disable(self, serial: str) -> CommandResult:
        """关闭设备WiFi（station）"""
        command = self.config.get_adb_command('wifi_disable')
        return self.execute_adb_command(command, serial)
    
    def wifi_connect(self, serial: str, ssid: str, password: str = '', security: str = 'wpa2') -> CommandResult:
        """
        连接到指定WiFi网络
        
        Args:
            serial: 设备序列号
            ssid: WiFi名称
            password: WiFi密码（Open类型时可为空）
            security: 加密方式 ('wpa2', 'wpa3', 'open')
            
        Returns:
            CommandResult: 执行结果
        """
        # 规范化security
        sec = (security or 'wpa2').strip().lower()
        
        # 支持open类型（不需要密码）
        if sec == 'open' or sec == 'none':
            command = self.config.get_adb_command('wifi_connect_open', ssid=ssid)
        else:
            # wpa2/wpa3需要密码
            if sec not in ('wpa2', 'wpa3'):
                sec = 'wpa2'
            command = self.config.get_adb_command('wifi_connect', ssid=ssid, password=password, security=sec)
        
        return self.execute_adb_command(command, serial)

    def wifi_scan(self, serial: str) -> CommandResult:
        """扫描WiFi热点"""
        import time
        
        # 确保WiFi已开启
        enable_result = self.wifi_enable(serial)
        if not enable_result.success:
            return CommandResult(
                success=False,
                status_code=1,
                error_message="无法开启WiFi"
            )
        
        # 启动扫描
        scan_command = self.config.get_adb_command('wifi_start_scan')
        scan_result = self.execute_adb_command(scan_command, serial)
        
        if not scan_result.success:
            return CommandResult(
                success=False,
                status_code=1,
                error_message="WiFi扫描启动失败"
            )
        
        # 等待扫描完成
        time.sleep(2)
        
        # 获取扫描结果
        results_command = self.config.get_adb_command('wifi_list_scan_results')
        results = self.execute_adb_command(results_command, serial)
        
        return results

    def wifi_get_status(self, serial: str) -> CommandResult:
        """获取当前WiFi连接状态"""
        command = self.config.get_adb_command('wifi_status')
        return self.execute_adb_command(command, serial)

    def parse_wifi_status(self, raw_output: str) -> Dict[str, str]:
        """
        解析WiFi状态信息
        
        Returns:
            Dict with keys:
            - enabled: WiFi是否开启 (true/false)
            - connected: 是否已连接 (true/false)
            - ssid: 当前连接的SSID
            - bssid: 当前连接的BSSID
            - frequency: 频率
            - rssi: 信号强度
        """
        status = {
            'enabled': 'false',
            'connected': 'false',
            'ssid': '',
            'bssid': '',
            'frequency': '',
            'rssi': ''
        }
        
        lines = raw_output.strip().split('\n')
        for line in lines:
            line = line.strip()
            
            if 'Wifi is' in line:
                if 'enabled' in line.lower():
                    status['enabled'] = 'true'
                elif 'disabled' in line.lower():
                    status['enabled'] = 'false'
            
            elif line.startswith('Wifi is connected to'):
                # 格式: Wifi is connected to "SSID"
                status['connected'] = 'true'
                # 提取SSID (在引号之间)
                import re
                ssid_match = re.search(r'"([^"]+)"', line)
                if ssid_match:
                    status['ssid'] = ssid_match.group(1)
                    
            elif 'BSSID:' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    status['bssid'] = parts[1].strip()
                    
            elif 'Frequency:' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    freq_str = parts[1].strip()
                    # 提取数字部分
                    import re
                    freq_match = re.search(r'(\d+)', freq_str)
                    if freq_match:
                        status['frequency'] = freq_match.group(1)
                        
            elif 'RSSI:' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    rssi_str = parts[1].strip()
                    # 提取数字部分 (可能是负数)
                    import re
                    rssi_match = re.search(r'(-?\d+)', rssi_str)
                    if rssi_match:
                        status['rssi'] = rssi_match.group(1)
        
        return status

    def get_current_wifi(self, serial: str) -> Dict[str, str]:
        """
        获取当前连接的WiFi信息
        
        Returns:
            Dict with keys:
            - connected: bool - 是否已连接WiFi
            - ssid: WiFi名称
            - bssid: MAC地址
            - frequency: 频率
            - signal: 信号强度
            - link_speed: 链接速度
            - band: 频段 (2.4G/5G)
            - signal_level: 信号等级
        """
        status_command = self.config.get_adb_command('wifi_status')
        result = self.execute_adb_command(status_command, serial)
        
        wifi_info = {
            'connected': False,
            'ssid': 'Not Connected',
            'bssid': '',
            'frequency': '',
            'signal': '',
            'link_speed': '',
            'band': '',
            'signal_level': ''
        }
        
        if not result.success:
            return wifi_info
        
        # 解析输出 - 新格式: WifiInfo: SSID: xxx, BSSID: xxx, ...
        output = result.raw_output
        
        # 检查是否已连接
        if 'Wifi is connected to' in output or 'WifiInfo:' in output:
            wifi_info['connected'] = True
            
            # 提取整个WifiInfo行
            wifiinfo_match = re.search(r'WifiInfo:(.+)', output, re.IGNORECASE)
            if wifiinfo_match:
                wifiinfo_line = wifiinfo_match.group(1)
                
                # 解析SSID
                ssid_match = re.search(r'SSID:\s*([^,]+)', wifiinfo_line)
                if ssid_match:
                    ssid = ssid_match.group(1).strip()
                    wifi_info['ssid'] = ssid
                    
                    # 修复中文乱码
                    if any(ord(c) > 127 for c in ssid):
                        for src_encoding, dst_encoding in [
                            ('latin1', 'utf-8'),
                            ('gbk', 'utf-8'),
                            ('gb2312', 'utf-8'),
                        ]:
                            try:
                                decoded = ssid.encode(src_encoding).decode(dst_encoding, errors='ignore')
                                if decoded and any('\u4e00' <= c <= '\u9fff' for c in decoded):
                                    wifi_info['ssid'] = decoded
                                    break
                            except:
                                continue
                
                # 解析BSSID
                bssid_match = re.search(r'BSSID:\s*([0-9a-fA-F:]+)', wifiinfo_line)
                if bssid_match:
                    wifi_info['bssid'] = bssid_match.group(1)
                
                # 解析信号强度 (RSSI)
                rssi_match = re.search(r'RSSI:\s*(-?\d+)', wifiinfo_line)
                if rssi_match:
                    signal = int(rssi_match.group(1))
                    wifi_info['signal'] = str(signal)
                    
                    # 判断信号等级
                    if signal >= -50:
                        wifi_info['signal_level'] = "优秀"
                    elif signal >= -70:
                        wifi_info['signal_level'] = "良好"
                    elif signal >= -85:
                        wifi_info['signal_level'] = "一般"
                    else:
                        wifi_info['signal_level'] = "差"
                
                # 解析频率
                freq_match = re.search(r'Frequency:\s*(\d+)MHz', wifiinfo_line)
                if freq_match:
                    freq = int(freq_match.group(1))
                    wifi_info['frequency'] = str(freq)
                    
                    # 判断频段
                    if 2400 <= freq <= 2500:
                        wifi_info['band'] = "2.4G"
                    elif 5000 <= freq <= 6000:
                        wifi_info['band'] = "5G"
                
                # 解析链接速度
                speed_match = re.search(r'Link speed:\s*(\d+)Mbps', wifiinfo_line)
                if speed_match:
                    wifi_info['link_speed'] = f"{speed_match.group(1)}Mbps"
        
        return wifi_info

    def parse_wifi_scan_results(self, raw_output: str) -> List[Dict[str, str]]:
        """
        解析WiFi扫描结果
        输出格式: BSSID Frequency RSSI Age(sec) SSID [Flags]
        
        Returns:
            List of wifi networks with keys:
            - ssid: WiFi名称
            - bssid: MAC地址
            - frequency: 频率
            - signal: 信号强度
            - security: 加密方式
            - band: 频段 (2.4G/5G)
            - signal_level: 信号等级 (优秀/良好/一般/差)
        """
        networks = []
        lines = raw_output.strip().split('\n')
        
        # 解析格式: BSSID Frequency RSSI Age SSID [Flags]
        # Flags可能在同一行或下一行
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            # 跳过空行和标题行
            if not line or 'BSSID' in line or 'Frequency' in line:
                continue
            
            # 尝试解析: BSSID Frequency RSSI Age SSID [Flags]
            parts = line.split()
            if len(parts) < 5:
                continue
            
            # 提取字段
            bssid = parts[0]
            frequency = parts[1]
            signal = parts[2]
            # parts[3] 是 Age(sec)，跳过
            
            # SSID从索引4开始，直到遇到[或行尾
            ssid_parts = []
            capabilities = ""
            
            for j in range(4, len(parts)):
                if parts[j].startswith('['):
                    capabilities = ' '.join(parts[j:])
                    break
                else:
                    ssid_parts.append(parts[j])
            
            ssid_raw = ' '.join(ssid_parts) if ssid_parts else "Unknown"
            
            # 修复中文乱码问题 - 尝试多种编码方式
            ssid = ssid_raw
            if any(ord(c) > 127 for c in ssid_raw):
                # 尝试多种编码转换
                for src_encoding, dst_encoding in [
                    ('latin1', 'utf-8'),
                    ('gbk', 'utf-8'),
                    ('gb2312', 'utf-8'),
                    ('cp936', 'utf-8'),
                ]:
                    try:
                        decoded = ssid_raw.encode(src_encoding).decode(dst_encoding, errors='ignore')
                        # 检查是否包含可打印的中文字符
                        if decoded and any('\u4e00' <= c <= '\u9fff' for c in decoded):
                            ssid = decoded
                            break
                    except:
                        continue
            
            # 如果下一行以[开始，追加capabilities
            if i < len(lines) and lines[i].strip().startswith('['):
                if capabilities:
                    capabilities += ' ' + lines[i].strip()
                else:
                    capabilities = lines[i].strip()
                i += 1
            
            # 判断频段
            try:
                freq_int = int(frequency)
                if 2400 <= freq_int <= 2500:
                    band = "2.4G"
                elif 5000 <= freq_int <= 6000:
                    band = "5G"
                else:
                    band = "Unknown"
            except ValueError:
                band = "Unknown"
            
            # 判断信号强度等级
            try:
                signal_int = int(signal)
                if signal_int >= -50:
                    signal_level = "优秀"
                elif signal_int >= -70:
                    signal_level = "良好"
                elif signal_int >= -85:
                    signal_level = "一般"
                else:
                    signal_level = "差"
            except ValueError:
                signal_level = "未知"
            
            # 判断加密方式
            security = "Open"
            if "SAE" in capabilities or "WPA3" in capabilities:
                security = "WPA3"
            elif "RSN" in capabilities or "WPA2" in capabilities:
                security = "WPA2"
            elif "WPA" in capabilities:
                security = "WPA"
            elif "WEP" in capabilities:
                security = "WEP"
            
            networks.append({
                'ssid': ssid,
                'bssid': bssid,
                'frequency': frequency,
                'signal': signal,
                'security': security,
                'band': band,
                'signal_level': signal_level,
                'raw_capabilities': capabilities
            })
        
        # 按信号强度排序（从强到弱）
        try:
            networks.sort(key=lambda x: int(x['signal']), reverse=True)
        except:
            pass
        
        # 同名WiFi去重，保留信号最强的
        unique_networks = []
        seen_ssids = set()
        
        for network in networks:
            ssid = network['ssid']
            if ssid not in seen_ssids:
                seen_ssids.add(ssid)
                unique_networks.append(network)
        
        return unique_networks

    # ------------------ 诊断日志操作 (NEW in Update 2) ------------------
    def diagnostic_token(self, serial: str, prefix: str) -> CommandResult:
        """获取token诊断日志"""
        command = self.config.get_adb_command('diagnostic_token', prefix=prefix)
        return self.execute_adb_command(command, serial)

    def diagnostic_trusted_service(self, serial: str, prefix: str) -> CommandResult:
        """获取TA诊断信息"""
        command = self.config.get_adb_command('diagnostic_trusted_service', prefix=prefix)
        return self.execute_adb_command(command, serial)

    def diagnostic_authorization(self, serial: str, prefix: str) -> CommandResult:
        """获取激活记录"""
        command = self.config.get_adb_command('diagnostic_authorization', prefix=prefix)
        return self.execute_adb_command(command, serial)

    def list_diagnostic_files(self, serial: str, prefix: str) -> List[str]:
        """列出设备上生成的诊断文件"""
        try:
            # 列出/sdcard/CbssDiagnostic/目录下以prefix开头的文件
            result = subprocess.run(
                [self.adb_path, '-s', serial, 'shell', 'ls', f'/sdcard/CbssDiagnostic/{prefix}*'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
            )
            if result.returncode == 0:
                files = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and not line.startswith('ls:'):
                        # 提取文件名（去掉路径前缀）
                        filename = line.split('/')[-1] if '/' in line else line
                        if filename.startswith(prefix):
                            files.append(filename)
                return files
            else:
                logging.warning(f"列出诊断文件失败: {result.stderr}")
                return []
        except Exception as e:
            logging.error(f"列出诊断文件异常: {e}")
            return []

    def pull_file(self, serial: str, remote_path: str, local_path: str) -> bool:
        """从设备拉取文件到本地"""
        try:
            result = subprocess.run(
                [self.adb_path, '-s', serial, 'pull', remote_path, local_path],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
            )

            if result.returncode == 0:
                logging.info(f"文件拉取成功: {remote_path} -> {local_path}")
                return True
            else:
                logging.error(f"文件拉取失败: {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"文件拉取异常: {e}")
            return False

    def remove_file(self, serial: str, remote_path: str) -> bool:
        """删除设备上的文件"""
        try:
            result = subprocess.run(
                [self.adb_path, '-s', serial, 'shell', 'rm', remote_path],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=SUBPROCESS_FLAGS if sys.platform == 'win32' else 0
            )

            if result.returncode == 0:
                logging.info(f"文件删除成功: {remote_path}")
                return True
            else:
                logging.warning(f"文件删除失败: {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"文件删除异常: {e}")
            return False

    def parse_snapshot_data(self, raw_data: str) -> AuthenticatorInfo:
        """解析激活盒子快照数据 - 支持每行都有[result]标记的格式"""
        auth_info = AuthenticatorInfo(serial="")        # 解析命令输出，收集所有[result]行的数据
        lines = raw_data.split('\n')
        result_data = ""
        # 收集所有[result]行的数据，每行单独处理
        result_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('[result]'):
                # 提取[result]后面的数据
                result_part = line[8:].strip()  # 去掉'[result]'前缀
                if result_part:
                    result_lines.append(result_part)

        # 如果没有找到[result]行，尝试解析整个输出
        if not result_lines:
            result_data = raw_data.strip()
            # 对于非[result]格式，按原来的方式处理
            if ',' in result_data:
                fields = [field.strip() for field in result_data.split(',')]
            else:
                field_pattern = r'(\w+):\s*([^\s,]+(?:\s+[^\s,:]+)*)'
                matches = re.findall(field_pattern, result_data)
                fields = [f"{key}:{value.strip()}" for key, value in matches]
        else:
            # 处理[result]行数据
            fields = []
            for result_line in result_lines:
                # 每行可能包含多个字段（逗号分隔）或单个字段
                if ',' in result_line:
                    # 逗号分隔的多个字段
                    line_fields = [field.strip() for field in result_line.split(',')]
                    fields.extend(line_fields)
                else:
                    # 单个字段
                    fields.append(result_line.strip())
        for field in fields:
            if ':' in field:
                key, value = field.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key == 'expired_date':
                    # 将unix时间戳转换为可读日期格式
                    try:
                        timestamp = int(value)
                        # 转换为datetime对象
                        dt = datetime.fromtimestamp(timestamp)
                        # 格式化为可读字符串
                        auth_info.expired_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, OSError) as e:
                        # 如果转换失败，保留原始值
                        logging.warning(f"无法转换expired_date时间戳 {value}: {e}")
                        auth_info.expired_date = value
                elif key == 'counter':
                    try:
                        auth_info.counter = int(value)
                    except ValueError:
                        pass
                elif key == 'authorized_device_num':
                    try:
                        auth_info.authorized_device_num = int(value)
                    except ValueError:
                        pass
                elif key == 'device_status':
                    try:
                        auth_info.device_status = int(value)
                    except ValueError:
                        pass
                elif key == 'time_status':
                    auth_info.time_status = value

        # 保存原始数据
        auth_info.raw_data = raw_data

        return auth_info

    # ------------------ 网络连通性测试 (NEW in Update 4) ------------------
    def ping_host(self, serial: str, host: str, count: int = None, timeout: int = None) -> bool:
        """
        通过adb ping指定主机
        
        Args:
            serial: 设备序列号
            host: 目标主机
            count: ping包数量（从配置读取，默认1）
            timeout: 超时时间（从配置读取，默认3秒）
            
        Returns:
            bool: ping成功返回True，失败返回False
        """
        if count is None:
            count = self.config.getint('Network', 'ping_count', 1)
        if timeout is None:
            timeout = self.config.getint('Network', 'ping_timeout', 3)
            
        try:
            command = self.config.get_adb_command('ping', host=host, count=count, timeout=timeout)
            result = self.execute_adb_command(command, serial)
            
            # 检查输出中是否包含成功标志
            output_lower = result.raw_output.lower()
            success = ("bytes from" in output_lower or 
                      "0% packet loss" in output_lower or
                      "0% loss" in output_lower)

            logging.debug(f"Ping {host}: {'成功' if success else '失败'}")
            return success
        except Exception as e:
            logging.error(f"Ping {host} 失败: {e}")
            return False

    def test_network_connectivity(self, serial: str, hosts: List[str]) -> Dict[str, bool]:
        """
        测试多个主机的连通性
        
        Args:
            serial: 设备序列号
            hosts: 主机列表
            
        Returns:
            Dict[str, bool]: 主机连通性结果字典
        """
        results = {}
        for host in hosts:
            results[host] = self.ping_host(serial, host)
        return results
