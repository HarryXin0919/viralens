"""
viralens · app.py —— 图形界面(本地网页版)。

跑这一句,浏览器自动打开一个界面:填自己的 B站 / YouTube key → 点「抓取」或「抓取并分析」
→ 看结果、开报告。也能导入你之前抓过的数据。

    python app.py

安全:只监听 127.0.0.1(本机),不对外网开放;你的 key 只写进本地 config_local.py
(已被 .gitignore 排除,绝不上传);界面只回传"key 设没设"的真假,不回传明文。
纯标准库,零依赖。
"""
import importlib
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import runtime                        # 收口「源码跑 vs 打包成 app 跑」的路径/子进程差异

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = runtime.ASSET_DIR              # scripts/(源码)或打包资源目录(app),只读
DATA = runtime.DATA                   # 可写:源码=仓库/data,app=用户数据目录
REPORTS = runtime.REPORTS
GUI = runtime.ASSET_DIR / "gui.html"
CONFIG = runtime.CONFIG               # 密钥文件:源码=scripts/,app=用户数据目录

# runtime 已把 ASSET_DIR / USER_DIR 放进 sys.path —— import creators / config_local 即可用

# —— 跑流水线时的实时进度(后台线程写,/api/progress 读)——
PROGRESS = {"running": False, "lines": [], "returncode": None, "mode": ""}
LOCK = threading.Lock()


# ————————————————————— 密钥(只在本机读写,明文不外发) —————————————————————
def _read_config():
    """读现有 config_local 的两个值(明文,仅内部合并/判空用)。"""
    sd = yt = ""
    try:
        import config_local
        importlib.reload(config_local)
        sd = (getattr(config_local, "SESSDATA", "") or "").strip()
        yt = (getattr(config_local, "YOUTUBE_API_KEY", "") or "").strip()
    except Exception:
        pass
    return sd, yt


def keys_set():
    """只返回真假,绝不返回明文。"""
    sd, yt = _read_config()
    return bool(sd), bool(yt)


def write_keys(sessdata, youtube):
    """把新 key 写进 config_local.py;留空的字段保留原值(不清空)。"""
    cur_sd, cur_yt = _read_config()
    sd = sessdata.strip() or cur_sd
    yt = youtube.strip() or cur_yt
    proxy = ""                       # 保留用户可能手填的 PROXY(界面没这输入框,别冲掉)
    try:
        import config_local as _c
        importlib.reload(_c)
        proxy = (getattr(_c, "PROXY", "") or "").strip()
    except Exception:
        pass
    body = (
        '"""viralens 本地密钥 —— 由图形界面写入。已被 .gitignore 排除,不会上传 GitHub。"""\n'
        f"SESSDATA = {json.dumps(sd, ensure_ascii=False)}\n"
        f"YOUTUBE_API_KEY = {json.dumps(yt, ensure_ascii=False)}\n"
    )
    if proxy:
        body += f"PROXY = {json.dumps(proxy, ensure_ascii=False)}\n"
    CONFIG.write_text(body, encoding="utf-8")


# ————————————————————————————— 状态 —————————————————————————————
def list_creators():
    try:
        import creators
        importlib.reload(creators)
        return [{"name": c["name"], "platform": c.get("platform", "bilibili"),
                 "zone": c.get("zone", "")} for c in creators.CREATORS]
    except Exception:
        return []


def data_stats():
    files = [p for p in DATA.glob("*_videos.json") if p.name != "all_videos.json"]
    count = 0
    av = DATA / "all_videos.json"
    if av.exists():
        try:
            count = len(json.loads(av.read_text(encoding="utf-8")))
        except Exception:
            pass
    return len(files), count


def video_url(v):
    """按平台拼出可点开的视频链接(给结果卡片用)。"""
    p = (v.get("platform") or "bilibili").lower()
    vid = v.get("bvid") or v.get("vid") or ""
    if not vid:
        return ""
    if p == "youtube":
        return f"https://www.youtube.com/watch?v={vid}"
    return f"https://www.bilibili.com/video/{vid}"


# ——————————————————————— 诊断页:选择器数据 + 单视频诊断 ———————————————————————
def diag_list():
    """给诊断页的选择器:每个创作者 + 其视频(按播放降序)。"""
    import diagnose as _d
    _d.invalidate()
    av = DATA / "all_videos.json"
    vids = []
    if av.exists():
        try:
            vids = json.loads(av.read_text(encoding="utf-8"))
        except Exception:
            vids = []
    by = {}
    for v in vids:
        by.setdefault(v.get("alias") or "?", []).append(v)
    prof = _d._profile_index()
    out = []
    for a, vs in by.items():
        vs.sort(key=lambda x: x.get("play") or 0, reverse=True)
        pinfo = prof.get(a, {})
        out.append({
            "alias": a,
            "name": pinfo.get("name") or (vs[0].get("creator") if vs else a),
            "platform": (vs[0].get("platform") if vs else "") or "bilibili",
            "zone": pinfo.get("zone") or (vs[0].get("zone") if vs else ""),
            "count": len(vs),
            "videos": [{"vid": x.get("vid") or x.get("bvid"), "title": x.get("title"),
                        "play": x.get("play"), "cover_url": x.get("cover_url") or "",
                        "duration_sec": x.get("duration_sec"),
                        "published": (x.get("created_iso") or "")[:10]} for x in vs],
        })
    out.sort(key=lambda c: -((c["videos"][0]["play"] or 0) if c["videos"] else 0))
    return {"creators": out}


def diag_video(alias, vid):
    import diagnose as _d
    _d.invalidate()
    return _d.diagnose_video(alias, vid)


def diag_clip(alias, vid):
    """『视频下载层』:下开头 ~45 秒,分析开头镜头 + 配乐。慢(10–30 秒),结果缓存。"""
    import analyze_video as _av
    return _av.analyze(alias, vid)


# ——————————————————————— 跑流水线(后台线程) ———————————————————————
def run_pipeline(mode, no_fetch, force, platforms=None):
    extra = []
    if mode == "report":
        extra.append("--report")
    if no_fetch:
        extra.append("--no-fetch")
    if force:
        extra.append("--force")
    cmd = runtime.worker_cmd("viralens.py", extra)   # 源码:[py, viralens.py];app:[自己, --vl-exec, viralens]
    shown = "viralens.py " + " ".join(extra)
    # 只抓用户在界面勾选的平台(通过环境变量传给 fetch_multi.py)
    env = os.environ.copy()
    if platforms:
        env["VIRALENS_PLATFORMS"] = ",".join(platforms)
    with LOCK:
        PROGRESS.update(running=True, lines=[f"$ {shown}"], returncode=None, mode=mode)
    try:
        # 打包模式 cwd 用可写的用户目录(程序目录只读);源码模式保持 scripts/(行为不变)
        cwd = str(runtime.USER_DIR) if runtime.FROZEN else str(HERE)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace",
                             bufsize=1, cwd=cwd, env=env)
        for line in p.stdout:
            with LOCK:
                PROGRESS["lines"].append(line.rstrip("\n"))
        p.wait()
        rc = p.returncode
    except Exception as e:
        with LOCK:
            PROGRESS["lines"].append(f"✗ 启动失败:{type(e).__name__}: {e}")
        rc = -1
    with LOCK:
        PROGRESS.update(running=False, returncode=rc)


# ——————————————————————————— 导入已有数据 ———————————————————————————
def slug(s):
    s = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(s)).strip("_")
    return s or "imported"


def do_import(path):
    p = Path(path.strip().strip('"').strip("'"))
    if not p.exists():
        return {"ok": False, "error": f"找不到文件:{p}"}
    if p.suffix.lower() != ".json":
        return {"ok": False, "error": "v1 先支持 .json(all_videos.json 格式);CSV 稍后加"}
    try:
        recs = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"读取失败:{e}"}
    if not isinstance(recs, list) or not recs:
        return {"ok": False, "error": "格式不对:应是视频记录组成的列表"}
    DATA.mkdir(exist_ok=True)
    groups = {}
    for v in recs:
        key = slug(v.get("alias") or v.get("creator") or "imported")
        groups.setdefault(key, []).append(v)
    for a, vs in groups.items():
        (DATA / f"{a}_videos.json").write_text(
            json.dumps(vs, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(runtime.worker_cmd("export_data.py"))
    return {"ok": True, "creators": len(groups), "videos": len(recs)}


# ————————————————————————————— HTTP —————————————————————————————
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # 安静,别刷屏

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, target: Path):
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not GUI.exists():
                return self._json(500, {"error": "gui.html 不见了"})
            return self._file(GUI)
        if path == "/api/status":
            sd, yt = keys_set()
            nfiles, count = data_stats()
            return self._json(200, {"bilibili_key": sd, "youtube_key": yt,
                                    "creators": list_creators(),
                                    "files": nfiles, "count": count})
        if path == "/api/progress":
            with LOCK:
                return self._json(200, dict(PROGRESS))
        if path == "/api/data":
            av = DATA / "all_videos.json"
            vids = []
            if av.exists():
                try:
                    vids = json.loads(av.read_text(encoding="utf-8"))
                except Exception:
                    vids = []
            slim = []
            for v in vids:
                u = video_url(v)
                # 老 B 站记录可能没写 platform 字段,从链接反推,保证界面能正确分类/筛选
                plat = v.get("platform") or (
                    "youtube" if "youtube.com" in u else "bilibili" if u else "")
                slim.append({"creator": v.get("creator"), "platform": plat,
                             "title": v.get("title"), "play": v.get("play"),
                             "comment": v.get("comment"), "like": v.get("like"),
                             "danmaku": v.get("danmaku"),   # B 站卡片用弹幕替点赞(YT 没弹幕)
                             "duration_sec": v.get("duration_sec"),
                             "cover_url": v.get("cover_url") or "",
                             "url": u,
                             "published": (v.get("created_iso") or "")[:10]})
            return self._json(200, {"count": len(slim), "videos": slim[:300]})
        if path in ("/diagnose", "/diagnose.html"):
            dg = HERE / "diagnose.html"
            if not dg.exists():
                return self._json(500, {"error": "diagnose.html 不见了"})
            return self._file(dg)
        if path == "/api/diag/list":
            return self._json(200, diag_list())
        if path == "/api/diag/video":
            qs = parse_qs(urlparse(self.path).query)
            alias = (qs.get("alias") or [""])[0]
            vid = (qs.get("vid") or [""])[0]
            if not alias or not vid:
                return self._json(400, {"ok": False, "error": "缺 alias 或 vid"})
            return self._json(200, diag_video(alias, vid))
        if path == "/api/diag/clip":
            qs = parse_qs(urlparse(self.path).query)
            alias = (qs.get("alias") or [""])[0]
            vid = (qs.get("vid") or [""])[0]
            if not alias or not vid:
                return self._json(400, {"ok": False, "error": "缺 alias 或 vid"})
            return self._json(200, diag_clip(alias, vid))
        if path == "/api/private/status":
            import import_private
            qs = parse_qs(urlparse(self.path).query)
            alias = (qs.get("alias") or [""])[0]
            vids = import_private.load_private(alias) if alias else {}
            return self._json(200, {"ok": True, "n": len(vids)})
        if path == "/report" or path.startswith("/report/"):
            rel = path[len("/report"):].lstrip("/") or "index.html"
            target = (REPORTS / rel).resolve()
            if not str(target).startswith(str(REPORTS.resolve())) or not target.exists():
                return self._json(404, {"error": "还没有报告 —— 先点『抓取并分析』生成"})
            return self._file(target)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        if path == "/api/keys":
            write_keys(body.get("sessdata", ""), body.get("youtube_api_key", ""))
            sd, yt = keys_set()
            return self._json(200, {"ok": True, "bilibili_key": sd, "youtube_key": yt})
        if path == "/api/run":
            with LOCK:
                if PROGRESS["running"]:
                    return self._json(409, {"error": "正在跑,稍等它结束"})
            plats = body.get("platforms") or []
            if not isinstance(plats, list):
                plats = []
            t = threading.Thread(target=run_pipeline,
                                 args=(body.get("mode", "data"),
                                       bool(body.get("no_fetch")), bool(body.get("force")),
                                       plats),
                                 daemon=True)
            t.start()
            return self._json(200, {"started": True})
        if path == "/api/import":
            return self._json(200, do_import(body.get("path", "")))
        if path == "/api/private/upload":
            import import_private
            alias = (body.get("alias") or "").strip()
            csv_text = body.get("csv") or ""
            if not alias or not csv_text:
                return self._json(400, {"ok": False, "error": "缺 alias 或 csv 内容"})
            return self._json(200, import_private.save_private(alias, csv_text))
        return self._json(404, {"error": "not found"})


def find_port(start=8722):
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main():
    port = find_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print("=" * 56)
    print(f"  viralens 界面已启动 → {url}")
    print("  浏览器没自动开就手动复制上面这个地址。")
    print("  关掉这个窗口 或 按 Ctrl+C 即可停止。")
    print("=" * 56)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
