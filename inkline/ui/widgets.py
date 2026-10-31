"""自绘控件：卡片、参数滑块、图像预览画布。"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget)

from .theme import COLORS

MIN_SCALE = 0.05
MAX_SCALE = 8.0


# --------------------------------------------------------------------------
# 图像格式转换
# --------------------------------------------------------------------------

def bgr_to_qimage(image: np.ndarray) -> QImage:
    """BGR/BGRA 数组 → QImage（持有独立内存）。"""
    if image.ndim == 2:
        gray = np.ascontiguousarray(image)
        h, w = gray.shape
        return QImage(gray.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if image.shape[2] == 4:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        h, w = rgba.shape[:2]
        return QImage(np.ascontiguousarray(rgba).data, w, h, w * 4,
                      QImage.Format.Format_RGBA8888).copy()
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(np.ascontiguousarray(rgb).data, w, h, w * 3,
                  QImage.Format.Format_RGB888).copy()


def gray_to_qimage(image: np.ndarray) -> QImage:
    gray = np.ascontiguousarray(image)
    h, w = gray.shape[:2]
    return QImage(gray.data, w, h, w, QImage.Format.Format_Grayscale8).copy()


# --------------------------------------------------------------------------
# 基础组件
# --------------------------------------------------------------------------

class Card(QFrame):
    """带小标题的分组卡片。"""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 14, 12)
        outer.setSpacing(8)
        if title:
            label = QLabel(title.upper())
            label.setObjectName("cardTitle")
            outer.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body)


class SliderRow(QWidget):
    """标题 + 数值 + 滑块的组合。"""

    valueChanged = Signal(int)

    def __init__(self, title: str, minimum: int, maximum: int, value: int,
                 suffix: str = "", tooltip: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._suffix = suffix
        self._blocked = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self._title = QLabel(title)
        self._title.setObjectName("muted")
        self._value = QLabel()
        self._value.setObjectName("value")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self._title)
        head.addStretch(1)
        head.addWidget(self._value)
        layout.addLayout(head)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.slider.valueChanged.connect(self._on_change)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.slider)

        if tooltip:
            self.setToolTip(tooltip)
            self.slider.setToolTip(tooltip)
        self._update_label(value)

    def _update_label(self, value: int) -> None:
        self._value.setText(f"{value}{self._suffix}")

    def _on_change(self, value: int) -> None:
        self._update_label(value)
        if not self._blocked:
            self.valueChanged.emit(int(value))

    def value(self) -> int:
        return int(self.slider.value())

    def set_value(self, value: int, emit: bool = False) -> None:
        self._blocked = not emit
        self.slider.setValue(int(value))
        self._update_label(int(value))
        self._blocked = False

    def set_enabled(self, enabled: bool) -> None:
        self.slider.setEnabled(enabled)
        self._title.setEnabled(enabled)
        self._value.setEnabled(enabled)


# --------------------------------------------------------------------------
# 画布：缩放 / 平移 / 前后对比
# --------------------------------------------------------------------------

class ImageView(QWidget):
    """图片预览画布，支持滚轮缩放、拖拽平移和拖动分割线对比。"""

    zoomChanged = Signal(float)
    compareChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self._original: Optional[QImage] = None
        self._result: Optional[QImage] = None
        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._fit = True

        self._panning = False
        self._last_pos = QPointF()
        self._compare = False
        self._split = 0.5
        self._dragging_split = False
        self._busy = False

    # -- 数据 ---------------------------------------------------------------
    def set_original(self, image: QImage) -> None:
        self._original = image
        self._result = None
        self._fit = True
        self._refit()
        self.update()

    def set_result(self, image: Optional[QImage]) -> None:
        self._result = image
        self.update()

    def clear(self) -> None:
        self._original = None
        self._result = None
        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._fit = True
        self.update()

    def has_image(self) -> bool:
        return self._original is not None

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.update()

    # -- 视图 ---------------------------------------------------------------
    def fit_to_window(self) -> None:
        self._fit = True
        self._refit()

    def actual_size(self) -> None:
        if not self._original:
            return
        self._fit = False
        self._scale = 1.0
        self._center()
        self.zoomChanged.emit(self._scale)
        self.update()

    def _refit(self) -> None:
        if not self._original or self.width() <= 0:
            return
        margin = 28.0
        iw = max(1, self._original.width())
        ih = max(1, self._original.height())
        sx = (self.width() - margin) / iw
        sy = (self.height() - margin) / ih
        self._scale = max(MIN_SCALE, min(sx, sy, 1.0))
        self._center()
        self.zoomChanged.emit(self._scale)

    def _center(self) -> None:
        if not self._original:
            return
        w = self._original.width() * self._scale
        h = self._original.height() * self._scale
        self._offset = QPointF((self.width() - w) / 2.0, (self.height() - h) / 2.0)

    def set_compare(self, enabled: bool) -> None:
        self._compare = enabled
        self.update()
        self.compareChanged.emit(enabled)

    def compare(self) -> bool:
        return self._compare

    def _image_rect(self) -> QRectF:
        if not self._original:
            return QRectF()
        return QRectF(self._offset.x(), self._offset.y(),
                      self._original.width() * self._scale,
                      self._original.height() * self._scale)

    def _split_x(self) -> float:
        rect = self._image_rect()
        return rect.left() + rect.width() * self._split

    # -- 绘制 ---------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(COLORS["canvas"]))

        if not self._original:
            self._paint_empty(painter)
            painter.end()
            return

        target = self._image_rect()

        # 画布阴影
        shadow = QRectF(target).adjusted(-1, -1, 1, 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(shadow.adjusted(-6, 4, 6, 12), 8, 8)

        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target)

        painter.save()
        painter.setClipRect(target)
        painter.drawImage(target, self._original)

        if self._result is not None:
            if self._compare:
                left = QRectF(target)
                left.setWidth(max(0.0, target.width() * self._split))
                painter.save()
                painter.setClipRect(left)
                painter.drawImage(target, self._original)
                painter.restore()
                painter.save()
                painter.setClipRect(QRectF(target.left() + target.width() * self._split,
                                           target.top(),
                                           target.width() * (1 - self._split),
                                           target.height()))
                painter.drawImage(target, self._result)
                painter.restore()
            else:
                painter.drawImage(target, self._result)
        painter.restore()

        if self._compare and self._result is not None:
            self._paint_split(painter, target)

        if self._busy:
            self._paint_busy(painter, target)

        painter.end()

    def _paint_empty(self, painter: QPainter) -> None:
        rect = self.rect().adjusted(60, 60, -60, -60)
        if rect.width() < 80 or rect.height() < 80:
            return
        pen = QPen(QColor(COLORS["border"]), 1.2, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 6])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

        # 一笔线条图案
        cx = rect.center().x()
        cy = rect.top() + rect.height() * 0.30
        path = QPainterPath()
        path.moveTo(cx - 54, cy + 16)
        path.cubicTo(cx - 34, cy - 32, cx + 6, cy - 32, cx + 10, cy + 2)
        path.cubicTo(cx + 13, cy + 25, cx + 44, cy - 4, cx + 52, cy + 10)
        pen = QPen(QColor(COLORS["accent"]), 2.6, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor("#C9CEDA"))
        font = QFont(self.font())
        font.setPointSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), cy + 54, rect.width(), 30),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         "把图片拖到这里")
        painter.setPen(QColor(COLORS["muted"]))
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), cy + 88, rect.width(), 26),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         "支持 PNG / JPG / WEBP / BMP / TIFF　·　或按 Ctrl+O 打开")

    def _paint_split(self, painter: QPainter, target: QRectF) -> None:
        x = self._split_x()
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.4))
        painter.drawLine(QPointF(x, target.top()), QPointF(x, target.bottom()))

        painter.setBrush(QColor(COLORS["accent"]))
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
        painter.drawEllipse(QPointF(x, target.center().y()), 9, 9)

        font = QFont(self.font())
        font.setPointSize(8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        for text, anchor_x, align in (("原图", x - 10, Qt.AlignmentFlag.AlignRight),
                                      ("线稿", x + 10, Qt.AlignmentFlag.AlignLeft)):
            tw = fm.horizontalAdvance(text) + 14
            box = QRectF(anchor_x - (tw if align == Qt.AlignmentFlag.AlignRight else 0),
                         target.top() + 10, tw, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.drawRoundedRect(box, 8, 8)
            painter.setPen(QColor(255, 255, 255, 210))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_busy(self, painter: QPainter, target: QRectF) -> None:
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        text = "正在生成…"
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 24
        box = QRectF(target.center().x() - w / 2, target.top() + 14, w, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(box, 12, 12)
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    # -- 交互 ---------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._original:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factors = event.modifiers()
        step = 1.0 + (0.0015 if delta > 0 else -0.0013) * abs(delta)
        if factors & Qt.KeyboardModifier.ControlModifier:
            step = 1.0 + (0.003 if delta > 0 else -0.0028) * abs(delta)
        self._zoom_at(event.position(), step)

    def _zoom_at(self, pos: QPointF, factor: float) -> None:
        old = self._scale
        new = max(MIN_SCALE, min(MAX_SCALE, old * factor))
        if abs(new - old) < 1e-6:
            return
        image_point = QPointF((pos.x() - self._offset.x()) / old,
                              (pos.y() - self._offset.y()) / old)
        self._offset = QPointF(pos.x() - image_point.x() * new,
                               pos.y() - image_point.y() * new)
        self._scale = new
        self._fit = False
        self.zoomChanged.emit(self._scale)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._original:
            return
        pos = event.position()
        if (self._compare and self._result is not None
                and abs(pos.x() - self._split_x()) < 12
                and self._image_rect().contains(pos)):
            self._dragging_split = True
            self.setCursor(Qt.CursorShape.SplitHCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._last_pos = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._original:
            return
        pos = event.position()
        if self._dragging_split:
            rect = self._image_rect()
            if rect.width() > 0:
                self._split = min(0.98, max(0.02, (pos.x() - rect.left()) / rect.width()))
            self.update()
            return
        if self._panning:
            delta = pos - self._last_pos
            self._offset += delta
            self._last_pos = pos
            self._fit = False
            self.update()
            return
        if (self._compare and self._result is not None
                and abs(pos.x() - self._split_x()) < 12
                and self._image_rect().contains(pos)):
            self.setCursor(Qt.CursorShape.SplitHCursor)
        elif self._original:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._panning = False
        self._dragging_split = False
        if self._original:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._fit:
            self.actual_size()
        else:
            self.fit_to_window()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self._refit()
        else:
            self.update()
