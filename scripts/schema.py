"""
viralens · schema.py —— 标准「视频记录」的字段契约(文档化用)。

所有平台适配器(fetch_bilibili / fetch_youtube)都吐出同一形状的 dict。以前这个 schema
只散落在各处的 dict 字面量里,传错字段很难发现。这里用一个 TypedDict 把它写下来,既给
人看(字段一览),也能给类型检查器用。total=False:不同平台填的字段略有差异(B 站有
danmaku、YouTube 有 like),都视为可选。
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
