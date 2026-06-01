"""
viralens · fetch_videos.py
抓一个 B 站 UP 主最近 N 个视频的元数据,输出 JSON 给后续分析用。
(这是早期单人脚本;多创作者请用 fetch_multi.py。)

依赖:
    python -m pip install bilibili-api-python aiohttp

使用:
    1. 浏览器登录 b站(www.bilibili.com)
    2. F12 → Application/存储 → Cookies → https://www.bilibili.com → 找 SESSDATA
       复制 Value(看起来像 "abc123%2Cxxxx%2Cyyy...")
    3. 把 Value 粘贴到下方 SESSDATA 变量(引号内)
    4. 跑: python fetch_videos.py

输出: ../data/<alias>_videos.json
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

from bilibili_api import user, Credential

# ============ 配置 ============
UID = 0                     # 换成你要抓的 UP 主 UID(resolve_creators.py 可按名字查)
NUM_VIDEOS = 30             # 抓最近多少个
try:
    from config_local import SESSDATA   # ← SESSDATA 统一放 config_local.py(已 gitignore,不进 git)
except ImportError:
    SESSDATA = ""
from runtime import DATA
OUTPUT = DATA / "bidao_videos.json"
# =============================


def parse_length(s: str) -> int:
    """B 站 length 字段是 'MM:SS' 或 'HH:MM:SS',转成秒"""
    if not s:
        return 0
    parts = [int(x) for x in s.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


async def main():
    if not SESSDATA:
        print("❌ 没读到 SESSDATA。把 config_local.example.py 复制为 config_local.py 并填入你的 SESSDATA")
        sys.exit(1)

    cred = Credential(sessdata=SESSDATA)
    u = user.User(uid=UID, credential=cred)

    print(f"📡 抓取 UID={UID} 最近 {NUM_VIDEOS} 个视频...")
    try:
        raw = await u.get_videos(ps=NUM_VIDEOS, pn=1)
    except Exception as e:
        print(f"❌ 调用失败: {e}")
        print("   检查 SESSDATA 是否过期、网络是否能访问 b站")
        sys.exit(1)

    vlist = raw.get("list", {}).get("vlist", [])
    if not vlist:
        print("❌ 没拿到视频。原始返回(前 500 字):")
        print(str(raw)[:500])
        sys.exit(1)

    videos = []
    for v in vlist:
        created_ts = v.get("created", 0)
        videos.append({
            "bvid": v.get("bvid"),
            "aid": v.get("aid"),
            "title": v.get("title"),
            "description": v.get("description", ""),
            "cover_url": v.get("pic"),
            "duration_sec": parse_length(v.get("length", "")),
            "duration_raw": v.get("length"),
            "created_ts": created_ts,
            "created_iso": datetime.fromtimestamp(created_ts).isoformat() if created_ts else None,
            "play": v.get("play"),
            "comment": v.get("comment"),
            "danmaku": v.get("video_review"),
            "tid": v.get("typeid"),
            "subtitle": v.get("subtitle", ""),
        })

    # 按播放量降序
    videos.sort(key=lambda x: x["play"] or 0, reverse=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)

    # 打印概览
    print(f"\n✅ 抓到 {len(videos)} 个视频")
    print(f"   写入: {OUTPUT}")
    print(f"\n📊 播放量分布:")
    print(f"   最高: {videos[0]['play']:>10,}  ←  {videos[0]['title'][:35]}")
    mid = videos[len(videos) // 2]
    print(f"   中位: {mid['play']:>10,}  ←  {mid['title'][:35]}")
    print(f"   最低: {videos[-1]['play']:>10,}  ←  {videos[-1]['title'][:35]}")
    print(f"\n📅 时间跨度:")
    print(f"   最早: {videos[-1]['created_iso'][:10] if videos[-1]['created_iso'] else '?'}")
    print(f"   最近: {videos[0]['created_iso'][:10] if videos[0]['created_iso'] else '?'}")


if __name__ == "__main__":
    asyncio.run(main())
