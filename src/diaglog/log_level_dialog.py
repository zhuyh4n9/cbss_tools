import tkinter as tk
from tkinter import ttk, messagebox

class LogLevelDialog:
    def __init__(self, parent, log_manager, prompt_mgr=None):
        self.log_manager = log_manager
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._t('Text.log_level_title', '配置日志级别'))
        self.dialog.geometry('300x200')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        ttk.Label(self.dialog, text=self._t('Text.select_log_level', '选择日志级别:')).pack(pady=10)
        self.level_var = tk.StringVar(value='INFO')
        for level in ['DEBUG','INFO','WARNING','ERROR','CRITICAL']:
            ttk.Radiobutton(self.dialog, text=level, variable=self.level_var, value=level).pack()
        bf = ttk.Frame(self.dialog); bf.pack(pady=10)
        ttk.Button(bf, text=self._t('Buttons.ok','确定'), command=self.apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Buttons.cancel','取消'), command=self.dialog.destroy).pack(side=tk.LEFT)
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def apply(self):
        level = self.level_var.get()
        if self.log_manager.update_log_level(level):
            messagebox.showinfo(self._t('Common.success_title','成功'), self._t('Text.log_level_updated', f'日志级别已更新为: {level}').format(level=level))
        else:
            messagebox.showerror(self._t('Common.error_title','错误'), self._t('Text.log_level_update_failed','日志级别更新失败'))
        self.dialog.destroy()
