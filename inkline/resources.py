"""打包资源路径解析。"""
from __future__ import annotations

import os
import sys

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative: str) -> str:
    """兼容源码运行与 PyInstaller 单文件模式。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, relative)
    return os.path.join(PACKAGE_ROOT, relative)
