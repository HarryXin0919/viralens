"""
viralens · diagnose.py —— 单条视频的「个性化诊断大脑」。

给定一条视频(创作者 alias + 视频 id),把它拆成几个维度逐项打分,
每项给出:值 / 参照 / 等级(good 好 · ok 一般 · warn 要改)/ 为什么 / 怎么改,
全部中英双语。供 app.py 的 /api/diag 调用;也能命令行单测:

    python diagnose.py                 # 列个例子
    python diagnose.py bidao BV1gcfWYqEsf
    python diagnose.py mrbeast <vid>

核心思路:不泛泛而谈。每条视频都跟「这个创作者自己的爆款」对照 ——
你自己的高播放视频封面平均饱和度多少?这条够不够?差在哪?该怎么调?

只读本地已抓好的数据,零网络、零下载。开头镜头 / 配乐 两维属「视频下载层」,
由 analyze_video.py(B 期)单独补,这里先在 pending 里占位。
"""
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA = Path(__file__).parent.parent / "data"

# —— 懒加载 + 缓存:同一进程里只读一次盘 ——
_CACHE = {}


def _load(name):
    if name not in _CACHE:
        p = DATA / name
        try:
            _CACHE[name] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _CACHE[name] = None
    return _CACHE[name]


def invalidate():
    """清空缓存:用户重抓数据后,下次诊断重新读盘拿最新。"""
    _CACHE.clear()


# ————————————————————————— 数据访问 —————————————————————————
def _all_videos():
    return _load("all_videos.json") or []


def creator_videos(alias):
    """这个创作者的全部视频(按播放从高到低)。"""
    vs = [v for v in _all_videos() if v.get("alias") == alias]
    vs.sort(key=lambda v: v.get("play") or 0, reverse=True)
    return vs


def find_video(alias, vid):
    for v in _all_videos():
        if v.get("alias") == alias and (v.get("vid") == vid or v.get("bvid") == vid):
            return v
    return None


def _covers(alias):
    return _load(f"{alias}_covers.json") or {}


def _cover_of(alias, v):
    cov = _covers(alias)
    return cov.get(v.get("vid") or "") or cov.get(v.get("bvid") or "") or None


def _profile_index():
    """alias -> {zone, stat, trend, benchmark}。"""
    if "_pidx" in _CACHE:
        return _CACHE["_pidx"]
    idx = {}
    prof = _load("creator_profile.json") or {}
    for zname, z in (prof.get("zones") or {}).items():
        bench = z.get("benchmark") or {}
        for c in z.get("creators") or []:
            idx[c.get("alias")] = {
                "zone": zname, "name": c.get("name"),
                "stat": c.get("stat") or {}, "trend": c.get("trend") or {},
                "benchmark": bench,
            }
    _CACHE["_pidx"] = idx
    return idx


def _subtitle_of(vid):
    arr = _load("subtitle_features.json") or []
    for r in arr:
        if r.get("bvid") == vid:
            return r
    return None


# ————————————————————————— 小工具 —————————————————————————
def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    n = len(xs)
    if not n:
        return None
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2


def zh_num(n):
    n = n or 0
    if n >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return f"{int(n)}"


def en_num(n):
    n = n or 0
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{int(n)}"


def _fmt_dur(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


def _worst(levels):
    """一组等级里取最差的当总评。"""
    if "warn" in levels:
        return "warn"
    if "ok" in levels:
        return "ok"
    return "good"


# ————————————————————————— 维度:封面 —————————————————————————
def dim_cover(alias, v):
    me = _cover_of(alias, v)
    label = {"zh": "封面", "en": "Cover"}
    if not me:
        return {"key": "cover", "label": label, "level": "na",
                "headline": {"zh": "这条没有封面数据(先在『抓取并分析』里下封面)。",
                             "en": "No cover data for this video yet."},
                "metrics": [], "advice": None}

    # 这个创作者自己的「爆款」封面长什么样:按播放取前 1/3
    vids = creator_videos(alias)
    n_hit = max(3, len(vids) // 3)
    hits = vids[:n_hit]
    cov = _covers(alias)

    def hit_med(metric):
        xs = []
        for h in hits:
            c = cov.get(h.get("vid") or "") or cov.get(h.get("bvid") or "")
            if c and c.get(metric) is not None:
                xs.append(c[metric])
        return _median(xs)

    metrics = []
    levels = []
    # 三个「越高越抓眼」的指标:跟自己的爆款比
    for key, name_zh, name_en, adv_zh, adv_en in [
        ("saturation", "饱和度", "Saturation", "调高饱和度,颜色更跳、更抓眼", "boost saturation for a punchier thumbnail"),
        ("contrast", "对比度", "Contrast", "拉高对比,主体和背景分得更开", "raise contrast to separate subject from background"),
        ("colorfulness", "色彩丰富度", "Colorfulness", "用更鲜明的配色,别太单调", "use a richer, more varied palette"),
    ]:
        val = me.get(key)
        ref = hit_med(key)
        if val is None:
            continue
        if ref is None:
            lvl = "ok"
        elif val >= ref * 0.92:
            lvl = "good"
        elif val >= ref * 0.75:
            lvl = "ok"
        else:
            lvl = "warn"
        levels.append(lvl)
        refzh = f"你爆款均值 {ref:.0f}" if ref is not None else "无对照"
        refen = f"your hits avg {ref:.0f}" if ref is not None else "no ref"
        metrics.append({
            "name": {"zh": name_zh, "en": name_en},
            "value": f"{val:.0f}", "ref": {"zh": refzh, "en": refen}, "level": lvl,
            "advice": ({"zh": adv_zh, "en": adv_en} if lvl == "warn" else None),
        })

    # 亮度:绝对范围更直观(太暗看不清,过曝发白)
    b = me.get("brightness")
    if b is not None:
        if b < 60:
            lvl, why_zh, why_en = "warn", "偏暗,缩略图里容易糊", "too dark, gets muddy as a thumbnail"
        elif b > 205:
            lvl, why_zh, why_en = "warn", "过曝发白,细节丢失", "blown out, losing detail"
        else:
            lvl, why_zh, why_en = "good", "亮度适中", "well exposed"
        levels.append(lvl)
        metrics.append({
            "name": {"zh": "亮度", "en": "Brightness"},
            "value": f"{b:.0f}", "ref": {"zh": "理想 60–205", "en": "ideal 60–205"},
            "level": lvl,
            "advice": ({"zh": why_zh, "en": why_en} if lvl == "warn" else None),
        })

    level = _worst(levels)
    nbad = sum(1 for m in metrics if m["level"] == "warn")
    if level == "good":
        head = {"zh": "封面跟你的爆款一个水准 —— 够抓眼。",
                "en": "This cover matches your hit-level thumbnails — eye-catching."}
        adv = None
    else:
        worst_names_zh = "、".join(m["name"]["zh"] for m in metrics if m["level"] == "warn")
        worst_names_en = ", ".join(m["name"]["en"] for m in metrics if m["level"] == "warn")
        head = {"zh": f"封面有 {nbad} 项不如你自己的爆款,主要差在{worst_names_zh}。",
                "en": f"{nbad} cover metric(s) lag your own hits — mainly {worst_names_en}."}
        adv = {"zh": "封面是点击率的第一道关。对照你播放最高那几条的封面,把上面标红的指标往上调。",
               "en": "The thumbnail is the first gate to clicks. Compare with your top-played covers and lift the flagged metrics."}
    return {"key": "cover", "label": label, "level": level,
            "headline": head, "metrics": metrics, "advice": adv}


# ————————————————————————— 维度:标题 —————————————————————————
_2ND = re.compile(r"你|您|your\b|you\b", re.I)
_HOOK_ZH = ["最", "吗", "?", "?", "为什么", "怎么", "竟然", "震惊", "原来",
            "居然", "揭秘", "真相", "千万", "如何", "！", "!"]
_HOOK_EN = ["how", "why", "secret", "never", "stop", "best", "worst",
            "most", "challenge", " vs", "$", "?", "!"]


def dim_title(alias, v):
    label = {"zh": "标题", "en": "Title"}
    title = v.get("title") or ""
    tlen = len(title)
    vids = creator_videos(alias)
    n_hit = max(3, len(vids) // 3)
    hit_len = _median([len(h.get("title") or "") for h in vids[:n_hit]]) or tlen

    metrics, levels = [], []
    # 长度:跟自己爆款比
    if hit_len and (0.7 * hit_len <= tlen <= 1.4 * hit_len):
        lvl = "good"
    elif hit_len and tlen > 1.4 * hit_len:
        lvl = "ok"
    else:
        lvl = "ok"
    levels.append(lvl)
    metrics.append({"name": {"zh": "长度", "en": "Length"},
                    "value": f"{tlen}", "ref": {"zh": f"你爆款约 {hit_len:.0f} 字", "en": f"your hits ~{hit_len:.0f} chars"},
                    "level": lvl,
                    "advice": ({"zh": "比你爆款标题长不少,信息可能太密,试着砍到一个钩子", "en": "longer than your hits — trim to a single hook"} if tlen > 1.4 * (hit_len or tlen) else None)})

    # 第二人称(报告里验证过:跟「你」对话更拉参与)
    has2 = bool(_2ND.search(title))
    lvl2 = "good" if has2 else "ok"
    levels.append(lvl2)
    metrics.append({"name": {"zh": "第二人称「你」", "en": "2nd person (you)"},
                    "value": {"zh": "有", "en": "yes"} if has2 else {"zh": "无", "en": "no"},
                    "ref": {"zh": "爆款常用", "en": "common in hits"}, "level": lvl2,
                    "advice": (None if has2 else {"zh": "试着把标题对着观众说『你』—— 同题材里更拉参与", "en": "address the viewer as ‘you’ — lifts engagement in this niche"})})

    # 点开信号(跨分区中性):悬念词 / 数字 / 书名号·括号,任一即可。没有也只是「平」,不算错 —
    # 不同分区习惯差很多(美食/生活的爆款标题常常一个悬念词都没有),所以最多给 ok,不 warn。
    low = title.lower()
    nh = sum(1 for h in _HOOK_ZH if h in title) + sum(1 for h in _HOOK_EN if h in low)
    grab = nh > 0 or bool(re.search(r"\d", title)) or bool(re.search(r"[《【\[（(]", title))
    lvl3 = "good" if grab else "ok"
    levels.append(lvl3)
    metrics.append({"name": {"zh": "点开信号", "en": "Click signal"},
                    "value": {"zh": "有", "en": "yes"} if grab else {"zh": "弱", "en": "weak"},
                    "ref": {"zh": "悬念词/数字/作品名 任一", "en": "hook / number / title — any"}, "level": lvl3,
                    "advice": (None if grab else {"zh": "标题较朴素 —— 按你的赛道挑:科普加悬念、作品类点名字、生活类点情绪", "en": "fairly plain — by niche: add a hook (explainer), name the work (music/film), or the emotion (vlog)"})})

    level = _worst(levels)
    head = ({"zh": "标题该有的钩子都在。", "en": "Title has the hooks it needs."}
            if level == "good" else
            {"zh": "标题还能更勾人 —— 看下面标红项。", "en": "Title could pull harder — see flagged items."})
    return {"key": "title", "label": label, "level": level,
            "headline": head, "metrics": metrics, "advice": None}


# ———————————————————————— 维度:互动表现 ————————————————————————
def dim_engagement(alias, v):
    label = {"zh": "互动表现", "en": "Engagement"}
    pidx = _profile_index().get(alias, {})
    stat = pidx.get("stat", {})
    bench = pidx.get("benchmark", {})
    play = v.get("play") or 0
    like = v.get("like") or 0
    comment = v.get("comment") or 0
    pmed = stat.get("play_med") or 0

    metrics, levels = [], []
    # 播放 vs 这个创作者自己的中位数
    if pmed:
        ratio = play / pmed
        if ratio >= 1.5:
            lvl, why_zh, why_en = "good", f"是你中位数的 {ratio:.1f} 倍 —— 爆款", f"{ratio:.1f}× your median — a hit"
        elif ratio >= 0.7:
            lvl, why_zh, why_en = "ok", f"约等于你的常规水平({ratio:.1f}×)", f"about your usual level ({ratio:.1f}×)"
        else:
            lvl, why_zh, why_en = "warn", f"只有你中位数的 {ratio:.1f} 倍 —— 偏冷", f"only {ratio:.1f}× your median — underperformed"
        levels.append(lvl)
        metrics.append({"name": {"zh": "播放", "en": "Views"},
                        "value": {"zh": zh_num(play), "en": en_num(play)},
                        "ref": {"zh": f"你中位 {zh_num(pmed)}", "en": f"your median {en_num(pmed)}"},
                        "level": lvl, "advice": None, "why": {"zh": why_zh, "en": why_en}})

    # 点赞率(B 站抓取没带点赞数 → like 为空时跳过,不冤枉它)
    if play and like:
        lr = like / play * 100
        # 实测 YouTube 点赞率中位约 2%,旧阈值(<2%=warn)会冤枉一半正常视频 → 下调
        lvl = "good" if lr >= 4.5 else "ok" if lr >= 1.5 else "warn"
        levels.append(lvl)
        metrics.append({"name": {"zh": "点赞率", "en": "Like rate"},
                        "value": f"{lr:.1f}%", "ref": {"zh": "≥4.5% 优 · 中位约 2%", "en": "≥4.5% strong · median ~2%"}, "level": lvl,
                        "advice": ({"zh": "点赞率低,通常是内容『有用但没爽点』,结尾给个明确的赞引导或情绪高点", "en": "low likes often mean ‘useful but no payoff’ — add a clear CTA or emotional peak"} if lvl == "warn" else None)})

    # 评论热度 vs 分区基准
    zbench = bench.get("comment_per_10k")
    if play and zbench:
        cp = comment / play * 10000
        lvl = "good" if cp >= zbench else "ok" if cp >= zbench * 0.6 else "warn"
        levels.append(lvl)
        metrics.append({"name": {"zh": "评论热度", "en": "Comments"},
                        "value": {"zh": f"每万播放 {cp:.1f} 条", "en": f"{cp:.1f}/10k views"},
                        "ref": {"zh": f"分区基准 {zbench:.1f}", "en": f"zone bench {zbench:.1f}"}, "level": lvl,
                        "advice": ({"zh": "评论比同区少,说明没留下『可讨论的话题』—— 抛个开放问题或争议点", "en": "fewer comments than your zone — leave an open question or hot take"} if lvl == "warn" else None)})

    level = _worst(levels) if levels else "na"
    head = ({"zh": "这条的数据表现高于你的常态。", "en": "This one beats your baseline."}
            if level == "good" else
            {"zh": "互动数据有短板 —— 看下面哪一项拖后腿。", "en": "Engagement has a weak spot — see which metric lags."}
            if level == "warn" else
            {"zh": "互动属常规水平。", "en": "Engagement is around normal."})
    return {"key": "engagement", "label": label, "level": level,
            "headline": head, "metrics": metrics, "advice": None}


# ———————————————————————— 维度:时长 ————————————————————————
def dim_duration(alias, v):
    label = {"zh": "时长", "en": "Duration"}
    pidx = _profile_index().get(alias, {})
    bench = pidx.get("benchmark", {})
    stat = pidx.get("stat", {})
    dur = v.get("duration_sec") or 0
    zmed = bench.get("dur_med") or stat.get("dur_med")
    metrics = []
    if not zmed:
        return {"key": "duration", "label": label, "level": "na",
                "headline": {"zh": "缺分区时长基准。", "en": "No zone duration benchmark."},
                "metrics": [], "advice": None}
    ratio = dur / zmed
    if ratio > 1.4:
        lvl, why_zh, why_en = "warn", "明显长于同区,完播率容易被拖累", "much longer than your zone — completion may suffer"
    elif ratio < 0.55:
        lvl, why_zh, why_en = "ok", "比同区短不少(短的不一定差,看节奏)", "shorter than your zone (not always bad)"
    else:
        lvl, why_zh, why_en = "good", "时长落在同区舒适区", "right in your zone's sweet spot"
    metrics.append({"name": {"zh": "本条时长", "en": "This video"},
                    "value": _fmt_dur(dur), "ref": {"zh": f"分区中位 {_fmt_dur(zmed)}", "en": f"zone median {_fmt_dur(zmed)}"},
                    "level": lvl, "advice": None})
    return {"key": "duration", "label": label, "level": lvl,
            "headline": {"zh": why_zh, "en": why_en}, "metrics": metrics,
            "advice": ({"zh": "太长的片子,要么砍冗余、要么前 30 秒就把最大爽点提上来。", "en": "If it runs long, cut filler or front-load the payoff in the first 30s."} if lvl == "warn" else None)}


# ———————————————————————— 维度:字幕(有才显示) ————————————————————————
def dim_subtitle(alias, v):
    sub = _subtitle_of(v.get("vid") or v.get("bvid") or "")
    if not sub:
        return None
    label = {"zh": "字幕/口播", "en": "Script"}
    metrics, levels = [], []
    spd = sub.get("speed_cpm")
    if spd:
        lvl = "good" if 220 <= spd <= 320 else "ok"
        levels.append(lvl)
        metrics.append({"name": {"zh": "语速", "en": "Pace"},
                        "value": {"zh": f"{spd} 字/分", "en": f"{spd} cpm"},
                        "ref": {"zh": "220–320 舒适", "en": "220–320 comfy"}, "level": lvl, "advice": None})
    hook = sub.get("hook_open")
    if hook is not None:
        lvl = "good" if hook else "ok"      # 「开场钩子」是口播/科普类的讲究,不对所有分区硬扣分
        levels.append(lvl)
        metrics.append({"name": {"zh": "开场钩子(口播类)", "en": "Opening hook (talk)"},
                        "value": {"zh": "有", "en": "yes"} if hook else {"zh": "无", "en": "no"},
                        "ref": {"zh": "口播/科普类前几句要抓人", "en": "talk/explainer: grab early"}, "level": lvl,
                        "advice": (None if hook else {"zh": "若是口播/科普类:前 3 句可抛个冲突/悬念/承诺(音乐/美食类不必)", "en": "if talk/explainer: open with conflict/curiosity/a promise (not needed for music/food)"})})
    if not metrics:
        return None
    level = _worst(levels)
    return {"key": "subtitle", "label": label, "level": level,
            "headline": ({"zh": "口播节奏和开场都在线。", "en": "Pacing and opening are solid."} if level == "good"
                         else {"zh": "口播开场可以更抓人。", "en": "The spoken opening could grab harder."}),
            "metrics": metrics, "advice": None}


# ————————————————————————— 组装 —————————————————————————
def diagnose_video(alias, vid):
    v = find_video(alias, vid)
    if not v:
        return {"ok": False, "error": f"找不到视频 alias={alias} vid={vid}"}
    pidx = _profile_index().get(alias, {})
    dims = [dim_cover(alias, v), dim_title(alias, v),
            dim_engagement(alias, v), dim_duration(alias, v)]
    sub = dim_subtitle(alias, v)
    if sub:
        dims.append(sub)
    dims = [d for d in dims if d]

    # 私有后台数据(用户上传 CSV 后才有):完播率 / 点击率 —— 有就插进来一起算
    try:
        import import_private
        priv = import_private.load_private(alias).get(v.get("vid") or v.get("bvid"))
        if priv:
            dims += import_private.private_dims(v, priv.get("metrics", {}))
    except Exception:
        pass

    real = [d for d in dims if d["level"] in ("good", "ok", "warn")]
    n_good = sum(1 for d in real if d["level"] == "good")
    n_warn = sum(1 for d in real if d["level"] == "warn")
    if n_warn == 0:
        sm = {"zh": f"{len(real)} 个维度基本都过关,这是一条扎实的作品。",
              "en": f"{len(real)} dimensions check out — a solid piece."}
    else:
        warn_zh = "、".join(d["label"]["zh"] for d in real if d["level"] == "warn")
        warn_en = ", ".join(d["label"]["en"] for d in real if d["level"] == "warn")
        sm = {"zh": f"主要可改进的是:{warn_zh}。逐项见下。",
              "en": f"Main things to improve: {warn_en}. Details below."}

    return {
        "ok": True,
        "video": {
            "creator": v.get("creator"), "alias": alias, "title": v.get("title"),
            "vid": v.get("vid") or v.get("bvid"), "platform": v.get("platform"),
            "zone": pidx.get("zone") or v.get("zone"),
            "play": v.get("play"), "like": v.get("like"), "danmaku": v.get("danmaku"),
            "comment": v.get("comment"),
            "duration_sec": v.get("duration_sec"), "cover_url": v.get("cover_url") or "",
            "published": (v.get("created_iso") or "")[:10],
        },
        "creator_info": {
            "name": pidx.get("name") or v.get("creator"),
            "play_med": pidx.get("stat", {}).get("play_med"),
            "trend": pidx.get("trend", {}).get("verdict"),
        },
        "dims": dims,
        "summary": {"good": n_good, "warn": n_warn, "headline": sm},
        "pending": [
            {"key": "opening", "label": {"zh": "开头镜头", "en": "Opening shots"},
             "note": {"zh": "需下载视频分析(B 期)", "en": "needs video download (Phase B)"}},
            {"key": "bgm", "label": {"zh": "配乐", "en": "BGM"},
             "note": {"zh": "需下载音频分析(B 期)", "en": "needs audio download (Phase B)"}},
        ],
    }


# ————————————————————————— CLI —————————————————————————
def _demo_pick():
    vs = _all_videos()
    return (vs[0].get("alias"), vs[0].get("vid")) if vs else (None, None)


def main():
    if len(sys.argv) >= 3:
        alias, vid = sys.argv[1], sys.argv[2]
    else:
        alias, vid = _demo_pick()
        print(f"(没给参数,拿第一条示范:alias={alias} vid={vid})\n")
    if not alias:
        print("没有数据。先在界面里『抓取并分析』。")
        return
    res = diagnose_video(alias, vid)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
