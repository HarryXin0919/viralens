"""
viralens · scan_signals.py
「信号扫描器」—— 一次跑完所有分类/对比维度,不用手写几十个脚本。

对每位 UP 主:把视频拆成通用特征,逐个维度测「这个分类能不能把高播放和低播放分开」,
按效果(中位数倍数)排序,告诉你"什么因素真的影响你的播放"。
再做跨创作者归纳:哪些是通用杠杆(多数 UP 主同向),哪些因人而异。

可切换"被比较指标":播放/天、总播放、互动率、弹幕密度 —— 同一套维度问不同问题。
通用特征,适用于任何分区/任何 UP 主。纯元数据,零额外抓取。

跑: python scan_signals.py
输出: data/signal_scan.json + 终端排行
"""
import json
import sys
import math
import time
from pathlib import Path
from statistics import median

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from creators import CREATORS
from features import (extract, BINARY_LABELS, CAT_LABELS, NUMERIC_LABELS, METRIC_LABELS)

MIN_N = 4              # 每组至少 4 条才报告,避免小样本噪声
GEN_THRESH = 0.2       # log2 阈值:|log2|>0.2 ≈ 1.15× 才算"有方向"
NOW = time.time()


def spearman(xs, ys):
    """秩相关(无需 scipy):对 ranks 做 Pearson。返回 [-1,1] 或 None。"""
    n = len(xs)
    if n < 6:
        return None

    def rank(a):
        order = sorted(range(n), key=lambda i: a[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n))
                    * sum((ry[i] - my) ** 2 for i in range(n)))
    return num / den if den else None


def binary_effect(feats, key, metric):
    a = [f[metric] for f in feats if f.get(key) is True]
    b = [f[metric] for f in feats if f.get(key) is False]
    if len(a) < MIN_N or len(b) < MIN_N:
        return None
    ma, mb = median(a), median(b)
    if mb <= 0:
        return None
    ratio = ma / mb
    return {"n_true": len(a), "n_false": len(b),
            "med_true": round(ma, 2), "med_false": round(mb, 2),
            "ratio": round(ratio, 3), "log2": round(math.log2(ratio), 3) if ratio > 0 else 0}


def cat_effect(feats, key, metric):
    levels = {}
    for f in feats:
        if key in f:
            levels.setdefault(f[key], []).append(f[metric])
    levels = {k: v for k, v in levels.items() if len(v) >= MIN_N}
    if len(levels) < 2:
        return None
    meds = {k: median(v) for k, v in levels.items()}
    best = max(meds, key=meds.get)
    worst = min(meds, key=meds.get)
    return {"levels": {k: {"n": len(levels[k]), "med": round(meds[k], 2)} for k in levels},
            "best": best, "worst": worst,
            "spread": round(meds[best] / meds[worst], 2) if meds[worst] > 0 else None}


def arrow(ratio):
    return "↑↑" if ratio >= 2 else "↑" if ratio > 1.15 else "↓↓" if ratio <= 0.5 else "↓" if ratio < 0.87 else "≈"


def fmt_ratio(ratio):
    """ratio>1: '2.3× 更高';  ratio<1: '只有 0.4×' """
    if ratio >= 1:
        return f"{ratio:.1f}× 更高"
    return f"{ratio:.2f}× (更低)"


def scan_creator(c, metric):
    p = DATA / f"{c['alias']}_videos.json"
    if not p.exists():
        return None
    vids = json.loads(p.read_text(encoding="utf-8"))
    cov_p = DATA / f"{c['alias']}_covers.json"
    if cov_p.exists():
        covers = json.loads(cov_p.read_text(encoding="utf-8"))
        for v in vids:
            v["cover"] = covers.get(v.get("bvid"), {})
    feats = [extract(v, NOW) for v in vids]

    binary = {}
    for k in BINARY_LABELS:
        e = binary_effect(feats, k, metric)
        if e:
            binary[k] = e
    cat = {}
    for k in CAT_LABELS:
        e = cat_effect(feats, k, metric)
        if e:
            cat[k] = e
    numeric = {}
    for k in NUMERIC_LABELS:
        xs = [f[k] for f in feats if k in f]
        ys = [f[metric] for f in feats if k in f]
        rho = spearman(xs, ys)
        if rho is not None:
            numeric[k] = round(rho, 3)
    return {"creator": c["name"], "n_videos": len(vids),
            "binary": binary, "cat": cat, "numeric": numeric}


def print_creator(r):
    print("\n" + "=" * 76)
    print(f"■ {r['creator']}  ({r['n_videos']} 条)  —— 哪些因素把你的高/低播放分开")
    ranked = sorted(r["binary"].items(), key=lambda kv: -abs(kv[1]["log2"]))
    for k, e in ranked[:6]:
        print(f"   {arrow(e['ratio']):<3} {BINARY_LABELS[k]:<26} "
              f"{fmt_ratio(e['ratio']):<14} (有{e['n_true']}条 vs 无{e['n_false']}条)")
    # 时长档 / 时段
    for k, e in r["cat"].items():
        print(f"   ◆  {CAT_LABELS[k]}: 最佳「{e['best']}」 vs 最差「{e['worst']}」 差 {e['spread']}×")
    # 数值相关
    nums = [f"{NUMERIC_LABELS[k]} ρ={v:+.2f}" for k, v in r["numeric"].items() if abs(v) >= 0.2]
    if nums:
        print("   ~  相关性(强的): " + " · ".join(nums))


def generalize(results):
    """跨创作者归纳:每个二元特征,多少 UP 主同向 + 几何平均倍数。"""
    agg = {}
    for r in results:
        for k, e in r["binary"].items():
            agg.setdefault(k, []).append(e["log2"])
    rows = []
    for k, vals in agg.items():
        n = len(vals)
        pos = sum(1 for x in vals if x > GEN_THRESH)
        neg = sum(1 for x in vals if x < -GEN_THRESH)
        geo = 2 ** (sum(vals) / n)               # 几何平均倍数
        if pos >= math.ceil(0.7 * n) and pos >= 3:
            verdict, lean = "通用正向杠杆 ✅", "↑"
        elif neg >= math.ceil(0.7 * n) and neg >= 3:
            verdict, lean = "通用负向 ❌", "↓"
        else:
            verdict, lean = "因人而异 〰", "~"
        rows.append({"key": k, "n": n, "pos": pos, "neg": neg,
                     "geo_ratio": round(geo, 2), "verdict": verdict, "lean": lean})
    rows.sort(key=lambda x: -abs(math.log2(x["geo_ratio"]) if x["geo_ratio"] > 0 else 0))
    return rows


def generalize_numeric(results):
    """跨创作者归纳数值特征(相关性方向):多少 UP 主正/负相关 + 平均 ρ。
    用来判断像「封面色彩/亮度」这类是不是通用杠杆,还是因人而异/相互矛盾/普遍无信号。"""
    agg = {}
    for r in results:
        for k, rho in r["numeric"].items():
            agg.setdefault(k, []).append(rho)
    rows = []
    for k, vals in agg.items():
        n = len(vals)
        pos = sum(1 for x in vals if x >= 0.2)
        neg = sum(1 for x in vals if x <= -0.2)
        mean = sum(vals) / n
        if pos >= math.ceil(0.7 * n) and pos >= 3:
            verdict = "通用正相关 ✅"
        elif neg >= math.ceil(0.7 * n) and neg >= 3:
            verdict = "通用负相关 ❌"
        elif pos and neg:
            verdict = "相互矛盾 〰"
        elif pos + neg == 0:
            verdict = "普遍无信号 ·"
        else:
            verdict = "因人而异 〰"
        rows.append({"key": k, "n": n, "pos": pos, "neg": neg,
                     "mean_rho": round(mean, 3), "verdict": verdict})
    rows.sort(key=lambda x: -abs(x["mean_rho"]))
    return rows


def main():
    metric = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in METRIC_LABELS else "play_per_day"
    print(f"信号扫描 · 指标 = {METRIC_LABELS[metric]}   (换指标: scan_signals.py play | comment_per_10k | danmaku_per_min)")

    results = []
    for c in CREATORS:
        r = scan_creator(c, metric)
        if r:
            results.append(r)
            print_creator(r)
        else:
            print(f"  ✗ 缺 {c['alias']}_videos.json,先跑 fetch_multi.py")

    if not results:
        print("\n⚠️ 没数据"); return

    gen = generalize(results)
    print("\n" + "=" * 76)
    print(f"跨创作者归纳 · 哪些是通用杠杆,哪些因人而异  (指标={METRIC_LABELS[metric]})")
    print("=" * 76)
    print(f"{'特征':<28}{'同向':>10}{'平均倍数':>10}   判决")
    for g in gen:
        same = f"{g['pos']}↑ / {g['neg']}↓ / 共{g['n']}"
        print(f"{BINARY_LABELS[g['key']]:<28}{same:>12}{g['geo_ratio']:>8}×   {g['verdict']}")

    genn = generalize_numeric(results)
    print("\n" + "=" * 76)
    print(f"跨创作者归纳 · 数值特征的相关性方向(含封面)  (指标={METRIC_LABELS[metric]})")
    print("=" * 76)
    print(f"{'特征':<24}{'方向(|ρ|≥.2)':>16}{'平均ρ':>9}   判决")
    for g in genn:
        same = f"{g['pos']}+ / {g['neg']}- / 共{g['n']}"
        print(f"{NUMERIC_LABELS[g['key']]:<24}{same:>16}{g['mean_rho']:>+8.2f}   {g['verdict']}")

    out = DATA / "signal_scan.json"
    out.write_text(json.dumps({"metric": metric, "creators": results,
                               "generalization": gen, "generalization_numeric": genn},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写 {out.name} —— 把整段贴给我解读,或换指标再扫一遍")


if __name__ == "__main__":
    main()
