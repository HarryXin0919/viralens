"""
viralens · fetch_multi.py
抓取调度器:按 creators.py 里每个创作者的 platform 字段,派发给对应平台适配器,
统一写出 data/<alias>_videos.json(标准视频表)。任意平台 / 任意分区 / 任意创作者。

适配器:
  bilibili → fetch_bilibili.py(用 SESSDATA)
  youtube  → fetch_youtube.py (用 YOUTUBE_API_KEY)
想加新平台?照着写一个 fetch_<平台>.py,吐出同样字段,在 fetch_for() 里挂一行即可。

跑: python fetch_multi.py          (默认跳过已抓过的,保护已验证数据集)
    python fetch_multi.py --force  (强制重抓)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 可写数据目录(源码=仓库/data,app=用户目录;runtime 已自动建好)

try:
    from config_local import SESSDATA
except ImportError:
    SESSDATA = ""
try:
    from config_local import YOUTUBE_API_KEY
except ImportError:
    YOUTUBE_API_KEY = ""

from creators import CREATORS, validate_creators

NUM_VIDEOS = 40   # 每个创作者抓最近多少个


async def fetch_for(c):
    """按平台派发(适配器懒加载:只装了 B 站依赖也能单跑 YouTube,反之亦然)。"""
    platform = (c.get("platform") or "bilibili").lower()
    if platform == "bilibili":
        import fetch_bilibili
        return await fetch_bilibili.fetch_creator(c, SESSDATA, NUM_VIDEOS)
    if platform == "youtube":
        import fetch_youtube
        return fetch_youtube.fetch_creator(c, YOUTUBE_API_KEY, NUM_VIDEOS)
    raise RuntimeError(f"未知平台 '{platform}'(目前支持 bilibili / youtube)")


async def main():
    force = "--force" in sys.argv
    problems = validate_creators()
    if problems:
        print("✗ creators.py 配置有误,请先修正:")
        for p in problems:
            print(f"    - {p}")
        return
    # 界面勾选了哪些平台就只抓哪些(app.py 通过环境变量传入;空=全抓,命令行单跑时不受限)
    only = [p.strip().lower() for p in os.environ.get("VIRALENS_PLATFORMS", "").split(",") if p.strip()]
    if only:
        print(f"  (只抓:{'、'.join(only)})")
    n_ok = 0
    for c in CREATORS:
        platform = (c.get("platform") or "bilibili").lower()
        if only and platform not in only:
            continue
        out = DATA / f"{c['alias']}_videos.json"
        if out.exists() and not force:
            print(f"  ⏭  {c['name']:<16} 已有 {out.name},跳过(要重抓加 --force)")
            continue
        try:
            videos = await fetch_for(c)
        except Exception as e:
            print(f"  ✗ {c['name']} [{platform}]: {type(e).__name__}: {e}")
            continue
        if not videos:
            print(f"  ✗ {c['name']} [{platform}]: 没抓到视频")
            continue
        out.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")
        n_ok += 1
        hi, lo = videos[0], videos[-1]
        span = f"{(videos[-1].get('created_iso') or '?')[:10]} ~ {(videos[0].get('created_iso') or '?')[:10]}"
        print(f"  ✓ {c['name']:<16} [{platform}] {len(videos):>2}个  "
              f"播放 {lo['play'] or 0:>10,} ~ {hi['play'] or 0:>11,}  时间 {span}")
        if platform == "bilibili":
            await asyncio.sleep(2.0)   # B 站要防风控;YouTube 官方 API 不用等
    print(f"\n✅ 完成,{n_ok} 个创作者已写 data/<alias>_videos.json")


if __name__ == "__main__":
    asyncio.run(main())
