import tkinter as tk
from tkinter import ttk

class AuthenticationDialog:
    def __init__(self, parent, device_serial, authenticators, callback, prompt_mgr=None):
        self.callback = callback
        self.device_serial = device_serial
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._t('Text.single_activation_title','设备激活'))
        self.dialog.geometry('380x240')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Text.select_authenticator','选择激活盒子:')).pack(pady=10)
        self.auth_var = tk.StringVar()
        self.combo = ttk.Combobox(self.dialog, textvariable=self.auth_var, values=authenticators, state='readonly')
        self.combo.pack(pady=5, fill=tk.X, padx=20)
        self.combo.set(authenticators[0] if authenticators else '')
        ttk.Button(self.dialog, text=self._t('Text.start_activation','开始激活'), command=self._start).pack(pady=15)
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def _start(self):
        serial = self.auth_var.get()
        self.callback(self.device_serial, serial)
        self.dialog.destroy()
