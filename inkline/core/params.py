"""参数模型、算法清单与预设。"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Params:
    """一次渲染所需的全部可调参数。

    所有滑块均为 0~100 的整数，内部会映射到各算法的实际取值范围，
    这样界面可以保持简单统一，算法端仍然有充分的调节空间。
    """

    method: str = "smart"
    detail: int = 55       # 细节密度：越大保留越多细碎线条
    thickness: int = 2     # 线条粗细：1 表示单像素细线
    contrast: int = 55     # 线条浓淡：越大线条越重、越黑
    smooth: int = 35       # 降噪平滑：越大画面越干净，细节越少
    cleanup: int = 30      # 杂点清理：去掉面积过小的孤立笔触
    invert: bool = False   # 反相（白线黑底）

    def with_values(self, **kwargs) -> "Params":
        return replace(self, **kwargs)

    def clamped(self) -> "Params":
        def c(v: int, lo: int, hi: int) -> int:
            return int(max(lo, min(hi, v)))

        return replace(
            self,
            detail=c(self.detail, 0, 100),
            thickness=c(self.thickness, 1, 12),
            contrast=c(self.contrast, 0, 100),
            smooth=c(self.smooth, 0, 100),
            cleanup=c(self.cleanup, 0, 100),
        )


#: (内部键, 中文名, 一句话说明)
METHODS: List[Tuple[str, str, str]] = [
    ("smart", "智能", "自动分析画面，挑选最合适的算法与参数"),
    ("line", "墨线", "多尺度勾线，线条干净、细节完整"),
    ("manga", "漫画", "粗勾线加实心黑块，氛围感强"),
    ("minimal", "极简", "只留主体轮廓，干净利落"),
    ("pencil", "素描", "保留明暗调子，像铅笔手绘"),
    ("wash", "水墨", "柔和的淡墨块面，留白自然"),
]

METHOD_LABELS: Dict[str, str] = {k: name for k, name, _ in METHODS}
METHOD_HINTS: Dict[str, str] = {k: hint for k, _, hint in METHODS}


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    note: str
    params: Params


PRESETS: Tuple[Preset, ...] = (
    Preset(
        "auto",
        "智能推荐",
        "什么都不用调，直接出图",
        Params(method="smart", detail=55, thickness=2, contrast=55, smooth=35, cleanup=30),
    ),
    Preset(
        "comic",
        "漫画线稿",
        "粗线条、强对比，适合转漫画",
        Params(method="manga", detail=52, thickness=3, contrast=60, smooth=48, cleanup=45),
    ),
    Preset(
        "architecture",
        "建筑速写",
        "线条挺括、细节多",
        Params(method="line", detail=68, thickness=2, contrast=58, smooth=25, cleanup=22),
    ),
    Preset(
        "minimal",
        "极简勾线",
        "只留主要轮廓，干净留白",
        Params(method="minimal", detail=40, thickness=3, contrast=50, smooth=55, cleanup=55),
    ),
    Preset(
        "pencil",
        "铅笔素描",
        "柔和的铅笔调子",
        Params(method="pencil", detail=55, thickness=1, contrast=52, smooth=30, cleanup=10),
    ),
    Preset(
        "wash",
        "水墨淡彩",
        "晕染、留白、很中国",
        Params(method="wash", detail=45, thickness=2, contrast=46, smooth=62, cleanup=35),
    ),
)

PRESET_BY_KEY: Dict[str, Preset] = {p.key: p for p in PRESETS}
