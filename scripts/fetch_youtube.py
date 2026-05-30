"""
viralens · fetch_youtube.py
平台适配器:YouTube。用官方 YouTube Data API v3(免费额度足),只用标准库 urllib,零额外依赖。
吐出和 fetch_bilibili.py 一模一样的「标准视频表」,下游脚本(compare_form / scan_signals /
creator_profile / fetch_covers)无需任何改动。

需要:免费 API key —— 放进 config_local.py 的 YOUTUBE_API_KEY(已 gitignore,不进 git)。
拿 key:https://console.cloud.google.com → 新建项目 → 启用 "YouTube Data API v3" → 凭据 → API 密钥。

creators.py 里 YouTube 创作者写法(platform 必须是 "youtube"):
  {"name": "Example Channel", "platform": "youtube", "channel": "@example", "alias": "demo_yt", "zone": "STEM-YT"}
channel 支持三种写法:
  - "@handle"     (推荐,稳定、你能直接核对)
  - "UCxxxx..."   (频道 ID,以 UC 开头)
  - "随便的名字"   (兜底:按名字搜索,取第一个;会多花 100 配额)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "https://www.googleapis.com/youtube/v3"


class YouTubeError(Exception):
    """对外抛出的可读错误,由 fetch_multi 调度器捕获打印。"""


def _get(endpoint, params, key, tries=3):
    """调一个 YouTube Data API 端点 → JSON dict。配额/密钥错误给出中文提示;网络抖动重试。"""
    params = dict(params, key=key)
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "viralens/1.0"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            msg, reason = body, ""
            try:
                j = json.loads(body)
                msg = j.get("error", {}).get("message", body)
                reason = (j.get("error", {}).get("errors") or [{}])[0].get("reason", "")
            except Exception:
                pass
            low = (reason + " " + msg).lower()
            if e.code == 403 and "quota" in low:
                raise YouTubeError("YouTube 配额用尽(今天免费额度跑完;明天再跑或在 Google Cloud 提额)") from None
            if "api key" in low or "keyinvalid" in low or ("badrequest" in low and "key" in low):
                raise YouTubeError(f"API key 有问题(检查 config_local.py 的 YOUTUBE_API_KEY):{msg}") from None
            raise YouTubeError(f"HTTP {e.code}: {msg}") from None
        except Exception as e:
            if attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise YouTubeError(f"网络/解析失败:{type(e).__name__}: {e}") from None


def _parse_iso8601_duration(s):
    """'PT1H2M3S' → 秒。短视频 / 直播也兼容。"""
    if not s:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    h, mn, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mn * 60 + sec


def _parse_published(s):
    """'2023-05-01T12:00:00Z' → (unix_ts, iso_str)。"""
    if not s:
        return 0, None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp()), dt.isoformat()
    except Exception:
        return 0, s


def _resolve_channel_id(channel, key):
    """把 @handle / UCxxxx / 名字 解析成 channelId。"""
    channel = (channel or "").strip()
    if channel.startswith("UC") and len(channel) >= 20:
        return channel
    if channel.startswith("@"):
        data = _get("channels", {"part": "id", "forHandle": channel}, key)
        items = data.get("items") or []
        if items:
            return items[0]["id"]
    # 兜底:按名字搜索频道,取第一个(花 100 配额)
    data = _get("search", {"part": "snippet", "type": "channel",
                           "q": channel.lstrip("@"), "maxResults": 1}, key)
    items = data.get("items") or []
    if items:
        idobj = items[0].get("id") or {}
        cid = idobj.get("channelId") or items[0].get("snippet", {}).get("channelId")
        if cid:
            return cid
    raise YouTubeError(f"找不到频道:{channel}(试试用 @handle 或 UC 开头的频道ID)")


def _uploads_playlist(channel_id, key):
    data = _get("channels", {"part": "contentDetails", "id": channel_id}, key)
    items = data.get("items") or []
    if not items:
        raise YouTubeError(f"频道 ID 无效:{channel_id}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _recent_video_ids(playlist_id, key, num):
    """上传播放列表按时间倒序;取最近 num 个 videoId。"""
    ids, token = [], None
    while len(ids) < num:
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = _get("playlistItems", params, key)
        for it in data.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        token = data.get("nextPageToken")
        if not token:
            break
    return ids[:num]


def _videos_meta(video_ids, key):
    """一次最多查 50 个 videoId 的 snippet+statistics+contentDetails。"""
    out = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        data = _get("videos", {"part": "snippet,statistics,contentDetails",
                               "id": ",".join(chunk)}, key)
        for it in data.get("items", []):
            out[it["id"]] = it
    return out


def _thumb(snippet):
    th = snippet.get("thumbnails", {})
    for size in ("maxres", "standard", "high", "medium", "default"):
        if size in th:
            return th[size]["url"]
    return None


def fetch_creator(c, api_key, num=40):
    """标准适配器接口:给一个 creators.py 条目 → 标准视频表 list[dict]。
    字段与 fetch_bilibili.py 完全一致(YouTube 没有的 danmaku 填 0、tid 填 None)。

    支持 creators.py 里的 per-creator 字段:
      min_duration_sec: 过滤掉短于该秒数的视频(默认 60,排除 YouTube Shorts)。
        Shorts/长视频在 YouTube 是两套算法+受众,混在一起 form 测试会失真。
        纯长视频频道默认 60 没有副作用;以 Shorts 为主的频道建议设到 180。
    """
    if not api_key:
        raise YouTubeError("没读到 YOUTUBE_API_KEY(在 config_local.py 里加一行 YOUTUBE_API_KEY = \"你的key\")")
    channel = c.get("channel") or c.get("uid") or c.get("name")
    min_dur = int(c.get("min_duration_sec", 60))
    cid = _resolve_channel_id(str(channel), api_key)
    uploads = _uploads_playlist(cid, api_key)
    # Shorts 比例高的频道一次拿不够 num 条长视频,多拉 8 倍兜底(quota 也只翻几倍,远低于日额)
    raw_num = num * 8 if min_dur > 0 else num
    vids = _recent_video_ids(uploads, api_key, raw_num)
    meta = _videos_meta(vids, api_key)

    videos = []
    for vid in vids:
        it = meta.get(vid)
        if not it:
            continue
        cont = it.get("contentDetails", {})
        dur = _parse_iso8601_duration(cont.get("duration", ""))
        if dur < min_dur:
            continue   # 过滤 Shorts:不进入下游 form / cover / signal 测试
        snip = it.get("snippet", {})
        stats = it.get("statistics", {})
        ts, iso = _parse_published(snip.get("publishedAt"))
        videos.append({
            "creator": c["name"], "alias": c["alias"], "zone": c["zone"],
            "platform": "youtube",
            "vid": vid, "bvid": vid, "aid": None,          # bvid=videoId:封面缓存/查找零改动复用
            "title": snip.get("title"), "description": snip.get("description", ""),
            "cover_url": _thumb(snip),
            "duration_sec": dur,
            "created_ts": ts,
            "created_iso": iso,
            "play": int(stats.get("viewCount", 0) or 0),
            "comment": int(stats.get("commentCount", 0) or 0),
            "like": int(stats.get("likeCount", 0) or 0),   # 附赠字段;B站表没有,下游忽略
            "danmaku": 0,                                  # YouTube 没有弹幕
            "tid": None,
        })
        if len(videos) >= num:
            break
    videos.sort(key=lambda x: x["play"] or 0, reverse=True)
    return videos
