"""线稿渲染核心。

所有算法都输出一张「墨量图」(ink map)：0 表示纯白纸面，1 表示纯黑墨线。
统一在墨量图上做去噪、加粗、抗锯齿，因此各算法的手感保持一致。

设计要点
--------
* 参数与画幅无关：所有核尺寸按最长边缩放，预览与导出观感一致。
* 阈值按分位数自适应：不管照片多亮多暗，线条密度都稳定。
* 多尺度融合：粗尺度抓主轮廓，细尺度补细节，避免线条断裂。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np

from .analyzer import SceneInfo, analyze, auto_params
from .params import METHOD_LABELS, Params


@dataclass
class RenderResult:
    image: np.ndarray          # 灰度输出，白底黑线
    method: str                # 实际使用的算法
    method_label: str
    scene: Optional[SceneInfo] # 智能模式下的画面分析
    note: str                  # 状态栏文案
    elapsed: float             # 秒
    params: Params = None      # 实际生效的参数（智能模式解析后）


def _odd(value: float, lo: int = 3, hi: int = 199) -> int:
    v = int(round(value))
    v = max(lo, min(hi, v))
    return v if v % 2 == 1 else v + 1


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def resize_max(image: np.ndarray, max_side: Optional[int]) -> np.ndarray:
    """把最长边限制在 max_side 内（只缩小不放大）。"""
    if not max_side:
        return image
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    return cv2.resize(image, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                      interpolation=cv2.INTER_AREA)


def _scale_of(shape: Tuple[int, int]) -> float:
    """按画幅大小缩放内核尺寸，保证预览与导出图观感一致。"""
    h, w = shape[0], shape[1]
    return float(np.clip(max(h, w) / 1600.0, 0.35, 3.0))


def _auto_levels(gray: np.ndarray) -> np.ndarray:
    """百分位拉伸：让发灰、欠曝的照片也有稳定的黑白关系。"""
    sample = gray[::4, ::4]
    lo, hi = np.percentile(sample, (1.0, 99.0))
    lo, hi = float(lo), float(hi)
    if hi - lo < 6:
        lo, hi = float(gray.min()), float(gray.max())
    if hi - lo < 1:
        return gray.astype(np.float32)
    out = (gray.astype(np.float32) - lo) * np.float32(255.0 / (hi - lo))
    return np.clip(out, 0.0, 255.0).astype(np.float32)


def _prepare(gray: np.ndarray, p: Params, s: float) -> np.ndarray:
    """保边降噪 + 局部对比度增强，得到更适合提取线条的灰度图。"""
    g = np.ascontiguousarray(_auto_levels(gray), dtype=np.float32)
    smooth = p.smooth / 100.0
    if smooth > 0.02:
        sigma_c = 10.0 + smooth * 85.0
        d = _odd(3 + smooth * 9.0, 3, 17)
        g = cv2.bilateralFilter(g, d, sigma_c, max(1.0, sigma_c * 0.45))
    if p.contrast > 40:
        clahe = cv2.createCLAHE(clipLimit=1.0 + (p.contrast - 40) / 60.0 * 2.6,
                                tileGridSize=(8, 8))
        g = clahe.apply(np.clip(g, 0, 255).astype(np.uint8)).astype(np.float32)
    return np.ascontiguousarray(g, dtype=np.float32)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

EDGE_FLOOR = 0.22


def _canny_density(g: np.ndarray, sigma: float, target_ratio: float,
                   low_ratio: float, iterations: int = 4) -> np.ndarray:
    """自动把线条密度锁定到 target_ratio（占画面的百分比）。

    用梯度幅值的分位数做初值，再根据实际墨量迭代微调阈值，
    因此无论照片多灰、多碎，出线的疏密都稳定可控。
    """
    blur = cv2.GaussianBlur(g, (0, 0), sigma) if sigma > 0.3 else g
    blur8 = np.clip(blur, 0, 255).astype(np.uint8)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)

    target = float(np.clip(target_ratio, 0.15, 30.0))
    high = max(6.0, float(np.percentile(mag[::2, ::2], 100.0 - target * 3.0)))
    # 强度下限：宁可不达密度，也不把纹理噪声画成线
    floor = EDGE_FLOOR * float(np.percentile(mag[::2, ::2], 99.0))
    best, best_err = None, 1e9

    for _ in range(max(1, iterations)):
        low = max(3.0, high * low_ratio)
        edge = cv2.Canny(blur8, int(round(low)), int(round(high)), L2gradient=True)
        ratio = float((edge > 0).mean() * 100.0)
        err = abs(ratio - target)
        if err < best_err:
            best, best_err = edge, err
        if target <= 0:
            break
        if ratio <= 0.05 or ratio > 60.0:
            high *= 0.5 if ratio <= 0.05 else 1.8
            continue
        if err <= target * 0.18:
            break
        high = float(np.clip(high * (ratio / target) ** 0.75, max(4.0, floor), 4000.0))
        high = max(high, floor)

    return best.astype(np.float32) / 255.0


def _close_gaps(ink: np.ndarray, s: float, size: int = 3) -> np.ndarray:
    """闭运算：把断开的笔触接上，让线条更像手绘。"""
    binary = (ink > 0.5).astype(np.uint8)
    if not binary.any():
        return ink
    k = max(2, int(round(size * np.clip(s, 0.5, 2.0))))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return np.maximum(ink, closed.astype(np.float32))


def _smoothstep(x: np.ndarray, edge0: float, edge1: float) -> np.ndarray:
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------
# 各算法：返回 float32 墨量图 (0..1)
# --------------------------------------------------------------------------

def _ink_line(g: np.ndarray, p: Params, s: float) -> np.ndarray:
    """墨线：多尺度分位数边缘 + 断线连接，最干净的勾线方案。"""
    detail = p.detail / 100.0
    coverage = 1.4 + detail * 5.6                 # 1.4% ~ 7%
    coverage *= 1.10 - p.contrast / 100.0 * 0.25  # 对比度高 → 线条更少更重
    low_ratio = 0.55 - p.contrast / 100.0 * 0.32

    fine_sigma = max(0.55, (1.9 - detail * 1.35) * s)
    coarse_sigma = fine_sigma * 2.6

    fine = _canny_density(g, fine_sigma, coverage, low_ratio)
    coarse = _canny_density(g, coarse_sigma, coverage * 0.35, low_ratio * 0.8, iterations=3)

    # 主轮廓加粗一档，形成「外粗内细」的手绘层次
    if coarse.any():
        coarse = cv2.dilate(coarse, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    ink = np.maximum(fine * 0.92, coarse * 0.98)
    ink = _close_gaps(ink, s, size=3)
    return ink.astype(np.float32)


def _ink_manga(g: np.ndarray, p: Params, s: float) -> np.ndarray:
    """漫画：粗勾线 + 实心黑块，适合人像和氛围照片。"""
    detail = p.detail / 100.0
    coverage = 1.0 + detail * 3.4
    low_ratio = 0.60 - p.contrast / 100.0 * 0.35

    fine_sigma = max(0.6, (2.0 - detail * 1.4) * s)
    coarse_sigma = fine_sigma * 3.0

    fine = _canny_density(g, fine_sigma, coverage, low_ratio, iterations=3)
    coarse = _canny_density(g, coarse_sigma, coverage * 0.32, low_ratio * 0.75, iterations=3)
    lines = np.maximum(fine, coarse * 1.0)

    # 实心黑：暗部且纹理平滑的区域涂黑
    f = g / 255.0
    base_sigma = max(2.0, 6.0 * s)
    base = cv2.GaussianBlur(f, (0, 0), base_sigma)
    dark_cut = 0.30 - p.contrast / 100.0 * 0.12
    fills = _smoothstep(dark_cut - base, 0.0, 0.055)

    # 只保留「成块」的暗部，细长的暗带（地平线、枝条）不涂黑，免得变成墨条
    solid = (fills > 0.5).astype(np.uint8)
    k = max(3, int(round(4 * s)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, kernel)
    if solid.any():
        # 细长条（远处树线、栏杆）不涂黑：按连通域长宽比与面积筛一遍
        n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
        min_area = max(80.0, 900.0 * s * s)
        keep = np.zeros_like(solid)
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < min_area:
                continue
            if max(w, h) > 6.0 * max(1.0, min(w, h)):
                continue
            # 贴边的暗部（背景、地平线）不涂黑，只填主体内部的暗块
            if x <= 1 or y <= 1 or x + w >= solid.shape[1] - 1 or y + h >= solid.shape[0] - 1:
                continue
            keep[labels == i] = 1
        solid = keep
    if solid.any():
        solid = cv2.dilate(solid, kernel)
        fills = cv2.GaussianBlur(solid.astype(np.float32) * 255.0, (0, 0), max(0.6, s * 0.8)) / 255.0
    else:
        fills = np.zeros_like(fills)

    ink = np.maximum(lines, fills * 0.95)
    ink = _close_gaps(ink, s, size=3)
    return ink.astype(np.float32)


def _ink_minimal(g: np.ndarray, p: Params, s: float) -> np.ndarray:
    """极简：只留最粗壮的主体轮廓，适合做贴纸、头像、图标。"""
    detail = p.detail / 100.0
    sigma = max(1.1, (2.9 - detail * 1.9) * s)

    main = _canny_density(g, sigma, 0.8 + detail * 1.8, low_ratio=0.60, iterations=3)
    mid = _canny_density(g, sigma * 0.55, 1.0 + detail * 2.2, low_ratio=0.55, iterations=3)
    ink = np.maximum(main, mid * 0.92)
    ink = _close_gaps(ink, s, size=5)
    # 极简风格：主体线更饱满
    ink = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))
    return ink.astype(np.float32)


def _ink_pencil(g: np.ndarray, p: Params, s: float) -> np.ndarray:
    """铅笔素描：dodge 混合 + 层次拉伸。"""
    f = g.astype(np.float32)
    inv = 255.0 - f
    radius = _odd(max(3.0, (13.0 + (100 - p.detail) * 0.35) * s), 3, 201)
    blur = cv2.GaussianBlur(inv, (0, 0), radius / 3.0)
    blur = np.where(blur < 1.0, 1.0, blur)
    sketch = np.clip(f / (255.0 - blur) * 255.0, 0, 255)

    lo, hi = np.percentile(sketch[::4, ::4], (1.0, 99.5))
    if hi - lo > 8:
        sketch = (sketch - lo) * (255.0 / (hi - lo))
    sketch = np.clip(sketch, 0, 255) / 255.0

    k = 0.8 + p.contrast / 100.0 * 1.5
    sketch = np.clip((sketch - 0.5) * k + 0.5, 0.0, 1.0)
    sketch = np.clip((sketch - 0.03) / 0.97, 0.0, 1.0)
    return (1.0 - sketch).astype(np.float32)


def _ink_wash(g: np.ndarray, p: Params, s: float) -> np.ndarray:
    """水墨：淡化块面 + 少量线条，突出留白。"""
    f = np.ascontiguousarray(g / 255.0, dtype=np.float32)
    detail = p.detail / 100.0

    # 大块面的淡墨：越暗越浓，但整体压得很淡
    base = cv2.GaussianBlur(f, (0, 0), max(1.5, 4.0 * s))
    strength = 0.35 + p.contrast / 100.0 * 0.55
    tone = _smoothstep(0.62 - base, 0.0, 0.5) * strength

    # 少量线条：只保留最明确的结构
    lines = _canny_density(g, max(0.8, (2.2 - detail * 1.5) * s),
                           target_ratio=0.7 + detail * 1.9,
                           low_ratio=0.45, iterations=3)
    lines = cv2.GaussianBlur(lines, (0, 0), max(0.5, 0.7 * s))
    ink = np.maximum(tone, lines * 0.9)
    return np.clip(ink, 0.0, 1.0).astype(np.float32)


_RENDERERS: Dict[str, Callable[[np.ndarray, Params, float], np.ndarray]] = {
    "line": _ink_line,
    "manga": _ink_manga,
    "minimal": _ink_minimal,
    "pencil": _ink_pencil,
    "wash": _ink_wash,
}

# 这些算法输出的是线条，需要做断线清理与线宽控制
LINE_METHODS = {"line", "manga", "minimal"}

# 兼容旧参数名
_ALIASES = {"edge": "line", "xdog": "manga", "ink": "wash"}


# --------------------------------------------------------------------------
# 后处理
# --------------------------------------------------------------------------

def _remove_specks(ink: np.ndarray, min_area: float) -> np.ndarray:
    if min_area <= 0:
        return ink
    mask = (ink > 0.5).astype(np.uint8)
    if not mask.any():
        return ink
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return ink
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(count, dtype=bool)
    keep[1:] = areas >= min_area
    return ink * keep[labels]


def _thicken(ink: np.ndarray, thickness: int, s: float) -> np.ndarray:
    if thickness <= 1:
        return ink
    size = _odd(1 + (thickness - 1) * max(0.9, 1.45 * s), 1, 61)
    if size <= 1:
        return ink
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    return cv2.dilate(ink, kernel)


def _postprocess(ink: np.ndarray, p: Params, s: float, is_line: bool) -> np.ndarray:
    ink = np.clip(ink, 0.0, 1.0).astype(np.float32)

    if is_line and p.cleanup > 0:
        # 清理面积过小的孤立点；按画幅缩放，预览与导出结果一致
        min_area = (p.cleanup / 100.0) ** 2 * 480.0 * s * s + 2.0
        ink = _remove_specks(ink, min_area)

    if is_line and p.thickness > 1:
        ink = _thicken(ink, p.thickness, s)
        ink = cv2.GaussianBlur(ink, (0, 0), 0.55 * s)   # 半像素抗锯齿
    return ink


def render(image: np.ndarray,
           params: Params,
           max_side: Optional[int] = None,
           analysis: Optional[SceneInfo] = None) -> RenderResult:
    """把照片渲染成线稿。

    :param max_side: 限制处理边长（预览时传 1600 左右，导出传 None）
    :param analysis: 智能模式下可以直接复用的画面分析结果
    """
    started = time.perf_counter()
    p = params.clamped()
    p = p.with_values(method=_ALIASES.get(p.method, p.method))
    img = resize_max(image, max_side)

    gray = to_gray(img)
    scene: Optional[SceneInfo] = None
    note = ""

    if p.method == "smart":
        scene = analysis or analyze(img)
        p = auto_params(scene, p)
        p = p.with_values(method=_ALIASES.get(p.method, p.method))
        note = f"智能识别：{scene.label}"
    if p.method not in _RENDERERS:
        p = p.with_values(method="line")

    s = _scale_of(gray.shape)
    g = _prepare(gray, p, s)
    ink = _RENDERERS[p.method](g, p, s)
    ink = _postprocess(ink, p, s, is_line=p.method in LINE_METHODS)

    out = np.clip((1.0 - ink) * 255.0, 0, 255).astype(np.uint8)
    if p.invert:
        out = 255 - out

    elapsed = time.perf_counter() - started
    return RenderResult(
        image=out,
        method=p.method,
        method_label=METHOD_LABELS.get(p.method, p.method),
        scene=scene,
        note=note,
        elapsed=elapsed,
        params=p,
    )
