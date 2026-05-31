"""
viralens 创作者配置(可提交,无密钥)。
任意平台 / 任意分区 / 任意创作者 —— 想对比谁,就在这里加一行。

⚠️ 想保留自己的私有清单又不进 git?把它放进同目录的 creators_local.py(已 gitignore),
   在里面定义同样的 CREATORS 列表,它会自动覆盖下面的示例(见文件末尾)。

每条字段:
  name      显示名
  platform  "bilibili"(默认,可省略)或 "youtube"
  alias     输出文件名 data/<alias>_videos.json(英文/拼音,别重复)
  zone      分区 / 赛道名,自己定。基准对比按 zone 分组,所以"同一个池子"的人用同一个 zone。
            ⚠️ 跨平台别混用 zone:B站和 YouTube 受众体量不同,给 YouTube 用各自的 zone 名
            (例:B站知识区写 "知识",YouTube 科普写 "STEM-YT"),否则基准就是在跨平台硬比。
  —— Bilibili 专用 ——
  uid       B站用户 UID(数字)。留 None 由 resolve_creators.py 按 name 搜索补全
  —— YouTube 专用 ——
  channel   "@handle"(推荐,稳定可核对) / "UCxxxx频道ID" / 频道名(兜底搜索)
  min_duration_sec  可选:过滤短视频(同时发 Shorts 的频道建议 180,排除 Shorts)
"""
# 下面是示例 —— 换成你想分析的创作者。
#   B站 UID:用 resolve_creators.py 按名字搜;YouTube @handle:在频道主页地址栏能看到。
CREATORS = [
    # —— Bilibili(uid 留 None 会自动按 name 搜索补全)——
    {"name": "示例UP主A", "platform": "bilibili", "uid": None, "alias": "demo_b1", "zone": "知识"},
    {"name": "示例UP主B", "platform": "bilibili", "uid": None, "alias": "demo_b2", "zone": "游戏"},

    # —— YouTube(同时发 Shorts 的频道,min_duration_sec=180 排除 Shorts)——
    {"name": "Example Channel", "platform": "youtube", "channel": "@example", "alias": "demo_y1",
     "zone": "Entertainment-YT", "min_duration_sec": 180},
]

# —— 你自己的私有清单 —— 放在 creators_local.py(已 gitignore,不进 git);存在就用它覆盖上面的示例。
try:
    from creators_local import CREATORS as _LOCAL_CREATORS
    if _LOCAL_CREATORS:
        CREATORS = _LOCAL_CREATORS
except Exception:
    pass
