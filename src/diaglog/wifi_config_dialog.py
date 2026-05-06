import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional

class WifiConfigDialog:
    """WiFi配置对话框：选择设备、输入SSID/密码、选择加密方式"""
    def __init__(self, parent, devices: List[str], callback, config_manager=None, prompt_mgr=None):
        self.callback = callback
        self.config_manager = config_manager
        self.prompt_mgr = prompt_mgr

        self.dialog = tk.Toplevel(parent)
        title_text = self.prompt_mgr.get('Dialogs.wifi_config_title')
        self.dialog.title(title_text)
        self.dialog.geometry("420x360")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 设备选择
        dev_label = self.prompt_mgr.get('Dialogs.wifi_config_select_device')
        ttk.Label(self.dialog, text=dev_label).pack(pady=(10, 5))
        self.dev_var = tk.StringVar()
        dev_combo = ttk.Combobox(self.dialog, textvariable=self.dev_var, values=devices, state="readonly")
        dev_combo.pack(pady=5, padx=10, fill=tk.X)
        if devices:
            dev_combo.set(devices[0])

        # 加载历史记录
        wifi_history = {'ssid': '', 'password': '', 'security': 'wpa2'}
        if self.config_manager:
            wifi_history = self.config_manager.get_wifi_history()

        # SSID
        ssid_label = self.prompt_mgr.get('Dialogs.wifi_config_label_ssid')
        ttk.Label(self.dialog, text=ssid_label).pack(pady=(10, 5))
        self.ssid_var = tk.StringVar(value=wifi_history['ssid'])
        ttk.Entry(self.dialog, textvariable=self.ssid_var).pack(padx=10, fill=tk.X)

        # Security (moved before password to control visibility)
        sec_label = self.prompt_mgr.get('Dialogs.wifi_config_label_security')
        ttk.Label(self.dialog, text=sec_label).pack(pady=(10, 5))
        self.sec_var = tk.StringVar(value=wifi_history['security'])
        sec_combo = ttk.Combobox(self.dialog, textvariable=self.sec_var, values=['wpa2', 'wpa3', 'open'], state="readonly")
        sec_combo.pack(padx=10, fill=tk.X)
        sec_combo.bind('<<ComboboxSelected>>', self._on_security_changed)

        # Password (with frame for easy show/hide)
        self.password_frame = ttk.Frame(self.dialog)
        self.password_frame.pack(fill=tk.X)

        pwd_label_text = self.prompt_mgr.get('Dialogs.wifi_config_label_password')
        self.password_label = ttk.Label(self.password_frame, text=pwd_label_text)
        self.password_label.pack(pady=(10, 5))
        self.pwd_var = tk.StringVar(value=wifi_history['password'])
        self.password_entry = ttk.Entry(self.password_frame, textvariable=self.pwd_var, show='*')
        self.password_entry.pack(padx=10, fill=tk.X)

        # Buttons frame
        btns = ttk.Frame(self.dialog)
        btns.pack(pady=15)
        connect_text = self.prompt_mgr.get('Buttons.connect')
        cancel_text = self.prompt_mgr.get('Buttons.cancel')
        ttk.Button(btns, text=connect_text, command=self.apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text=cancel_text, command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        # Initialize password field visibility
        self._on_security_changed(None)

    def _on_security_changed(self, event):
        """根据加密方式显示或隐藏密码输入框"""
        security = self.sec_var.get().strip().lower()
        if security == 'open':
            # 隐藏密码输入框
            self.password_label.pack_forget()
            self.password_entry.pack_forget()
        else:
            # 显示密码输入框
            self.password_label.pack(pady=(10, 5))
            self.password_entry.pack(padx=10, fill=tk.X)

    def apply(self):
        dev = self.dev_var.get()
        ssid = self.ssid_var.get().strip()
        pwd = self.pwd_var.get()
        sec = self.sec_var.get().strip().lower() or 'wpa2'

        error_title = self.prompt_mgr.get('Dialogs.wifi_password_title')

        if not dev:
            messagebox.showerror(error_title, self.prompt_mgr.get('Errors.no_device'))
            return
        if not ssid:
            messagebox.showerror(error_title, self.prompt_mgr.get('Errors.no_ssid'))
            return

        # Open WiFi不需要密码
        if sec != 'open':
            if not pwd:
                messagebox.showerror(error_title, self.prompt_mgr.get('Errors.invalid_password'))
                return
            if sec not in ('wpa2', 'wpa3'):
                messagebox.showerror(error_title, self.prompt_mgr.format('Errors.invalid_wifi_security', security=sec))
                return
        else:
            pwd = ''

        if self.config_manager:
            self.config_manager.save_wifi_history(ssid, pwd, sec)

        self.dialog.destroy()
        self.callback(dev, ssid, pwd, sec)