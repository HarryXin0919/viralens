"""
viralens · analyze_video.py —— B 期『视频下载层』。

诊断里「开头镜头」和「配乐 / 声音设计」这两维,光看元数据看不出来,
得真的把视频下下来看。这个脚本就干这件事 —— 但只下开头 ~45 秒、最低画质,
用已经装好的 ffmpeg 做两件分析:

  1. 开头镜头:场景切换检测 → 前 3 秒切了几个镜头、前 10 秒平均一个镜头多长。
     爆款开头普遍「快」—— 一上来就有画面变化,把人钩住;静止长镜头容易被划走。
  2. 配乐 / 声音:开场 2 秒有没有声(先声夺人)、整段响度和起伏
     (有没有一条配乐垫着,还是纯口播)。

顺手把开头第 0.5 秒那一帧抠出来存成小缩略图(base64),让你直接「看见」自己的开头。

结果缓存到 data/clips/<alias>/<vid>.json,下次秒开,不重下。
按需调用:用户在诊断页点「分析开头+配乐」才下这一条,不批量下 700 条。

命令行单测:
    python analyze_video.py <alias> <vid>            # 如 demo_b1 BVxxxxxxxxxx
    python analyze_video.py <alias> <youtube_vid>    # YouTube 视频 id
    python analyze_video.py <alias> <vid> --force    # 忽略缓存重算
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import DATA, CLIPS    # 源码=仓库/data,打包成 app 时=用户数据目录

CLIP_SECONDS = 45          # 只下开头这么多秒
SCENE_THRESH = 0.35        # 场景切换灵敏度(越低越敏感)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ————————————————————————— 数据 / 路径 —————————————————————————
def _all_videos():
    p = DATA / "all_videos.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def find_video(alias, vid):
    for v in _all_videos():
        if v.get("alias") == alias and (v.get("vid") == vid or v.get("bvid") == vid):
            return v
    return None


def cache_path(alias, vid):
    return CLIPS / _safe(alias) / f"{_safe(vid)}.json"   # alias 也要消毒,防目录穿越


def _safe(s):
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(s))[:80]


# ————————————————————————— 下载(yt-dlp,只下开头) —————————————————————————
def _sessdata():
    """B 站 cookie。只在内存里用,绝不打印/落盘到 git。"""
    try:
        from config_local import SESSDATA
        return (SESSDATA or "").strip()
    except Exception:
        return ""


def _no_proxy_env():
    """B 站要国内 IP 直连。Harry 开了 VPN 代理(走境外出口),B 站对境外 IP 风控 412。
    给 ffmpeg 子进程清掉所有代理环境变量,强制直连。"""
    env = dict(os.environ)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY"):
        env.pop(k, None)
    env["no_proxy"] = "*"
    return env


def _proxy():
    """YouTube 在国内要走代理。优先级:config_local.PROXY → 环境变量 → 直连。
    墙外用户留空直连即可;国内用户填 config_local 的 PROXY,或设好 HTTPS_PROXY 环境变量。"""
    try:
        from config_local import PROXY
        p = (PROXY or "").strip()
        if p:
            return p
    except Exception:
        pass
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def _ffmpeg_available():
    """这个『下视频分析开场+配乐』功能依赖 ffmpeg/ffprobe;其余功能都不需要。"""
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _ffmpeg_missing_result(alias, vid):
    tip = ("Windows: winget install Gyan.FFmpeg(或 ffmpeg.org 下载后加进 PATH)\n"
           "  macOS:   brew install ffmpeg\n"
           "  Linux:   sudo apt install ffmpeg")
    return {"ok": False, "stage": "ffmpeg", "alias": alias, "vid": vid,
            "error": "没检测到 ffmpeg —— 只有这个『下视频分析开场镜头+配乐』功能需要它。",
            "hint": {"zh": "抓取 / 分析 / 报告等其余功能都不需要 ffmpeg。装好后重试:\n  " + tip,
                     "en": "Everything else (fetch / analyze / report) works without ffmpeg. "
                           "Install it and retry:\n  " + tip}}


def _ffmpeg_fetch(url, out, dur, referer="https://www.bilibili.com/"):
    """ffmpeg 从远程流地址抓开头 dur 秒到 out。直连、带 Referer(B 站 CDN 必须)。"""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-user_agent", UA, "-headers", f"Referer: {referer}\r\n",
           "-i", url, "-t", str(dur), "-c", "copy", "-y", out]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=_no_proxy_env())
    if r.returncode != 0 or not Path(out).exists():
        raise RuntimeError(f"ffmpeg 抓流失败:{(r.stderr or '').strip()[:160]}")
    return out


def _download_bilibili(v, workdir):
    """B 站:用 bilibili-api(项目本来就在用)拿流地址,ffmpeg 直连下开头。
    DASH 是视频/音频分离的,各下一份。返回 (视频路径, 音频路径)。"""
    import asyncio
    from bilibili_api import Credential
    from bilibili_api import video as biliv
    from bilibili_api.video import VideoDownloadURLDataDetecter

    bvid = v.get("bvid") or v.get("vid")
    cred = Credential(sessdata=_sessdata()) if _sessdata() else None

    async def _streams():
        obj = biliv.Video(bvid=bvid, credential=cred)
        data = await obj.get_download_url(page_index=0, html5=True)
        return VideoDownloadURLDataDetecter(data).detect_best_streams()

    streams = asyncio.run(_streams())
    if not streams:
        raise RuntimeError("没解析到可下的流")

    vpath = str(Path(workdir) / "video.mp4")
    _ffmpeg_fetch(streams[0].url, vpath, CLIP_SECONDS)
    apath = vpath
    if len(streams) > 1 and getattr(streams[1], "url", None):
        apath = str(Path(workdir) / "audio.m4a")
        try:
            _ffmpeg_fetch(streams[1].url, apath, CLIP_SECONDS)
        except Exception:
            apath = vpath   # 音频单流抓不到就退回视频里的音轨
    return vpath, apath


def _download_youtube(v, workdir):
    """YouTube:yt-dlp 下开头(走用户的代理,YouTube 在国内要翻墙)。返回 (路径, 路径)。"""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    opts = {
        "format": "worst[height>=180]/worst",
        "outtmpl": str(Path(workdir) / "clip.%(ext)s"),
        "download_ranges": download_range_func(None, [(0, CLIP_SECONDS)]),
        "force_keyframes_at_cuts": False,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "retries": 2, "fragment_retries": 2, "socket_timeout": 30,
        "overwrites": True,
    }
    px = _proxy()
    if px:
        opts["proxy"] = px        # 显式喂代理给 yt-dlp,不再只靠继承环境变量
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={v.get('vid')}"])
    media = [p for p in Path(workdir).glob("clip.*")
             if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".flv", ".ts", ".m4v")]
    if not media:
        raise RuntimeError("下载完成但没找到媒体文件")
    p = str(max(media, key=lambda x: x.stat().st_size))
    return p, p


def _download(v, workdir):
    """按平台分流下开头 CLIP_SECONDS 秒。返回 (视频路径, 音频路径)。"""
    if (v.get("platform") or "").lower() == "youtube":
        return _download_youtube(v, workdir)
    return _download_bilibili(v, workdir)


# ————————————————————————— ffmpeg 分析 —————————————————————————
def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _scene_cuts(clip):
    """返回场景切换时间点列表(秒)。"""
    r = _run(["ffmpeg", "-hide_banner", "-i", clip, "-an",
              "-filter:v", f"select='gt(scene,{SCENE_THRESH})',showinfo",
              "-f", "null", "-"])
    return sorted(float(m.group(1))
                  for m in re.finditer(r"pts_time:([0-9.]+)", r.stderr))


def _duration(clip):
    r = _run(["ffprobe", "-hide_banner", "-v", "error", "-show_entries",
              "format=duration", "-of", "default=nw=1:nk=1", clip])
    try:
        return float(r.stdout.strip())
    except Exception:
        return None


def _loudness(clip):
    """整段积分响度 LUFS + 起伏 LRA。无音轨返回 (None, None)。"""
    r = _run(["ffmpeg", "-hide_banner", "-i", clip, "-map", "0:a:0?",
              "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', r.stderr, re.S)
    if not m:
        return None, None
    try:
        d = json.loads(m.group(0))
        lufs = float(d.get("input_i"))
        lra = float(d.get("input_lra"))
        # loudnorm 对纯静音会给 -70 左右
        return (None if lufs <= -69 else lufs), lra
    except Exception:
        return None, None


def _open_volume(clip, secs=2):
    """开场 secs 秒的平均音量(dB)。越接近 0 越响,-91 ≈ 静音。"""
    r = _run(["ffmpeg", "-hide_banner", "-i", clip, "-map", "0:a:0?",
              "-t", str(secs), "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def _open_frame_datauri(clip, t=0.5):
    """抠开场一帧,缩到 240px 宽,存成 base64 data URI(直接嵌进 JSON)。"""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(t), "-i", clip, "-frames:v", "1",
         "-vf", "scale=240:-1", "-q:v", "6", "-f", "image2pipe",
         "-vcodec", "mjpeg", "-"],
        capture_output=True)
    if r.returncode == 0 and r.stdout:
        return "data:image/jpeg;base64," + base64.b64encode(r.stdout).decode("ascii")
    return None


# ————————————————————————— 拼成诊断维度(和 diagnose.py 同一形状) —————————————————————————
def _dim_opening(cuts, dur, thumb):
    label = {"zh": "开头镜头", "en": "Opening shots"}
    win = min(dur or CLIP_SECONDS, 10.0)
    cuts_3 = sum(1 for t in cuts if t < 3.0)
    cuts_10 = sum(1 for t in cuts if t < win)
    avg_shot = win / (cuts_10 + 1)

    if cuts_3 >= 2:
        lvl = "good"
        head = {"zh": "开头节奏快 —— 前 3 秒就有镜头切换,容易把人钩住。",
                "en": "Punchy open — cuts within the first 3s grab attention."}
        adv = None
    elif cuts_3 == 1:
        lvl = "ok"
        head = {"zh": "开头有变化,但还能更紧。前 3 秒多给一个钩子镜头会更稳。",
                "en": "There's some motion, but it could be tighter. One more hook shot in the first 3s helps."}
        adv = {"zh": "把最有冲击力的画面提到最前面,别用平铺直叙的长镜头开场。",
               "en": "Lead with your most striking shot; avoid opening on one static long take."}
    else:
        lvl = "ok"          # 静止开场不一定是错 —— 看赛道,所以是描述性提示,不算扣分
        head = {"zh": "开场是一个静止 / 长镜头 —— 看你的赛道:快节奏类容易被划走,氛围 / 慢镜头类则没问题。",
                "en": "The open is one static / long shot — depends on your niche: risky for fast-paced content, fine for mood / slow genres."}
        adv = {"zh": "科普 / 娱乐 / 游戏:开头加个快切或钩子更稳;美食 / Vlog / 音乐:慢开场是常态,不用强改。",
               "en": "Explainer / entertainment / gaming: a quick cut or hook helps; food / vlog / music: a slow open is normal — no need to force it."}

    metrics = [
        {"name": {"zh": "前 3 秒镜头数", "en": "Cuts in first 3s"},
         "value": str(cuts_3),
         "ref": {"zh": "快节奏类常 ≥ 2", "en": "fast-paced often ≥ 2"},
         "level": "good" if cuts_3 >= 2 else "ok",
         "advice": None},
        {"name": {"zh": "前 10 秒平均镜头时长", "en": "Avg shot length (first 10s)"},
         "value": f"{avg_shot:.1f}s",
         "ref": {"zh": "短=快节奏 · 长=慢叙事(看赛道)", "en": "short = punchy · long = slow (niche-dependent)"},
         "level": "good" if avg_shot <= 3.5 else "ok",
         "advice": None},
    ]
    d = {"key": "opening", "label": label, "level": lvl,
         "headline": head, "metrics": metrics, "advice": adv}
    if thumb:
        d["thumb"] = thumb
        d["thumb_cap"] = {"zh": "你的开场第一帧", "en": "Your opening frame"}
    return d


def _dim_bgm(open_vol, lufs, lra):
    label = {"zh": "配乐 / 声音", "en": "BGM / Sound"}
    metrics = []
    levels = []

    # 1) 开场有没有声(先声夺人)
    if open_vol is not None:
        if open_vol > -40:
            lvl = "good"; why = {"zh": "开场即有声,先声夺人", "en": "sound from the first beat"}
        elif open_vol > -55:
            lvl = "ok"; why = {"zh": "开场声音偏弱", "en": "opening audio is a bit thin"}
        else:
            lvl = "ok"; why = {"zh": "开场近乎静音(留白 / ASMR / 纯人声开场可能是有意的)", "en": "near-silent open (could be intentional: a cappella / ASMR / quiet intro)"}
        levels.append(lvl)
        metrics.append({
            "name": {"zh": "开场 2 秒音量", "en": "Opening 2s loudness"},
            "value": f"{open_vol:.0f} dB", "ref": {"zh": "越接近 0 越响", "en": "closer to 0 = louder"},
            "level": lvl, "why": why,
            "advice": ({"zh": "若不是有意留白:开头加段配乐 / 音效更抓人", "en": "if the silence isn't intentional: music/SFX up front grabs harder"}
                       if open_vol <= -55 else None)})

    # 2) 整段响度密度(有没有配乐垫着)
    if lufs is not None:
        # -14 是平台播放目标响度;明显更低 = 声音稀、可能纯口播无配乐
        if lufs >= -20:
            lvl = "good"; why = {"zh": "声音饱满,像有配乐垫底", "en": "full mix, likely a music bed"}
        elif lufs >= -28:
            lvl = "ok"; why = {"zh": "声音密度中等", "en": "moderate sound density"}
        else:
            lvl = "ok"; why = {"zh": "整体偏安静(口播 / 慢节奏类常见,不一定是问题)", "en": "overall quiet (common for talk/slow genres — not necessarily a problem)"}
        levels.append(lvl)
        metrics.append({
            "name": {"zh": "整体响度", "en": "Integrated loudness"},
            "value": f"{lufs:.0f} LUFS", "ref": {"zh": "平台约 -14", "en": "platforms ~ -14"},
            "level": lvl, "why": why,
            "advice": ({"zh": "想更有情绪张力,可以铺一条轻配乐", "en": "for more emotional drive, consider a light music bed"}
                       if lufs < -28 else None)})

    # 3) 响度起伏 LRA(低=有持续配乐,高=以口播/动态为主)—— 仅信息,不判好坏
    if lra is not None:
        metrics.append({
            "name": {"zh": "响度起伏 LRA", "en": "Loudness range (LRA)"},
            "value": f"{lra:.0f}", "ref": {"zh": "低=有配乐垫底 · 高=偏口播", "en": "low = music bed · high = speech-driven"},
            "level": "good"})

    if not metrics:
        return {"key": "bgm", "label": label, "level": "na",
                "headline": {"zh": "这条没解析到音轨。", "en": "No audio track detected."},
                "metrics": [], "advice": None}

    lvl = _worst(levels)
    if lvl == "good":
        head = {"zh": "声音设计在线 —— 开场有声、整段也撑得住。",
                "en": "Sound design is working — strong open and a full mix."}
        adv = None
    elif lvl == "ok":
        head = {"zh": "声音够用,但还能更有存在感。",
                "en": "Audio is fine, but it could carry more presence."}
        adv = {"zh": "配乐不只是背景:开头用它造钩子,转场用它接气口。",
               "en": "Music isn't just backdrop — use it to hook the open and bridge transitions."}
    else:
        head = {"zh": "声音偏弱 —— 开场或整段不够满,情绪和节奏会泄气。",
                "en": "Audio is weak — a thin open or sparse mix leaks energy and pacing."}
        adv = {"zh": "先把开场 2 秒填满(音效/配乐),再给全片铺一条情绪线。"
                     "注:这里只测了响度,曲速 / 卡点还得更专业的音频分析。",
               "en": "Fill the first 2s (SFX/music), then lay an emotional bed across the cut. "
                     "Note: this measures loudness only — tempo/beat-sync needs deeper audio analysis."}
    return {"key": "bgm", "label": label, "level": lvl,
            "headline": head, "metrics": metrics, "advice": adv}


def _worst(levels):
    order = {"warn": 3, "ok": 2, "good": 1, "na": 0}
    return max(levels, key=lambda x: order.get(x, 0)) if levels else "na"


# ————————————————————————— 主入口 —————————————————————————
def analyze(alias, vid, force=False):
    """下开头并分析。返回 {ok, dims:[opening, bgm], raw, ...}。结果缓存。"""
    v = find_video(alias, vid)
    if not v:
        return {"ok": False, "error": f"找不到视频 alias={alias} vid={vid}"}
    real_vid = v.get("vid") or v.get("bvid")
    cp = cache_path(alias, real_vid)

    if cp.exists() and not force:
        try:
            cached = json.loads(cp.read_text(encoding="utf-8"))
            cached["cached"] = True
            return cached
        except Exception:
            pass

    # 缓存没命中才需要真去下视频 —— 这一步(且仅这一步)依赖 ffmpeg。缺了就优雅提示,不崩。
    if not _ffmpeg_available():
        return _ffmpeg_missing_result(alias, real_vid)

    with tempfile.TemporaryDirectory(prefix="viralens_clip_") as wd:
        try:
            video_path, audio_path = _download(v, wd)
        except Exception as e:
            return {"ok": False, "stage": "download", "alias": alias, "vid": real_vid,
                    "error": f"下载失败:{e}",
                    "hint": {"zh": "可能是会员/地区限制或风控。换一条公开视频试试。",
                             "en": "Could be members-only/region lock or rate-limit. Try another public video."}}
        try:
            dur = _duration(video_path)
            cuts = _scene_cuts(video_path)
            lufs, lra = _loudness(audio_path)
            open_vol = _open_volume(audio_path)
            thumb = _open_frame_datauri(video_path)
        except Exception as e:
            return {"ok": False, "stage": "analyze", "alias": alias, "vid": real_vid,
                    "error": f"分析失败:{e}"}

    dim_open = _dim_opening(cuts, dur, thumb)
    dim_bgm = _dim_bgm(open_vol, lufs, lra)
    result = {
        "ok": True, "cached": False,
        "alias": alias, "vid": real_vid,
        "title": v.get("title"), "platform": v.get("platform"),
        "analyzed_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "clip_seconds": CLIP_SECONDS,
        "dims": [dim_open, dim_bgm],
        "raw": {
            "duration_analyzed": round(dur, 2) if dur else None,
            "scene_cuts": [round(t, 2) for t in cuts],
            "cuts_3s": sum(1 for t in cuts if t < 3.0),
            "cuts_10s": sum(1 for t in cuts if t < min(dur or 10, 10)),
            "lufs": round(lufs, 1) if lufs is not None else None,
            "lra": round(lra, 1) if lra is not None else None,
            "open_volume_db": round(open_vol, 1) if open_vol is not None else None,
        },
    }
    try:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if len(args) >= 2:
        alias, vid = args[0], args[1]
    else:
        vs = _all_videos()
        if not vs:
            print("没有数据。先在界面里『抓取并分析』。")
            return
        alias, vid = vs[0].get("alias"), vs[0].get("vid")
        print(f"(没给参数,拿第一条示范:alias={alias} vid={vid})\n")
    res = analyze(alias, vid, force=force)
    # 缩略图 base64 太长,打印时截断
    show = json.loads(json.dumps(res))
    for d in show.get("dims", []):
        t = d.get("thumb")
        if t:
            d["thumb"] = f"{t[:40]}...(+{len(t)} chars)"
    print(json.dumps(show, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
