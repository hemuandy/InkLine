"""画面分析：猜测图片类型，并为「智能」模式生成合适的参数。"""
from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from .params import Params

SCENE_LABELS = {
    "portrait": "人像",
    "landscape": "风景",
    "architecture": "复杂场景",
    "graphic": "插画 / 线稿",
    "document": "文字 / 漫画页",
    "unknown": "通用画面",
}


@dataclass(frozen=True)
class SceneInfo:
    kind: str
    label: str
    brightness: float
    contrast: float
    edge_density: float
    noise: float
    saturation: float
    skin_ratio: float

    def describe(self) -> str:
        return f"{self.label} · 亮度 {self.brightness:.0f} · 细节密度 {self.edge_density * 100:.1f}%"


def _odd(value: int, lo: int = 3, hi: int = 99) -> int:
    v = int(max(lo, min(hi, value)))
    return v if v % 2 == 1 else v + 1


def analyze(image: np.ndarray) -> SceneInfo:
    """快速分析一张 BGR / 灰度图。

    只在缩小后的副本上统计，保证大图也能瞬间完成。
    """
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        saturation = float(hsv[:, :, 1].mean())
        ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycc, (0, 133, 77), (255, 173, 127))
        skin_ratio = float(mask.mean() / 255.0)
    else:
        gray = image
        saturation = 0.0
        skin_ratio = 0.0

    h, w = gray.shape[:2]
    scale = 480.0 / max(h, w)
    if scale < 1.0:
        small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = gray

    brightness = float(small.mean())
    contrast = float(small.std())
    edges = cv2.Canny(small, 40, 120)
    edge_density = float((edges > 0).mean())
    lap = cv2.Laplacian(small, cv2.CV_32F, ksize=3)
    noise = float(np.abs(lap).mean())

    if saturation < 26 and edge_density > 0.055 and contrast > 55:
        kind = "document"
    elif edge_density > 0.14 and saturation < 60:
        kind = "graphic"
    elif skin_ratio > 0.055 and edge_density < 0.13:
        kind = "portrait"
    elif edge_density > 0.095:
        kind = "architecture"
    elif saturation > 30 or edge_density > 0.03:
        kind = "landscape"
    else:
        kind = "unknown"

    return SceneInfo(
        kind=kind,
        label=SCENE_LABELS[kind],
        brightness=brightness,
        contrast=contrast,
        edge_density=edge_density,
        noise=noise,
        saturation=saturation,
        skin_ratio=skin_ratio,
    )


def auto_params(info: SceneInfo, base: Params | None = None) -> Params:
    """根据画面特征给出「智能」参数。用户手动调过的项会保留。"""
    base = base or Params()
    presets = {
        "portrait": dict(method="line", detail=50, thickness=2, contrast=58, smooth=58, cleanup=45),
        "landscape": dict(method="line", detail=58, thickness=2, contrast=55, smooth=42, cleanup=35),
        "architecture": dict(method="line", detail=66, thickness=2, contrast=58, smooth=28, cleanup=25),
        "graphic": dict(method="minimal", detail=45, thickness=2, contrast=55, smooth=35, cleanup=30),
        "document": dict(method="adaptive", detail=72, thickness=1, contrast=60, smooth=12, cleanup=15),
        "unknown": dict(method="line", detail=55, thickness=2, contrast=55, smooth=38, cleanup=32),
    }
    values = presets.get(info.kind, presets["unknown"])

    # 画面偏暗：降低阈值把细节拉出来；偏亮：略微收紧
    if info.brightness < 90:
        values["contrast"] += 6
        values["detail"] += 6
    elif info.brightness > 190:
        values["contrast"] += 4
    # 噪点重的图，加大平滑与清理
    if info.noise > 22:
        values["smooth"] += 14
        values["cleanup"] += 12
    # 低对比度照片
    if info.contrast < 38:
        values["contrast"] += 8
    # 细节过于密集的画面（树叶、沙砾、毛皮）：收一收，避免线条糊成一团
    if info.edge_density > 0.14:
        values["detail"] -= 10
        values["cleanup"] += 10
    if info.edge_density > 0.22:
        values["detail"] -= 8
        values["cleanup"] += 8

    bounded = {
        "detail": int(np.clip(values["detail"], 0, 100)),
        "thickness": int(np.clip(values["thickness"], 1, 12)),
        "contrast": int(np.clip(values["contrast"], 0, 100)),
        "smooth": int(np.clip(values["smooth"], 0, 100)),
        "cleanup": int(np.clip(values["cleanup"], 0, 100)),
    }
    return replace(base, method=values["method"], **bounded)
