"""
viralens · enrich_bilibili.py(可选步骤)—— B 站「三连」数据补全:赞 / 硬币 / 收藏 / 分享。

UP 主投稿列表接口(vlist)只给 播放/弹幕/评论;三连要逐条视频调 view 接口,
N=40 条/人 × 节流 ≈ 半分钟/人,所以做成可选步骤,不进默认流水线:

  python enrich_bilibili.py            # 增量:只补还没有 coin 字段的视频
  python enrich_bilibili.py --force    # 全量重取(刷新三连 + 播放/评论/弹幕)

为什么值得跑:投币/收藏是 B 站独有的「真金白银认可」。三连率 =(赞+币+藏)/万播放,
比评论率更硬的内容质量信号 —— 商业数据平台的核心指标,开源工具里还没人算。
跑完后无需其他操作:scan_signals.py / 报告会自动多出「三连率 / 投币率」维度
(features.py 检测到 coin/favorite 字段就启用),export_data.py 也会把新字段带进 CSV。
"""
import asyncio
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bilibili_api import video, Credential

from runtime import DATA
from creators import CREATORS

try:
    from config_local import SESSDATA
except ImportError:
    SESSDATA = ""
try:
    from config_local import BUVID3
except ImportError:
    BUVID3 = ""

PACE = 0.6   # 每条视频之间的节流(view 接口风控比 vlist 宽松,但仍要温和)


def _cred():
    """view 接口是公开的,不带登录态也能查;有 SESSDATA 更稳,有就带上。"""
    if SESSDATA and BUVID3:
        return Credential(sessdata=SESSDATA, buvid3=BUVID3)
    if SESSDATA:
        return Credential(sessdata=SESSDATA)
    return None


async def enrich_one(v, cred, tries=3):
    """给一条视频补 stat 字段。失败重试(退避),最终失败返回 False、不动原记录。"""
    bvid = v.get("bvid")
    for attempt in range(tries):
        try:
            info = await video.Video(bvid=bvid, credential=cred).get_info()
            st = info.get("stat") or {}
            v["like"] = st.get("like")
            v["coin"] = st.get("coin")
            v["favorite"] = st.get("favorite")
            v["share"] = st.get("share")
            # 顺手刷新基础数据(view 接口的数字比抓取时新;"--" 等占位符不覆盖)
            for src, dst in (("view", "play"), ("reply", "comment"), ("danmaku", "danmaku")):
                if isinstance(st.get(src), int):
                    v[dst] = st[src]
            return True
        except Exception as e:
            if attempt < tries - 1:
                await asyncio.sleep(5 * (attempt + 1))   # 5s,10s 退避(风控/网络抖动)
                continue
            print(f"    · 失败 {bvid}: {type(e).__name__}: {e}")
            return False
    return False


async def main():
    force = "--force" in sys.argv
    cred = _cred()
    targets = [c for c in CREATORS if (c.get("platform") or "bilibili").lower() == "bilibili"]
    if not targets:
        print("creators.py 里没有 B 站创作者,无事可做")
        return

    for c in targets:
        p = DATA / f"{c['alias']}_videos.json"
        if not p.exists():
            print(f"  ✗ 缺 {p.name},先跑 fetch_multi.py")
            continue
        vids = json.loads(p.read_text(encoding="utf-8"))
        todo = [v for v in vids if v.get("bvid") and (force or v.get("coin") is None)]
        if not todo:
            print(f"  ⏭  {c['name']:<16} 三连已齐,跳过(要刷新加 --force)")
            continue
        n_ok = 0
        for i, v in enumerate(todo):
            if i:
                await asyncio.sleep(PACE)
            n_ok += await enrich_one(v, cred)
            if n_ok and n_ok % 10 == 0:                  # 边取边存,中断不丢
                p.write_text(json.dumps(vids, ensure_ascii=False, indent=2), encoding="utf-8")
        p.write_text(json.dumps(vids, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {c['name']:<16} 三连补全 {n_ok}/{len(todo)} 条")

    print("\n✅ 完成。重跑 scan_signals.py / 报告,会自动出现「三连率 / 投币率」维度")


if __name__ == "__main__":
    asyncio.run(main())
