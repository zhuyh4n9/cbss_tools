import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


class TestMainGuiStartupImport(unittest.TestCase):
    def test_main_gui_can_be_loaded_via_run_path(self):
        repo_root = Path(__file__).resolve().parents[1]
        main_gui_path = repo_root / "src" / "main_gui.py"

        tkinter_module = types.ModuleType("tkinter")
        tkinter_ttk_module = types.ModuleType("tkinter.ttk")
        tkinter_messagebox_module = types.ModuleType("tkinter.messagebox")
        tkinter_filedialog_module = types.ModuleType("tkinter.filedialog")
        tkinter_simpledialog_module = types.ModuleType("tkinter.simpledialog")

        tkinter_module.ttk = tkinter_ttk_module
        tkinter_module.messagebox = tkinter_messagebox_module
        tkinter_module.filedialog = tkinter_filedialog_module
        tkinter_module.simpledialog = tkinter_simpledialog_module

        fake_modules = {
            "tkinter": tkinter_module,
            "tkinter.ttk": tkinter_ttk_module,
            "tkinter.messagebox": tkinter_messagebox_module,
            "tkinter.filedialog": tkinter_filedialog_module,
            "tkinter.simpledialog": tkinter_simpledialog_module,
        }

        with mock.patch.dict(sys.modules, fake_modules):
            runpy.run_path(str(main_gui_path), run_name="__test__")


if __name__ == "__main__":
    unittest.main()
