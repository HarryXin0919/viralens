"""
viralens · schema.py —— 标准「视频记录」的字段契约 + 操作这条记录的公共小工具。

所有平台适配器(fetch_bilibili / fetch_youtube)都吐出同一形状的 dict。以前这个 schema
只散落在各处的 dict 字面量里,传错字段很难发现。这里用一个 TypedDict 把它写下来,既给
人看(字段一览),也能给类型检查器用。total=False:不同平台填的字段略有差异(B 站有
danmaku、YouTube 有 like),都视为可选。

video_url / fmt_play 以前在 app / build_report / export_data / charts 里各复制了一份,
已经开始各改各的漂移(有一份还会在 play=None 时崩),收口到这里:纯标准库,谁都能 import。
"""
from __future__ import annotations

from typing import Optional, TypedDict


class VideoRecord(TypedDict, total=False):
    creator: str            # 显示名
    alias: str              # 输出文件名用的英文别名
    zone: str               # 分区 / 赛道
    platform: str           # "bilibili" | "youtube"
    vid: str                # 平台视频 id(B 站=bvid,YouTube=videoId)
    bvid: str               # B 站 BV 号
    aid: int                # B 站 av 号
    title: str
    description: str
    cover_url: str
    duration_sec: int
    created_ts: int         # 发布 Unix 时间戳
    created_iso: Optional[str]
    play: Optional[int]     # 播放 / views
    comment: Optional[int]
    danmaku: Optional[int]  # B 站弹幕数(YouTube 无)
    like: Optional[int]     # YouTube 点赞(B 站这里不填)
    tid: Optional[int]      # B 站分区 id


def video_url(v) -> str:
    """按平台拼出可点开的视频链接;没 id 返回空串。"""
    plat = (v.get("platform") or "bilibili").lower()
    vid = v.get("bvid") or v.get("vid") or ""
    if not vid:
        return ""
    if plat == "youtube":
        return f"https://www.youtube.com/watch?v={vid}"
    return f"https://www.bilibili.com/video/{vid}"


def fmt_play(n, yi: int = 2, wan: int = 1) -> str:
    """中文友好的播放量:1.50亿 / 814.0万 / 9,532;None/非数 → "-"。
    yi/wan 控制亿/万档的小数位(图表轴标签用更短的 yi=1, wan=0)。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1e8:
        return f"{n / 1e8:.{yi}f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.{wan}f}万"
    return f"{n:,.0f}"
