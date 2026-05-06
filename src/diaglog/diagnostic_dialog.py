import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class DiagnosticDialog:
    def __init__(self, parent, devices, diagnostic_type, title, callback, prompt_mgr=None):
        self.devices = devices
        self.diagnostic_type = diagnostic_type
        self.callback = callback
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry('480x260')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Text.select_device_generic','选择设备:')).pack(pady=8)
        self.device_var = tk.StringVar()
        self.combo = ttk.Combobox(self.dialog, textvariable=self.device_var, values=devices, state='readonly')
        self.combo.pack(fill=tk.X, padx=20)
        if devices:
            self.combo.set(devices[0])
        path_frame = ttk.Frame(self.dialog); path_frame.pack(fill=tk.X, padx=20, pady=12)
        ttk.Label(path_frame, text=self._t('Text.choose_file','选择文件')).grid(row=0, column=0, sticky='e')
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=1, sticky='we', padx=5)
        ttk.Button(path_frame, text=self._t('Buttons.choose_file','选择文件'), command=self._choose_dir).grid(row=0, column=2)
        path_frame.columnconfigure(1, weight=1)
        bf = ttk.Frame(self.dialog); bf.pack(pady=10)
        ttk.Button(bf, text=self._t('Buttons.ok','确定'), command=self._export).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Buttons.cancel','取消'), command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def _choose_dir(self):
        directory = filedialog.askdirectory(title=self._t('Diagnostic.export_title_fmt','导出{dtype}诊断日志').format(dtype=self.diagnostic_type))
        if directory:
            self.path_var.set(directory)
    def _export(self):
        serial = self.device_var.get()
        save_path = self.path_var.get().strip()
        if not serial:
            messagebox.showerror(self._t('Common.error_title','错误'), self._t('Validation.select_device_first','请选择设备'))
            return
        if not save_path:
            messagebox.showerror(self._t('Common.error_title','错误'), self._t('Validation.select_save_path_first','请选择保存路径'))
            return
        self.callback(serial, self.diagnostic_type, save_path)
        self.dialog.destroy()
