"""
viralens · compare_form.py
跨创作者验证"守住核心形式":偏离主线的视频(商单/vlog/访谈/音乐/直播)
是否集中在低播放端,核心形式视频是否占据高播放端。
纯元数据,零抓取,零成本。

输出: data/cross_creator_form.json + 终端 top5/bottom5 对照
"""
import json
import sys
from statistics import median

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from creators import CREATORS
import features

# 偏离核心形式的关键词 —— 单一数据源在 shared_markers.py(对比报告用保守口径版)。
from shared_markers import OFF_MARKERS_COMPARE as OFF_MARKERS


def off_tag(v):
    # YouTube description 几乎必含 brand list / hashtag(podcast/interview 等),全军 false positive;
    # 只扫 title。B 站 description 短而精,继续扫 title + description。
    # 匹配循环本身复用 features.off_tag,只是换成保守口径的标记表。
    desc = "" if (v.get("platform") or "bilibili") == "youtube" else (v.get("description") or "")
    return features.off_tag(v.get("title") or "", desc, OFF_MARKERS)


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
        if not vids:
            print(f"  ✗ {p.name} 是空的,跳过")
            continue
        for v in vids:
            v["off"] = off_tag(v)
        # 导入的数据可能缺 play/title 字段或为 null —— 全部走 .get + 兜底,别在分析里崩
        vids.sort(key=lambda x: -(x.get("play") or 0))
        top5, bot5 = vids[:5], vids[-5:]
        top5_med = median([v.get("play") or 0 for v in top5])
        bot5_med = median([v.get("play") or 0 for v in bot5])
        if not bot5_med:
            # 尾部播放全是 0/缺失:头尾倍数没意义,而且 Infinity 进不了 JSON
            print(f"  ✗ {c['name']} 尾部播放全是 0/缺失,头尾对比无意义,跳过")
            continue
        ratio = top5_med / bot5_med

        print("\n" + "=" * 74)
        print(f"■ {c['name']}   top5中位 {fmt(top5_med)} / bot5中位 {fmt(bot5_med)}  = {ratio:.0f}×")
        print("  🔴 TOP5(爆款):")
        for v in top5:
            tag = f"[{v['off']}]" if v["off"] else ""
            print(f"     {fmt(v.get('play')):>12}  {tag}{(v.get('title') or '')[:34]}")
        print("  🔵 BOTTOM5(翻车):")
        for v in bot5:
            tag = f"[{v['off']}]" if v["off"] else ""
            print(f"     {fmt(v.get('play')):>12}  {tag}{(v.get('title') or '')[:34]}")

        rows.append({
            "creator": c["name"],
            "top5_med": top5_med, "bot5_med": bot5_med, "ratio": round(ratio, 1),
            "off_in_top5": sum(1 for v in top5 if v["off"]),
            "off_in_bot5": sum(1 for v in bot5 if v["off"]),
            "top5": [{"play": v.get("play"), "off": v["off"], "title": v.get("title") or ""} for v in top5],
            "bot5": [{"play": v.get("play"), "off": v["off"], "title": v.get("title") or ""} for v in bot5],
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
