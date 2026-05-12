"""
日志管理模块
负责配置和管理应用程序日志
"""
import json
import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime


class LogManager:
    _MAX_RECORDS_PER_FILE = 200
    _auth_lock = threading.Lock()

    def __init__(self, config_manager):
        self.config = config_manager
        self._auth_file_index = 0
        self._auth_record_count = 0
        self.setup_logging()
        self._init_auth_log_dir()

    def _init_auth_log_dir(self):
        base_dir = os.path.join(os.path.dirname(
            self.config.get('Logging', 'log_file', 'logs/cbss_tool.log')
        ) or 'logs', 'detailed_info', 'all')
        os.makedirs(base_dir, exist_ok=True)
        # 找到当前最大文件id
        import glob
        existing = glob.glob(os.path.join(base_dir, 'authorization_*.json'))
        max_id = 0
        for f in existing:
            try:
                fid = int(os.path.splitext(os.path.basename(f))[0].split('_')[-1])
                max_id = max(max_id, fid)
            except ValueError:
                pass
        self._auth_file_index = max_id
        # 读取最后一个文件的记录数
        if max_id > 0:
            last_file = os.path.join(base_dir, f'authorization_{max_id:06d}.json')
            try:
                with open(last_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                    self._auth_record_count = len(records) if isinstance(records, list) else 0
            except Exception:
                self._auth_record_count = self._MAX_RECORDS_PER_FILE  # 强制新文件

    def setup_logging(self):
        """设置日志配置"""
        # 获取配置
        log_level = self.config.get('Logging', 'log_level', 'INFO')
        log_file = self.config.get('Logging', 'log_file', 'logs/cbss_tool.log')
        max_log_size = self.config.getint('Logging', 'max_log_size', 10485760)  # 10MB
        backup_count = self.config.getint('Logging', 'backup_count', 5)

        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 配置日志级别
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)

        # 创建logger
        logger = logging.getLogger()
        logger.setLevel(numeric_level)

        # 清除现有的处理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 创建文件处理器（带轮转）
        if log_file:
            try:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=max_log_size,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(numeric_level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"无法创建日志文件处理器: {e}")

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 记录日志系统初始化
        logging.info("日志系统初始化完成")
        logging.info(f"日志级别: {log_level}")
        logging.info(f"日志文件: {log_file}")

    def get_log_content(self, max_lines: int = 1000) -> str:
        """获取日志文件内容"""
        log_file = self.config.get('Logging', 'log_file', 'logs/cbss_tool.log')

        if not os.path.exists(log_file):
            return "日志文件不存在"

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

                # 如果行数超过限制，只返回最后的行数
                if len(lines) > max_lines:
                    lines = lines[-max_lines:]

                return ''.join(lines)
        except Exception as e:
            return f"读取日志文件失败: {str(e)}"

    def clear_logs(self):
        """清空日志文件"""
        log_file = self.config.get('Logging', 'log_file', 'logs/cbss_tool.log')

        try:
            if os.path.exists(log_file):
                open(log_file, 'w').close()
                logging.info("日志文件已清空")
                return True
        except Exception as e:
            logging.error(f"清空日志文件失败: {str(e)}")
            return False
        return False

    def update_log_level(self, new_level: str):
        """更新日志级别"""
        try:
            numeric_level = getattr(logging, new_level.upper(), logging.INFO)

            # 更新所有处理器的日志级别
            logger = logging.getLogger()
            logger.setLevel(numeric_level)

            for handler in logger.handlers:
                handler.setLevel(numeric_level)

            # 更新配置
            self.config.set('Logging', 'log_level', new_level.upper())

            logging.info(f"日志级别已更新为: {new_level.upper()}")
            return True
        except Exception as e:
            logging.error(f"更新日志级别失败: {str(e)}")
            return False

    def update_log_file(self, new_file: str):
        """更新日志文件路径"""
        try:
            # 确保新日志目录存在
            log_dir = os.path.dirname(new_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # 更新配置
            self.config.set('Logging', 'log_file', new_file)

            # 重新设置日志
            self.setup_logging()

            logging.info(f"日志文件路径已更新为: {new_file}")
            return True
        except Exception as e:
            logging.error(f"更新日志文件路径失败: {str(e)}")
            return False

    def _get_auth_dir(self, subdir: str) -> str:
        """获取授权日志目录，优先从配置读取"""
        key = f'auth_log_{subdir}_dir'
        configured = self.config.get('Logging', key, '')
        if configured and configured.strip():
            return configured.strip()
        base = os.path.dirname(self.config.get('Logging', 'log_file', 'logs/cbss_tool.log')) or 'logs'
        return os.path.join(base, 'detailed_info', subdir)

    def _write_auth_record(self, record: dict, subdir: str):
        with self._auth_lock:
            base_dir = self._get_auth_dir(subdir)
            os.makedirs(base_dir, exist_ok=True)
            filepath = os.path.join(base_dir, f'authorization_{self._auth_file_index:06d}.json')
            records = []
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        records = json.load(f)
                except Exception:
                    records = []
            if self._auth_record_count >= self._MAX_RECORDS_PER_FILE:
                self._auth_file_index += 1
                self._auth_record_count = 0
                filepath = os.path.join(base_dir, f'authorization_{self._auth_file_index:06d}.json')
                records = []
            records.append(record)
            self._auth_record_count = len(records)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

    def log_authorization(self, success: bool, device_serial: str, uuid: str,
                          signature: str, cube_id: str, error_reason: str = ""):
        """记录授权详情到 detailed_info/all/"""
        record = {
            "success": bool(success),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "serial_id": str(device_serial or ""),
            "uuid": str(uuid or ""),
            "signature": str(signature or ""),
            "cube_id": str(cube_id or ""),
        }
        if not success and error_reason:
            record["error_reason"] = str(error_reason)
        self._write_auth_record(record, 'all')

    def log_authorization_failure(self, device_serial: str, uuid: str, signature: str,
                                   cube_id: str, error_reason: str,
                                   cube_status: str = "", cube_expire: str = ""):
        """记录授权失败详情到 detailed_info/failure/（含Cube状态信息）"""
        record = {
            "success": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "serial_id": str(device_serial or ""),
            "uuid": str(uuid or ""),
            "signature": str(signature or ""),
            "cube_id": str(cube_id or ""),
            "error_reason": str(error_reason),
            "cube_status": str(cube_status or ""),
            "cube_expire": str(cube_expire or ""),
        }
        self._write_auth_record(record, 'failure')
