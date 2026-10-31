"""图片读写：兼容中文路径（走 numpy 缓冲区，绕开 OpenCV 的编码问题）。"""
from __future__ import annotations

import os
from typing import Tuple

import cv2
import numpy as np

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".jfif")

OPEN_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"


class ImageLoadError(RuntimeError):
    """图片读取失败。"""


def load_image(path: str) -> np.ndarray:
    """读取图片，返回 BGR 或 BGRA 的 uint8 数组。"""
    if not os.path.isfile(path):
        raise ImageLoadError("文件不存在")
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError as exc:
        raise ImageLoadError(f"无法读取文件：{exc}") from exc
    if data.size == 0:
        raise ImageLoadError("文件是空的")
    image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ImageLoadError("不是可识别的图片格式")
    if image.dtype != np.uint8:
        image = cv2.convertScaleAbs(image)
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        # 透明背景统一铺白，避免转线稿后出现黑底
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        rgb = image[:, :, :3].astype(np.float32)
        white = np.full_like(rgb, 255.0)
        blended = rgb * alpha + white * (1.0 - alpha)
        image = cv2.cvtColor(blended.astype(np.uint8), cv2.COLOR_RGB2BGR)
    return image


def save_image(path: str, image: np.ndarray, quality: int = 95) -> None:
    """保存图片，根据扩展名决定编码。灰度图会自动按灰度写。"""
    ext = os.path.splitext(path)[1].lower() or ".png"
    if ext in (".jpg", ".jpeg", ".jfif") and image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    params = []
    if ext in (".jpg", ".jpeg", ".jfif"):
        params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    elif ext == ".png":
        params = [int(cv2.IMWRITE_PNG_COMPRESSION), 6]
    ok, buffer = cv2.imencode(ext, image, params)
    if not ok:
        raise IOError("图片编码失败")
    buffer.tofile(path)


def image_size(image: np.ndarray) -> Tuple[int, int]:
    """返回 (宽, 高)。"""
    return int(image.shape[1]), int(image.shape[0])


def human_size(width: int, height: int) -> str:
    return f"{width} × {height}"
