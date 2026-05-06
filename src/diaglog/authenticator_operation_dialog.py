import tkinter as tk
from tkinter import ttk

class AuthenticatorOperationDialog:
    def __init__(self, parent, title, operation, authenticators, callback, prompt_mgr=None):
        self.callback = callback
        self.operation = operation
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry('400x220')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Text.select_authenticator','选择激活盒子:')).pack(pady=10)
        self.device_var = tk.StringVar()
        self.combo = ttk.Combobox(self.dialog, textvariable=self.device_var, values=authenticators, state='readonly')
        self.combo.pack(pady=5, fill=tk.X, padx=20)
        self.combo.set(authenticators[0] if authenticators else '')
        ttk.Label(self.dialog, text=self._t('Text.input_token_hint','输入128个hex字符(激活盒子剩余可激活设备数将被重置):')).pack(pady=10)
        self.token_text = tk.Text(self.dialog, height=4)
        self.token_text.pack(fill=tk.BOTH, expand=True, padx=20)
        bf = ttk.Frame(self.dialog); bf.pack(pady=10)
        ttk.Button(bf, text=self._t('Buttons.ok','确定'), command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Buttons.cancel','取消'), command=self.dialog.destroy).pack(side=tk.LEFT)
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def _ok(self):
        serial = self.device_var.get()
        token = self.token_text.get('1.0', tk.END).strip()
        self.callback(self.operation, serial, token)
        self.dialog.destroy()
