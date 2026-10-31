"""后台渲染任务：把算法放到线程池，保证拖动滑块时界面不卡。"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.params import Params
from ..core.renderer import RenderResult, render


class _Signals(QObject):
    finished = Signal(int, str, object)   # token, kind, RenderResult
    failed = Signal(int, str, str)        # token, kind, 错误信息


class RenderTask(QRunnable):
    """一次线稿渲染。token 用来丢弃过期的预览结果。"""

    def __init__(self, token: int, kind: str, image: np.ndarray, params: Params,
                 max_side: Optional[int], signals: _Signals,
                 is_valid: Callable[[int, str], bool]) -> None:
        super().__init__()
        self.token = token
        self.kind = kind
        self.image = image
        self.params = params
        self.max_side = max_side
        self.signals = signals
        self._is_valid = is_valid
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D401
        if not self._is_valid(self.token, self.kind):
            return
        try:
            result = render(self.image, self.params, max_side=self.max_side)
        except Exception as exc:  # pragma: no cover - 防御性
            self.signals.failed.emit(self.token, self.kind, str(exc))
            return
        if not self._is_valid(self.token, self.kind):
            return
        self.signals.finished.emit(self.token, self.kind, result)


class RenderQueue(QObject):
    """单线程渲染队列，新预览会自动淘汰旧预览。"""

    preview_ready = Signal(int, object)
    preview_failed = Signal(int, str)
    export_ready = Signal(int, object)
    export_failed = Signal(int, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._preview_token = 0
        self._export_token = 0
        self._export_path: Optional[str] = None
        self._signals = _Signals()
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)

    def _is_valid(self, token: int, kind: str) -> bool:
        return token == (self._export_token if kind == "export" else self._preview_token)

    def request_preview(self, image: np.ndarray, params: Params, max_side: int) -> int:
        self._preview_token += 1
        token = self._preview_token
        task = RenderTask(token, "preview", image, params, max_side,
                          self._signals, self._is_valid)
        self._pool.start(task)
        return token

    def request_export(self, image: np.ndarray, params: Params, path: str) -> int:
        self._export_token += 1
        token = self._export_token
        self._export_path = path
        task = RenderTask(token, "export", image, params, None,
                          self._signals, self._is_valid)
        self._pool.start(task)
        return token

    def cancel_export(self) -> None:
        self._export_token += 1
        self._export_path = None

    def _on_finished(self, token: int, kind: str, result: RenderResult) -> None:
        if kind == "export":
            if token != self._export_token:
                return
            path = self._export_path or ""
            self._export_path = None
            self.export_ready.emit(token, (result, path))
        else:
            if token != self._preview_token:
                return
            self.preview_ready.emit(token, result)

    def _on_failed(self, token: int, kind: str, message: str) -> None:
        if kind == "export":
            if token == self._export_token:
                self._export_path = None
                self.export_failed.emit(token, message)
        elif token == self._preview_token:
            self.preview_failed.emit(token, message)

    def shutdown(self) -> None:
        self._preview_token += 1
        self._export_token += 1
        self._pool.clear()
        self._pool.waitForDone(3000)
