"""
viralens · 02_classify_and_stats.py
读 bidao_videos.json,自动给视频打类型标签,按多个维度算对比统计。
纯本地,零成本,零网络。

跑: python 02_classify_and_stats.py

输出:
  - data/classified.json  (每个视频加了 type / 派生指标字段)
  - 终端打印多维对比表
"""
import json
import time
from pathlib import Path
from collections import defaultdict
from statistics import median, mean

DATA = Path(__file__).parent.parent / "data"
IN = DATA / "bidao_videos.json"
OUT = DATA / "classified.json"

NOW = time.time()


def year_of(v):
    return (v.get("created_iso") or "")[:4]


def classify(v):
    """规则分类。可能有误判,跑完人工校正。"""
    title = v["title"]
    desc = v.get("description", "")
    tid = v.get("tid")
    age_days = (NOW - (v.get("created_ts") or NOW)) / 86400

    if age_days < 7:
        return "新发布(数据未成熟)"
    if tid != 201:
        return "官方活动/其他分区"
    if "×" in title:                       # 【毕导×品牌】格式
        return "商单合作"
    if "科研大赏" in desc:
        return "论文盘点(搞笑科研大赏)"
    if "消防" in desc:
        return "机构合作"
    if "打脸" in title:
        return "回应/补充"
    return "正经科普"


def fmt(n):
    return f"{n:,.0f}" if n else "-"


def main():
    videos = json.loads(IN.read_text(encoding="utf-8"))

    for v in videos:
        v["type"] = classify(v)
        play = v.get("play") or 0
        # 相对指标:每万播放的评论/弹幕数 → 反映"讨论激发力",不受粉丝量影响
        v["comment_per_10k"] = round((v.get("comment") or 0) / play * 10000, 1) if play else 0
        v["danmaku_per_10k"] = round((v.get("danmaku") or 0) / play * 10000, 1) if play else 0

    OUT.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")

    groups = defaultdict(list)
    for v in videos:
        groups[v["type"]].append(v)

    # === 维度 A:类型对比(哪种形式天花板最高) ===
    print("=" * 72)
    print("【维度 A】类型对比 — 按组内平均播放降序")
    print("=" * 72)
    order = sorted(groups.items(), key=lambda kv: -mean([x["play"] for x in kv[1]]))
    for typ, vs in order:
        plays = [x["play"] for x in vs]
        durs = [x["duration_sec"] for x in vs]
        cpm = [x["comment_per_10k"] for x in vs]
        print(f"\n■ {typ}  (n={len(vs)})")
        print(f"   播放   均值 {fmt(mean(plays))} | 中位 {fmt(median(plays))} | 范围 {fmt(min(plays))} ~ {fmt(max(plays))}")
        print(f"   时长   均值 {mean(durs)/60:.1f} 分 | 范围 {min(durs)/60:.1f} ~ {max(durs)/60:.1f} 分")
        print(f"   评论率 均值 {mean(cpm):.1f} 条/万播放")

    # === 维度 B:正经科普 2025 高低对比 ===
    print("\n" + "=" * 72)
    print("【维度 B】正经科普 · 2025年 · 高低播放对比(控制时间→粉丝量相近)")
    print("=" * 72)
    sci2025 = [v for v in videos if v["type"] == "正经科普" and year_of(v) == "2025"]
    sci2025.sort(key=lambda x: -x["play"])
    print(f"  2025 正经科普共 {len(sci2025)} 个")
    print("\n  🔴 高播放 Top 5:")
    for v in sci2025[:5]:
        print(f"     {fmt(v['play']):>11}  {v['duration_sec']/60:>4.1f}分  评{v['comment_per_10k']:>5}  {v['title'][:30]}")
    print("\n  🔵 低播放 Bottom 5:")
    for v in sci2025[-5:]:
        print(f"     {fmt(v['play']):>11}  {v['duration_sec']/60:>4.1f}分  评{v['comment_per_10k']:>5}  {v['title'][:30]}")

    # === 维度 D:时间演化 ===
    print("\n" + "=" * 72)
    print("【维度 D】正经科普 · 按年份(看涨粉 + 内容演化)")
    print("=" * 72)
    by_year = defaultdict(list)
    for v in videos:
        if v["type"] == "正经科普":
            by_year[year_of(v)].append(v["play"])
    for yr in sorted(by_year):
        ps = by_year[yr]
        print(f"   {yr}:  n={len(ps):>2}   播放中位 {fmt(median(ps)):>11}   均值 {fmt(mean(ps)):>11}")

    print("\n" + "=" * 72)
    print("✅ 已写 data/classified.json")
    print("   注:维度 C(实验型 vs 思辨型)需要字幕,等 03 脚本")
    print("   分类可能有误判,把上面结果发我,我们一起校正")
    print("=" * 72)


if __name__ == "__main__":
    main()
