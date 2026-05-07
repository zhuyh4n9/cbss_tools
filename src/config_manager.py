"""
配置管理模块
负责加载、保存和管理应用程序配置
"""
import configparser
import os
import logging
from typing import Dict, Any


class ConfigManager:
    def __init__(self, config_file: str = None):
        self.config = configparser.ConfigParser()
        self.config_file = config_file or "config/default_config.ini"
        self.load_config()

    def load_config(self, config_file: str = None):
        """加载配置文件"""
        if config_file:
            self.config_file = config_file

        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file, encoding='utf-8')
                logging.info(f"配置文件已加载: {self.config_file}")
            except Exception as e:
                logging.error(f"加载配置文件失败: {e}")
                # 加载默认配置
                self._load_default_config()
        else:
            logging.warning(f"配置文件不存在: {self.config_file}")
            self._load_default_config()

    def save_config(self, config_file: str = None):
        """保存配置文件"""
        if config_file:
            self.config_file = config_file

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
            logging.info(f"配置文件已保存: {self.config_file}")
            return True
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")
            return False

    def get(self, section: str, key: str, fallback=None):
        """获取配置值"""
        try:
            return self.config.get(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getint(self, section: str, key: str, fallback: int = 0):
        """获取整数配置值"""
        try:
            return self.config.getint(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getfloat(self, section: str, key: str, fallback: float = 0.0):
        """获取浮点数配置值"""
        try:
            return self.config.getfloat(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getboolean(self, section: str, key: str, fallback: bool = False):
        """获取布尔值配置值"""
        try:
            return self.config.getboolean(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def set(self, section: str, key: str, value: str):
        """设置配置值"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))

    def get_section(self, section: str) -> Dict[str, str]:
        """获取整个配置节"""
        if self.config.has_section(section):
            return dict(self.config.items(section))
        return {}

    def get_status_message(self, status_code: str) -> str:
        """获取状态码对应的诊断信息"""
        return self.get('Status_Messages', str(status_code), f"未知状态码: {status_code}")

    def get_adb_command(self, command_name: str, **kwargs) -> str:
        """获取ADB命令模板并填充参数"""
        template = self.get('ADB_Commands', command_name, "")
        if template and kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logging.error(f"ADB命令模板参数缺失: {e}")
        return template

    def save_wifi_history(self, ssid: str, password: str, security: str):
        """保存WiFi历史记录"""
        try:
            if not self.config.has_section('WiFi_History'):
                self.config.add_section('WiFi_History')
            
            self.config.set('WiFi_History', 'last_ssid', ssid)
            self.config.set('WiFi_History', 'last_password', password)
            self.config.set('WiFi_History', 'last_security', security)
            
            # 自动保存到文件
            self.save_config()
            logging.info(f"WiFi历史记录已保存: SSID={ssid}, Security={security}")
        except Exception as e:
            logging.error(f"保存WiFi历史记录失败: {e}")

    def get_wifi_history(self) -> Dict[str, str]:
        """获取WiFi历史记录"""
        try:
            return {
                'ssid': self.get('WiFi_History', 'last_ssid', ''),
                'password': self.get('WiFi_History', 'last_password', ''),
                'security': self.get('WiFi_History', 'last_security', 'wpa2')
            }
        except Exception as e:
            logging.error(f"获取WiFi历史记录失败: {e}")
            return {'ssid': '', 'password': '', 'security': 'wpa2'}

    def _load_default_config(self):
        """加载默认配置"""
        # 基本配置
        self.config.add_section('General')
        self.config.set('General', 'refresh_rate', '1')
        self.config.set('General', 'adb_path', 'adb/adb.exe')
        self.config.set('General', 'version', '3.1')
        self.config.set('General', 'auto_activation_enabled', 'false')

        # UI配置
        self.config.add_section('UI')
        self.config.set('UI', 'window_title', 'AC8267激活工具')
        self.config.set('UI', 'window_width', '1200')
        self.config.set('UI', 'window_height', '800')
        self.config.set('UI', 'show_na_devices', 'false')

        # 日志配置
        self.config.add_section('Logging')
        self.config.set('Logging', 'log_level', 'INFO')
        self.config.set('Logging', 'log_file', 'logs/cbss_tool.log')

        # 关于信息
        self.config.add_section('About')
        self.config.set('About', 'company', 'Autochips Inc')
        self.config.set('About', 'description', 'AC8267激活工具')

        logging.info("已加载默认配置")
