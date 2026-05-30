"""
viralens · import_private.py —— 创作者「自己后台数据」CSV 导入。

创作者从 YouTube Studio /(B站创作中心手填模板)导出 CSV,上传进来。本脚本:
  1. 解析 CSV,自动认列(完播率 / 平均观看时长 / 点击率CTR / 曝光 / 播放),不管表头叫啥都尽量对上;
  2. 跟已抓到的公开视频按「视频ID / 标题」匹配,存 data/private/<alias>.json;
  3. 生成「私有维度」诊断卡片(完播率、点击率),跟 benchmarks 的参考线对照。

只走 CSV(不碰截图 OCR、不碰登录态抓取)。私有数据只存本机 data/(已 gitignore)。

命令行自测:
    python import_private.py mrbeast some_export.csv
"""
import csv
import io
import json
import re
import sys
import time
from pathlib import Path

import benchmarks

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
PRIV = DATA / "private"


# ————————————————————————— 数据 —————————————————————————
def _all_videos():
    p = DATA / "all_videos.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _safe(s):
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(s))[:80]


# ————————————————————————— CSV 解析 —————————————————————————
def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _map_headers(headers):
    """把各种表头名对到统一字段。一个表头只认一个字段(elif),避免抢。
    注意顺序:CTR 必须在 impressions 之前判(YT 的 CTR 列名里也带 impressions)。"""
    m = {}
    for i, h in enumerate(headers):
        n = _norm(h)
        has = lambda *subs: any(s in n for s in subs)
        if "vid" not in m and n in ("content", "video id", "视频id", "bvid", "av号", "aid"):
            m["vid"] = i
        elif "title" not in m and has("title", "标题"):
            m["title"] = i
        elif "ctr" not in m and has("click-through", "click through", "ctr", "点击率"):
            m["ctr"] = i
        elif "impressions" not in m and has("impression", "曝光", "展示"):
            m["impressions"] = i
        elif "retention" not in m and has("percentage viewed", "完播", "观看率", "播放进度", "平均播放进度"):
            m["retention"] = i
        elif "avd" not in m and has("average view duration", "avg view duration", "平均观看时长", "平均播放时长"):
            m["avd"] = i
        elif "watch_hours" not in m and has("watch time", "观看时长"):
            m["watch_hours"] = i
        elif "views" not in m and (n == "views" or has("观看次数", "播放量", "播放数") or
                                   (has("views") and not has("watch"))):
            m["views"] = i
    return m


def _num(s):
    """'45.2%' → 45.2;'1,234' → 1234;'0:02:34' → 154(秒);空/横杠 → None。"""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("%", "").replace("$", "").replace("¥", "")
    if t == "" or t == "-" or t.lower() == "nan":
        return None
    if ":" in t:                                  # 时长 H:MM:SS / M:SS
        try:
            sec = 0.0
            for p in t.split(":"):
                sec = sec * 60 + float(p)
            return sec
        except Exception:
            return None
    try:
        return float(t)
    except Exception:
        return None


def parse_csv(text):
    """返回 [{title, vid, metrics{...}}]。容错:认不出的列忽略,汇总行/空行跳过。"""
    text = (text or "").lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return []
    cmap = _map_headers(rows[0])
    out = []
    for r in rows[1:]:
        if not any((c or "").strip() for c in r):
            continue

        def cell(key):
            i = cmap.get(key)
            return r[i].strip() if (i is not None and i < len(r)) else ""

        title, vid = cell("title"), cell("vid")
        if title.lower() in ("total", "totals", "合计", "总计", "—") or \
           (not title and vid.lower() in ("total", "totals", "合计", "总计")):
            continue                              # 跳过 YouTube 导出末尾的汇总行
        metrics = {
            "retention_pct": _num(cell("retention")),
            "avd_sec": _num(cell("avd")),
            "ctr_pct": _num(cell("ctr")),
            "impressions": _num(cell("impressions")),
            "views": _num(cell("views")),
            "watch_hours": _num(cell("watch_hours")),
        }
        if (not title and not vid) or all(v is None for v in metrics.values()):
            continue
        out.append({"title": title, "vid": vid, "metrics": metrics})
    return out


# ————————————————————————— 匹配到已抓视频 —————————————————————————
def _norm_title(t):
    return re.sub(r"[\s\W_]+", "", (t or "").lower())


def match_rows(alias, rows):
    vids = [v for v in _all_videos() if v.get("alias") == alias]
    by_id, by_title = {}, {}
    for v in vids:
        for k in (v.get("vid"), v.get("bvid")):
            if k:
                by_id[str(k)] = v
        nt = _norm_title(v.get("title"))
        if nt:
            by_title[nt] = v
    matched, unmatched = {}, []
    for row in rows:
        v = by_id.get(str(row["vid"])) if row["vid"] else None
        if not v and row["title"]:
            nt = _norm_title(row["title"])
            v = by_title.get(nt)
            if not v:                              # 标题包含匹配(后台标题可能带后缀)
                for tnt, tv in by_title.items():
                    if nt and (nt in tnt or tnt in nt) and abs(len(nt) - len(tnt)) <= 8:
                        v = tv
                        break
        if v:
            rid = v.get("vid") or v.get("bvid")
            matched[rid] = {"metrics": row["metrics"], "title": v.get("title")}
        else:
            unmatched.append(row["title"] or row["vid"])
    return matched, unmatched


def save_private(alias, csv_text):
    rows = parse_csv(csv_text)
    if not rows:
        return {"ok": False,
                "error": "没解析出数据 —— 确认是后台导出的 CSV(逗号分隔、第一行是表头)"}
    matched, unmatched = match_rows(alias, rows)
    PRIV.mkdir(parents=True, exist_ok=True)
    (PRIV / f"{_safe(alias)}.json").write_text(
        json.dumps({"alias": alias, "updated_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "videos": matched}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "n_rows": len(rows), "n_matched": len(matched),
            "n_unmatched": len(unmatched), "unmatched": unmatched[:8]}


def load_private(alias):
    p = PRIV / f"{_safe(alias)}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("videos", {})
    except Exception:
        return {}


# ————————————————————————— 私有维度卡片(同 diagnose.py 形状) —————————————————————————
def private_dims(v, m):
    """v=视频元数据(取时长/平台),m=该视频的私有指标。返回维度卡片列表。"""
    if not m:
        return []
    plat = (v.get("platform") or "bilibili")
    dur = v.get("duration_sec")
    dims = []

    # —— 完播率 / 平均观看 ——
    ret = m.get("retention_pct")
    if ret is not None:
        band = benchmarks.retention_band(plat, dur)
        lvl = benchmarks.level_by_band(ret, band)
        metrics = [{"name": {"zh": "完播率(平均观看%)", "en": "Avg % viewed"},
                    "value": f"{ret:.0f}%", "ref": benchmarks.retention_ref(plat, dur),
                    "level": lvl,
                    "advice": ({"zh": "开头或中段在掉人,回看前 30 秒和中间节奏是不是拖了",
                                "en": "viewers drop early/mid — recheck the first 30s and mid pacing"}
                               if lvl == "warn" else None)}]
        avd = m.get("avd_sec")
        if avd is not None:
            metrics.append({"name": {"zh": "平均观看时长", "en": "Avg view duration"},
                            "value": f"{avd:.0f}s",
                            "ref": {"zh": "越长越好,但要看占比", "en": "longer is better, relative to length"},
                            "level": "warn" if avd < benchmarks.avd_floor_sec() else "good"})
        head = ({"zh": "留存不错 —— 大部分人愿意看下去。", "en": "Solid retention — most viewers stay."} if lvl == "good"
                else {"zh": "留存中等,还有提升空间。", "en": "Mid retention — room to improve."} if lvl == "ok"
                else {"zh": "留存偏低 —— 这是涨播放最该先修的地方。", "en": "Low retention — the first thing to fix for reach."})
        dims.append({"key": "retention", "label": {"zh": "完播率 / 留存", "en": "Retention"},
                     "level": lvl, "headline": head, "metrics": metrics,
                     "advice": ({"zh": "留存是平台推荐的核心。把开头钩子前置、删掉中段废话、用进度感留人。",
                                 "en": "Retention drives the algorithm. Front-load the hook, cut mid-roll filler, add a sense of progress."}
                                if lvl != "good" else None)})

    # —— 点击率 CTR ——
    ctr = m.get("ctr_pct")
    if ctr is not None:
        band = benchmarks.ctr_band(plat)
        lvl = benchmarks.level_by_band(ctr, band)
        metrics = [{"name": {"zh": "曝光点击率 CTR", "en": "Impressions CTR"},
                    "value": f"{ctr:.1f}%", "ref": benchmarks.ctr_ref(plat), "level": lvl,
                    "advice": ({"zh": "封面/标题没勾住人,同主题多做几版封面对比",
                                "en": "thumbnail/title isn't pulling clicks — try a few thumbnail variants"}
                               if lvl == "warn" else None)}]
        imp = m.get("impressions")
        if imp is not None:
            small = imp < 5000
            metrics.append({"name": {"zh": "曝光量", "en": "Impressions"},
                            "value": f"{imp:,.0f}",
                            "ref": ({"zh": "样本偏小,CTR 仅供参考", "en": "small sample — CTR is rough"} if small
                                    else {"zh": "曝光充足", "en": "enough reach"}),
                            "level": "ok" if small else "good",
                            "why": ({"zh": "曝光太少时 CTR 波动大,别过度解读", "en": "CTR is noisy at low impressions"} if small else None)})
        head = ({"zh": "封面标题很能打 —— 点击率在线。", "en": "Strong packaging — CTR is healthy."} if lvl == "good"
                else {"zh": "点击率中等,封面标题还能更狠。", "en": "CTR is okay — packaging could hit harder."} if lvl == "ok"
                else {"zh": "点击率偏低 —— 内容再好也先得让人点进来。", "en": "Low CTR — even great content needs the click first."})
        dims.append({"key": "ctr", "label": {"zh": "点击率 / 封面标题", "en": "CTR / Packaging"},
                     "level": lvl, "headline": head, "metrics": metrics,
                     "advice": ({"zh": "封面一个清晰主体 + 一个情绪/悬念点;标题用第二人称对观众说话。",
                                 "en": "One clear subject + one emotion/curiosity beat on the thumbnail; write titles in second person."}
                                if lvl != "good" else None)})
    return dims


# ————————————————————————— CLI —————————————————————————
def main():
    if len(sys.argv) < 3:
        print("用法:python import_private.py <alias> <导出的.csv 路径>")
        return
    alias, path = sys.argv[1], sys.argv[2]
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    res = save_private(alias, text)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # 顺手打印第一条匹配上的私有维度,肉眼看一眼
    vids = load_private(alias)
    if vids:
        rid, rec = next(iter(vids.items()))
        v = next((x for x in _all_videos() if (x.get("vid") == rid or x.get("bvid") == rid)
                  and x.get("alias") == alias), {"platform": "", "duration_sec": None})
        print("\n示例维度(", rec.get("title"), "):")
        print(json.dumps(private_dims(v, rec["metrics"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
