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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


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


async def fetch_creator(c, sessdata, num=40, tries=4):
    """标准适配器接口(异步):给一个 creators.py 条目 → 标准视频表 list[dict]。"""
    if not sessdata:
        raise RuntimeError("没读到 SESSDATA(config_local.py)")
    uid = c.get("uid")
    if not uid:
        raise RuntimeError("缺 UID,先跑 resolve_creators.py")
    cred = Credential(sessdata=sessdata)
    u = user.User(uid=uid, credential=cred)
    raw = None
    for attempt in range(tries):
        try:
            raw = await u.get_videos(ps=num, pn=1)
            break
        except Exception:
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)   # 5s,10s,15s 退避,清掉 412 风控
            print(f"     ...{c['name']} 第{attempt + 1}次失败(412?),{wait}s 后重试")
            await asyncio.sleep(wait)
    vlist = raw.get("list", {}).get("vlist", [])
    videos = []
    for v in vlist:
        ts = v.get("created", 0)
        bvid = v.get("bvid")
        videos.append({
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
        })
    videos.sort(key=lambda x: x["play"] or 0, reverse=True)
    return videos
