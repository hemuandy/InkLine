"""应用入口。"""
from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME, APP_NAME_EN, __version__
from .resources import resource_path
from .ui.main_window import MainWindow
from .ui.theme import COLORS


def _set_windows_app_id() -> None:
    """让任务栏使用自己的图标而不是 Python 的。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("InkLine.LineArt.1")
    except Exception:
        pass


def _selftest(out_path: str) -> int:
    """无界面自检：跑一遍完整算法链，把结果写盘。用于验证打包产物。"""
    import numpy as np

    from .core.analyzer import analyze, auto_params
    from .core.renderer import render
    from .imageio import save_image

    h, w = 640, 960
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.zeros((h, w, 3), np.uint8)
    base[:] = (40, 60, 90)
    for cx, cy, r, color in ((240, 300, 120, (230, 230, 240)),
                             (560, 260, 90, (250, 210, 200)),
                             (760, 460, 110, (180, 240, 210))):
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
        base[mask] = color
    base = np.clip(base.astype(np.float32) + np.random.default_rng(0).normal(0, 6, base.shape),
                   0, 255).astype(np.uint8)

    params = auto_params(analyze(base))
    result = render(base, params, max_side=None)
    save_image(out_path, result.image)
    with open(out_path + ".txt", "w", encoding="utf-8") as fh:
        fh.write(f"{__version__} {params.method} {result.image.shape}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        idx = argv.index("--selftest")
        out = argv[idx + 1] if len(argv) > idx + 1 else "selftest.png"
        return _selftest(out)
    _set_windows_app_id()

    app = QApplication(argv)
    app.setApplicationName(APP_NAME_EN)
    app.setApplicationDisplayName(f"{APP_NAME} {APP_NAME_EN}")
    app.setOrganizationName(APP_NAME_EN)
    app.setApplicationVersion(__version__)

    icon_path = resource_path(os.path.join("inkline", "assets", "icon.ico"))
    icon = QIcon(icon_path)
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    # 支持「用墨线打开图片」和命令行参数
    for arg in argv[1:]:
        if os.path.isfile(arg):
            window.load(arg)
            break

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
