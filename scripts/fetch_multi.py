"""
viralens · fetch_multi.py
抓取调度器:按 creators.py 里每个创作者的 platform 字段,派发给对应平台适配器,
统一写出 data/<alias>_videos.json(标准视频表)。任意平台 / 任意分区 / 任意创作者。

适配器:
  bilibili → fetch_bilibili.py(用 SESSDATA)
  youtube  → fetch_youtube.py (用 YOUTUBE_API_KEY)
想加新平台?照着写一个 fetch_<平台>.py,吐出同样字段,在 fetch_for() 里挂一行即可。

并发策略(效率与风控的平衡):
  - B 站:**串行 + 每人 2s 间隔** —— 有 412 风控,快了会被封一阵子,不值得。
  - YouTube:**4 路线程并发** —— 官方 API 只按日配额计费,没有每秒风控;
    并发不多花一分配额,只省墙上时间(实测 8 个频道 ~4× 提速)。
  两条线同时跑:B 站在等风控间隔时,YouTube 在并行抓。

跑: python fetch_multi.py          (默认跳过已抓过的,保护已验证数据集)
    python fetch_multi.py --force  (强制重抓)
"""
import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

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
try:
    from config_local import BUVID3        # 可选:B 站部分接口要求的 Cookie,遇 -352 再填
except ImportError:
    BUVID3 = ""

from creators import CREATORS, validate_creators

NUM_VIDEOS = 40   # 每个创作者抓最近多少个
YT_WORKERS = 4    # YouTube 并发路数(官方 API 无每秒风控;并发不多花配额,只省时间)


async def fetch_for(c):
    """按平台派发(适配器懒加载:只装了 B 站依赖也能单跑 YouTube,反之亦然)。"""
    platform = (c.get("platform") or "bilibili").lower()
    if platform == "bilibili":
        import fetch_bilibili
        return await fetch_bilibili.fetch_creator(c, SESSDATA, NUM_VIDEOS, buvid3=BUVID3)
    if platform == "youtube":
        import fetch_youtube
        return fetch_youtube.fetch_creator(c, YOUTUBE_API_KEY, NUM_VIDEOS)
    raise RuntimeError(f"未知平台 '{platform}'(目前支持 bilibili / youtube)")


def _save_result(c, platform, videos):
    """写 data/<alias>_videos.json + 打印一行摘要。返回是否成功(空结果算失败)。"""
    if not videos:
        print(f"  ✗ {c['name']} [{platform}]: 没抓到视频")
        return False
    out = DATA / f"{c['alias']}_videos.json"
    out.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")
    hi, lo = videos[0], videos[-1]               # 适配器按播放降序返回:hi=最高播放,lo=最低
    # 时间跨度要按日期算,不能拿播放排序的首尾凑(那是"最低播放的日期 ~ 最高播放的日期")
    isos = sorted(i for i in (v.get("created_iso") for v in videos) if i)
    span = f"{isos[0][:10]} ~ {isos[-1][:10]}" if isos else "?"
    print(f"  ✓ {c['name']:<16} [{platform}] {len(videos):>2}个  "
          f"播放 {lo['play'] or 0:>10,} ~ {hi['play'] or 0:>11,}  时间 {span}")
    return True


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

    todo = []
    for c in CREATORS:
        platform = (c.get("platform") or "bilibili").lower()
        if only and platform not in only:
            continue
        out = DATA / f"{c['alias']}_videos.json"
        if out.exists() and not force:
            print(f"  ⏭  {c['name']:<16} 已有 {out.name},跳过(要重抓加 --force)")
            continue
        todo.append((c, platform))

    bili = [c for c, p in todo if p == "bilibili"]
    others = [(c, p) for c, p in todo if p != "bilibili"]
    n_ok = 0

    async def run_bili_serial():
        """B 站:串行 + 间隔,防 412 风控。"""
        nonlocal n_ok
        for i, c in enumerate(bili):
            if i:
                await asyncio.sleep(2.0)
            try:
                videos = await fetch_for(c)
            except Exception as e:
                print(f"  ✗ {c['name']} [bilibili]: {type(e).__name__}: {e}")
                continue
            n_ok += _save_result(c, "bilibili", videos)

    async def run_others_parallel():
        """YouTube(及未来的无风控平台):线程池并发;按清单顺序收割,输出顺序稳定。"""
        nonlocal n_ok
        if not others:
            return
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=min(YT_WORKERS, len(others))) as ex:

            def work(c, platform):
                if platform == "youtube":
                    import fetch_youtube
                    return fetch_youtube.fetch_creator(c, YOUTUBE_API_KEY, NUM_VIDEOS)
                raise RuntimeError(f"未知平台 '{platform}'(目前支持 bilibili / youtube)")

            tasks = [loop.run_in_executor(ex, work, c, p) for c, p in others]
            for (c, platform), t in zip(others, tasks):
                try:
                    videos = await t
                except Exception as e:
                    print(f"  ✗ {c['name']} [{platform}]: {type(e).__name__}: {e}")
                    continue
                n_ok += _save_result(c, platform, videos)

    # 两条线同时跑:B 站在等风控间隔时,YouTube 在并行抓
    await asyncio.gather(run_bili_serial(), run_others_parallel())
    print(f"\n✅ 完成,{n_ok} 个创作者已写 data/<alias>_videos.json")


if __name__ == "__main__":
    asyncio.run(main())
