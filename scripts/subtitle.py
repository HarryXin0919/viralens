"""
viralens · subtitle.py
抓 pilot 视频(2025正经科普 高5+低5)的 B站字幕,算"实验 vs 思辨"密度、语速、开场钩子。
验证假设:高播放组 是不是 思辨密度更高、实验奇观更少。

依赖: bilibili-api-python aiohttp (已装)
SESSDATA: 从 01 脚本复制粘贴到下方

跑: python subtitle.py
输出: data/subtitle_features.json + 终端高低组对比
"""
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean

import aiohttp
from bilibili_api import video, Credential

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # Win 控制台默认 GBK,强制 UTF-8 防 ✓/emoji 崩

DATA = Path(__file__).parent.parent / "data"
try:
    from config_local import SESSDATA   # ← 统一从 config_local.py 读(已 gitignore,不进 git)
except ImportError:
    SESSDATA = ""

# 粗糙词典:pilot 看趋势用,后续会换成更精细的
EXP_WORDS = ["实验", "我们来", "你看", "倒进", "倒入", "加热", "点燃", "装置",
             "材料", "试一下", "试试", "测量", "拍摄", "高速", "帧", "操作"]
THINK_WORDS = ["为什么", "其实", "真相", "你以为", "本质", "原因", "意味着",
               "证明", "逻辑", "悖论", "假设", "定律", "并不是", "误解", "概念"]
HOOK_WORDS = ["为什么", "竟然", "居然", "真的", "你知道", "想象", "到底", "难道", "？", "?"]


async def get_subtitle_body(v):
    """返回字幕 body 列表 [{from,to,content}] 或 (None, 错误说明)"""
    info = await v.get_info()
    cid = info.get("cid") or info["pages"][0]["cid"]

    subs = []
    err_trace = ""
    # 试两种接口(版本差异)
    for getter in ("get_player_info", "get_subtitle"):
        try:
            fn = getattr(v, getter)
            raw = await fn(cid=cid)
            subs = raw.get("subtitle", {}).get("subtitles", []) or raw.get("subtitles", [])
            if subs:
                break
        except Exception as e:
            err_trace += f"[{getter}:{e}] "
    if not subs:
        return None, f"无字幕({err_trace or '列表为空'})"

    # 优先中文字幕
    subs.sort(key=lambda s: 0 if "zh" in s.get("lan", "") else 1)
    url = subs[0].get("subtitle_url", "")
    if url.startswith("//"):
        url = "https:" + url
    if not url:
        return None, "字幕无下载链接"

    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as sess:
        async with sess.get(url) as r:
            data = await r.json()
    return data.get("body", []), None


def count(text, words):
    return sum(text.count(w) for w in words)


async def main():
    if not SESSDATA:
        print("❌ 请先粘 SESSDATA(从 01 脚本复制)")
        return

    classified = json.loads((DATA / "classified.json").read_text(encoding="utf-8"))
    sci = [v for v in classified if v.get("type") == "正经科普"
           and (v.get("created_iso") or "")[:4] == "2025"]
    sci.sort(key=lambda x: -x["play"])
    pilot = [("高", v) for v in sci[:5]] + [("低", v) for v in sci[-5:]]

    cred = Credential(sessdata=SESSDATA)
    results = []
    print("抓字幕中(每个约 1-2 秒)...\n")
    for group, v in pilot:
        vid = video.Video(bvid=v["bvid"], credential=cred)
        try:
            body, err = await get_subtitle_body(vid)
        except Exception as e:
            body, err = None, f"异常 {e}"
        if err:
            print(f"  ✗ [{group}] {v['title'][:22]}: {err}")
            continue

        full = "".join(seg["content"] for seg in body)
        opening = "".join(seg["content"] for seg in body if seg.get("from", 0) <= 30)
        n = len(full) or 1
        dur_min = v["duration_sec"] / 60
        rec = {
            "group": group, "bvid": v["bvid"], "title": v["title"],
            "play": v["play"], "chars": len(full),
            "speed_cpm": round(len(full) / dur_min),         # 语速:字/分钟
            "exp_per_1k": round(count(full, EXP_WORDS) / n * 1000, 1),
            "think_per_1k": round(count(full, THINK_WORDS) / n * 1000, 1),
            "hook_open": count(opening, HOOK_WORDS),
        }
        rec["think_exp_ratio"] = round(rec["think_per_1k"] / (rec["exp_per_1k"] + 0.1), 2)
        results.append(rec)
        print(f"  ✓ [{group}] {v['title'][:22]:<22} 思辨{rec['think_per_1k']:>4} 实验{rec['exp_per_1k']:>4} "
              f"比{rec['think_exp_ratio']:>4} 语速{rec['speed_cpm']} 开场钩子{rec['hook_open']}")

    if not results:
        print("\n⚠️ 一个字幕都没抓到。把上面的 ✗ 报错贴给我,我改接口。")
        return

    (DATA / "subtitle_features.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 高低组对比
    print("\n" + "=" * 60)
    print("高 vs 低 播放组 · 字幕特征对比")
    print("=" * 60)
    for g in ("高", "低"):
        rows = [r for r in results if r["group"] == g]
        if not rows:
            continue
        print(f"\n■ {g}播放组 (n={len(rows)})")
        print(f"   思辨密度 {mean(r['think_per_1k'] for r in rows):.1f} /千字")
        print(f"   实验密度 {mean(r['exp_per_1k'] for r in rows):.1f} /千字")
        agg_ratio = mean(r['think_per_1k'] for r in rows) / (mean(r['exp_per_1k'] for r in rows) + 0.1)
        print(f"   思辨/实验比(组合计,抗异常值) {agg_ratio:.2f}")
        print(f"   语速 {mean(r['speed_cpm'] for r in rows):.0f} 字/分")
        print(f"   开场钩子词 {mean(r['hook_open'] for r in rows):.1f} 个")
    print("\n✅ 已写 data/subtitle_features.json — 把上面整段贴给我解读")


if __name__ == "__main__":
    asyncio.run(main())
