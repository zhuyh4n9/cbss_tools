"""
主GUI应用程序
实现激活盒子盒子PC Tool的用户界面
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
import importlib
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

if __package__ in (None, ""):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    module_prefix = "src"
else:
    module_prefix = __package__


def _load_dependencies(prefix):
    config_module = importlib.import_module(f"{prefix}.config_manager")
    log_module = importlib.import_module(f"{prefix}.log_manager")
    adb_module = importlib.import_module(f"{prefix}.adb_manager")
    device_monitor_module = importlib.import_module(f"{prefix}.device_monitor")
    auth_module = importlib.import_module(f"{prefix}.auth_manager")
    prompt_module = importlib.import_module(f"{prefix}.prompt_manager")
    diaglog_module = importlib.import_module(f"{prefix}.diaglog")
    return (
        config_module.ConfigManager,
        log_module.LogManager,
        adb_module.ADBManager,
        adb_module.DeviceInfo,
        adb_module.AuthenticatorInfo,
        device_monitor_module.DeviceMonitor,
        auth_module.AuthenticationManager,
        prompt_module.PromptManager,
        diaglog_module.LogLevelDialog,
        diaglog_module.LogViewDialog,
        diaglog_module.AuthenticatorOperationDialog,
        diaglog_module.AuthenticationDialog,
        diaglog_module.BatchAuthenticationDialog,
        diaglog_module.ProgressDialog,
        diaglog_module.WifiDisconnectDialog,
        diaglog_module.WifiConfigDialog,
        diaglog_module.WifiScanDialog,
        diaglog_module.DiagnosticDialog,
    )


(
    ConfigManager,
    LogManager,
    ADBManager,
    DeviceInfo,
    AuthenticatorInfo,
    DeviceMonitor,
    AuthenticationManager,
    PromptManager,
    LogLevelDialog,
    LogViewDialog,
    AuthenticatorOperationDialog,
    AuthenticationDialog,
    BatchAuthenticationDialog,
    ProgressDialog,
    WifiDisconnectDialog,
    WifiConfigDialog,
    WifiScanDialog,
    DiagnosticDialog,
) = _load_dependencies(module_prefix)

NETWORK_MONITOR_THREAD_JOIN_TIMEOUT = 0.1

class AuthenticatorToolGUI:
    _SIMULATOR_DEVICE_TYPE = "SimulatorDevice"

    def __init__(self):
        self.root = tk.Tk()
        # initialize prompt manager before UI
        self.prompt_mgr = PromptManager(
            'config/prompt_chn.ini'
        )
        self.setup_managers()
        self.setup_ui()
        self.setup_monitoring()        # 状态变量
        self.is_operation_in_progress = False
        self.is_refreshing_devices = False  # 防止频繁刷新设备

        # 网络监控变量
        self.current_authenticator = None
        self.network_monitor_thread = None
        self.network_monitor_stop = threading.Event()
        self.ping_hosts = []
        self.monitor_interval = 10
        self.critical_host = "ntp.ntsc.ac.cn"

        # 加载网络监控配置
        self.load_network_config()

    def setup_managers(self):
        """初始化各种管理器"""
        try:
            # 配置管理器
            self.config_manager = ConfigManager()

            # 日志管理器
            self.log_manager = LogManager(self.config_manager)

            # ADB管理器
            self.adb_manager = ADBManager(self.config_manager)

            # 设备监控器
            self.device_monitor = DeviceMonitor(self.adb_manager, self.config_manager)

            # 激活管理器
            self.auth_manager = AuthenticationManager(self.adb_manager, self.device_monitor)

            logging.info("所有管理器初始化完成")

        except Exception as e:
            messagebox.showerror("初始化错误", f"初始化管理器失败: {str(e)}")
            logging.error(f"初始化管理器失败: {e}")

    def setup_ui(self):
        """设置用户界面"""
        # 窗口基本设置
        title = self.config_manager.get('UI', 'window_title', self.prompt_mgr.get('Misc.window_title'))
        width = self.config_manager.getint('UI', 'window_width', 1200)
        height = self.config_manager.getint('UI', 'window_height', 800)

        self.root.title(title)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(800, 600)

        # 创建菜单栏
        self.create_menu_bar()

        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建激活盒子信息区域
        self.create_authenticator_frame(main_frame)

        # 创建设备列表区域
        self.create_device_frame(main_frame)

        # 创建状态栏
        self.create_status_bar()

        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.prompt_mgr.get('Menus.file'), menu=file_menu)
        file_menu.add_command(label=self.prompt_mgr.get('MenuItems.load_config'), command=self.load_config)
        file_menu.add_command(label=self.prompt_mgr.get('MenuItems.export_config'), command=self.export_config)
        file_menu.add_separator()

        # 配置日志子菜单
        log_config_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label=self.prompt_mgr.get('Menus.log_config'), menu=log_config_menu)
        log_config_menu.add_command(label=self.prompt_mgr.get('MenuItems.log_level'), command=self.config_log_level)
        log_config_menu.add_command(label=self.prompt_mgr.get('MenuItems.log_path'), command=self.config_log_path)

        file_menu.add_command(label=self.prompt_mgr.get('Menus.view_logs'), command=self.view_logs)        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.prompt_mgr.get('Menus.tools'), menu=tools_menu)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.lock_auth'), command=self.lock_authenticator)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.unlock_auth'), command=self.unlock_authenticator)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.activate_auth'), command=self.activate_authenticator)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.config_auth'), command=self.config_authenticator)
        tools_menu.add_separator()
        self.auto_activation_menu_var = tk.BooleanVar(value=self.auth_manager.is_auto_activation_enabled())
        tools_menu.add_checkbutton(
            label=self.prompt_mgr.get('MenuItems.auto_activation_toggle'),
            variable=self.auto_activation_menu_var,
            command=self.toggle_auto_activation
        )
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.clear_logs'), command=self.clear_logs_from_tools_menu)
        tools_menu.add_separator()
        if self.device_monitor.is_simulated_device_enabled():
            tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.add_simulated_device'), command=self.show_add_simulated_device_dialog)
            tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.create_simulated_cube'), command=self.show_create_simulated_cube_dialog)
            tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.load_simulated_cube'), command=self.show_load_simulated_cube_dialog)
        # 新增：设备WiFi连接
        tools_menu.add_separator()
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.current_wifi'), command=self.view_current_wifi)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.scan_and_connect_wifi'), command=self.scan_and_connect_wifi)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.auth_wifi_connect'), command=self.authenticator_wifi_connect)
        tools_menu.add_command(label=self.prompt_mgr.get('MenuItems.auth_wifi_disconnect'), command=self.authenticator_wifi_disconnect)

        # 新增：诊断日志功能 (Update 2)
        tools_menu.add_separator()
        diagnostic_menu = tk.Menu(tools_menu, tearoff=0)
        tools_menu.add_cascade(label=self.prompt_mgr.get('MenuItems.diagnostic'), menu=diagnostic_menu)
        diagnostic_menu.add_command(label=self.prompt_mgr.get('MenuItems.get_token_log'), command=self.get_token_diagnostic)
        diagnostic_menu.add_command(label=self.prompt_mgr.get('MenuItems.get_ta_log'), command=self.get_trusted_service_diagnostic)
        diagnostic_menu.add_command(label=self.prompt_mgr.get('MenuItems.get_auth_log'), command=self.get_authorization_diagnostic)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.prompt_mgr.get('Menus.help'), menu=help_menu)
        help_menu.add_command(label=self.prompt_mgr.get('MenuItems.usage'), command=self.show_help)

        # 关于菜单
        about_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.prompt_mgr.get('Menus.about'), menu=about_menu)
        about_menu.add_command(label=self.prompt_mgr.get('Menus.about'), command=self.show_about)
        about_menu.add_command(label=self.prompt_mgr.get('Menus.changelog'), command=self.show_changelog)

    def create_authenticator_frame(self, parent):
        auth_frame = ttk.LabelFrame(parent, text=self.prompt_mgr.get('UI.auth_frame_title'), padding=10)
        auth_frame.pack(fill=tk.X, pady=(0, 5))
        selector_frame = ttk.Frame(auth_frame)
        selector_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(selector_frame, text=self.prompt_mgr.get('UI.select_auth_label')).pack(side=tk.LEFT)
        self.auth_selector = ttk.Combobox(selector_frame, state="readonly", width=25)
        self.auth_selector.pack(side=tk.LEFT, padx=(10, 0))
        self.auth_selector.bind('<<ComboboxSelected>>', self.on_authenticator_selected)
        ttk.Button(selector_frame, text=self.prompt_mgr.get('UI.details_button'), command=self.show_detailed_info).pack(side=tk.RIGHT)
        info_frame = ttk.Frame(auth_frame)
        info_frame.pack(fill=tk.BOTH, expand=True)
        left_frame = ttk.Frame(info_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        basic_info_frame = ttk.LabelFrame(left_frame, text=self.prompt_mgr.get('UI.basic_info_group'), padding=5)
        basic_info_frame.pack(fill=tk.X, pady=(0, 5))
        self.serial_id_var = tk.StringVar(value=self.prompt_mgr.get('UI.no_auth_selected'))
        self.device_type_var = tk.StringVar(value=self.prompt_mgr.get('UI.device_type_label').rstrip(':'))
        self.last_connect_var = tk.StringVar(value='-')
        ttk.Label(basic_info_frame, text=self.prompt_mgr.get('UI.serial_id_label')).grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(basic_info_frame, textvariable=self.serial_id_var, foreground='blue').grid(row=0, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(basic_info_frame, text=self.prompt_mgr.get('UI.device_type_label')).grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(basic_info_frame, textvariable=self.device_type_var).grid(row=1, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(basic_info_frame, text=self.prompt_mgr.get('UI.last_connect_label')).grid(row=2, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(basic_info_frame, textvariable=self.last_connect_var).grid(row=2, column=1, sticky='w', padx=5, pady=2)
        status_info_frame = ttk.LabelFrame(left_frame, text=self.prompt_mgr.get('UI.status_info_group'), padding=5)
        status_info_frame.pack(fill=tk.X)
        self.expire_date_var = tk.StringVar(value='-')
        self.expire_status_var = tk.StringVar(value='-')
        self.counter_var = tk.StringVar(value='-')
        self.authorized_num_var = tk.StringVar(value='-')
        self.device_status_var = tk.StringVar(value='-')
        self.time_status_var = tk.StringVar(value='-')
        self.network_status_var = tk.StringVar(value='-')
        self.wifi_ssid_var = tk.StringVar(value='-')
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.expire')).grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.expire_date_label = ttk.Label(status_info_frame, textvariable=self.expire_date_var)
        self.expire_date_label.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.count_left')).grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, textvariable=self.counter_var).grid(row=1, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.count_used')).grid(row=1, column=2, sticky='w', padx=(20,5), pady=2)
        ttk.Label(status_info_frame, textvariable=self.authorized_num_var).grid(row=1, column=3, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.device_state')).grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.device_status_label = ttk.Label(status_info_frame, textvariable=self.device_status_var)
        self.device_status_label.grid(row=2, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.time_state')).grid(row=2, column=2, sticky='w', padx=(20,5), pady=2)
        self.time_status_label = ttk.Label(status_info_frame, textvariable=self.time_status_var)
        self.time_status_label.grid(row=2, column=3, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.network_state')).grid(row=3, column=0, sticky='w', padx=5, pady=2)
        self.network_status_label = ttk.Label(status_info_frame, textvariable=self.network_status_var)
        self.network_status_label.grid(row=3, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(status_info_frame, text=self.prompt_mgr.get('Status.current_wifi')).grid(row=3, column=2, sticky='w', padx=(20,5), pady=2)
        self.wifi_ssid_label = ttk.Label(status_info_frame, textvariable=self.wifi_ssid_var)
        self.wifi_ssid_label.grid(row=3, column=3, sticky='w', padx=5, pady=2)
        right_frame = ttk.Frame(info_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        snapshot_frame = ttk.LabelFrame(right_frame, text=self.prompt_mgr.get('UI.snapshot_group'), padding=5)
        snapshot_frame.pack(fill=tk.BOTH, expand=True)
        self.snapshot_text = tk.Text(snapshot_frame, height=8, width=40, wrap=tk.WORD)
        snapshot_scrollbar = ttk.Scrollbar(snapshot_frame, orient=tk.VERTICAL, command=self.snapshot_text.yview)
        self.snapshot_text.configure(yscrollcommand=snapshot_scrollbar.set)
        self.snapshot_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        snapshot_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.update_authenticator_selector([])
        self.clear_authenticator_display()

    def create_device_frame(self, parent):
        device_frame = ttk.LabelFrame(parent, text=self.prompt_mgr.get('UI.device_list_title'), padding=10)
        device_frame.pack(fill=tk.BOTH, expand=True)

        self.auto_auth_tip_var = tk.StringVar(value="")
        self.auto_auth_tip_label = tk.Label(
            device_frame,
            textvariable=self.auto_auth_tip_var,
            fg='red',
            anchor='w',
            justify='left'
        )
        self.auto_auth_tip_label.pack(fill=tk.X, pady=(0, 4))

        button_frame = ttk.Frame(device_frame)
        button_frame.pack(fill=tk.X, pady=(0,5))
        self.refresh_button = ttk.Button(button_frame, text=self.prompt_mgr.get('UI.refresh_devices_btn'), command=self.refresh_devices)
        self.refresh_button.pack(side=tk.LEFT, padx=(0,5))
        self.activate_all_button = ttk.Button(button_frame, text=self.prompt_mgr.get('UI.activate_all_btn'), command=self.authenticate_all_devices)
        self.activate_all_button.pack(side=tk.LEFT)
        device_columns = (
            self.prompt_mgr.get('DeviceTable.col_serial'),
            self.prompt_mgr.get('DeviceTable.col_uuid'),
            self.prompt_mgr.get('DeviceTable.col_usb_port'),
            self.prompt_mgr.get('DeviceTable.col_status'),
            self.prompt_mgr.get('DeviceTable.col_action')
        )
        self.device_tree = ttk.Treeview(device_frame, columns=device_columns, show='headings')
        for col in device_columns:
            self.device_tree.heading(col, text=col)
            # width logic omitted for brevity
        device_scrollbar_v = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.device_tree.yview)
        device_scrollbar_h = ttk.Scrollbar(device_frame, orient=tk.HORIZONTAL, command=self.device_tree.xview)
        self.device_tree.configure(yscrollcommand=device_scrollbar_v.set, xscrollcommand=device_scrollbar_h.set)
        self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        device_scrollbar_v.pack(side=tk.RIGHT, fill=tk.Y)
        device_scrollbar_h.pack(side=tk.BOTTOM, fill=tk.X)
        self.device_tree.bind('<Double-1>', self.on_device_double_click)
        self.device_tree.bind('<Button-3>', self.on_device_right_click)
        self.device_context_menu = tk.Menu(self.root, tearoff=0)
        self._update_auto_auth_ui_state()

    def create_status_bar(self):
        """创建状态栏"""
        self.status_var = tk.StringVar()
        self.status_var.set(self.prompt_mgr.get('UI.status_ready'))

        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(status_bar, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, padx=2, pady=2)

    def setup_monitoring(self):
        """设置监控"""
        # 添加回调函数
        self.device_monitor.add_callback('authenticator_update', self.update_authenticator_display)
        self.device_monitor.add_callback('device_update', self.update_device_display)
        self.device_monitor.add_callback('error', self.on_monitor_error)

        self.device_monitor.start_monitoring()

    def load_network_config(self):
        """加载网络监控配置"""
        try:
            ping_hosts_str = self.config_manager.get('Network', 'ping_hosts',
                'ntp.ntsc.ac.cn,ntp1.aliyun.com,www.baidu.com,www.google.com,8.8.8.8')
            self.ping_hosts = [host.strip() for host in ping_hosts_str.split(',') if host.strip()]

            self.monitor_interval = self.config_manager.getint('Network', 'monitor_interval', 10)

            # Critical host
            self.critical_host = self.config_manager.get('Network', 'critical_host', 'ntp.ntsc.ac.cn')

            logging.info(f"Network monitoring configuration loaded: Nodes={len(self.ping_hosts)}, Interval={self.monitor_interval}s")
        except Exception as e:
            logging.error(f"Failed to load network monitoring configuration: {e}")

    def start_network_monitoring(self):
        """Start network monitoring thread"""
        if hasattr(self, 'network_monitor_thread') and self.network_monitor_thread and self.network_monitor_thread.is_alive():
            return

        self.network_monitor_stop.clear()
        self.network_monitor_thread = threading.Thread(target=self._network_monitor_worker, daemon=True)
        self.network_monitor_thread.start()
        logging.info("Network monitoring started")

    def stop_network_monitoring(self, join_timeout: float = 2.0):
        """Stop network monitoring thread"""
        if hasattr(self, 'network_monitor_stop'):
            self.network_monitor_stop.set()
        if hasattr(self, 'network_monitor_thread') and self.network_monitor_thread:
            self.network_monitor_thread.join(timeout=max(float(join_timeout or 0), 0.0))
        logging.info("Network monitoring stopped")

    def _network_monitor_worker(self):
        """Network monitoring worker thread"""
        while not self.network_monitor_stop.is_set():
            try:
                try:
                    wifi_info = self.adb_manager.get_current_wifi(self.current_authenticator)
                    self.root.after(0, lambda w=wifi_info: self.update_wifi_status(w))
                except Exception as e:
                    logging.debug(self.prompt_mgr.format('Monitoring.wifi_status_fetch_failed', error=str(e)))
                if self.current_authenticator and not self.is_operation_in_progress:
                    # 执行ping测试
                    results = self.adb_manager.test_network_connectivity(
                        self.current_authenticator,
                        self.ping_hosts
                    )
                    # 更新UI显示
                    self.root.after(0, lambda r=results: self.update_network_status(r))

            except Exception as e:
                logging.error(self.prompt_mgr.format('Monitoring.network_monitor_error', error=str(e)))

            # 等待下一次检测
            self.network_monitor_stop.wait(self.monitor_interval)

    def update_network_status(self, results: Dict[str, bool]):
        """更新网络状态显示"""
        try:
            if not results:
                self.network_status_var.set("-")
                self.network_status_label.config(foreground="gray")
                return

            # 计算连通性百分比
            total = len(results)
            success_count = sum(1 for v in results.values() if v)
            percentage = int((success_count / total) * 100) if total > 0 else 0

            # 检查关键节点
            critical_failed = self.critical_host in results and not results[self.critical_host]

            # 构建状态文本
            status_text = f"{percentage}% ({success_count}/{total})"
            if critical_failed:
                status_text += " ⚠"

            self.network_status_var.set(status_text)
            if percentage >= 80:
                self.network_status_label.config(foreground="green")
            elif percentage >= 50:
                self.network_status_label.config(foreground="orange")
            else:
                self.network_status_label.config(foreground="red")

        except Exception as e:
            logging.error(f"Failed to update network status display: {e}")

    def update_wifi_status(self, wifi_status: Dict[str, str]):
        """更新WiFi状态显示"""
        try:
            # 支持两种格式: connected可以是布尔值或字符串 'true'
            is_connected = wifi_status.get('connected')
            if isinstance(is_connected, bool):
                connected = is_connected
            else:
                connected = is_connected == 'true'

            if connected and wifi_status.get('ssid') and wifi_status.get('ssid') != 'Not Connected':
                ssid = wifi_status['ssid']
                signal = wifi_status.get('signal', '')
                band = wifi_status.get('band', '')

                display_text = f"{ssid}"
                if signal:
                    display_text += f" ({signal}dBm"
                    if band:
                        display_text += f", {band}"
                    display_text += ")"
                elif band:
                    display_text += f" ({band})"

                self.wifi_ssid_var.set(display_text)
                self.wifi_ssid_label.config(foreground="blue")
            else:
                self.wifi_ssid_var.set(self.prompt_mgr.get('Network.wifi_not_connected'))
                self.wifi_ssid_label.config(foreground="gray")

        except Exception as e:
            logging.error(self.prompt_mgr.format('Monitoring.update_wifi_status_failed', error=str(e)))
            self.wifi_ssid_var.set("-")

    def update_authenticator_display(self, authenticators: Dict[str, AuthenticatorInfo]):
        """更新激活盒子显示"""
        def update_ui():
            merged_authenticators = dict(authenticators or {})
            merged_authenticators.update(self.auth_manager.get_simulated_cube_infos())
            self._update_auto_auth_ui_state(len(merged_authenticators))
            # 更新激活盒子选择器
            authenticator_serials = list(merged_authenticators.keys())
            self.update_authenticator_selector(authenticator_serials)

            # 保存激活盒子数据
            self.authenticators_data = merged_authenticators
            current_selection = self.auth_selector.get()
            if current_selection and current_selection in merged_authenticators:
                self.update_authenticator_info(current_selection)
            elif authenticator_serials:
                self.auth_selector.set(authenticator_serials[0])
                self.update_authenticator_info(authenticator_serials[0])
            else:
                # 没有激活盒子时清空显示
                self.clear_authenticator_display()

        # 在主线程中更新UI
        self.root.after(0, update_ui)

    def update_authenticator_selector(self, authenticator_serials: List[str]):
        """更新激活盒子选择器"""
        self.auth_selector['values'] = authenticator_serials
        if not authenticator_serials:
            self.auth_selector.set('')

    def on_authenticator_selected(self, event=None):
        """激活盒子选择事件处理"""
        selected = self.auth_selector.get()
        if selected:
            self.update_authenticator_info(selected)

    def update_authenticator_info(self, serial: str):
        """更新激活盒子详细信息"""
        if hasattr(self, 'authenticators_data') and serial in self.authenticators_data:
            auth_info = self.authenticators_data[serial]
            is_simulated_cube = self.auth_manager.is_simulated_cube(serial)

            # 更新基本信息
            self.serial_id_var.set(serial)
            self.device_type_var.set(self.prompt_mgr.get('UI.device_type_box'))
            self.last_connect_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # 更新状态信息
            self.expire_date_var.set(auth_info.expired_date if auth_info.expired_date else "-")
            self.counter_var.set(str(auth_info.counter))
            self.authorized_num_var.set(str(auth_info.authorized_device_num))

            # 更新时间状态 (NEW in Update 4)
            self.time_status_var.set(auth_info.time_status if auth_info.time_status else "-")

            # 更新设备状态信息
            self.update_device_status_display(auth_info.device_status)

            # 设置过期时间标签颜色
            exp_status = self.device_monitor.get_expiration_status(auth_info.expired_date)
            if exp_status == "expired":
                self.expire_date_label.config(foreground="red")
            elif exp_status == "warning":
                self.expire_date_label.config(foreground="orange")
            else:
                self.expire_date_label.config(foreground="green")

            # 更新snapshot信息
            self.snapshot_text.delete('1.0', tk.END)
            if auth_info.raw_data:
                # 格式化显示snapshot数据
                formatted_data = self.format_snapshot_data(auth_info)
                self.snapshot_text.insert('1.0', formatted_data)

            if is_simulated_cube:
                self.current_authenticator = None
                self.stop_network_monitoring(join_timeout=NETWORK_MONITOR_THREAD_JOIN_TIMEOUT)
                self.network_status_var.set(self.prompt_mgr.get('Status.simulated_network_ok'))
                self.network_status_label.config(foreground="green")
                self.wifi_ssid_var.set(self.prompt_mgr.get('Status.simulated_wifi_name'))
                self.wifi_ssid_label.config(foreground="blue")
            else:
                # 启动网络监控 (NEW in Update 4)
                if self.current_authenticator != serial:
                    self.current_authenticator = serial
                    self.start_network_monitoring()
        else:
            self.clear_authenticator_display()

    def update_device_status_display(self, device_status: int):
        """更新设备状态显示"""
        status_bits = self.device_monitor.get_authenticator_status_description(device_status)
        status_text = f"0x{device_status:02X}"
        status_parts = []

        if status_bits['locked']:
            status_parts.append(self.prompt_mgr.get('StatusLabels.locked'))
        if status_bits['frozen']:
            status_parts.append(self.prompt_mgr.get('StatusLabels.frozen'))
        if status_bits['temp_lock_support']:
            status_parts.append(self.prompt_mgr.get('StatusLabels.temp_lock'))

        if status_parts:
            status_text += f" ({', '.join(status_parts)})"
        else:
            status_text += f" ({self.prompt_mgr.get('StatusLabels.normal')})"

        self.device_status_var.set(status_text)

        # 根据状态设置颜色
        if status_bits['locked'] or status_bits['frozen']:
            self.device_status_label.config(foreground="red")
        elif status_bits['temp_lock_support']:
            self.device_status_label.config(foreground="orange")
        else:
            self.device_status_label.config(foreground="green")

    def format_snapshot_data(self, auth_info: AuthenticatorInfo) -> str:
        """格式化snapshot数据显示"""
        formatted = f"Serial ID: {auth_info.serial}\n"
        formatted += f"{self.prompt_mgr.get('UI.device_type_label')} 激活盒子\n"
        formatted += f"{self.prompt_mgr.get('UI.last_connect_label')} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        # 设备状态分析
        status_bits = self.device_monitor.get_authenticator_status_description(auth_info.device_status)

        if status_bits['locked']:
            formatted += f"  - {self.prompt_mgr.get('StatusLabels.locked_detail')}\n"
        if status_bits['frozen']:
            formatted += f"  - {self.prompt_mgr.get('StatusLabels.frozen_detail')}\n"
        if status_bits['temp_lock_support']:
            formatted += f"  - {self.prompt_mgr.get('StatusLabels.temp_lock_detail')}\n"
        formatted += "\n"
        if auth_info.raw_data:
            for line in auth_info.raw_data.splitlines():
                if line.startswith("[status] "):
                    continue
                line = line.strip("[result] ")
                formatted += f"{line}\n"

        return formatted

    def clear_authenticator_display(self):
        self.serial_id_var.set(self.prompt_mgr.get('Text.snapshot_placeholder'))
        self.device_type_var.set('-')
        self.last_connect_var.set('-')
        self.expire_date_var.set('-')
        self.counter_var.set('-')
        self.authorized_num_var.set('-')
        self.device_status_var.set('-')
        self.time_status_var.set('-')
        self.network_status_var.set('-')
        self.wifi_ssid_var.set('-')
        self.expire_date_label.config(foreground='black')
        self.device_status_label.config(foreground='black')
        self.snapshot_text.delete('1.0', tk.END)
        self.snapshot_text.insert('1.0', self.prompt_mgr.get('Text.snapshot_placeholder'))

    def show_detailed_info(self):
        selected = self.auth_selector.get()
        if not selected:
            messagebox.showinfo(self.prompt_mgr.get('Common.info_title'), self.prompt_mgr.get('Validation.select_authenticator_first'))
            return
        if hasattr(self, 'authenticators_data') and selected in self.authenticators_data:
            auth_info = self.authenticators_data[selected]
            dialog = tk.Toplevel(self.root)
            dialog.title(self.prompt_mgr.format('Dialogs.about_title') + f" - {selected}")
            dialog.geometry('700x500')
            dialog.transient(self.root)
            dialog.grab_set()
            text_frame = ttk.Frame(dialog)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_widget = tk.Text(text_frame, wrap=tk.WORD)
            scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            detailed_info = self.get_detailed_authenticator_info(auth_info)
            text_widget.insert('1.0', detailed_info)
            text_widget.config(state=tk.DISABLED)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            button_frame = ttk.Frame(dialog)
            button_frame.pack(pady=10)
            ttk.Button(button_frame, text=self.prompt_mgr.get('Buttons.close'), command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def get_detailed_authenticator_info(self, auth_info: AuthenticatorInfo) -> str:
        """获取激活盒子详细信息"""
        info = f"{self.prompt_mgr.get('Text.box_detailed_info')}\n"
        info += "=" * 50 + "\n\n"

        info += f"{self.prompt_mgr.get('UI.device_info_label')}\n"
        info += f"  {self.prompt_mgr.get('UI.serial_id_label')} {auth_info.serial}\n"
        info += f"  {self.prompt_mgr.get('UI.device_type_label')} {self.prompt_mgr.get('UI.device_type_box')}\n"
        info += f"  {self.prompt_mgr.get('UI.last_update_label')} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        info += f"{self.prompt_mgr.get('UI.status_info_group')}:\n"
        info += f"  {self.prompt_mgr.get('UI.expire_date_label')} {auth_info.expired_date if auth_info.expired_date else '未知'}\n"

        # 过期状态分析
        exp_status = self.device_monitor.get_expiration_status(auth_info.expired_date)
        if exp_status == "expired":
            info += f"  {self.prompt_mgr.get('UI.expiration_status_label')} {self.prompt_mgr.get('UI.expired')}\n"
        elif exp_status == "warning":
            info += f"  {self.prompt_mgr.get('UI.expiration_status_label')} {self.prompt_mgr.get('UI.warning')}\n"
        elif exp_status == "normal":
            info += f"  {self.prompt_mgr.get('UI.expiration_status_label')} {self.prompt_mgr.get('UI.normal')}\n"
        else:
            info += f"  {self.prompt_mgr.get('UI.expiration_status_label')} {self.prompt_mgr.get('UI.unknown_expiration')}\n"

        info += f"  {self.prompt_mgr.get('UI.remaining_activations_label')} {auth_info.counter}\n"
        info += f"  {self.prompt_mgr.get('UI.used_activations_label')} {auth_info.authorized_device_num}\n\n"

        # 设备状态位分析
        info += f"{self.prompt_mgr.get('UI.device_status_label')}\n"
        info += f"  {self.prompt_mgr.get('UI.status_values_label')} {auth_info.device_status} (0x{auth_info.device_status:02X})\n"

        status_bits = self.device_monitor.get_authenticator_status_description(auth_info.device_status)
        info += f"  {self.prompt_mgr.get('UI.locked_status_label')} {self.prompt_mgr.get('Text.yes') if status_bits['locked'] else self.prompt_mgr.get('Text.no')}\n"
        info += f"  {self.prompt_mgr.get('UI.frozen_status_label')} {self.prompt_mgr.get('Text.yes') if status_bits['frozen'] else self.prompt_mgr.get('Text.no')}\n"
        info += f"  {self.prompt_mgr.get('UI.temp_lock_status_label')} {self.prompt_mgr.get('Text.yes') if status_bits['temp_lock_support'] else self.prompt_mgr.get('Text.no')}\n\n"

        # 原始snapshot数据
        info += f"origin snapshot:\n"
        info += "-" * 30 + "\n"
        info += auth_info.raw_data if auth_info.raw_data else "n/a"

        return info

    def refresh_detailed_info(self, text_widget, serial: str):
        """刷新详细信息"""
        if hasattr(self, 'authenticators_data') and serial in self.authenticators_data:
            # 手动刷新设备信息
            self.device_monitor.refresh_devices()

            # 等待一下让数据更新
            self.root.after(1000, lambda: self._update_detailed_info_display(text_widget, serial))

    def _update_detailed_info_display(self, text_widget, serial: str):
        """更新详细信息显示"""
        if hasattr(self, 'authenticators_data') and serial in self.authenticators_data:
            auth_info = self.authenticators_data[serial]
            detailed_info = self.get_detailed_authenticator_info(auth_info)

            text_widget.config(state=tk.NORMAL)
            text_widget.delete('1.0', tk.END)
            text_widget.insert('1.0', detailed_info)
            text_widget.config(state=tk.DISABLED)

    def _resolve_device_action_heading(self, serial: str, status_lower: str, uuid_display: str, auto_enabled: bool) -> str:
        manual_available_text = self.prompt_mgr.get('DeviceTable.action_manual_activate')
        manual_unavailable_text = self.prompt_mgr.get('DeviceTable.action_unavailable')
        auto_waiting_text = self.prompt_mgr.get('DeviceTable.action_waiting_auto')
        auto_done_text = self.prompt_mgr.get('DeviceTable.action_auto_completed')
        auto_anomaly_text = self.prompt_mgr.get('DeviceTable.action_auto_queue_anomaly')
        uuid_ready = self._is_uuid_ready(uuid_display)

        if auto_enabled:
            if self.auth_manager.is_device_auto_activation_completed(serial):
                return auto_done_text
            if status_lower == "unauthorized" and uuid_ready:
                if self.auth_manager.is_device_queued_for_auto_activation(serial):
                    return auto_waiting_text
                return auto_anomaly_text
            return manual_unavailable_text

        if status_lower == "unauthorized" and uuid_ready:
            return manual_available_text
        return manual_unavailable_text

    def update_device_display(self, devices: List[DeviceInfo]):
        """更新设备显示"""
        all_devices = list(devices or [])

        logging.debug(f"Updating device display with {len(all_devices)} devices")
        show_na_devices = self.config_manager.getboolean('UI', 'show_na_devices', False)
        auto_enabled = self.auth_manager.is_auto_activation_enabled()
        rows = []
        seen_serials = set()
        for device in all_devices:
            if device.serial in seen_serials:
                continue
            seen_serials.add(device.serial)

            if device.device_type == "unknown" and not show_na_devices:
                continue

            status_text = (device.status or "").strip()
            if not status_text:
                status_text = "Checking..."
            status_lower = status_text.lower()

            uuid_text = (device.uuid or "").strip()
            is_unknown_like = status_lower in ("unknown", "unknown device")
            if device.device_type == "unknown" or (not uuid_text and is_unknown_like):
                uuid_display = "N/A"
            else:
                uuid_display = uuid_text if uuid_text else "获取中..."

            heading = self._resolve_device_action_heading(
                serial=str(device.serial),
                status_lower=status_lower,
                uuid_display=uuid_display,
                auto_enabled=auto_enabled,
            )
            rows.append((
                "serial:" + str(device.serial),
                uuid_display,
                device.usb_port,
                status_text,
                heading
            ))

        self.root.after(0, lambda r=rows: self._apply_device_rows(r))

    def _update_auto_auth_ui_state(self, authenticator_count: Optional[int] = None):
        """根据自动授权开关更新UI提示与手动操作可用性"""
        auto_enabled = self.auth_manager.is_auto_activation_enabled()

        if authenticator_count is None:
            authenticator_count = len(getattr(self, 'authenticators_data', {}) or {})

        if auto_enabled:
            if authenticator_count > 0:
                self.auto_auth_tip_var.set(self.prompt_mgr.get('UI.auto_auth_enabled_hint'))
            else:
                self.auto_auth_tip_var.set(self.prompt_mgr.get('UI.auto_auth_enabled_cube_unavailable_hint'))

            if hasattr(self, 'activate_all_button'):
                self.activate_all_button.config(state='disabled')
        else:
            self.auto_auth_tip_var.set("")
            if hasattr(self, 'activate_all_button'):
                self.activate_all_button.config(state='normal')

    def _apply_device_rows(self, rows: List[tuple]):
        """在主线程应用设备表格数据"""
        # 保留用户当前选择与滚动位置
        selected_serials = []
        for item_id in self.device_tree.selection():
            values = self.device_tree.item(item_id).get('values', [])
            if values:
                serial_text = str(values[0])
                serial = serial_text.split('serial:')[-1] if serial_text.startswith('serial:') else serial_text
                if serial:
                    selected_serials.append(serial)

        focus_serial = None
        focus_item = self.device_tree.focus()
        if focus_item:
            focus_values = self.device_tree.item(focus_item).get('values', [])
            if focus_values:
                focus_text = str(focus_values[0])
                focus_serial = focus_text.split('serial:')[-1] if focus_text.startswith('serial:') else focus_text

        yview = self.device_tree.yview()

        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        serial_to_item = {}
        for row in rows:
            item_id = self.device_tree.insert('', 'end', values=row)
            serial_text = str(row[0]) if len(row) > 0 else ""
            serial = serial_text.split('serial:')[-1] if serial_text.startswith('serial:') else serial_text
            if serial:
                serial_to_item[serial] = item_id

        # 恢复选择
        selected_item_ids = [serial_to_item[s] for s in selected_serials if s in serial_to_item]
        if selected_item_ids:
            self.device_tree.selection_set(selected_item_ids)

            if focus_serial and focus_serial in serial_to_item:
                self.device_tree.focus(serial_to_item[focus_serial])
            else:
                self.device_tree.focus(selected_item_ids[0])

        # 恢复滚动位置
        if yview and len(yview) >= 1:
            self.device_tree.yview_moveto(yview[0])

    def on_monitor_error(self, error_message: str):
        """监控错误处理"""
        self.status_var.set(self.prompt_mgr.format('Monitoring.monitor_error', error=error_message))
        logging.error(self.prompt_mgr.format('Monitoring.network_monitor_error', error=error_message))

    # 菜单事件处理方法
    def load_config(self):
        file_path = filedialog.askopenfilename(title=self.prompt_mgr.get('MenuItems.load_config'), filetypes=[('INI文件','*.ini'),('所有文件','*.*')])
        if file_path:
            self.config_manager.load_config(file_path)
            # 配置重载后，同步自动授权开关
            auto_enabled = self.config_manager.getboolean('General', 'auto_activation_enabled', False)
            self.auth_manager.set_auto_activation_enabled(auto_enabled)
            if hasattr(self, 'auto_activation_menu_var'):
                self.auto_activation_menu_var.set(auto_enabled)
            self._update_auto_auth_ui_state()
            self.status_var.set(self.prompt_mgr.format('InfoMessages.config_loaded_status', path=file_path))
            messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), self.prompt_mgr.get('InfoMessages.config_loaded_success'))

    def toggle_auto_activation(self):
        """通过工具菜单切换自动授权开关并持久化到配置"""
        desired_state = bool(self.auto_activation_menu_var.get())

        if self.is_operation_in_progress or self.auth_manager.is_authenticating():
            # 当前有操作时不允许切换
            self.auto_activation_menu_var.set(self.auth_manager.is_auto_activation_enabled())
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        try:
            self.auth_manager.set_auto_activation_enabled(desired_state)
            self.config_manager.set('General', 'auto_activation_enabled', 'true' if desired_state else 'false')
            saved = self.config_manager.save_config()

            self._update_auto_auth_ui_state()
            if saved:
                self.status_var.set(
                    self.prompt_mgr.get('InfoMessages.auto_auth_enabled_status')
                    if desired_state else
                    self.prompt_mgr.get('InfoMessages.auto_auth_disabled_status')
                )
            else:
                self.status_var.set(self.prompt_mgr.get('InfoMessages.auto_auth_save_failed_status'))
                messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('InfoMessages.auto_auth_save_failed_status'))
        except Exception as e:
            logging.error(f"切换自动授权功能失败: {e}")
            self.auto_activation_menu_var.set(self.auth_manager.is_auto_activation_enabled())
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=str(e)))

    def export_config(self):
        file_path = filedialog.asksaveasfilename(title=self.prompt_mgr.get('MenuItems.export_config'), defaultextension='.ini', filetypes=[('INI文件','*.ini'),('所有文件','*.*')])
        if file_path:
            if self.config_manager.save_config(file_path):
                self.status_var.set(self.prompt_mgr.format('InfoMessages.config_loaded_status', path=file_path))
                messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), self.prompt_mgr.get('InfoMessages.config_export_success'))
            else:
                messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('InfoMessages.config_export_fail'))

    def config_log_level(self):
        """配置日志级别"""
        dialog = LogLevelDialog(self.root, self.log_manager, self.prompt_mgr)
        self.root.wait_window(dialog.dialog)

    def config_log_path(self):
        file_path = filedialog.asksaveasfilename(title=self.prompt_mgr.get('MenuItems.log_path'), defaultextension='.log', filetypes=[('日志文件','*.log'),('所有文件','*.*')])
        if file_path:
            if self.log_manager.update_log_file(file_path):
                messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), self.prompt_mgr.format('InfoMessages.log_path_updated', path=file_path))
            else:
                messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('InfoMessages.log_path_update_fail'))

    def view_logs(self):
        """查看日志"""
        dialog = LogViewDialog(self.root, self.log_manager, self.prompt_mgr)

    def clear_logs_from_tools_menu(self):
        """从工具菜单清空日志"""
        if not messagebox.askyesno(
            self.prompt_mgr.get('Common.confirm_title'),
            self.prompt_mgr.get('Text.confirm_clear_log')
        ):
            return

        action_name = self.prompt_mgr.get('MenuItems.clear_logs')
        if self.log_manager.clear_logs():
            self.status_var.set(self.prompt_mgr.get('Text.log_cleared'))
            messagebox.showinfo(
                self.prompt_mgr.get('Common.success_title'),
                self.prompt_mgr.format('InfoMessages.operation_success', name=action_name)
            )
            return

        messagebox.showerror(
            self.prompt_mgr.get('Common.fail_title'),
            self.prompt_mgr.format('InfoMessages.operation_fail', name=action_name)
        )

    def show_help(self):
        """显示帮助信息"""
        help_text = self.prompt_mgr.get('Text.help_content').replace('\\n', '\n')
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.get('Text.help_title'))
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()
        text_widget = tk.Text(dialog, wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert('1.0', help_text)
        text_widget.config(state=tk.DISABLED)
        ttk.Button(dialog, text=self.prompt_mgr.get('Text.help_close'), command=dialog.destroy).pack(pady=10)

    def show_about(self):
        """显示关于信息"""
        company = self.config_manager.get('About', 'company', 'Autochips Inc')
        version = self.config_manager.get('General', 'version', '3.1.8')
        description = self.config_manager.get('About', 'description', self.prompt_mgr.get('Dialogs.about_desc'))

        about_text = f"""
{description}

{self.prompt_mgr.format('Dialogs.about_company', company=company)}
{self.prompt_mgr.format('Dialogs.about_version', version=version)}
        """

        messagebox.showinfo(self.prompt_mgr.get('Dialogs.about_title'), about_text)

    def show_changelog(self):
        """显示更新日志"""
        changelog_path = 'changelog/CHANGELOG.md'

        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.get('Dialogs.changelog_title'))
        dialog.geometry("800x600")
        dialog.transient(self.root)

        # 创建文本显示区域
        text_frame = ttk.Frame(dialog, padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True)

        # 创建滚动文本框
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 读取并显示changelog内容
        try:
            if os.path.exists(changelog_path):
                with open(changelog_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    text_widget.insert('1.0', content)
            else:
                text_widget.insert('1.0', self.prompt_mgr.format('Errors.changelog_not_found', path=changelog_path))
        except Exception as e:
            text_widget.insert('1.0', self.prompt_mgr.get('Errors.load_changelog_fail') + f"\n{str(e)}")

        # 设置为只读
        text_widget.config(state='disabled')

        # 关闭按钮
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.close'), command=dialog.destroy).pack(side=tk.RIGHT)

    def lock_authenticator(self):
        """锁定激活盒子"""
        self.show_authenticator_operation_dialog("lock", self.prompt_mgr.get('UI.lock_authenticator_title'))

    def unlock_authenticator(self):
        """解锁激活盒子"""
        self.show_authenticator_operation_dialog("unlock", self.prompt_mgr.get('UI.unlock_authenticator_title'))

    def activate_authenticator(self):
        """激活激活盒子"""
        self.show_authenticator_operation_dialog("activate", self.prompt_mgr.get('UI.activate_authenticator_title'))

    def config_authenticator(self):
        """配置激活盒子"""
        self.show_authenticator_operation_dialog("config", self.prompt_mgr.get('UI.config_authenticator_title'))

    # 新增：查看当前WiFi连接
    def view_current_wifi(self):
        """查看当前WiFi连接状态"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        # 获取激活盒子列表
        authenticators = list(self.device_monitor.authenticators.keys())
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Errors.no_device'))
            return

        # 如果只有一个设备，直接显示
        if len(authenticators) == 1:
            device_serial = authenticators[0]
            self._show_wifi_status_dialog(device_serial)
            return

        # 多个设备时，创建设备选择对话框
        device_dialog = tk.Toplevel(self.root)
        device_dialog.title(self.prompt_mgr.get('Dialogs.select_device_title'))
        device_dialog.geometry("400x200")
        device_dialog.transient(self.root)
        device_dialog.grab_set()

        ttk.Label(device_dialog, text=self.prompt_mgr.get('Dialogs.device_list_label'), font=('Arial', 10)).pack(pady=20)

        device_var = tk.StringVar()
        device_combo = ttk.Combobox(device_dialog, textvariable=device_var, values=authenticators, state="readonly", width=40)
        device_combo.pack(pady=10)
        device_combo.set(authenticators[0])

        def on_select():
            selected = device_var.get()
            if selected:
                device_dialog.destroy()
                self._show_wifi_status_dialog(selected)

        ttk.Button(device_dialog, text=self.prompt_mgr.get('Buttons.ok'), command=on_select).pack(pady=10)
        ttk.Button(device_dialog, text=self.prompt_mgr.get('Buttons.cancel'), command=device_dialog.destroy).pack(pady=5)

    def _show_wifi_status_dialog(self, device_serial: str):
        """显示WiFi状态对话框"""
        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.format('Dialogs.wifi_status_title', device=device_serial))
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        # 状态标签
        status_label = ttk.Label(dialog, text=self.prompt_mgr.get('WifiStatus.fetching', fallback='正在获取WiFi状态...'), foreground="blue")
        status_label.pack(pady=20)

        # 信息显示区域
        info_frame = ttk.LabelFrame(dialog, text=self.prompt_mgr.get('Dialogs.wifi_info_group'), padding=20)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 创建信息标签
        info_labels = {}
        info_items = [
            (self.prompt_mgr.get('WifiStatus.status', fallback='状态'), 'status'),
            (self.prompt_mgr.get('WifiStatus.ssid', fallback='WiFi名称'), 'ssid'),
            (self.prompt_mgr.get('WifiStatus.bssid', fallback='MAC地址'), 'bssid'),
            (self.prompt_mgr.get('WifiStatus.signal', fallback='信号强度'), 'signal'),
            (self.prompt_mgr.get('WifiStatus.band', fallback='频段'), 'band'),
            (self.prompt_mgr.get('WifiStatus.frequency', fallback='频率'), 'frequency'),
            (self.prompt_mgr.get('WifiStatus.link_speed', fallback='链接速度'), 'link_speed'),
        ]

        for i, (label_text, key) in enumerate(info_items):
            row_frame = ttk.Frame(info_frame)
            row_frame.pack(fill=tk.X, pady=5)

            ttk.Label(row_frame, text=f"{label_text}:", width=12, anchor='e').pack(side=tk.LEFT, padx=(0, 10))
            value_label = ttk.Label(row_frame, text="--", anchor='w', font=('Arial', 10, 'bold'))
            value_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            info_labels[key] = value_label

        # 按钮区域
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        ttk.Button(button_frame, text=self.prompt_mgr.get('Buttons.refresh', fallback='刷新'), command=lambda: refresh_status()).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=self.prompt_mgr.get('Buttons.close'), command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        def refresh_status():
            """刷新WiFi状态"""
            status_label.config(text=self.prompt_mgr.get('WifiStatus.fetching', fallback='正在获取WiFi状态...'), foreground="blue")
            dialog.update()

            def worker():
                try:
                    wifi_info = self.adb_manager.get_current_wifi(device_serial)
                    dialog.after(0, lambda: display_info(wifi_info))
                except Exception as e:
                    dialog.after(0, lambda: show_error(str(e)))

            threading.Thread(target=worker, daemon=True).start()
        def display_info(wifi_info):
            """显示WiFi信息"""
            good = self.prompt_mgr.get('Network.signal_good', fallback='优秀')
            normal = self.prompt_mgr.get('Network.signal_normal', fallback='良好')
            bad = self.prompt_mgr.get('Network.signal_bad', fallback='较差')
            if wifi_info['connected']:
                status_label.config(text=self.prompt_mgr.get('WifiStatus.connected', fallback='✓ 已连接到WiFi'), foreground="green")
                info_labels['status'].config(text=self.prompt_mgr.get('WifiStatus.connected_short', fallback='已连接'), foreground="green")
                info_labels['ssid'].config(text=wifi_info['ssid'])
                info_labels['bssid'].config(text=wifi_info['bssid'] or "--")

                # 信号强度显示
                if wifi_info['signal']:
                    signal_text = f"{wifi_info['signal']}dBm"
                    if wifi_info['signal_level']:
                        signal_text += f" ({wifi_info['signal_level']})"
                    info_labels['signal'].config(text=signal_text)

                    # 根据信号等级设置颜色
                    level = wifi_info.get('signal_level')
                    if level == good:
                        info_labels['signal'].config(foreground="green")
                    elif level == normal:
                        info_labels['signal'].config(foreground="blue")
                    elif level in ("一般", bad):
                        info_labels['signal'].config(foreground="orange")
                    else:
                        info_labels['signal'].config(foreground="red")
                else:
                    info_labels['signal'].config(text="--")

                info_labels['band'].config(text=wifi_info['band'] or "--")
                info_labels['frequency'].config(text=f"{wifi_info['frequency']}MHz" if wifi_info['frequency'] else "--")
                info_labels['link_speed'].config(text=wifi_info['link_speed'] or "--")
            else:
                status_label.config(text=self.prompt_mgr.get('WifiStatus.disconnected', fallback='✗ 未连接WiFi'), foreground="red")
                info_labels['status'].config(text=self.prompt_mgr.get('WifiStatus.disconnected_short', fallback='未连接'), foreground="red")
                info_labels['ssid'].config(text="--")
                info_labels['bssid'].config(text="--")
                info_labels['signal'].config(text="--", foreground="black")
                info_labels['band'].config(text="--")
                info_labels['frequency'].config(text="--")
                info_labels['link_speed'].config(text="--")

        def show_error(error_msg):
            """显示错误"""
            status_label.config(text=self.prompt_mgr.format('Errors.unknown_error', msg=error_msg), foreground="red")
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=error_msg))

        # 初始加载
        refresh_status()

    def scan_and_connect_wifi(self):
        """扫描并连接WiFi"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        # 获取激活盒子列表
        authenticators = list(self.device_monitor.authenticators.keys())
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Errors.no_device'))
            return

        # 如果只有一个设备，直接打开扫描对话框
        if len(authenticators) == 1:
            device_serial = authenticators[0]
            dialog = WifiScanDialog(
                self.root,
                device_serial,
                self.adb_manager,
                self.perform_authenticator_wifi_connect,
                self.config_manager,
                self.prompt_mgr
            )
            return

        # 多个设备时，创建设备选择对话框
        device_dialog = tk.Toplevel(self.root)
        device_dialog.title(self.prompt_mgr.get('Dialogs.select_device_title'))
        device_dialog.geometry("400x200")
        device_dialog.transient(self.root)
        device_dialog.grab_set()

        ttk.Label(device_dialog, text=self.prompt_mgr.get('Dialogs.device_list_label'), font=('Arial', 10)).pack(pady=20)

        device_var = tk.StringVar()
        device_combo = ttk.Combobox(device_dialog, textvariable=device_var, values=authenticators, state="readonly", width=40)
        device_combo.pack(pady=10)
        device_combo.set(authenticators[0])

        def on_select():
            selected = device_var.get()
            if selected:
                device_dialog.destroy()
                _dialog = WifiScanDialog(
                    self.root,
                    selected,
                    self.adb_manager,
                    self.perform_authenticator_wifi_connect,
                    self.config_manager,
                    self.prompt_mgr
                )

        ttk.Button(device_dialog, text=self.prompt_mgr.get('Buttons.ok'), command=on_select).pack(pady=10)
        ttk.Button(device_dialog, text=self.prompt_mgr.get('Buttons.cancel'), command=device_dialog.destroy).pack(pady=5)

    def authenticator_wifi_connect(self):
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        authenticators = [d.serial for d in self.device_monitor.authenticators.values()]
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Errors.no_pending_authenticator'))
            return
        dialog = WifiConfigDialog(self.root, authenticators, self.perform_authenticator_wifi_connect, self.config_manager, self.prompt_mgr)
        self.root.wait_window(dialog.dialog)

    def authenticator_wifi_disconnect(self):
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return
        authenticators = [d.serial for d in self.device_monitor.authenticators.values()]
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Errors.no_pending_authenticator'))
            return
        dialog = WifiDisconnectDialog(self.root, authenticators, self.perform_authenticator_wifi_disconnect, self.prompt_mgr)
        self.root.wait_window(dialog.dialog)

    def perform_authenticator_wifi_disconnect(self, device_serial: str):
        """执行设备WiFi断开流程"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return
        self.is_operation_in_progress = True

        progress = ProgressDialog(self.root, self.prompt_mgr.get('Progress.wifi_disconnect_title'), self.prompt_mgr.get('Progress.preparing'))

        def worker():
            try:
                progress.update_progress(self.prompt_mgr.get('Progress.wifi_disconnect_progress'))
                disconn_res = self.adb_manager.wifi_disable(device_serial)
                if not disconn_res.success:
                    raise Exception(disconn_res.error_message or 'Unknown')

                self.root.after(0, lambda: (progress.close(), self._on_wifi_done(True, self.prompt_mgr.get('Progress.wifi_disconnect_success'))))
            except Exception as e:
                msg = self.prompt_mgr.format('Progress.wifi_disconnect_fail', error=str(e))
                self.root.after(0, lambda: (progress.close(), self._on_wifi_done(False, msg)))

        threading.Thread(target=worker, daemon=True).start()

    def perform_authenticator_wifi_connect(self, device_serial: str, ssid: str, password: str, security: str):
        """执行设备WiFi连接流程"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return
        self.is_operation_in_progress = True

        progress = ProgressDialog(self.root, self.prompt_mgr.get('Dialogs.wifi_config_title'), self.prompt_mgr.get('Progress.preparing'))

        def worker():
            try:                # 可选：先关闭再打开
                progress.update_progress(self.prompt_mgr.get('Progress.closing_wifi'))
                self.adb_manager.wifi_disable(device_serial)

                progress.update_progress(self.prompt_mgr.get('Progress.enabling_wifi'))
                enable_res = self.adb_manager.wifi_enable(device_serial)
                if not enable_res.success:
                    raise Exception(enable_res.error_message or 'Enable failed')

                progress.update_progress(self.prompt_mgr.get('Progress.connecting_wifi_progress'))
                conn_res = self.adb_manager.wifi_connect(device_serial, ssid, password, security)
                if not conn_res.success:
                    raise Exception(conn_res.error_message or 'Connect failed')

                # NEW in Update 4: 等待网络稳定（增加等待时间，确保DHCP和DNS配置完成）
                progress.update_progress(self.prompt_mgr.get('Progress.waiting_network_stable'))
                time.sleep(3)

                # NEW in Update 4: 测试网络连通性
                progress.update_progress(self.prompt_mgr.get('Progress.testing_connectivity'))
                total = len(self.ping_hosts)
                success_count = 0

                for idx, host in enumerate(self.ping_hosts):
                    progress.update_progress(self.prompt_mgr.format('Progress.connectivity_host_progress', idx=idx+1, total=total, host=host))
                    # 首次失败后重试一次（可能DNS刚配置完成）
                    if self.adb_manager.ping_host(device_serial, host):
                        success_count += 1
                    else:
                        # 等待1秒后重试
                        time.sleep(1)
                        if self.adb_manager.ping_host(device_serial, host):
                            success_count += 1

                # 判断结果
                if success_count == 0:
                    raise Exception(self.prompt_mgr.get('Progress.all_ping_failed'))

                # 构建成功消息
                percentage = int((success_count / total) * 100) if total > 0 else 0
                success_msg = self.prompt_mgr.format('Progress.wifi_connect_success_with_test', success_count=success_count, total=total, percentage=percentage).replace('\\n', '\n')

                # 检查关键节点
                critical_success = self.adb_manager.ping_host(device_serial, self.critical_host)
                if not critical_success:
                    success_msg += "\n\n" + self.prompt_mgr.format('Progress.critical_host_unreachable_warn', host=self.critical_host)

                self.root.after(0, lambda: (progress.close(), self._on_wifi_done(True, success_msg)))

            except Exception as e:
                msg = f"{self.prompt_mgr.get('Errors.wifi_connect_fail').format(reason=str(e))}"
                self.root.after(0, lambda: (progress.close(), self._on_wifi_done(False, msg)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_wifi_done(self, success: bool, msg: str):
        self.is_operation_in_progress = False
        if success:
            self.status_var.set(self.prompt_mgr.get('Status.wifi_connected'))
            messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), msg)
        else:
            self.status_var.set(self.prompt_mgr.get('Errors.wifi_connect_fail').format(reason=msg))
            messagebox.showerror(self.prompt_mgr.get('Common.fail_title'), msg)

    def show_authenticator_operation_dialog(self, operation: str, title: str):
        """显示激活盒子操作对话框"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        dialog = AuthenticatorOperationDialog(
            self.root,
            title,
            operation,
            self.auth_manager.get_available_authenticators(),
            self.perform_authenticator_operation,
            self.prompt_mgr
        )

    def perform_authenticator_operation(self, operation: str, serial: str, token_data: str):
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return
        self.is_operation_in_progress = True
        names = {
            'lock': self.prompt_mgr.get('MenuItems.lock_auth'),
            'unlock': self.prompt_mgr.get('MenuItems.unlock_auth'),
            'activate': self.prompt_mgr.get('MenuItems.activate_auth'),
            'config': self.prompt_mgr.get('MenuItems.config_auth')
        }
        operation_title = names.get(operation, operation)
        progress = ProgressDialog(self.root, operation_title, self.prompt_mgr.get('Progress.preparing'))
        def operation_thread():
            try:
                progress.update_progress(self.prompt_mgr.format('Progress.executing_operation', name=operation_title))
                result = self.auth_manager.perform_cube_operation(operation, serial, token_data)
                self.root.after(0, lambda: (progress.close(), self.on_operation_complete(operation, result)))
            except Exception as e:
                self.root.after(0, lambda: (progress.close(), self.on_operation_error(operation, str(e))))
        threading.Thread(target=operation_thread, daemon=True).start()

    def on_operation_complete(self, operation: str, result):
        self.is_operation_in_progress = False
        names = {
            'lock': self.prompt_mgr.get('MenuItems.lock_auth'),
            'unlock': self.prompt_mgr.get('MenuItems.unlock_auth'),
            'activate': self.prompt_mgr.get('MenuItems.activate_auth'),
            'config': self.prompt_mgr.get('MenuItems.config_auth')
        }
        operation_title = names.get(operation, operation)
        if result and result.success:
            self.status_var.set(self.prompt_mgr.format('Status.operation_success', name=operation_title))
            messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), self.prompt_mgr.format('Status.operation_success', name=operation_title))
        else:
            error_msg = result.error_message if result else self.prompt_mgr.get('Errors.unknown_error')
            self.status_var.set(self.prompt_mgr.format('Status.operation_fail', name=operation_title))
            messagebox.showerror(self.prompt_mgr.get('Common.fail_title'), self.prompt_mgr.format('Status.operation_fail', name=operation_title) + f"\n{error_msg}")

    def on_operation_error(self, operation: str, error_message: str):
        self.is_operation_in_progress = False
        names = {
            'lock': self.prompt_mgr.get('MenuItems.lock_auth'),
            'unlock': self.prompt_mgr.get('MenuItems.unlock_auth'),
            'activate': self.prompt_mgr.get('MenuItems.activate_auth'),
            'config': self.prompt_mgr.get('MenuItems.config_auth')
        }
        operation_title = names.get(operation, operation)
        self.status_var.set(self.prompt_mgr.format('Status.operation_fail', name=operation_title))
        messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=error_message))

    def refresh_devices(self):
        """手动刷新设备"""
        # 如果正在刷新，防止重复操作
        if self.is_refreshing_devices:
            logging.warning(self.prompt_mgr.get('Refresh.refresh_in_progress_warn'))
            return

        try:
            # 设置刷新标志并禁用按钮
            self.is_refreshing_devices = True
            self.refresh_button.config(state='disabled')
            self.status_var.set(self.prompt_mgr.get('Refresh.refreshing_devices'))

            # 在后台线程中执行刷新
            def do_refresh():
                try:
                    self.device_monitor.refresh_devices()
                    self.root.after(0, lambda: self.status_var.set(self.prompt_mgr.get('Refresh.devices_refreshed')))
                except Exception as e:
                    logging.error(f"刷新设备失败: {e}")
                    self.root.after(0, lambda: self.status_var.set(self.prompt_mgr.format('Refresh.devices_refresh_failed', error=str(e))))
                finally:
                    # 恢复按钮状态
                    self.root.after(0, self._enable_refresh_button)

            # 启动后台线程
            threading.Thread(target=do_refresh, daemon=True).start()

        except Exception as e:
            logging.error(f"启动刷新任务失败: {e}")
            self._enable_refresh_button()

    def _enable_refresh_button(self):
        """恢复刷新按钮的可用状态"""
        self.is_refreshing_devices = False
        self.refresh_button.config(state='normal')

    def on_device_double_click(self, event):
        if self.auth_manager.is_auto_activation_enabled():
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.auto_auth_manual_disabled'))
            return

        selection = self.device_tree.selection()
        if selection:
            item = self.device_tree.item(selection[0])
            device_serial = item['values'][0].split('serial:')[-1]
            uuid_text = item['values'][1] if len(item['values']) > 1 else ""
            auth_status = item['values'][3]
            if auth_status.strip().lower() == 'unauthorized':
                if not self._is_uuid_ready(uuid_text):
                    messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), f"设备 {device_serial} 的UUID尚未获取完成，暂不允许激活")
                    return
                self.authenticate_device(device_serial)
            else:
                messagebox.showinfo(self.prompt_mgr.get('Common.info_title'), self.prompt_mgr.format('InfoMessages.device_already_activated', device=device_serial))

    @staticmethod
    def _extract_device_serial(item_values) -> str:
        if not item_values:
            return ""
        serial_text = str(item_values[0])
        return serial_text.split('serial:')[-1] if serial_text.startswith('serial:') else serial_text

    def on_device_right_click(self, event):
        item_id = self.device_tree.identify_row(event.y)
        if not item_id:
            return
        self.device_tree.selection_set(item_id)
        self.device_tree.focus(item_id)
        values = self.device_tree.item(item_id).get('values', [])
        device_serial = self._extract_device_serial(values)
        if not device_serial:
            return
        target_device = self.device_monitor.get_target_device(device_serial)
        if not target_device or target_device.getType() != self._SIMULATOR_DEVICE_TYPE:
            return

        self.device_context_menu.delete(0, 'end')
        self.device_context_menu.add_command(
            label=self.prompt_mgr.get('MenuItems.remove_simulated_device'),
            command=lambda s=device_serial: self.remove_simulated_device(s),
        )
        self.device_context_menu.tk_popup(event.x_root, event.y_root)
        self.device_context_menu.grab_release()

    def remove_simulated_device(self, device_serial: str):
        target_device = self.device_monitor.get_target_device(device_serial)
        if not target_device or target_device.getType() != self._SIMULATOR_DEVICE_TYPE:
            return False

        if not messagebox.askyesno(
            self.prompt_mgr.get('Common.confirm_title'),
            self.prompt_mgr.format('Text.confirm_remove_simulated_device', serial=device_serial),
        ):
            return False

        if not self.device_monitor.remove_simulated_device(device_serial):
            messagebox.showerror(
                self.prompt_mgr.get('Common.error_title'),
                self.prompt_mgr.format('InfoMessages.simulated_device_remove_failed', serial=device_serial),
            )
            return False

        self.device_monitor.update_devices()
        self.status_var.set(self.prompt_mgr.format('InfoMessages.simulated_device_removed', serial=device_serial))
        return True

    def _is_uuid_ready(self, uuid_text: str) -> bool:
        """判断UUID是否已准备好"""
        value = (uuid_text or "").strip()
        return value not in ("", "-", "获取中...", "Checking...")

    def show_add_simulated_device_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.get('Dialogs.add_simulated_device_title'))
        dialog.geometry("360x180")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=self.prompt_mgr.get('Dialogs.simulated_device_status_label')).pack(anchor='w', pady=(0, 8))
        status_var = tk.StringVar(value="Unauthorized")
        status_box = ttk.Combobox(frame, textvariable=status_var, state="readonly", values=["Unauthorized", "Authorized", "Pirated"])
        status_box.pack(fill=tk.X, pady=(0, 12))

        def do_add():
            try:
                simulated = DeviceMonitor.create_simulated_device(self.device_monitor, status_var.get())
                self.device_monitor.update_devices()
                self.status_var.set(self.prompt_mgr.format('InfoMessages.simulated_device_added', status=simulated.status))
                dialog.destroy()
            except Exception as e:
                messagebox.showerror(self.prompt_mgr.get('Common.fail_title'), str(e))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.ok'), command=do_add).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.cancel'), command=dialog.destroy).pack(side=tk.RIGHT)

    def show_create_simulated_cube_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.get('Dialogs.create_simulated_cube_title'))
        dialog.geometry("520x390")
        dialog.transient(self.root)
        dialog.grab_set()

        fields = ttk.Frame(dialog, padding=12)
        fields.pack(fill=tk.BOTH, expand=True)

        expire_var = tk.StringVar()
        counter_var = tk.StringVar(value="100")
        key_path_var = tk.StringVar()
        cube_id_var = tk.StringVar()
        oem_id_var = tk.StringVar()
        persist_path_var = tk.StringVar()

        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_expire_label')).grid(row=0, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=expire_var, width=45).grid(row=0, column=1, sticky='we', pady=4)
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_counter_label')).grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=counter_var, width=45).grid(row=1, column=1, sticky='we', pady=4)
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_private_key_label')).grid(row=2, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=key_path_var, width=45).grid(row=2, column=1, sticky='we', pady=4)
        ttk.Button(fields, text=self.prompt_mgr.get('Buttons.choose_file'), command=lambda: key_path_var.set(filedialog.askopenfilename() or key_path_var.get())).grid(row=2, column=2, padx=(5, 0))
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_id_label')).grid(row=3, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=cube_id_var, width=45).grid(row=3, column=1, sticky='we', pady=4)
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_oem_id_label')).grid(row=4, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=oem_id_var, width=45).grid(row=4, column=1, sticky='we', pady=4)
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_persist_path_label')).grid(row=5, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=persist_path_var, width=45).grid(row=5, column=1, sticky='we', pady=4)
        ttk.Button(fields, text=self.prompt_mgr.get('Buttons.choose_file'), command=lambda: persist_path_var.set(filedialog.asksaveasfilename(defaultextension=".json") or persist_path_var.get())).grid(row=5, column=2, padx=(5, 0))
        fields.columnconfigure(1, weight=1)

        def on_create():
            try:
                serial = self.auth_manager.create_simulated_cube(
                    expired_date=expire_var.get().strip(),
                    counter=int(counter_var.get().strip() or "0"),
                    private_key_path=key_path_var.get().strip(),
                    cube_id=cube_id_var.get().strip(),
                    oem_id=oem_id_var.get().strip(),
                    persist_path=persist_path_var.get().strip(),
                )
                dialog.destroy()
                self.status_var.set(self.prompt_mgr.format('InfoMessages.simulated_cube_created', serial=serial))
                self.update_authenticator_display(self.device_monitor.authenticators)
            except Exception as e:
                messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=str(e)))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, pady=(5, 10))
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.ok'), command=on_create).pack(side=tk.RIGHT, padx=8)
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.cancel'), command=dialog.destroy).pack(side=tk.RIGHT)

    def show_load_simulated_cube_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.prompt_mgr.get('Dialogs.load_simulated_cube_title'))
        dialog.geometry("520x220")
        dialog.transient(self.root)
        dialog.grab_set()

        fields = ttk.Frame(dialog, padding=12)
        fields.pack(fill=tk.BOTH, expand=True)

        cube_path_var = tk.StringVar()
        key_path_var = tk.StringVar()

        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_file_path_label')).grid(row=0, column=0, sticky='w', pady=6)
        ttk.Entry(fields, textvariable=cube_path_var, width=45).grid(row=0, column=1, sticky='we', pady=6)
        ttk.Button(fields, text=self.prompt_mgr.get('Buttons.choose_file'), command=lambda: cube_path_var.set(filedialog.askopenfilename() or cube_path_var.get())).grid(row=0, column=2, padx=(5, 0))
        ttk.Label(fields, text=self.prompt_mgr.get('Dialogs.sim_cube_private_key_label')).grid(row=1, column=0, sticky='w', pady=6)
        ttk.Entry(fields, textvariable=key_path_var, width=45).grid(row=1, column=1, sticky='we', pady=6)
        ttk.Button(fields, text=self.prompt_mgr.get('Buttons.choose_file'), command=lambda: key_path_var.set(filedialog.askopenfilename() or key_path_var.get())).grid(row=1, column=2, padx=(5, 0))
        fields.columnconfigure(1, weight=1)

        def on_load():
            try:
                serial = self.auth_manager.load_simulated_cube(
                    persist_path=cube_path_var.get().strip(),
                    private_key_path=key_path_var.get().strip(),
                )
                dialog.destroy()
                self.status_var.set(self.prompt_mgr.format('InfoMessages.simulated_cube_loaded', serial=serial))
                self.update_authenticator_display(self.device_monitor.authenticators)
            except Exception as e:
                messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=str(e)))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, pady=(5, 10))
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.ok'), command=on_load).pack(side=tk.RIGHT, padx=8)
        ttk.Button(btn_frame, text=self.prompt_mgr.get('Buttons.cancel'), command=dialog.destroy).pack(side=tk.RIGHT)

    def _get_uuid_by_serial_from_tree(self, device_serial: str) -> str:
        """从设备表格中按serial获取UUID显示值"""
        target = f"serial:{device_serial}"
        for item_id in self.device_tree.get_children():
            values = self.device_tree.item(item_id).get('values', [])
            if len(values) >= 2 and str(values[0]) == target:
                return str(values[1])
        return ""

    def authenticate_device(self, device_serial: str):
        """激活单个设备"""
        if self.auth_manager.is_auto_activation_enabled():
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.auto_auth_manual_disabled'))
            return

        if self.is_operation_in_progress or self.auth_manager.is_authenticating():
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        # UUID未准备好时不允许激活
        uuid_text = self._get_uuid_by_serial_from_tree(device_serial)
        if not self._is_uuid_ready(uuid_text):
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), f"设备 {device_serial} 的UUID尚未获取完成，暂不允许激活")
            return

        # 获取可用的激活盒子
        authenticators = self.auth_manager.get_available_authenticators()
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Validation.no_available_authenticator'))
            return

        dialog = AuthenticationDialog(
            self.root,
            device_serial,
            authenticators,
            self.perform_device_authentication,
            self.prompt_mgr
        )

    def authenticate_all_devices(self):
        """激活所有设备"""
        if self.auth_manager.is_auto_activation_enabled():
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.auto_auth_manual_disabled'))
            return

        if self.is_operation_in_progress or self.auth_manager.is_authenticating():
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Errors.operation_in_progress'))
            return

        # 获取未激活设备
        unauthorized_devices = self.auth_manager.get_unauthorized_devices()
        if not unauthorized_devices:
            messagebox.showinfo(self.prompt_mgr.get('Common.info_title'), self.prompt_mgr.get('Validation.no_need_activation'))
            return

        # 获取可用的激活盒子
        authenticators = self.auth_manager.get_available_authenticators()
        if not authenticators:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Validation.no_available_authenticator'))
            return

        # UUID未获取完成的设备不允许进入批量激活
        invalid_devices = []
        for device in unauthorized_devices:
            serial = str(device.serial)
            uuid_text = self._get_uuid_by_serial_from_tree(serial)
            if not self._is_uuid_ready(uuid_text):
                invalid_devices.append(serial)
        if invalid_devices:
            messagebox.showwarning(
                self.prompt_mgr.get('Common.warn_title'),
                "以下设备UUID尚未获取完成，暂不允许批量激活:\n" + "\n".join(invalid_devices)
            )
            return

        dialog = BatchAuthenticationDialog(
            self.root,
            len(unauthorized_devices),
            authenticators,
            self.perform_batch_authentication,
            self.prompt_mgr
        )

    def perform_device_authentication(self, device_serial: str, authenticator_serial: str):
        """执行设备激活"""
        uuid_text = self._get_uuid_by_serial_from_tree(device_serial)
        if not self._is_uuid_ready(uuid_text):
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), f"设备 {device_serial} 的UUID尚未获取完成，暂不允许激活")
            return

        self.is_operation_in_progress = True

        dialog = ProgressDialog(self.root, self.prompt_mgr.get('Text.single_activation_title'), self.prompt_mgr.get('Text.activation_preparing'))

        def auth_thread():
            try:
                result = self.auth_manager.authenticate_device(
                    device_serial,
                    authenticator_serial,
                    lambda msg: dialog.update_progress(msg)
                )

                self.root.after(0, lambda: self.on_authentication_complete(result, dialog, device_serial))

            except Exception as e:
                self.root.after(0, lambda: self.on_authentication_error(str(e), dialog, device_serial))

        threading.Thread(target=auth_thread, daemon=True).start()

    def perform_batch_authentication(self, authenticator_serial: str):
        """执行批量激活"""
        # 执行前再次校验，防止UI状态变化导致UUID缺失设备被激活
        unauthorized_devices = self.auth_manager.get_unauthorized_devices()
        not_ready = []
        for device in unauthorized_devices:
            serial = str(device.serial)
            uuid_text = self._get_uuid_by_serial_from_tree(serial)
            if not self._is_uuid_ready(uuid_text):
                not_ready.append(serial)
        if not_ready:
            messagebox.showwarning(
                self.prompt_mgr.get('Common.warn_title'),
                "以下设备UUID尚未获取完成，暂不允许批量激活:\n" + "\n".join(not_ready)
            )
            return

        self.is_operation_in_progress = True

        dialog = ProgressDialog(self.root, self.prompt_mgr.get('Text.batch_activation_title'), self.prompt_mgr.get('Text.batch_activation_preparing'))

        def auth_thread():
            try:
                result = self.auth_manager.authenticate_all_devices(
                    authenticator_serial,
                    lambda msg: dialog.update_progress(msg)
                )

                self.root.after(0, lambda: self.on_batch_authentication_complete(result, dialog))

            except Exception as e:
                self.root.after(0, lambda: self.on_authentication_error(str(e), dialog))

        threading.Thread(target=auth_thread, daemon=True).start()

    def on_authentication_complete(self, result: dict, progress_dialog, device_serial: str = None):
        """激活完成处理"""
        progress_dialog.close()
        self.is_operation_in_progress = False

        if result['success']:
            self.status_var.set(self.prompt_mgr.get('Text.activation_success'))
            messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), result['message'])
        else:
            self.status_var.set(self.prompt_mgr.get('Text.activation_fail'))
            messagebox.showerror(self.prompt_mgr.get('Common.fail_title'), result['message'])
        # 单设备激活完成后（无论成功失败）刷新该设备解析状态
        if device_serial:
            self.device_monitor.refresh_device(device_serial)
            self.device_monitor.refresh_all_cube()

    def on_batch_authentication_complete(self, result: dict, progress_dialog):
        """批量激活完成处理"""
        progress_dialog.close()
        self.is_operation_in_progress = False

        if result['success']:
            self.status_var.set(self.prompt_mgr.format('Text.batch_activation_success', success_count=result['success_count'], failed_count=result['failed_count']))
            messagebox.showinfo(self.prompt_mgr.get('Common.success_title'), result['message'])
        else:
            self.status_var.set(self.prompt_mgr.get('Text.batch_activation_fail_status'))
            messagebox.showerror(self.prompt_mgr.get('Common.fail_title'), result['message'])
        # 批量激活完成后刷新全部设备解析状态
        self.device_monitor.refresh_all_device()

    def on_authentication_error(self, error_message: str, progress_dialog, device_serial: str = None):
        """激活错误处理"""
        progress_dialog.close()
        self.is_operation_in_progress = False
        self.status_var.set(self.prompt_mgr.format('Errors.unknown_error', msg=error_message))
        messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.unknown_error', msg=error_message))

        # 异常结束同样触发刷新
        if device_serial:
            self.device_monitor.refresh_device(device_serial)
            self.device_monitor.refresh_all_cube()
        else:
            self.device_monitor.refresh_all_device()

    # 诊断日志功能方法 (NEW in Update 2)
    def get_token_diagnostic(self):
        """获取token记录"""
        self.get_diagnostic_logs("token", self.prompt_mgr.get('Diagnostic.get_token_diag_title'))

    def get_trusted_service_diagnostic(self):
        """获取TA诊断信息"""
        self.get_diagnostic_logs("trusted_service", self.prompt_mgr.get('Diagnostic.get_trusted_service_diag_title'))

    def get_authorization_diagnostic(self):
        """获取激活记录"""
        self.get_diagnostic_logs("authorization", self.prompt_mgr.get('Diagnostic.get_authorization_diag_title'))

    def get_diagnostic_logs(self, diagnostic_type: str, title: str):
        """通用诊断日志处理"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Diagnostic.operation_in_progress_warn'))
            return

        # 获取激活盒子设备列表（诊断功能针对激活盒子执行）
        devices = list(self.device_monitor.authenticators.keys())
        if not devices:
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.get('Diagnostic.no_authenticator_devices'))
            return

        dialog = DiagnosticDialog(self.root, devices, diagnostic_type, title, self.perform_diagnostic_export, self.prompt_mgr)
        self.root.wait_window(dialog.dialog)

    def perform_diagnostic_export(self, device_serial: str, diagnostic_type: str, save_path: str):
        """执行诊断日志导出流程"""
        if self.is_operation_in_progress:
            messagebox.showwarning(self.prompt_mgr.get('Common.warn_title'), self.prompt_mgr.get('Diagnostic.operation_in_progress_warn'))
            return

        self.is_operation_in_progress = True
        progress = ProgressDialog(self.root, self.prompt_mgr.format('Diagnostic.export_title_fmt', dtype=diagnostic_type), self.prompt_mgr.get('Diagnostic.generating_diag'))

        def worker():
            try:
                # 生成唯一前缀
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = f"diag_{diagnostic_type}_{timestamp}"

                # 执行诊断命令
                progress.update_progress(self.prompt_mgr.format('Diagnostic.executing_diag', dtype=diagnostic_type))
                if diagnostic_type == "token":
                    result = self.adb_manager.diagnostic_token(device_serial, prefix)
                elif diagnostic_type == "trusted_service":
                    result = self.adb_manager.diagnostic_trusted_service(device_serial, prefix)
                elif diagnostic_type == "authorization":
                    result = self.adb_manager.diagnostic_authorization(device_serial, prefix)
                else:
                    raise Exception(self.prompt_mgr.format('Diagnostic.unsupported_diag_type', dtype=diagnostic_type))

                if not result.success:
                    raise Exception(result.error_message)

                # 等待文件生成
                progress.update_progress(self.prompt_mgr.get('Diagnostic.waiting_files'))
                time.sleep(1)

                # 列出生成的文件
                progress.update_progress(self.prompt_mgr.get('Diagnostic.searching_files'))
                files = self.adb_manager.list_diagnostic_files(device_serial, prefix)
                if not files:
                    raise Exception(self.prompt_mgr.get('Diagnostic.no_diag_files'))

                # 拉取文件到本地
                progress.update_progress(self.prompt_mgr.get('Diagnostic.exporting_files'))
                os.makedirs(save_path, exist_ok=True)

                pulled_files = []
                for filename in files:
                    remote_path = f"/sdcard/CbssDiagnostic/{filename}"
                    local_path = os.path.join(save_path, filename)

                    if self.adb_manager.pull_file(device_serial, remote_path, local_path):
                        pulled_files.append(local_path)

                if not pulled_files:
                    raise Exception(self.prompt_mgr.get('Diagnostic.file_export_fail'))

                # 清理设备上的文件
                progress.update_progress(self.prompt_mgr.get('Diagnostic.cleaning_files'))
                for filename in files:
                    remote_path = f"/sdcard/CbssDiagnostic/{filename}"
                    self.adb_manager.remove_file(device_serial, remote_path)

                # 操作完成
                self.root.after(0, lambda: self._on_diagnostic_done(pulled_files, save_path, progress))

            except Exception as e:
                self.root.after(0, lambda: self._on_diagnostic_error(str(e), progress))

        threading.Thread(target=worker, daemon=True).start()

    def _on_diagnostic_done(self, pulled_files: List[str], save_path: str, progress_dialog):
        """诊断导出完成处理"""
        progress_dialog.close()
        self.is_operation_in_progress = False

        file_list = "\n".join([os.path.basename(f) for f in pulled_files])
        message = self.prompt_mgr.format('Diagnostic.diag_export_done', file_list=file_list, save_path=save_path).replace('\\n', '\n')

        self.status_var.set(self.prompt_mgr.format('Diagnostic.diag_export_status', count=len(pulled_files)))
        messagebox.showinfo(self.prompt_mgr.get('Common.export_done_title'), message)

    def _on_diagnostic_error(self, error_message: str, progress_dialog):
        """诊断导出错误处理"""
        progress_dialog.close()
        self.is_operation_in_progress = False
        self.status_var.set(self.prompt_mgr.format('Diagnostic.diag_export_fail_status', error=error_message))
        messagebox.showerror(self.prompt_mgr.get('Common.export_fail_title'), self.prompt_mgr.format('Diagnostic.diag_export_fail_status', error=error_message))

    def on_closing(self):
        """关闭程序处理"""
        try:
            # 停止网络监控 (NEW in Update 4)
            self.stop_network_monitoring(join_timeout=0.5)

            # 停止自动授权工作线程
            self.auth_manager.stop(join_timeout=5.0)

            # 停止设备监控
            self.device_monitor.stop_monitoring(join_timeout=0.5)

            # 保存配置
            self.config_manager.save_config()

            logging.info("程序正常退出")

        except Exception as e:
            logging.error(f"程序退出时发生错误: {e}")
        finally:
            self.root.destroy()

    def run(self):
        """运行应用程序"""
        try:
            self.root.mainloop()
        except Exception as e:
            logging.error(f"程序运行异常: {e}")
            messagebox.showerror(self.prompt_mgr.get('Common.error_title'), self.prompt_mgr.format('Errors.app_run_exception', msg=str(e)))


if __name__ == "__main__":
    app = AuthenticatorToolGUI()
    app.run()
