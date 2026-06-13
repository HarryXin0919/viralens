"""
viralens · creator_profile.py
创作者画像 —— 两件纯元数据、零成本的事:

① 同分区基准对比:你 vs 同分区其他人。
   - 体量(播放中位数)= 受众规模,只反映你多大,**不是**可调杠杆,只用来定位"头部/腰部"。
   - 招牌命中率 / 典型时长 / 发布节奏 / 互动率 / 弹幕密度 = 可对比的结构性选择。

② 时间趋势 / 疲态检测:你的播放在涨还是在跌?

—— 方法学修正(重要,别踩坑)——
play_per_day 对新视频系统性偏高(分母 days 小,而首发播放高峰已计入),
直接拿它判断趋势会出现假性"上升"。反过来,总播放对老视频偏高(长尾多积累了几年)。
两害相权:对「成熟视频」(发布满 30 天、播放已基本稳定)用**总播放**做趋势,
长尾偏差远小于 play_per_day 的新视频偏差。
前提:B 站绝大多数播放在前两周累积,30 天后总播放近似封顶。残留长尾偏差在输出里标注。

跑: python creator_profile.py
输出: data/creator_profile.json + 终端
"""
import json
import sys
import time
from statistics import median

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA           # 源码=仓库/data,打包成 app 时=用户数据目录
from creators import CREATORS
from features import extract
from scan_signals import spearman      # 复用秩相关,避免重复实现
from schema import fmt_play            # 播放量格式化收口在 schema.py(旧本地版遇 None 会崩)

NOW = time.time()
MATURE_DAYS = 30        # 发布满 30 天才算"播放稳定",用于趋势
MIN_TREND_N = 8         # 成熟视频少于 8 条不做趋势(噪声太大)


def safe_div(a, b):
    return a / b if b else 0


def creator_stats(vids):
    """一位 UP 主的结构性画像(可跨人对比的量)。"""
    if not vids:
        # 空数据集:返回零化但键齐全的画像,别让 len(feats)/len(vids) 除零崩掉整条 --report
        return {
            "play_med": 0,
            "in_format_rate": 0,
            "dur_med": 0,
            "gap_days": None,
            "comment_per_10k": 0,
            "danmaku_per_min": 0,
        }
    feats = [extract(v, NOW) for v in vids]
    plays = [f["play"] for f in feats]
    durs = [f["duration_sec"] for f in feats if f["duration_sec"] > 0]
    c10k = [f["comment_per_10k"] for f in feats if f["play"] > 0]
    dpm = [f["danmaku_per_min"] for f in feats if f["duration_sec"] > 0]
    in_format = sum(1 for f in feats if not f["off_format"]) / len(feats)

    # 发布节奏:相邻两更的间隔天数中位数
    ts = sorted(v.get("created_ts") or 0 for v in vids)
    ts = [t for t in ts if t > 0]
    gaps = [(ts[i + 1] - ts[i]) / 86400 for i in range(len(ts) - 1)] if len(ts) > 1 else []
    return {
        "play_med": round(median(plays)) if plays else 0,
        "in_format_rate": round(in_format, 3),
        "dur_med": round(median(durs)) if durs else 0,
        "gap_days": round(median(gaps), 1) if gaps else None,
        "comment_per_10k": round(median(c10k), 2) if c10k else 0,
        "danmaku_per_min": round(median(dpm), 2) if dpm else 0,
    }


def trend(vids):
    """疲态检测:只用成熟视频(>=30天)的总播放,Spearman(时间,播放)+ 近期 vs 早期 中位数。"""
    mature = [v for v in vids
              if v.get("created_ts") and (NOW - v["created_ts"]) / 86400 >= MATURE_DAYS]
    mature.sort(key=lambda v: v["created_ts"])
    n = len(mature)
    if n < MIN_TREND_N:
        return {"n_mature": n, "verdict": "样本不足", "note": f"成熟视频仅 {n} 条"}

    tss = [v["created_ts"] for v in mature]
    plays = [v.get("play") or 0 for v in mature]
    rho = spearman(tss, plays)               # +1 越新越火,-1 越新越凉

    mid = n // 2
    early_med = median(plays[:mid])
    recent_med = median(plays[mid:])
    ratio = safe_div(recent_med, early_med)

    # 更新节奏的变化:早期 vs 近期 相邻间隔中位数
    gaps = [(tss[i + 1] - tss[i]) / 86400 for i in range(n - 1)]
    gmid = len(gaps) // 2
    gap_early = round(median(gaps[:gmid]), 1) if gaps[:gmid] else None
    gap_recent = round(median(gaps[gmid:]), 1) if gaps[gmid:] else None

    rho = rho if rho is not None else 0
    if rho >= 0.3 and ratio >= 1.2:
        verdict = "上升 📈"
    elif rho <= -0.3 and ratio <= 0.83:
        verdict = "下滑 📉(疲态信号)"
    else:
        verdict = "平稳 ➡️"

    cad = ""
    if gap_early and gap_recent:
        if gap_recent > gap_early * 1.3:
            cad = f"更新变慢(早期 {gap_early}天/更 → 近期 {gap_recent}天/更)"
        elif gap_recent < gap_early * 0.77:
            cad = f"更新提速(早期 {gap_early}天/更 → 近期 {gap_recent}天/更)"
        else:
            cad = f"节奏稳定(约 {gap_recent}天/更)"

    return {"n_mature": n, "rho": round(rho, 3),
            "early_med": round(early_med), "recent_med": round(recent_med),
            "ratio": round(ratio, 2), "verdict": verdict,
            "gap_early": gap_early, "gap_recent": gap_recent, "cadence": cad}


def fmt_dur(sec):
    return f"{sec//60}分{sec%60:02d}秒"


def vs(ratio):
    """与分区中位数的倍数 → 箭头描述。"""
    if ratio is None:
        return "—"
    if ratio >= 1.5:
        return f"{ratio:.1f}× 🔼"
    if ratio >= 1.1:
        return f"{ratio:.1f}× ↑"
    if ratio <= 0.67:
        s = f"{ratio:.2f}" if ratio < 0.1 else f"{ratio:.1f}"
        return f"{s}× 🔽"
    if ratio <= 0.9:
        return f"{ratio:.1f}× ↓"
    return f"{ratio:.1f}× ≈"


def main():
    profiles = []
    for c in CREATORS:
        p = DATA / f"{c['alias']}_videos.json"
        if not p.exists():
            print(f"  ✗ 缺 {c['alias']}_videos.json")
            continue
        vids = json.loads(p.read_text(encoding="utf-8"))
        profiles.append({"name": c["name"], "alias": c["alias"], "zone": c.get("zone", "?"),
                         "stat": creator_stats(vids), "trend": trend(vids)})

    if not profiles:
        print("⚠️ 没数据,先跑 fetch_multi.py"); return

    # —— 分区基准 = 各 UP 主该指标的中位数(“典型创作者”)——
    keys = ["play_med", "in_format_rate", "dur_med", "gap_days", "comment_per_10k", "danmaku_per_min"]
    # 按分区分组:每区各算各的基准(跨区比体量无意义,游戏区天然比生活区播放高)
    zones = {}
    for pr in profiles:
        zones.setdefault(pr["zone"], []).append(pr)

    out_zones = {}
    print("=" * 78)
    print("① 同分区基准对比 · 体量只定位头部/腰部(受众规模,非杠杆);招牌率/时长/互动才是结构性选择")
    for zone, prs in zones.items():
        bench = {}
        for k in keys:
            vals = [pr["stat"][k] for pr in prs if pr["stat"][k] is not None]
            bench[k] = round(median(vals), 2) if vals else None
        out_zones[zone] = {"benchmark": bench, "creators": prs}

        print("\n" + "-" * 78)
        print(f"【{zone}】{len(prs)} 位 · 典型: 体量 {fmt_play(bench['play_med'])} · "
              f"招牌率 {bench['in_format_rate']*100:.0f}% · 时长 {fmt_dur(int(bench['dur_med']))} · "
              f"{bench['gap_days']}天/更 · 互动 {bench['comment_per_10k']} · 弹幕 {bench['danmaku_per_min']}/分")
        print(f"{'UP主':<16}{'体量':>10}{'招牌率':>9}{'时长':>9}{'更新':>9}{'互动率':>9}{'弹幕':>8}")
        for pr in prs:
            s = pr["stat"]
            print(f"{pr['name'][:14]:<16}"
                  f"{fmt_play(s['play_med']):>10}"
                  f"{s['in_format_rate']*100:>7.0f}%"
                  f"{fmt_dur(s['dur_med']):>11}"
                  f"{(str(s['gap_days'])+'天'):>9}"
                  f"{s['comment_per_10k']:>9}"
                  f"{s['danmaku_per_min']:>8}")
        for pr in prs:
            s = pr["stat"]
            print(f"   {pr['name'][:14]:<15} "
                  f"体量 {vs(safe_div(s['play_med'], bench['play_med']))} · "
                  f"招牌 {vs(safe_div(s['in_format_rate'], bench['in_format_rate']))} · "
                  f"时长 {vs(safe_div(s['dur_med'], bench['dur_med']))} · "
                  f"互动 {vs(safe_div(s['comment_per_10k'], bench['comment_per_10k']))}")

    print("\n" + "=" * 78)
    print("② 时间趋势 / 疲态检测 · 只用成熟视频(发布满30天、播放基本封顶)的总播放")
    print("   (play_per_day 会让新视频假性偏高 → 趋势必须用总播放;残留长尾偏差已知)")
    for zone, prs in zones.items():
        print("-" * 78 + f"\n【{zone}】")
        for pr in prs:
            t = pr["trend"]
            if t.get("verdict") == "样本不足":
                print(f"   {pr['name'][:14]:<15} {t['note']}")
                continue
            print(f"   {pr['name'][:14]:<15} {t['verdict']:<14} "
                  f"近期/早期 {t['ratio']}× (早 {fmt_play(t['early_med'])} → 近 {fmt_play(t['recent_med'])}) "
                  f"ρ={t['rho']:+.2f}  [{t['n_mature']}条]")
            if t.get("cadence"):
                print(f"   {'':<15} └ {t['cadence']}")

    out = DATA / "creator_profile.json"
    out.write_text(json.dumps({"zones": out_zones}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写 {out.name}")


if __name__ == "__main__":
    main()
