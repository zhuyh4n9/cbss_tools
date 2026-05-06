import tkinter as tk
from tkinter import ttk

class ProgressDialog:
    def __init__(self, parent, title, initial_message, prompt_mgr=None):
        self.prompt_mgr = prompt_mgr
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry('400x180')
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.message_var = tk.StringVar(value=initial_message)
        ttk.Label(self.dialog, textvariable=self.message_var, wraplength=360).pack(padx=15, pady=25)
        self.progress = ttk.Progressbar(self.dialog, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=20, pady=10)
        self.progress.start(10)
    def update_progress(self, msg: str):
        self.message_var.set(msg)
    def close(self):
        try:
            self.progress.stop()
        except Exception:
            pass
        self.dialog.destroy()
