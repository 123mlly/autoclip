"""混剪转场常量"""

from typing import Dict, Optional, Set

# FFmpeg xfade 支持的转场名
XFADE_TRANSITIONS: Set[str] = {
    "fade",
    "fadeblack",
    "fadewhite",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "circleopen",
    "circleclose",
    "dissolve",
}

TRANSITION_LABELS: Dict[str, str] = {
    "none": "硬切",
    "fade": "淡入淡出",
    "fadeblack": "黑场过渡",
    "fadewhite": "闪白",
    "wipeleft": "左划",
    "wiperight": "右划",
    "wipeup": "上划",
    "wipedown": "下划",
    "slideleft": "左滑",
    "slideright": "右滑",
    "slideup": "上滑",
    "slidedown": "下滑",
    "circleopen": "圆形展开",
    "circleclose": "圆形收缩",
    "dissolve": "溶解",
}


def normalize_transition(value: Optional[str]) -> str:
    if not value or value == "none":
        return "none"
    return value if value in XFADE_TRANSITIONS else "fade"


def resolve_output_size(aspect_ratio: Optional[str]) -> tuple[int, int]:
    """返回 (width, height)。"""
    ratio = (aspect_ratio or "9:16").strip()
    if ratio == "16:9":
        return 1920, 1080
    return 1080, 1920
