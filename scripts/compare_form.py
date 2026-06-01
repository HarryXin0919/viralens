"""
viralens · compare_form.py
跨创作者验证"守住核心形式":偏离主线的视频(商单/vlog/访谈/音乐/直播)
是否集中在低播放端,核心形式视频是否占据高播放端。
纯元数据,零抓取,零成本。

输出: data/cross_creator_form.json + 终端 top5/bottom5 对照
"""
import json
import sys
from pathlib import Path
from statistics import median

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from creators import CREATORS

# 偏离核心形式的粗标记(宁紧勿松,误判靠人眼复核打印的标题)
OFF_MARKERS = {
    "商单": ["×", "合作", "赞助", "广告", "推广"],
    "vlog": ["vlog"],
    "直播": ["直播回放", "录播", "直播录"],
    "访谈": ["专访", "对谈", "采访", "对话"],
    "音乐": ["翻唱", "弹唱", "音乐区"],
    # 英文(给 YouTube 等英文标题用;只用多字符安全词,绝不误伤中文标题)
    # 不包含 "livestream"/"live stream":有些 Entertainment 创作者把 "secretly in X livestream"
    # 当招牌挑战在用,误伤太大。真正的直播录像偏题标题通常含 "(Live)"/"VOD"/"Live Recording"。
    "EN": ["sponsored", "#ad", "(ad)", "[ad]", "paid promotion",
           "podcast", "q&a", "interview"],
}


def off_tag(v):
    # YouTube description 几乎必含 brand list / hashtag(podcast/interview 等),全军 false positive;
    # 只扫 title。B 站 description 短而精,继续扫 title + description。
    if (v.get("platform") or "bilibili") == "youtube":
        s = (v.get("title", "") or "").lower()
    else:
        s = (v.get("title", "") + " " + v.get("description", "")).lower()
    for label, ms in OFF_MARKERS.items():
        if any(m.lower() in s for m in ms):
            return label
    return ""


def fmt(n):
    return f"{n:,.0f}" if n else "-"


def main():
    rows = []
    for c in CREATORS:
        p = DATA / f"{c['alias']}_videos.json"
        if not p.exists():
            print(f"  ✗ 缺 {p.name}")
            continue
        vids = json.loads(p.read_text(encoding="utf-8"))
        for v in vids:
            v["off"] = off_tag(v)
        vids.sort(key=lambda x: -(x["play"] or 0))
        top5, bot5 = vids[:5], vids[-5:]
        top5_med = median([v["play"] for v in top5])
        bot5_med = median([v["play"] for v in bot5])
        ratio = top5_med / bot5_med if bot5_med else float("inf")

        print("\n" + "=" * 74)
        print(f"■ {c['name']}   top5中位 {fmt(top5_med)} / bot5中位 {fmt(bot5_med)}  = {ratio:.0f}×")
        print("  🔴 TOP5(爆款):")
        for v in top5:
            tag = f"[{v['off']}]" if v["off"] else ""
            print(f"     {fmt(v['play']):>12}  {tag}{v['title'][:34]}")
        print("  🔵 BOTTOM5(翻车):")
        for v in bot5:
            tag = f"[{v['off']}]" if v["off"] else ""
            print(f"     {fmt(v['play']):>12}  {tag}{v['title'][:34]}")

        rows.append({
            "creator": c["name"],
            "top5_med": top5_med, "bot5_med": bot5_med, "ratio": round(ratio, 1),
            "off_in_top5": sum(1 for v in top5 if v["off"]),
            "off_in_bot5": sum(1 for v in bot5 if v["off"]),
            "top5": [{"play": v["play"], "off": v["off"], "title": v["title"]} for v in top5],
            "bot5": [{"play": v["play"], "off": v["off"], "title": v["title"]} for v in bot5],
        })

    (DATA / "cross_creator_form.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 74)
    print("汇总 · 头尾播放差 + 偏题视频落点")
    print("=" * 74)
    print(f"{'创作者':<13}{'头尾倍数':>9}{'偏题数@top5':>13}{'偏题数@bot5':>13}")
    for r in rows:
        print(f"{r['creator']:<13}{r['ratio']:>8.0f}×{r['off_in_top5']:>13}{r['off_in_bot5']:>13}")
    print("\n✅ 已写 data/cross_creator_form.json — 把整段贴给我解读")


if __name__ == "__main__":
    main()
