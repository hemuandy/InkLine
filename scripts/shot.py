"""截图工具：把界面渲染成 PNG，用于 README 与自检。

用法：
    python scripts/shot.py                      # 空状态
    python scripts/shot.py portrait.jpg         # 打开图片
    python scripts/shot.py portrait.jpg compare # 打开并进入对比模式
    python scripts/shot.py portrait.jpg --out docs/screenshots/main.png
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from inkline.ui.main_window import MainWindow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    args = [a for a in sys.argv[1:]]
    out = os.path.join(ROOT, "_samples", "out", "ui.png")
    if "--out" in args:
        idx = args.index("--out")
        out = args[idx + 1]
        del args[idx:idx + 2]

    mode = "normal"
    for flag in ("compare", "empty"):
        if flag in args:
            mode = flag
            args.remove(flag)
    target = args[0] if args else None

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    win = MainWindow()
    win.resize(1320, 880)
    win.show()

    if mode != "empty" and target:
        win.load(target if os.path.isabs(target) else os.path.join(ROOT, "_samples", target))

    deadline = time.time() + 25
    while time.time() < deadline:
        app.processEvents()
        if win._result is not None or mode == "empty":
            break
        time.sleep(0.02)

    if mode == "compare" and win._result is not None:
        win._set_compare(True)
        win._view._split = 0.5
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)

    app.processEvents()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    win.grab().save(out)
    print("saved", out, "| result:", win._result.method if win._result else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
