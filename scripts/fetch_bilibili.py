"""
viralens · fetch_bilibili.py
平台适配器:Bilibili。原 fetch_multi.py 里的 B 站抓取逻辑抽到这里。
吐出标准视频表(和 fetch_youtube.py 完全一致的字段),由 fetch_multi.py 调度。

依赖: bilibili-api-python  /  SESSDATA 从 config_local.py 读(已 gitignore,不进 git)。
"""
import asyncio
import sys
from datetime import datetime

from bilibili_api import user, Credential

from schema import VideoRecord

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class BilibiliError(Exception):
    """对外抛出的可读错误,由 fetch_multi 调度器统一捕获打印(对应 YouTube 的 YouTubeError)。"""


def parse_length(s):
    """'12:34' / '1:02:03' → 秒。"""
    if not s:
        return 0
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


PAGE_MAX = 50   # B 站 get_videos 每页上限


def _to_record(c, v) -> VideoRecord:
    """一条 B 站原始视频 → 标准视频表记录(字段契约见 schema.VideoRecord)。"""
    ts = v.get("created", 0)
    bvid = v.get("bvid")
    return {
        "creator": c["name"], "alias": c["alias"], "zone": c["zone"],
        "platform": "bilibili",
        "vid": bvid, "bvid": bvid, "aid": v.get("aid"),
        "title": v.get("title"), "description": v.get("description", ""),
        "cover_url": v.get("pic"),
        "duration_sec": parse_length(v.get("length", "")),
        "created_ts": ts,
        "created_iso": datetime.fromtimestamp(ts).isoformat() if ts else None,
        "play": v.get("play"), "comment": v.get("comment"),
        "danmaku": v.get("video_review"), "tid": v.get("typeid"),
    }


async def _get_page(u, ps, pn, name, tries):
    """抓一页,带 412 风控退避重试;失败统一抛 BilibiliError。"""
    for attempt in range(tries):
        try:
            return await u.get_videos(ps=ps, pn=pn)
        except Exception as e:
            if attempt == tries - 1:
                raise BilibiliError(
                    f"{name}:调 B 站 API 失败(网络 / 风控 412?):{type(e).__name__}: {e}") from None
            wait = 5 * (attempt + 1)   # 5s,10s,15s 退避,清掉 412 风控
            print(f"     ...{name} 第 {pn} 页第 {attempt + 1} 次失败(412?),{wait}s 后重试")
            await asyncio.sleep(wait)


async def fetch_creator(c, sessdata, num=40, tries=4, buvid3="") -> "list[VideoRecord]":
    """标准适配器接口(异步):给一个 creators.py 条目 → 标准视频表。
    **分页**抓取直到取够 num 条或没有更多(B 站每页上限 50;旧版只取第一页,num>50 会漏数据)。
    buvid3 可选:B 站 2025 年起部分接口要求该 Cookie,遇到 -352 时在 config_local.py 里补上。"""
    if not sessdata:
        raise BilibiliError("没读到 SESSDATA —— 在 config_local.py 里填上(浏览器 Cookie 里的 SESSDATA)")
    uid = c.get("uid")
    if not uid:
        raise BilibiliError(
            f"{c.get('name', '?')} 缺 uid —— 先跑 resolve_creators.py 查出 UP 主 ID 填进 creators.py")
    cred = Credential(sessdata=sessdata, buvid3=buvid3) if buvid3 else Credential(sessdata=sessdata)
    u = user.User(uid=uid, credential=cred)

    raw_videos: list[dict] = []
    pn = 1
    # 页大小定死:B 站按 [(pn-1)*ps, pn*ps) 取窗口,最后一页改小 ps 会让窗口错位
    # (重复抓前面的 + 漏掉后面的)。宁可末页多拿几条,最后统一切片到 num。
    ps = min(PAGE_MAX, num)
    while len(raw_videos) < num:
        if pn > 1:
            await asyncio.sleep(0.8)   # 成功路径也节流:把 412 防在前面,而不是事后退避救
        raw = await _get_page(u, ps, pn, c["name"], tries)
        page = (raw.get("list", {}) or {}).get("vlist", []) or []
        raw_videos.extend(page)
        total = (raw.get("page") or {}).get("count")     # 该 UP 主总投稿数(可提前停)
        if len(page) < ps:                                # 这一页没满 → 没有更多了
            break
        if total is not None and len(raw_videos) >= total:
            break
        pn += 1

    videos = [_to_record(c, v) for v in raw_videos[:num]]
    videos.sort(key=lambda x: x["play"] or 0, reverse=True)
    return videos
