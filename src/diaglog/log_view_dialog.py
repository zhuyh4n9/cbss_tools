import tkinter as tk
from tkinter import ttk, messagebox

class LogViewDialog:
    def __init__(self, parent, log_manager, prompt_mgr=None):
        self.log_manager = log_manager
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._t('Text.log_view_title','查看日志'))
        self.dialog.geometry('800x600')
        self.dialog.transient(parent)
        tf = ttk.Frame(self.dialog); tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.text_widget = tk.Text(tf, wrap=tk.WORD)
        sb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=sb.set)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        bf = ttk.Frame(self.dialog); bf.pack(pady=10)
        ttk.Button(bf, text=self._t('Text.log_refresh','刷新'), command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Text.log_clear','清空日志'), command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self._t('Buttons.close','关闭'), command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)
        self.refresh_logs()
    def _t(self, key, default):
        return self.prompt_mgr.get(key) if self.prompt_mgr else default
    def refresh_logs(self):
        content = self.log_manager.get_log_content()
        self.text_widget.delete('1.0', tk.END)
        self.text_widget.insert('1.0', content)
        self.text_widget.see(tk.END)
    def clear_logs(self):
        if messagebox.askyesno(self._t('Common.confirm_title','确认'), self._t('Text.confirm_clear_log','确定要清空日志吗？')):
            if self.log_manager.clear_logs():
                self.refresh_logs()
                messagebox.showinfo(self._t('Common.success_title','成功'), self._t('Text.log_cleared','日志已清空'))
