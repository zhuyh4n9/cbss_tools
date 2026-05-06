import os
import configparser
from typing import Optional
import logging

class PromptManager:
    """Simple i18n/prompt manager backed by ini file.
    Keys use the format Section.key, e.g. "Menus.menu_tools".
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.parser = configparser.ConfigParser()
        self._loaded = False
        self.load()

    def show(self):
        if not self._loaded:
            logging.error("提示文本未加载")
            return
        for section in self.parser.sections():
            logging.info(f"[{section}]")
            for key, value in self.parser.items(section):
                logging.info(key + " " + value)

    def load(self):
        try:
            if os.path.exists(self.config_path):
                self.parser.read(self.config_path, encoding="utf-8")
                self._loaded = True
            else:
                self._loaded = False
        except Exception:
            self._loaded = False

    def get(self, key: str, default: Optional[str] = None, fallback: Optional[str] = None) -> str:
        """Get a string by Section.key.
        default/fallback are synonyms; fallback is prioritized if provided.
        """
        effective_default = fallback if fallback is not None else default
        if not key or "." not in key:
            return effective_default if effective_default is not None else (key or "")
        section, item = key.split(".", 1)
        try:
            if self.parser.has_option(section, item):
                return self.parser.get(section, item)
        except Exception:
            logging.error(f"获取提示文本失败: {key}")
            self.show()
        return effective_default if effective_default is not None else key

    def format(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        raw = self.get(key, default if default is not None else key)
        try:
            return raw.format(**kwargs)
        except Exception:
            return raw
