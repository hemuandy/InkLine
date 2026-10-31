"""主窗口。"""
from __future__ import annotations

import os
from typing import Dict, Optional

import numpy as np
from PySide6.QtCore import QSize, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressDialog, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import APP_NAME, APP_NAME_EN, __version__
from ..core.params import (METHODS, METHOD_HINTS, METHOD_LABELS, PRESETS,
                           PRESET_BY_KEY, Params)
from ..core.renderer import RenderResult
from ..imageio import OPEN_FILTER, SUPPORTED_EXTS, ImageLoadError, human_size
from ..imageio import load_image as read_image
from ..imageio import save_image as write_image
from .theme import COLORS, QSS
from .widgets import Card, ImageView, SliderRow, bgr_to_qimage, gray_to_qimage
from .workers import RenderQueue

#: 每种风格对应的默认参数（点风格按钮时载入）
METHOD_DEFAULTS: Dict[str, Dict[str, int]] = {
    "classic": dict(detail=50, thickness=1, contrast=55, smooth=0, cleanup=0),
    "line": dict(detail=55, thickness=2, contrast=55, smooth=35, cleanup=30),
    "manga": dict(detail=52, thickness=3, contrast=60, smooth=48, cleanup=45),
    "minimal": dict(detail=40, thickness=3, contrast=50, smooth=55, cleanup=55),
    "pencil": dict(detail=55, thickness=1, contrast=52, smooth=30, cleanup=10),
    "wash": dict(detail=45, thickness=2, contrast=46, smooth=62, cleanup=35),
}

PROJECT_URL = "https://github.com/hemuandy/InkLine"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_NAME_EN} · 图片转线稿")
        self.resize(1320, 880)
        self.setMinimumSize(1000, 700)

        self._settings = QSettings("InkLine", "InkLine")
        self._image: Optional[np.ndarray] = None
        self._image_path: Optional[str] = None
        self._result: Optional[RenderResult] = None
        self._resolved: Optional[Params] = None
        self._params = Params()
        self._suspend = False
        self._last_dir = str(self._settings.value("last_dir", os.path.expanduser("~")))
        self._progress: Optional[QProgressDialog] = None

        self._queue = RenderQueue(self)
        self._queue.preview_ready.connect(self._on_preview_ready)
        self._queue.preview_failed.connect(self._on_preview_failed)
        self._queue.export_ready.connect(self._on_export_ready)
        self._queue.export_failed.connect(self._on_export_failed)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render_preview)

        self.setAcceptDrops(True)
        self._build_ui()
        self._build_menu()
        self._apply_theme()
        self._sync_method_buttons()
        self._update_controls()
        self._restore_geometry()

    # ------------------------------------------------------------------
    # 构建界面
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(14, 14, 14, 10)
        body.setSpacing(14)
        body.addWidget(self._build_sidebar())

        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(self._build_canvas_toolbar())
        self._view = ImageView()
        self._view.zoomChanged.connect(self._on_zoom_changed)
        self._view.compareChanged.connect(self._on_compare_changed)
        canvas_layout.addWidget(self._view, 1)
        body.addWidget(canvas, 1)
        layout.addLayout(body, 1)

        self._status = self.statusBar()
        self._status.setSizeGripEnabled(False)
        self._status_label = QLabel("准备就绪 · 把图片拖进窗口即可开始")
        self._status.addWidget(self._status_label, 1)
        self._stat_label = QLabel("")
        self._stat_label.setObjectName("muted")
        self._status.addPermanentWidget(self._stat_label)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(66)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 10, 18, 10)
        row.setSpacing(12)

        mark = QLabel("墨")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            f"background: {COLORS['accent_soft']}; color: #FF7F72;"
            f"border: 1px solid {COLORS['accent']}; border-radius: 10px;"
            "font-size: 21px; font-weight: 700;"
        )
        row.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("appName")
        sub = QLabel("INKLINE · 图片转线稿")
        sub.setObjectName("appSub")
        titles.addWidget(name)
        titles.addWidget(sub)
        row.addLayout(titles)
        row.addStretch(1)

        self._open_btn = QPushButton("打开图片")
        self._open_btn.setToolTip("打开一张照片（Ctrl+O）")
        self._open_btn.clicked.connect(self.open_image)
        row.addWidget(self._open_btn)

        self._save_btn = QPushButton("保存线稿")
        self._save_btn.setObjectName("primary")
        self._save_btn.setToolTip("按原始分辨率导出（Ctrl+S）")
        self._save_btn.clicked.connect(self.save_image)
        row.addWidget(self._save_btn)
        return header

    def _build_sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(324)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(12)

        column.addWidget(self._build_file_card())
        column.addWidget(self._build_method_card())
        column.addWidget(self._build_preset_card())
        column.addWidget(self._build_param_card())
        column.addStretch(1)

        scroll.setWidget(inner)
        return scroll

    def _build_file_card(self) -> Card:
        card = Card("图片")
        self._file_label = QLabel("尚未打开图片")
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet("font-weight: 600;")
        self._size_label = QLabel("—")
        self._size_label.setObjectName("muted")
        self._scene_label = QLabel("等待分析…")
        self._scene_label.setObjectName("muted")
        self._scene_label.setWordWrap(True)
        card.body.addWidget(self._file_label)
        card.body.addWidget(self._size_label)
        card.body.addWidget(self._scene_label)
        return card

    def _build_method_card(self) -> Card:
        card = Card("风格")
        grid = QGridLayout()
        grid.setSpacing(6)
        self._method_group: Dict[str, QPushButton] = {}
        for index, (key, name, _hint) in enumerate(METHODS):
            button = QPushButton(name)
            button.setObjectName("method")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(_hint)
            button.setMinimumHeight(38)
            button.clicked.connect(lambda _checked=False, k=key: self.set_method(k))
            grid.addWidget(button, index // 4, index % 4)
            self._method_group[key] = button
        card.body.addLayout(grid)

        self._method_hint = QLabel(METHOD_HINTS["smart"])
        self._method_hint.setObjectName("hint")
        self._method_hint.setWordWrap(True)
        card.body.addWidget(self._method_hint)
        return card

    def _build_preset_card(self) -> Card:
        card = Card("预设")
        grid = QGridLayout()
        grid.setSpacing(6)
        self._preset_buttons: Dict[str, QPushButton] = {}
        for index, preset in enumerate(PRESETS):
            button = QPushButton(preset.name)
            button.setObjectName("chip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(preset.note)
            button.clicked.connect(lambda _checked=False, k=preset.key: self.apply_preset(k))
            grid.addWidget(button, index // 3, index % 3)
            self._preset_buttons[preset.key] = button
        card.body.addLayout(grid)
        return card

    def _build_param_card(self) -> Card:
        card = Card("参数")
        self._sliders: Dict[str, SliderRow] = {}
        specs = [
            ("detail", "细节密度", 0, 100, "保留多少细碎线条：数值越大越丰富"),
            ("thickness", "线条粗细", 1, 12, "数值越大线条越粗"),
            ("contrast", "线条浓淡", 0, 100, "数值越大墨色越重"),
            ("smooth", "降噪平滑", 0, 100, "数值越大画面越干净，同时会牺牲细节"),
            ("cleanup", "杂点清理", 0, 100, "去掉细小的孤立笔触"),
        ]
        for key, title, lo, hi, tip in specs:
            row = SliderRow(title, lo, hi, getattr(self._params, key), tooltip=tip)
            row.valueChanged.connect(lambda value, k=key: self._on_slider(k, value))
            card.body.addWidget(row)
            self._sliders[key] = row

        self._invert_check = QCheckBox("反相（白线黑底）")
        self._invert_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._invert_check.toggled.connect(self._on_invert)
        card.body.addWidget(self._invert_check)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        self._smart_hint = QLabel("智能模式：参数由画面自动决定")
        self._smart_hint.setObjectName("hint")
        self._smart_hint.setWordWrap(True)
        footer.addWidget(self._smart_hint, 1)

        reset = QPushButton("重置")
        reset.setObjectName("chip")
        reset.setFixedWidth(60)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.setToolTip("恢复智能模式的默认参数")
        reset.clicked.connect(self.reset_params)
        footer.addWidget(reset)
        card.body.addLayout(footer)
        return card

    def _build_canvas_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(38)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 6)
        row.setSpacing(4)

        fit_btn = QPushButton("适应窗口")
        fit_btn.setObjectName("iconButton")
        fit_btn.clicked.connect(lambda: self._view.fit_to_window())
        row.addWidget(fit_btn)

        actual_btn = QPushButton("100%")
        actual_btn.setObjectName("iconButton")
        actual_btn.clicked.connect(lambda: self._view.actual_size())
        row.addWidget(actual_btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setObjectName("muted")
        self._zoom_label.setMinimumWidth(46)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._zoom_label)
        row.addStretch(1)

        self._compare_btn = QPushButton("对比")
        self._compare_btn.setObjectName("iconButton")
        self._compare_btn.setCheckable(True)
        self._compare_btn.setToolTip("左右拖动分割线，对比原图与线稿（C）")
        self._compare_btn.toggled.connect(self._set_compare)
        row.addWidget(self._compare_btn)
        return bar

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("文件")
        act_open = QAction("打开图片…", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_image)
        file_menu.addAction(act_open)

        self._act_save = QAction("保存线稿…", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self.save_image)
        file_menu.addAction(self._act_save)
        file_menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = bar.addMenu("视图")
        act_fit = QAction("适应窗口", self)
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.triggered.connect(lambda: self._view.fit_to_window())
        view_menu.addAction(act_fit)

        act_actual = QAction("实际大小", self)
        act_actual.setShortcut(QKeySequence("Ctrl+1"))
        act_actual.triggered.connect(lambda: self._view.actual_size())
        view_menu.addAction(act_actual)

        act_compare = QAction("对比模式", self)
        act_compare.setShortcut(QKeySequence("C"))
        act_compare.setCheckable(True)
        act_compare.toggled.connect(self._set_compare)
        view_menu.addAction(act_compare)
        self._act_compare = act_compare

        act_invert = QAction("反相", self)
        act_invert.setShortcut(QKeySequence("I"))
        act_invert.setCheckable(True)
        act_invert.toggled.connect(self._invert_check.setChecked)
        view_menu.addAction(act_invert)
        self._act_invert = act_invert

        help_menu = bar.addMenu("帮助")
        act_about = QAction("关于墨线", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)
        act_github = QAction("项目主页", self)
        act_github.triggered.connect(self._open_project_page)
        help_menu.addAction(act_github)

    def _apply_theme(self) -> None:
        self.setStyleSheet(QSS)
        font = QFont("Microsoft YaHei UI", 9)
        self.setFont(font)

    # ------------------------------------------------------------------
    # 图片与渲染
    # ------------------------------------------------------------------
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", self._last_dir, OPEN_FILTER)
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        if not path.lower().endswith(SUPPORTED_EXTS):
            QMessageBox.warning(self, "无法打开", "暂不支持这种图片格式。")
            return
        try:
            image = read_image(path)
        except ImageLoadError as exc:
            QMessageBox.critical(self, "打开失败", f"{os.path.basename(path)}\n\n{exc}")
            return

        self._image = image
        self._image_path = path
        self._last_dir = os.path.dirname(path) or self._last_dir
        self._settings.setValue("last_dir", self._last_dir)
        self._result = None
        self._resolved = None

        h, w = image.shape[:2]
        self._file_label.setText(self._elide(os.path.basename(path), 250))
        self._file_label.setToolTip(path)
        self._size_label.setText(f"{human_size(w, h)}  ·  {self._file_mb(path)}")
        self._scene_label.setText("正在分析画面…")
        self._view.set_original(bgr_to_qimage(image))
        self._view.set_result(None)
        self._save_btn.setEnabled(False)
        self._act_save.setEnabled(False)
        self.setWindowTitle(f"{os.path.basename(path)} — {APP_NAME} {APP_NAME_EN}")
        self._status_label.setText("已打开图片，正在生成线稿…")
        self._update_controls()
        self._schedule_preview(delay=30)

    def _file_mb(self, path: str) -> str:
        try:
            size = os.path.getsize(path) / 1024.0 / 1024.0
        except OSError:
            return ""
        return f"{size:.1f} MB" if size >= 1 else f"{size * 1024:.0f} KB"

    def _preview_side(self) -> int:
        screen = self._view.width()
        return int(max(1100, min(1800, screen * 1.6)))

    def _schedule_preview(self, delay: int = 200) -> None:
        if self._image is None:
            return
        self._timer.start(delay)

    def _render_preview(self) -> None:
        if self._image is None:
            return
        self._view.set_busy(True)
        self._queue.request_preview(self._image, self._params, self._preview_side())

    def _on_preview_ready(self, _token: int, result: RenderResult) -> None:
        self._view.set_busy(False)
        self._result = result
        self._resolved = result.params
        self._view.set_result(gray_to_qimage(result.image))
        self._save_btn.setEnabled(True)
        self._act_save.setEnabled(True)

        if result.scene is not None:
            self._scene_label.setText("识别：" + result.scene.describe())
        elif result.method_label:
            self._scene_label.setText(f"风格：{result.method_label}")

        if self._params.method == "smart" and result.params is not None:
            self._write_sliders(result.params)

        ms = result.elapsed * 1000
        h, w = result.image.shape[:2]
        self._stat_label.setText(f"{result.method_label} · {w}×{h} · {ms:.0f} ms")
        self._status_label.setText(self._status_text(result))

    def _status_text(self, result: RenderResult) -> str:
        if result.scene is not None:
            return f"已生成 · 智能识别为{result.scene.label}，自动匹配「{result.method_label}」参数"
        return f"已生成 · {result.method_label}风格"

    def _on_preview_failed(self, _token: int, message: str) -> None:
        self._view.set_busy(False)
        self._status_label.setText("生成失败：" + message)

    # ------------------------------------------------------------------
    # 参数交互
    # ------------------------------------------------------------------
    def _write_sliders(self, params: Params) -> None:
        self._suspend = True
        for key, row in self._sliders.items():
            row.set_value(getattr(params, key))
        self._suspend = False

    def _on_slider(self, key: str, value: int) -> None:
        if self._suspend:
            return
        if self._params.method == "smart":
            # 智能模式下拖动参数 → 沿用上次解析出的具体算法
            resolved = self._resolved.method if self._resolved else "line"
            if resolved == "smart":
                resolved = "line"
            self._params = self._params.with_values(method=resolved)
            self._sync_method_buttons()
            self._sync_preset_buttons(None)
        self._params = self._params.with_values(**{key: int(value)})
        self._sync_preset_buttons(None)
        self._update_controls()
        self._schedule_preview()

    def _on_invert(self, checked: bool) -> None:
        self._params = self._params.with_values(invert=bool(checked))
        if self._act_invert.isChecked() != checked:
            self._act_invert.blockSignals(True)
            self._act_invert.setChecked(bool(checked))
            self._act_invert.blockSignals(False)
        self._schedule_preview()

    def set_method(self, method: str) -> None:
        if method not in METHOD_LABELS:
            return
        self._params = self._params.with_values(method=method)
        defaults = METHOD_DEFAULTS.get(method)
        if defaults:
            self._params = self._params.with_values(**defaults)
        self._sync_method_buttons()
        self._sync_preset_buttons(None)
        self._update_controls()
        self._method_hint.setText(METHOD_HINTS.get(method, ""))
        self._write_sliders(self._params)
        self._schedule_preview(delay=60)

    def apply_preset(self, key: str) -> None:
        preset = PRESET_BY_KEY.get(key)
        if preset is None:
            return
        self._params = preset.params
        self._write_sliders(self._params)
        self._sync_method_buttons()
        self._sync_preset_buttons(key)
        self._update_controls()
        self._method_hint.setText(METHOD_HINTS.get(preset.params.method, ""))
        self._schedule_preview(delay=60)

    def reset_params(self) -> None:
        self._params = Params()
        self._write_sliders(self._params)
        self._invert_check.setChecked(False)
        self._sync_method_buttons()
        self._sync_preset_buttons("auto")
        self._update_controls()
        self._method_hint.setText(METHOD_HINTS["smart"])
        self._schedule_preview(delay=60)

    def _sync_method_buttons(self) -> None:
        current = self._params.method
        for key, button in self._method_group.items():
            button.blockSignals(True)
            button.setChecked(key == current)
            button.blockSignals(False)
        if current != "smart":
            self._method_hint.setText(METHOD_HINTS.get(current, ""))

    def _sync_preset_buttons(self, active: Optional[str]) -> None:
        for key, button in self._preset_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == active)
            button.blockSignals(False)

    def _update_controls(self) -> None:
        smart = self._params.method == "smart"
        for row in self._sliders.values():
            row.set_enabled(not smart)
        if smart:
            self._smart_hint.setText("智能模式：参数由画面自动决定")
        else:
            self._smart_hint.setText(f"手动模式：{METHOD_LABELS.get(self._params.method, '')}风格")
        self._smart_hint.setVisible(True)
        has_image = self._image is not None
        self._open_btn.setEnabled(True)
        self._save_btn.setEnabled(has_image and self._result is not None)
        self._compare_btn.setEnabled(self._result is not None)
        if not has_image:
            self._compare_btn.setChecked(False)

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def _on_zoom_changed(self, scale: float) -> None:
        self._zoom_label.setText(f"{scale * 100:.0f}%")

    def _set_compare(self, enabled: bool) -> None:
        if enabled and self._result is None:
            enabled = False
        self._view.set_compare(enabled)
        if self._compare_btn.isChecked() != enabled:
            self._compare_btn.blockSignals(True)
            self._compare_btn.setChecked(enabled)
            self._compare_btn.blockSignals(False)
        if self._act_compare.isChecked() != enabled:
            self._act_compare.blockSignals(True)
            self._act_compare.setChecked(enabled)
            self._act_compare.blockSignals(False)

    def _on_compare_changed(self, enabled: bool) -> None:
        if self._compare_btn.isChecked() != enabled:
            self._compare_btn.blockSignals(True)
            self._compare_btn.setChecked(enabled)
            self._compare_btn.blockSignals(False)
        if self._act_compare.isChecked() != enabled:
            self._act_compare.blockSignals(True)
            self._act_compare.setChecked(enabled)
            self._act_compare.blockSignals(False)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def save_image(self) -> None:
        if self._image is None or self._result is None:
            QMessageBox.information(self, "还没有线稿", "请先打开一张图片并等待生成。")
            return
        base = os.path.splitext(os.path.basename(self._image_path or "线稿"))[0]
        suggested = os.path.join(self._last_dir, f"{base}_线稿.png")
        path, selected = QFileDialog.getSaveFileName(
            self, "保存线稿", suggested,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*.*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".jpg" if "JPEG" in selected else ".png"
        if os.path.abspath(path) == os.path.abspath(self._image_path or ""):
            QMessageBox.warning(self, "无法保存", "不能覆盖正在编辑的原图，请换一个文件名。")
            return

        params = self._resolved if (self._params.method == "smart" and self._resolved) else self._params
        self._progress = QProgressDialog("正在按原始分辨率生成线稿…", None, 0, 0, self)
        self._progress.setWindowTitle("导出")
        self._progress.setCancelButton(None)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(150)
        self._progress.setMinimumWidth(320)
        self._progress.show()
        self._status_label.setText("正在生成高清线稿…")
        self._queue.request_export(self._image, params, path)

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_export_ready(self, _token: int, payload) -> None:
        self._close_progress()
        result, path = payload
        try:
            write_image(path, result.image)
        except Exception as exc:  # pragma: no cover - 磁盘错误
            QMessageBox.critical(self, "保存失败", f"{path}\n\n{exc}")
            self._status_label.setText("保存失败")
            return
        h, w = result.image.shape[:2]
        self._status_label.setText(f"已保存 · {path}")
        self._last_dir = os.path.dirname(path) or self._last_dir
        self._settings.setValue("last_dir", self._last_dir)
        QMessageBox.information(
            self, "保存成功",
            f"线稿已保存到：\n{path}\n\n尺寸：{w} × {h} 像素")

    def _on_export_failed(self, _token: int, message: str) -> None:
        self._close_progress()
        QMessageBox.critical(self, "保存失败", message)
        self._status_label.setText("保存失败：" + message)

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def show_about(self) -> None:
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h3>{APP_NAME} · {APP_NAME_EN} <span style='color:#8B93A3'>v{__version__}</span></h3>"
            "<p>把照片变成手绘线稿的桌面工具。</p>"
            "<p>· 智能识别画面类型，自动匹配算法与参数<br>"
            "· 多尺度勾线 + 自动密度控制，线条干净连贯<br>"
            "· 导出时按原始分辨率重新渲染，不是简单放大</p>"
            f"<p style='color:#8B93A3'>项目主页：{PROJECT_URL}</p>")

    def _open_project_page(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(PROJECT_URL))

    def _elide(self, text: str, width: int) -> str:
        metrics = QFontMetrics(self._file_label.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, width)

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    # ------------------------------------------------------------------
    # 拖放
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._urls_from_event(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._urls_from_event(event)
        if paths:
            self.load(paths[0])
            event.acceptProposedAction()

    def _urls_from_event(self, event) -> list:
        if not event.mimeData().hasUrls():
            return []
        result = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(SUPPORTED_EXTS):
                result.append(path)
        return result

    def closeEvent(self, event) -> None:  # noqa: N802
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("last_dir", self._last_dir)
        self._queue.shutdown()
        super().closeEvent(event)
