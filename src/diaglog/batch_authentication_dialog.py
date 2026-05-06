import tkinter as tk
from tkinter import ttk

class BatchAuthenticationDialog:
    def __init__(self, parent, device_count, authenticators, callback, prompt_mgr=None):
        self.callback = callback
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._t('Text.batch_activation_title','批量激活'))
        self.dialog.geometry('400x240')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Text.select_authenticator','选择激活盒子:')).pack(pady=10)
        self.auth_var = tk.StringVar()
        self.combo = ttk.Combobox(self.dialog, textvariable=self.auth_var, values=authenticators, state='readonly')
        self.combo.pack(pady=5, fill=tk.X, padx=20)
        self.combo.set(authenticators[0] if authenticators else '')
        ttk.Button(self.dialog, text=self._t('Text.start_activation','开始激活'), command=self._start).pack(pady=15)
        ttk.Label(self.dialog, text=self._t('Text.devices_to_activate', f'待激活设备数量: {device_count}').format(count=device_count)).pack()
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def _start(self):
        serial = self.auth_var.get()
        self.callback(serial)
        self.dialog.destroy()
