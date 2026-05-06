import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import threading

class WifiScanDialog:
    """WiFi扫描和连接对话框"""
    def __init__(self, parent, device_serial: str, adb_manager, callback, config_manager=None, prompt_mgr=None):
        self.device_serial = device_serial
        self.adb_manager = adb_manager
        self.callback = callback
        self.config_manager = config_manager
        self.prompt_mgr = prompt_mgr
        self.networks = []

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self.prompt_mgr.get('scan_wifi_hotspot_title'))
        self.dialog.geometry("750x550")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 顶部按钮区域
        top_frame = ttk.Frame(self.dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(top_frame, text=self.prompt_mgr.get("Buttons.scan_wifi"), command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text=self.prompt_mgr.get("Buttons.refresh"), command=self.refresh_list).pack(side=tk.LEFT, padx=5)

        self.scan_status_label = ttk.Label(top_frame, text=self.prompt_mgr.get("Status.scan_start"), foreground="gray")
        self.scan_status_label.pack(side=tk.LEFT, padx=20)

        # WiFi列表区域
        list_frame = ttk.LabelFrame(self.dialog, text=self.prompt_mgr.get("Text.available_wifi_group"), padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # 创建表格
        columns = (self.prompt_mgr.get("WifiTable.col_wifi_ssid"),
                   self.prompt_mgr.get("WifiTable.col_wifi_signal"),
                   self.prompt_mgr.get("WifiTable.col_wifi_band"),
                   self.prompt_mgr.get("WifiTable.col_wifi_security"),
                   self.prompt_mgr.get("WifiTable.col_wifi_bssid"))
        self.wifi_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        # 设置列标题和宽度
        self.wifi_tree.heading(self.prompt_mgr.get("WifiTable.col_wifi_ssid"), text=self.prompt_mgr.get("WifiTable.col_wifi_ssid"))
        self.wifi_tree.heading(self.prompt_mgr.get("WifiTable.col_wifi_signal"), text=self.prompt_mgr.get("WifiTable.col_wifi_signal"))
        self.wifi_tree.heading(self.prompt_mgr.get("WifiTable.col_wifi_band"), text=self.prompt_mgr.get("WifiTable.col_wifi_band"))
        self.wifi_tree.heading(self.prompt_mgr.get("WifiTable.col_wifi_security"), text=self.prompt_mgr.get("WifiTable.col_wifi_security"))
        self.wifi_tree.heading(self.prompt_mgr.get("WifiTable.col_wifi_bssid"), text=self.prompt_mgr.get("WifiTable.col_wifi_bssid"))

        self.wifi_tree.column(self.prompt_mgr.get("WifiTable.col_wifi_ssid"), width=200, anchor='w')
        self.wifi_tree.column(self.prompt_mgr.get("WifiTable.col_wifi_signal"), width=120, anchor='center')
        self.wifi_tree.column(self.prompt_mgr.get("WifiTable.col_wifi_band"), width=80, anchor='center')
        self.wifi_tree.column(self.prompt_mgr.get("WifiTable.col_wifi_security"), width=80, anchor='center')
        self.wifi_tree.column(self.prompt_mgr.get("WifiTable.col_wifi_bssid"), width=150, anchor='center')

        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.wifi_tree.yview)
        self.wifi_tree.configure(yscrollcommand=scrollbar.set)

        self.wifi_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
          # 双击事件
        self.wifi_tree.bind('<Double-1>', self.on_wifi_selected)

        # 底部按钮（移除密码输入框，改为选择WiFi后弹出）
        bottom_frame = ttk.Frame(self.dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(bottom_frame, text=self.prompt_mgr.get("Buttons.connect"), command=self.connect_wifi).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text=self.prompt_mgr.get("Buttons.close"), command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def start_scan(self):
        """开始WiFi扫描"""
        self.scan_status_label.config(text=self.prompt_mgr.get("Status.scan_running"), foreground="blue")
        self.dialog.update()

        def scan_worker():
            try:
                # 执行扫描
                result = self.adb_manager.wifi_scan(self.device_serial)

                if result.success:
                    # 解析结果
                    self.networks = self.adb_manager.parse_wifi_scan_results(result.raw_output)
                    self.dialog.after(0, self.display_results)
                else:
                    self.dialog.after(0, lambda: self.scan_error(result.error_message))
            except Exception as e:
                self.dialog.after(0, lambda: self.scan_error(str(e)))

        threading.Thread(target=scan_worker, daemon=True).start()

    def display_results(self):
        """显示扫描结果"""
        # 清空现有列表
        for item in self.wifi_tree.get_children():
            self.wifi_tree.delete(item)

        # 添加新结果
        for network in self.networks:
            signal_display = f"{network['signal']}dBm ({network['signal_level']})"
            self.wifi_tree.insert('', 'end', values=(
                network['ssid'],
                signal_display,
                network['band'],
                network['security'],
                network['bssid']
            ))

        count = len(self.networks)
        self.scan_status_label.config(
            text=f"{self.prompt_mgr.get('Status.scan_done').format(count=count)}",
            foreground="green"
        )

    def scan_error(self, error_msg: str):
        """扫描错误处理"""
        self.scan_status_label.config(text=f"{self.prompt_mgr.get('Common.error_title')}", foreground="red")
        messagebox.showerror(self.prompt_mgr.get('Common.error_title'), f"{self.prompt_mgr.get('Status.scan_error').format(error=error_msg)}")

    def refresh_list(self):
        """刷新列表"""
        self.start_scan()

    def on_wifi_selected(self, event):
        """Wi-Fi双击事件"""
        self.connect_wifi()

    def connect_wifi(self):
        """连接选中的WiFi"""
        selection = self.wifi_tree.selection()
        if not selection:
            messagebox.showwarning(self.prompt_mgr.get("Dialogs.select_wifi_title"), self.prompt_mgr.get("Dialogs.select_wifi_msg"))
            return

        # 获取选中的网络
        item = self.wifi_tree.item(selection[0])
        ssid = item['values'][0]
          # 找到对应的网络信息
        network = next((n for n in self.networks if n['ssid'] == ssid), None)
        if not network:
            messagebox.showerror(self.prompt_mgr.get("Dialogs.select_wifi_title"), self.prompt_mgr.get("Dialogs.select_wifi_msg"))
            return

        security = network['security']

        # Open类型WiFi不需要密码，直接连接
        if security == "Open":
            sec_type = 'open'
            password = ''
            # 确认连接
            if messagebox.askyesno(self.prompt_mgr.get("Dialogs.connect_wifi_title"),
                                   self.prompt_mgr.get("Dialogs.connect_open_wifi_msg").format(ssid=ssid)):
                self.dialog.destroy()
                self.callback(self.device_serial, ssid, password, sec_type)
        else:
            # 加密WiFi需要密码，弹出密码输入对话框
            self._show_password_dialog(ssid, security)

    def _show_password_dialog(self, ssid: str, security: str):
        """显示密码输入对话框"""
        pwd_dialog = tk.Toplevel(self.dialog)
        pwd_dialog.title(f"{self.prompt_mgr.get('Dialogs.wifi_password_title').format(ssid=ssid)}")
        pwd_dialog.geometry("400x250")
        pwd_dialog.transient(self.dialog)
        pwd_dialog.grab_set()

        # WiFi信息显示
        info_frame = ttk.Frame(pwd_dialog, padding=20)
        info_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(info_frame, text=f"{self.prompt_mgr.get('Text.wifi_name_label').format(ssid=ssid)}", font=('Arial', 10, 'bold')).pack(pady=5)
        ttk.Label(info_frame, text=f"{self.prompt_mgr.get('Text.wifi_security_label').format(security=security)}", foreground="gray").pack(pady=5)

        # 密码输入
        ttk.Label(info_frame, text=self.prompt_mgr.get("Text.enter_wifi_password"), font=('Arial', 10)).pack(pady=(15, 5))

        pwd_var = tk.StringVar()
        # 加载历史密码
        if self.config_manager:
            history = self.config_manager.get_wifi_history()
            if history.get('ssid') == ssid:
                pwd_var.set(history.get('password', ''))

        pwd_entry = ttk.Entry(info_frame, textvariable=pwd_var, show='*', width=40, font=('Arial', 10))
        pwd_entry.pack(pady=5)
        pwd_entry.focus_set()

        # 按钮
        btn_frame = ttk.Frame(pwd_dialog)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        def on_connect():
            password = pwd_var.get().strip()
            if not password:
                messagebox.showwarning(self.prompt_mgr.get("Dialogs.wifi_password_title"), self.prompt_mgr.get("Text.enter_wifi_password"), parent=pwd_dialog)
                pwd_entry.focus_set()
                return

            # 根据加密方式选择安全类型
            if 'WPA3' in security:
                sec_type = 'wpa3'
            else:
                sec_type = 'wpa2'

            # 保存历史记录
            if self.config_manager:
                self.config_manager.save_wifi_history(ssid, password, sec_type)

            # 关闭两个对话框并执行连接
            pwd_dialog.destroy()
            self.dialog.destroy()
            self.callback(self.device_serial, ssid, password, sec_type)

        def on_cancel():
            pwd_dialog.destroy()

        ttk.Button(btn_frame, text=self.prompt_mgr.get("Buttons.connect"), command=on_connect, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=self.prompt_mgr.get("Buttons.cancel"), command=on_cancel, width=15).pack(side=tk.RIGHT, padx=5)

        # 回车键连接
        pwd_entry.bind('<Return>', lambda e: on_connect())
