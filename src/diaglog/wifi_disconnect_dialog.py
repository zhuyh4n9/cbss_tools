import tkinter as tk
from tkinter import ttk

class WifiDisconnectDialog:
    def __init__(self, parent, authenticators, callback, prompt_mgr=None):
        self.callback = callback
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._t('Dialogs.wifi_disconnect_title','设备WiFi断开'))
        self.dialog.geometry('360x180')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Dialogs.select_device','选择设备:')).pack(pady=10)
        self.device_var = tk.StringVar()
        self.combo = ttk.Combobox(self.dialog, textvariable=self.device_var, values=authenticators, state='readonly')
        self.combo.pack(fill=tk.X, padx=20)
        if authenticators:
            self.combo.set(authenticators[0])
        bf = ttk.Frame(self.dialog); bf.pack(pady=15)
        ttk.Button(bf, text=self._t('Buttons.disconnect','断开'), command=self._do).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Buttons.cancel','取消'), command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def _do(self):
        device_serial = self.device_var.get()
        self.callback(device_serial)
        self.dialog.destroy()
